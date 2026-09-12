import unittest
from types import SimpleNamespace
from unittest.mock import patch
from model_quality.protocol import Variant
from vibe_learner.prepare_quality import matrix
from vibe_learner import study_policy


class PolicyTests(unittest.TestCase):
    def test_only_selected_wire_factor_changes_and_config_restores(self):
        for arm in ('baseline','adaptive','force-write-first'):
            c=matrix()
            seen=[]
            transport=SimpleNamespace(campaign=c)
            def request(payload, **kwargs):
                seen.append((payload,transport.campaign.thinking))
            transport.request=request
            context=SimpleNamespace(transport=transport)
            def sample(context,case,variant):
                context.transport.request({'tool_choice':'auto'})
                context.transport.request({'tool_choice':'auto'})
                return {'status':'completed'}
            with patch.object(study_policy.study,'run_sample',sample):
                study_policy.run_sample(context,c.cases[0],Variant(id=arm,instruction='same request'))
            self.assertIs(transport.campaign,c)
            self.assertIs(transport.request,request)
            self.assertEqual(seen[1][0]['tool_choice'],'auto')
            self.assertEqual(seen[0][0]['tool_choice'],{'type':'function','function':{'name':'write_session_memory'}} if arm=='force-write-first' else 'auto')
            self.assertTrue(all(thinking==('adaptive' if arm=='adaptive' else 'disabled') for _,thinking in seen))


class EnvelopeTests(unittest.TestCase):
    def test_only_reviewed_index_metadata_removed_without_mutating_original(self):
        from vibe_learner.study_wire_shape import normalize_index
        call={'id':'call-a','type':'function','function':{'name':'write_session_memory','arguments':'{}'},'index':0}
        raw={'choices':[{'message':{'tool_calls':[call]}}]}
        result=normalize_index(raw)
        self.assertIn('index',call)
        self.assertNotIn('index',result['choices'][0]['message']['tool_calls'][0])
        for invalid in ({**call,'extra':1},{**call,'index':True},{**call,'index':-1}):
            envelope={'choices':[{'message':{'tool_calls':[invalid]}}]}
            self.assertEqual(normalize_index(envelope),envelope)
