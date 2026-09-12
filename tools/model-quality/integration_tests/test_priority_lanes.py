import json
from pathlib import Path
import tempfile
import unittest
from model_quality.runner import run
from vibe_learner.prepare_lanes import campaign
from vibe_learner.study_fixture import grade_json_answer
from vibe_learner.citation import normalized_tokens


class PriorityLaneTests(unittest.TestCase):
    def test_gold_grader_rejects_extra_fields_and_narrative(self):
        gold={'state':'cancelled'}
        self.assertEqual(grade_json_answer('```json\n{"state":"cancelled"}\n```',gold)[:2],(True,True))
        self.assertEqual(grade_json_answer('{"state":"active"}',gold)[:2],(True,False))
        self.assertEqual(grade_json_answer('{"state":"cancelled","extra":"x"}',gold)[:2],(False,False))
        self.assertEqual(grade_json_answer('It was cancelled.',gold)[:2],(False,False))
        self.assertNotIn('the',normalized_tokens('the valve'))
        self.assertIn('警报',normalized_tokens('警报状态'))

    def test_citation_multilingual_actual_document_and_receipts(self):
        c=campaign('citation');c=c.model_copy(update={'cases':[c.cases[i] for i in (0,4,8,16)]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=run(c,root/'run',root/'ledger.sqlite3')
            self.assertEqual(sum(report['states'].values()),8)
            for sample in report['samples']:
                self.assertTrue(sample['result']['metrics'].get('committed'),sample)
                self.assertTrue(sample['result']['metrics'].get('answer_exact'),sample)
                self.assertTrue(sample['result']['metrics'].get('restart_equal'),sample)
            evidence=[json.loads(p.read_text()) for p in (root/'run').glob('*/*/*/storage/domain-evidence.json')]
            self.assertEqual(len({e['operations'][0]['harness_operation_id'] for e in evidence}),8)

    def test_temporal_seeds_isolation_metering_and_oracle_coverage(self):
        c=campaign('temporal');c=c.model_copy(update={'cases':[c.cases[i] for i in (0,7)]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=run(c,root/'run',root/'ledger.sqlite3')
            self.assertEqual(report['campaign_usage']['wire_count'],12)
            kinds=[w['metadata']['call_kind'] for w in report['campaign_usage']['wires']]
            self.assertEqual(kinds.count('seed'),8)
            for sample in report['samples']:
                metrics=sample['result']['metrics']
                for key in ('seed_committed','committed','restart_equal','isolated_memory_sources','answer_exact'):
                    self.assertTrue(metrics.get(key),sample)
                if sample['variant']=='oracle-context':self.assertTrue(metrics['evidence_anchor_coverage'])

    def test_binding_only_changes_authorized_content_and_mixed_cases_are_distinct(self):
        from vibe_learner.write_binding import bind_source
        call={'id':'x','type':'function','function':{'name':'write_session_memory','arguments':'{"key":"experiment_reference","content":"changed"}'}}
        raw={'choices':[{'message':{'tool_calls':[call]}}]}
        result=bind_source(raw,'literal\nsource')
        self.assertEqual(json.loads(result['choices'][0]['message']['tool_calls'][0]['function']['arguments'])['content'],'literal\nsource')
        self.assertIn('changed',call['function']['arguments'])
        for arguments in ('{"key":"other","content":"x"}','{"key":"experiment_reference","content":"x","content":"y"}','{"key":"experiment_reference","content":"x","extra":1}'):
            call['function']['arguments']=arguments
            self.assertEqual(bind_source(raw,'literal'),raw)
        c=campaign('mixed')
        self.assertEqual(len(c.cases),78)
        self.assertEqual(len(list(c.samples())),156)
        self.assertEqual(len({case.id for case in c.cases}),78)

    def test_mixed_scheduler_exercises_all_three_actual_domain_paths(self):
        c=campaign('mixed')
        selected=[]
        for lane in ('citation','temporal','verbatim'):
            selected.append(next(case for case in c.cases if case.lane==lane))
        c=c.model_copy(update={'cases':selected})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=run(c,root/'run',root/'ledger.sqlite3')
            self.assertEqual(report['states'],{'completed':6},report['samples'])
            self.assertEqual(report['campaign_usage']['wire_count'],14)

    def test_summary_fact_grader_and_domain_effects(self):
        from vibe_learner.prepare_summary import campaign as summary_campaign
        self.assertEqual(grade_json_answer('{"state":"active","state":"cancelled"}',{'state':'cancelled'})[:2],(False,False))
        c=summary_campaign();c=c.model_copy(update={'cases':[c.cases[0],c.cases[4]]})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);r=run(c,root/'run',root/'ledger.sqlite3')
            self.assertEqual(r['states'],{'completed':4},r['samples'])
            for sample in r['samples']:
                self.assertTrue(sample['result']['metrics']['summary_effect_facts_exact'])
                self.assertNotIn('memory_exact',sample['result']['metrics'])

    def test_uncommitted_citation_is_not_successful_abstention(self):
        import time
        from unittest.mock import patch
        from model_quality.adapters import Context
        from model_quality.ledger import Ledger
        from model_quality.transport import MeteredTransport
        from vibe_learner import citation
        from vibe_learner.common import envelope
        c=campaign('citation')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'storage').mkdir();ledger=Ledger(root/'ledger.sqlite3');ledger.initialize(c.budget,'fake')
            context=Context(MeteredTransport(c,ledger,'uncommitted-citation',time.monotonic()+300),root/'storage',root/'domain.sqlite3')
            with patch.object(citation,'envelope',return_value=envelope('{"unexpected":"payload"}')):
                result=citation.run_sample(context,c.cases[4],c.variants[0])
            self.assertEqual(result['status'],'uncertain')
            self.assertFalse(result['metrics']['citation_precision'])
            self.assertFalse(result['metrics']['citation_recall_or_correct_abstention'])

    def test_seed_failure_retains_receipt_and_does_not_dispatch_query(self):
        import time
        from unittest.mock import patch
        from model_quality.adapters import Context
        from model_quality.ledger import Ledger
        from model_quality.transport import MeteredTransport
        from vibe_learner import temporal
        from vibe_learner.common import envelope
        c=campaign('temporal')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'storage').mkdir();ledger=Ledger(root/'ledger.sqlite3');ledger.initialize(c.budget,'fake')
            context=Context(MeteredTransport(c,ledger,'failed-seed',time.monotonic()+300),root/'storage',root/'domain.sqlite3')
            with patch.object(temporal,'envelope',return_value=envelope('{"unexpected":"payload"}')):
                result=temporal.run_sample(context,c.cases[0],c.variants[0])
            self.assertEqual(result['status'],'uncertain')
            self.assertFalse(result['metrics']['seed_committed'])
            e=json.loads((root/'storage/domain-evidence.json').read_text())
            self.assertEqual(len(e['operations']),1)
            self.assertEqual(e['operations'][0]['receipt']['status'],'uncertain')
            self.assertTrue(e['operations'][0]['harness_operation_id'])
            self.assertTrue(all(w['metadata']['call_kind']=='seed' for w in ledger.snapshot()['wires']))
