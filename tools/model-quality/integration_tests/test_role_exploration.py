import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from vibe_learner.role_exploration import run_sample
from vibe_learner.common import envelope

class RoleTests(unittest.TestCase):
    def test_critic_cannot_turn_wrong_revision_into_success(self):
        with tempfile.TemporaryDirectory() as directory:
            replies=[{'facts':{'answer':'4'},'activities':[5],'learner_prompt':'Solve.'},
                     {'issues':[],'recommendation':'Approved'},
                     {'facts':{'answer':'5'},'activities':[5],'learner_prompt':'Solve.'}]
            kinds=[]
            def request(payload,call_kind):
                kinds.append(call_kind)
                return envelope(json.dumps(replies.pop(0)))
            ctx=SimpleNamespace(storage=Path(directory),transport=SimpleNamespace(campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=4096,temperature=.1),request=request))
            case=SimpleNamespace(id='x',source='2+2=4',request='Solve.',gold=json.dumps({'facts':{'answer':'4'},'minutes':5,'activity_count':1}))
            result=run_sample(ctx,case,SimpleNamespace(id='review-revise'))
            self.assertEqual(result['status'],'candidate_failed')
            self.assertEqual(kinds,['generation','critic','repair'])
            self.assertFalse(result['metrics']['facts_exact'])
            self.assertNotEqual(result.get('scope'),'domain-primary-output-readback')

    def test_invalid_generation_is_not_repaired_or_graded_successfully(self):
        with tempfile.TemporaryDirectory() as directory:
            calls=[]
            def request(payload,call_kind):
                calls.append(call_kind)
                return envelope('{"facts":{},"facts":{},"activities":[5],"learner_prompt":"ok"}')
            ctx=SimpleNamespace(storage=Path(directory),transport=SimpleNamespace(campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=4096,temperature=.1),request=request))
            result=run_sample(ctx,SimpleNamespace(id='x',source='s',request='r',gold=json.dumps({'facts':{},'minutes':5,'activity_count':1})),SimpleNamespace(id='review-revise'))
            self.assertEqual(result['status'],'candidate_failed')
            self.assertEqual(calls,['generation'])

class FenceTests(unittest.TestCase):
    def test_only_whole_fence_is_unwrapped_and_fields_remain_strict(self):
        from vibe_learner.role_exploration import Draft,parse
        payload=json.dumps({'facts':{'answer':'4'},'activities':[5],'learner_prompt':'Solve.'})
        self.assertEqual(parse(envelope('```json\n'+payload+'\n```'),Draft).facts,{'answer':'4'})
        for value in ['preface\n```json\n'+payload+'\n```','```json\n'+payload+'\n```\npostscript',payload.replace('[5]','["5"]')]:
            with self.assertRaises(ValueError):parse(envelope(value),Draft)
