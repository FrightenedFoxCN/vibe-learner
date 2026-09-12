import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch

from app.models.harness import HarnessStage,HarnessWorkflow
from app.services.provider_transport import ProviderTransport
from app.services.tool_provider_projection import ProviderToolCallDecodeError,decode_provider_tool_call
from model_quality.adapters import Context
from model_quality.ledger import GateClosed,Ledger
from model_quality.transport import MeteredTransport,WireFailure
from vibe_learner.common import Bridge,envelope
from vibe_learner.fixtures import campaign

class BridgeParityTests(unittest.TestCase):
    def call(self,index=0):
        return {'id':'sample-call','type':'function','index':index,'function':{'name':'get_study_unit_detail','arguments':'{"study_unit_id":"unit-1"}'}}

    def test_metered_native_index_has_production_decode_parity(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);c=campaign('study');ledger=Ledger(root/'ledger.sqlite3');ledger.initialize(c.budget,'fake')
            ctx=Context(MeteredTransport(c,ledger,'projection',time.monotonic()+300),root,root/'domain.sqlite3')
            raw=envelope(tools=[self.call()]);before=copy.deepcopy(raw)
            bridge=Bridge(ctx,lambda _:raw)
            got,_=bridge.request(None,{'model':c.model,'messages':[{'role':'user','content':'synthetic'}],'max_tokens':c.max_output_tokens},request_kind='chat',model=c.model)
            expected,_=ProviderTransport(timeout_seconds=3).execute(request_kind='plan',model=c.model,invoke=lambda:raw)
            self.assertEqual(got,expected);self.assertEqual(raw,before)
            self.assertEqual(bridge.normalized_tool_indexes,1)
            call=decode_provider_tool_call(got['choices'][0]['message']['tool_calls'][0],workflow=HarnessWorkflow.PLANNING,offered_in_stage=HarnessStage.PLAN_GENERATION)
            self.assertEqual(call.transport_correlation_id,'sample-call')
            snap=ledger.snapshot();self.assertEqual(snap['wire_count'],1)
            shape=snap['wires'][0]['metadata']['tool_call_shapes'][0]
            self.assertTrue(shape['index_is_nonnegative_integer']);self.assertIn('index',shape['known_fields'])

    def test_malformed_or_unknown_fields_stay_visible_to_strict_decoder(self):
        variants=[self.call(x) for x in (True,'0',-1,2147483648,None)]
        variants.extend([{**self.call(),'extra':'not-authorized'}, {**self.call(),'id':''},
                         {**self.call(),'function':{'name':'get_study_unit_detail'}}])
        for value in variants:
            with self.subTest(value=value):
                raw=envelope(tools=[value]);ctx=SimpleNamespace(transport=SimpleNamespace(campaign=SimpleNamespace(transport='minimax'),request=Mock(return_value=raw)))
                bridge=Bridge(ctx,None);got,_=bridge.request(None,{},request_kind='chat',model='MiniMax-M3')
                self.assertEqual(got,raw);self.assertEqual(bridge.normalized_tool_indexes,0)
                with self.assertRaises(ProviderToolCallDecodeError):
                    decode_provider_tool_call(got['choices'][0]['message']['tool_calls'][0],workflow=HarnessWorkflow.PLANNING,offered_in_stage=HarnessStage.PLAN_GENERATION)
        for raw in ({'choices':None},{'choices':[None,{'message':None}]},{'choices':[{'message':{'tool_calls':None}}]}):
            ctx=SimpleNamespace(transport=SimpleNamespace(campaign=SimpleNamespace(transport='minimax'),request=Mock(return_value=raw)))
            self.assertEqual(Bridge(ctx,None).request(None,{},request_kind='chat',model='MiniMax-M3')[0],raw)

    def test_failures_are_not_retried_or_wrapped(self):
        for error in (WireFailure('http_529',uncertain=True),GateClosed('budget_exhausted')):
            request=Mock(side_effect=error);ctx=SimpleNamespace(transport=SimpleNamespace(campaign=SimpleNamespace(transport='minimax'),request=request))
            bridge=Bridge(ctx,None)
            with self.assertRaises(type(error)) as raised:bridge.request(None,{},request_kind='chat',model='MiniMax-M3')
            self.assertIs(raised.exception,error);self.assertIs(bridge.failure,error);request.assert_called_once()

    def test_native_indexes_pass_through_actual_study_commit_and_restart(self):
        from vibe_learner import study
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);storage=root/'storage';storage.mkdir();c=campaign('study');ledger=Ledger(root/'ledger.sqlite3');ledger.initialize(c.budget,'fake')
            context=Context(MeteredTransport(c,ledger,'study-index',time.monotonic()+300),storage,root/'domain.sqlite3')
            initialize=Bridge.__init__
            def with_native_indexes(bridge,context,fake):
                def native(payload):
                    raw=fake(payload)
                    for choice in raw.get('choices',[]):
                        for call in choice.get('message',{}).get('tool_calls',[]):call['index']=0
                    return raw
                initialize(bridge,context,native)
            with patch.object(Bridge,'__init__',with_native_indexes):result=study.run_sample(context,c.cases[0],c.variants[0])
            self.assertEqual(result['status'],'completed',result)
            self.assertTrue(result['metrics']['restart_equal'])
            self.assertTrue(result['metrics']['memory_effect_exact'])
            self.assertTrue(any(s.get('index_is_nonnegative_integer') for w in ledger.snapshot()['wires'] for s in w['metadata']['tool_call_shapes']))
