import json
import tempfile
import unittest
from pathlib import Path
from vibe_learner.role_artifacts import (ChartQuestion, requirement, build_delivery,
    validate_delivery, digest)

SOURCE='Chart data: A=4, B=9, C=6.\nCHART_SOURCE_JSON:\n'+json.dumps(
    {'kind':'bar-chart-source-v1','labels':['A','B','C'],'values':[4,9,6]})
SOURCE+='\nCHART_QUESTION_REQUIREMENTS_JSON:\n'+json.dumps([{'operation':'maximum','labels':['A','B','C']},{'operation':'difference','labels':['C','A']}])
QUESTIONS=[ChartQuestion(operation='maximum',labels=['A','B','C']),
           ChartQuestion(operation='difference',labels=['C','A'])]

class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.req=requirement(SOURCE)
    def tearDown(self):self.tmp.cleanup()
    def build(self):return build_delivery(self.root,self.req,QUESTIONS)
    def test_valid_chart_and_public_page(self):
        self.build()
        self.assertTrue(validate_delivery(self.root,self.req)['valid'])
        page=(self.root/'learner.html').read_text()
        self.assertIn('src="chart.svg"',page)
        self.assertIn('C minus A',page)
        self.assertNotIn('facts',page)
    def test_missing_manifest_even_if_asset_exists(self):
        self.build();(self.root/'delivery.json').unlink()
        self.assertFalse(validate_delivery(self.root,self.req)['valid'])
    def test_missing_or_deleted_asset(self):
        for name in ['chart.svg','chart-data.json','learner.html']:
            self.build();(self.root/name).unlink()
            self.assertFalse(validate_delivery(self.root,self.req)['valid'])
    def test_forged_asset_and_matching_digest_cannot_change_source_values(self):
        self.build();chart=(self.root/'chart.svg').read_bytes().replace(b'>9<',b'>99<')
        (self.root/'chart.svg').write_bytes(chart)
        value=json.loads((self.root/'delivery.json').read_text());value['chart_sha256']=digest(chart)
        (self.root/'delivery.json').write_text(json.dumps(value))
        self.assertFalse(validate_delivery(self.root,self.req)['valid'])
    def test_digest_wrong(self):
        self.build();value=json.loads((self.root/'delivery.json').read_text());value['chart_sha256']='0'*64
        (self.root/'delivery.json').write_text(json.dumps(value))
        self.assertFalse(validate_delivery(self.root,self.req)['valid'])
    def test_asset_not_referenced_by_public_page(self):
        self.build();page=b'<html>Read the chart.</html>'; (self.root/'learner.html').write_bytes(page)
        value=json.loads((self.root/'delivery.json').read_text());value['page_sha256']=digest(page)
        (self.root/'delivery.json').write_text(json.dumps(value))
        self.assertFalse(validate_delivery(self.root,self.req)['valid'])
    def test_wrong_source_binding(self):
        self.build();req=requirement(SOURCE.replace('A=4','A=5'))
        self.assertFalse(validate_delivery(self.root,req)['valid'])
    def test_undeclared_label_and_missing_questions_rejected(self):
        for questions in [[],QUESTIONS[:1],list(reversed(QUESTIONS)),[QUESTIONS[0],QUESTIONS[0]],[ChartQuestion(operation='difference',labels=['Z','A'])],
                          [ChartQuestion(operation='maximum',labels=['A'])]]:
            with self.assertRaises(ValueError):build_delivery(self.root,self.req,questions)
    def test_proposed_application_reference_is_rejected(self):
        from vibe_learner.role_exploration import Draft
        with self.assertRaises(ValueError):
            Draft.model_validate({'facts':{},'activities':[5],'learner_prompt':'ok',
                'chart_sha256':'fake','chart_path':'chart.svg'})
    def test_wrong_or_empty_source_data_rejected(self):
        for values in [[],[0,0,0],[True,9,6],[4,9]]:
            with self.assertRaises(ValueError):
                requirement('s\nCHART_SOURCE_JSON:\n'+json.dumps(
                    {'kind':'bar-chart-source-v1','labels':['A','B','C'],'values':values})+'\nCHART_QUESTION_REQUIREMENTS_JSON:\n'+json.dumps([q.model_dump() for q in QUESTIONS]))

    def test_run_sample_delivers_chart_or_fails_missing_structured_questions(self):
        from types import SimpleNamespace
        from vibe_learner.role_exploration import run_sample
        for questions,expected in [(QUESTIONS,'completed'),([],'candidate_failed')]:
            with tempfile.TemporaryDirectory() as directory:
                draft={'facts':{'maximum_label':'B'},'activities':[5,6],
                    'learner_prompt':'Look at the chart.',
                    'chart_questions':[q.model_dump() for q in questions]}
                ctx=SimpleNamespace(storage=Path(directory),transport=SimpleNamespace(
                    campaign=SimpleNamespace(model='test',max_output_tokens=100,temperature=0),
                    request=lambda *a,**k: {'choices':[{'message':{'content':json.dumps(draft)}}]}))
                case=SimpleNamespace(id='media-chart',source=SOURCE,request='Read chart.',
                    gold=json.dumps({'facts':{'maximum_label':'B'},'minutes':11,'activity_count':2}))
                result=run_sample(ctx,case,SimpleNamespace(id='baseline'))
                self.assertEqual(result['status'],expected)
                self.assertEqual(result['metrics']['artifact_delivery_valid'],bool(questions))
                if questions:
                    from model_quality.protocol import AdapterResult
                    checked=AdapterResult.model_validate(result)
                    for ref in checked.evidence:
                        json.loads((Path(directory)/ref.path).read_text())
                    bundle=json.loads((Path(directory)/'artifact-bundle.json').read_text())
                    self.assertEqual({f['path'] for f in bundle['files']},{'learner.html','chart.svg','chart-data.json'})
                    for entry in bundle['files']:
                        self.assertEqual(entry['content'].encode(),(Path(directory)/entry['path']).read_bytes())
                        self.assertEqual(entry['sha256'],digest(entry['content'].encode()))

    def test_worker_fake_transport_commits_exportable_evidence(self):
        import os,time
        from unittest.mock import patch
        from model_quality.protocol import Campaign
        from model_quality.runner import Checkpoints,worker,source_state
        from model_quality.ledger import Ledger
        from model_quality.transport import MeteredTransport
        c=Campaign.model_validate(dict(version='quality-campaign-v1',id='role-bundle-test',
            purpose='Role artifact worker regression',transport='fake',
            adapter='vibe_learner.role_exploration:run_sample',
            budget=dict(token_limit=100000,wire_limit=10,rpm=20,tpm=100000,max_inflight=1,expires_at=time.time()+3600),
            cases=[dict(id='media-chart',family='media-chart',lane='roles',provenance='synthetic-authored',
                source=SOURCE,request='Read the source chart.',rubric='role-exact-v1',
                gold=json.dumps({'facts':{'maximum_label':'B'},'minutes':11,'activity_count':2}))],
            variants=[dict(id='baseline',instruction='One generation')]))
        ledger_path=self.root/'ledger.sqlite3';Ledger(ledger_path).initialize(c.budget,'fake')
        cp=Checkpoints(self.root/'checkpoints.sqlite3');cp.initialize(c.samples())
        sid,identity,case,variant=next(iter(c.samples()));cp.start(sid)
        (self.root/'media-chart'/'baseline'/'0'/'storage').mkdir(parents=True)
        draft={'facts':{'maximum_label':'B'},'activities':[5,6],'learner_prompt':'Read the chart.',
               'chart_questions':[q.model_dump() for q in QUESTIONS]}
        raw={'model':'MiniMax-M3','choices':[{'message':{'content':json.dumps(draft)},'finish_reason':'stop'}],
             'usage':{'prompt_tokens':10,'completion_tokens':10,'total_tokens':20}}
        original=MeteredTransport.request
        def fake_request(transport,payload,**kwargs):
            return original(transport,payload,**kwargs,fake_response=raw)
        cwd=Path.cwd()
        try:
            with patch.object(MeteredTransport,'request',fake_request),patch.dict(os.environ):
                worker(c.model_dump(),str(ledger_path),str(self.root),sid)
        finally:os.chdir(cwd)
        result=json.loads(cp.rows()[0]['result'])
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(Ledger(ledger_path).snapshot()['wire_count'],1)
        self.assertIn('artifact-bundle.json',[ref['path'] for ref in result['evidence']])
        state=source_state(c.adapter)
        self.assertTrue(state['adapter_source_manifest']['source_files'])
        self.assertTrue(any(path.endswith('role_artifacts.py') for path in state['adapter_source_manifest']['source_files']))
