import json,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from vibe_learner.role_exploration import run_sample
from vibe_learner.common import envelope

class RoleTests(unittest.TestCase):
    def test_single_pass_prompt_variants_make_exactly_one_generation_call(self):
        for variant,marker in [('constraint-checklist','silently turn every explicit task constraint'),
                               ('evidence-ledger','silently build an evidence ledger')]:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as directory:
                calls=[]
                def request(payload,call_kind):
                    calls.append((call_kind,payload['messages'][0]['content']))
                    return envelope(json.dumps({'facts':{'answer':'4'},'activities':[5],
                                                'learner_prompt':'Solve the practice item.'}))
                ctx=SimpleNamespace(storage=Path(directory),transport=SimpleNamespace(
                    campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=4096,temperature=.1),request=request))
                case=SimpleNamespace(id='new-case',source='2+2=4',request='Create one activity.',
                    gold=json.dumps({'facts':{'answer':'4'},'minutes':5,'activity_count':1}),rubric='role-exact-v1')
                result=run_sample(ctx,case,SimpleNamespace(id=variant))
                self.assertEqual(result['status'],'completed')
                self.assertEqual(len(calls),1)
                self.assertEqual(calls[0][0],'generation')
                self.assertIn(marker,calls[0][1])

    def test_unknown_variant_fails_before_wire(self):
        with tempfile.TemporaryDirectory() as directory:
            ctx=SimpleNamespace(storage=Path(directory),transport=SimpleNamespace(
                campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=4096,temperature=.1),
                request=lambda *a,**k: self.fail('must not call provider')))
            result=run_sample(ctx,SimpleNamespace(id='x',source='s',request='r',gold='{}',rubric='role-exact-v1'),
                              SimpleNamespace(id='not-registered'))
            self.assertEqual(result['status'],'data_failed')
            self.assertEqual(result['error_code'],'unknown_role_variant')

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
            case=SimpleNamespace(id='x',source='2+2=4',request='Solve.',gold=json.dumps({'facts':{'answer':'4'},'minutes':5,'activity_count':1}),rubric='role-exact-v1')
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
            result=run_sample(ctx,SimpleNamespace(id='x',source='s',request='r',gold=json.dumps({'facts':{'answer':'4'},'minutes':5,'activity_count':1}),rubric='role-exact-v1'),SimpleNamespace(id='review-revise'))
            self.assertEqual(result['status'],'candidate_failed')
            self.assertEqual(calls,['generation'])

    def test_rubric_and_gold_fail_closed_before_wire(self):
        with tempfile.TemporaryDirectory() as directory:
            calls=[]
            ctx=SimpleNamespace(storage=Path(directory),transport=SimpleNamespace(
                campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=4096,temperature=.1),
                request=lambda *a,**k: calls.append((a,k))))
            base=dict(id='x',source='s',request='r')
            unknown=run_sample(ctx,SimpleNamespace(**base,rubric='role-semantic-v9',gold='{}'),SimpleNamespace(id='baseline'))
            malformed=run_sample(ctx,SimpleNamespace(**base,rubric='role-exact-v1',gold=json.dumps(
                {'facts':{'x':'1'},'minutes':5,'activity_count':1,'forbidden':'answer'})),SimpleNamespace(id='baseline'))
            self.assertEqual(unknown['error_code'],'unknown_role_rubric')
            self.assertEqual(malformed['error_code'],'invalid_role_gold')
            self.assertEqual(calls,[])

    def test_prompt_presence_does_not_claim_semantic_grade(self):
        with tempfile.TemporaryDirectory() as directory:
            def request(payload,call_kind):
                return envelope(json.dumps({'facts':{'answer':'4'},'activities':[5],
                                            'learner_prompt':'A fluent but unreviewed prompt.'}))
            ctx=SimpleNamespace(storage=Path(directory),transport=SimpleNamespace(
                campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=4096,temperature=.1),request=request))
            case=SimpleNamespace(id='x',source='2+2=4',request='Solve.',rubric='role-exact-v1',
                gold=json.dumps({'facts':{'answer':'4'},'minutes':5,'activity_count':1}))
            result=run_sample(ctx,case,SimpleNamespace(id='baseline'))
            evidence=json.loads((Path(directory)/'role-evidence.json').read_text())
            self.assertEqual(result['status'],'completed')
            self.assertTrue(result['metrics']['prompt_present'])
            self.assertFalse(evidence['learner_prompt_semantics_graded'])
            self.assertTrue(evidence['manual_semantic_review_required'])

class FenceTests(unittest.TestCase):
    def test_only_whole_fence_is_unwrapped_and_fields_remain_strict(self):
        from vibe_learner.role_exploration import Draft,parse
        payload=json.dumps({'facts':{'answer':'4'},'activities':[5],'learner_prompt':'Solve.'})
        self.assertEqual(parse(envelope('```json\n'+payload+'\n```'),Draft).facts,{'answer':'4'})
        for value in ['preface\n```json\n'+payload+'\n```','```json\n'+payload+'\n```\npostscript',payload.replace('[5]','["5"]')]:
            with self.assertRaises(ValueError):parse(envelope(value),Draft)

class PreparationTests(unittest.TestCase):
    def test_v2_preparation_adds_eight_new_families_and_single_pass_variants(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);budget=root/'budget.json';output=root/'campaign.json'
            budget.write_text(json.dumps({'budget':{'token_limit':10000000,'wire_limit':100,
                'rpm':100,'tpm':1000000,'max_inflight':4,'expires_at':time.time()+3600}}))
            script=Path(__file__).parents[1]/'examples'/'prepare_role_exploration.py'
            subprocess.run([sys.executable,str(script),'--budget-from',str(budget),'--output',str(output)],
                           check=True,cwd=script.parents[1])
            data=json.loads(output.read_text())
            old={'plan-pages','plan-scope','media-chart','media-question'}
            new=data['cases']
            self.assertGreaterEqual(len(new),8)
            self.assertEqual(len({case['family'] for case in new}),len(new))
            self.assertTrue(old.isdisjoint({case['family'] for case in new}))
            self.assertEqual({'constraint-checklist','evidence-ledger'},
                {v['id'] for v in data['variants']} & {'constraint-checklist','evidence-ledger'})
            self.assertEqual(data['sample_wire_limit'],3)
            self.assertEqual({'condition-window','appendix-page-map','unknown-denominator',
                'third-party-speakers','cancellation-access','policy-effective-time',
                'observational-claim','source-priority'},{case['id'] for case in new})
            gold={case['id']:json.loads(case['gold']) for case in new}
            self.assertEqual(gold['appendix-page-map']['facts']['formula_physical_page'],'4')
            self.assertEqual(gold['appendix-page-map']['facts']['formula_printed_page'],'42')
            self.assertEqual(gold['unknown-denominator']['facts']['response_rate'],'unknown')
            self.assertEqual(gold['third-party-speakers']['facts']['statement_speaker'],'Priya')
            self.assertEqual(gold['cancellation-access']['facts']['effective_date'],'2026-04-30')
            self.assertEqual(gold['policy-effective-time']['facts']['applicable_limit_minutes'],'20')
            self.assertFalse(gold['observational-claim']['forbidden'])
            policy_case=next(case for case in new if case['id']=='policy-effective-time')
            self.assertIn('YYYY-MM-DD HH:MM',policy_case['request'])
            from model_quality.protocol import Campaign
            Campaign.model_validate(data)

    def test_single_phase_excludes_expensive_comparators(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);budget=root/'budget.json';output=root/'campaign.json'
            budget.write_text(json.dumps({'budget':{'token_limit':10000000,'wire_limit':100,
                'rpm':100,'tpm':1000000,'max_inflight':4,'expires_at':time.time()+3600}}))
            script=Path(__file__).parents[1]/'examples'/'prepare_role_exploration.py'
            subprocess.run([sys.executable,str(script),'--budget-from',str(budget),'--output',str(output),
                            '--phase','single'],check=True,cwd=script.parents[1])
            data=json.loads(output.read_text())
            self.assertEqual(data['id'],'m3-role-exploration-20260913-v2-single')
            self.assertEqual(['baseline','constraint-checklist','evidence-ledger'],
                             [variant['id'] for variant in data['variants']])
