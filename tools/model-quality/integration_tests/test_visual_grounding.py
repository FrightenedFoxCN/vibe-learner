import base64,json,tempfile,time,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image,ImageDraw
from model_quality.protocol import AdapterResult,Case,Variant
from vibe_learner.visual_grounding import Direct,Selection,decode,grade,run_sample,source_manifest,provider_proposal_table
from vibe_learner.visual_grounding_detector import propose,mark
from vibe_learner.visual_grounding_fixtures import build_fixtures

class VisualGroundingTests(unittest.TestCase):
    def test_strict_decode_abstain_and_mapping_contract(self):
        for raw,cls in [('{"status":"found","box":[0,0,.5,.5]}',Direct),('{"status":"found","box":[0,0,0.5,1.2]}',Direct),('{"status":"found","box":[false,0,0.5,0.5]}',Direct),('{"status":"absent","proposal_id":1}',Selection),('{"status":"found","proposal_id":true}',Selection),('{"status":"absent","box":null,"status":"found"}',Direct)]:
            with self.assertRaises(ValueError):decode(raw,cls)
        self.assertEqual(decode('{"status":"found","box":[0,0,0.5,0.5]}',Direct).box,[0,0,.5,.5])
    def test_only_complete_fence_is_accepted(self):
        text='{"status":"absent","box":null}'
        self.assertEqual(decode('```json\n'+text+'\n```',Direct).status,'absent')
        for value in ['before\n```json\n'+text+'\n```','```json\n'+text+'\n```\nafter']:
            with self.assertRaises(ValueError):decode(value,Direct)
    def test_visible_missing_candidate_is_not_absent(self):
        prediction=decode('{"status":"unlocalized","proposal_id":null}',Selection)
        self.assertEqual(prediction.status,'unlocalized')
        g=dict(expected='found',target_px=[10,20,50,60],minimum_iou=.5,minimum_coverage=.8)
        m=grade(prediction.status,None,g,[])
        self.assertFalse(m['task_pass']);self.assertFalse(m['proposal_recall_at_threshold'])
    def test_proposal_table_keeps_every_candidate_but_no_masks_or_gold(self):
        ps=[dict(id=1,kind='dino',text='cup',box_px=[1,2,3,4],confidence=.8,mask_png_base64='payload'),dict(id=2,kind='dino',text='spoon',box_px=[4,5,6,7],confidence=.6)]
        table=provider_proposal_table(ps)
        self.assertEqual([p['id'] for p in table],[1,2]);self.assertNotIn('payload',str(table))
    def test_real_detector_has_no_fixture_input_and_all_assets_bounded(self):
        with tempfile.TemporaryDirectory() as d:
            cases=build_fixtures(d);self.assertEqual(len(cases),12)
            for c in cases:
                png=Path(json.loads(c['source'])['path']).read_bytes();ps,meta=propose(png)
                self.assertLessEqual(len(png),32768);self.assertLessEqual(len(mark(png,ps)),32768)
                self.assertEqual(len({p['id'] for p in ps}),len(ps));self.assertIn('tesseract',meta['method'])
                # Outcome is measured rather than asserted successful for all fixtures.
                result=grade('absent',None,json.loads(c['gold']),ps);self.assertIn('proposal_recall_at_threshold',result)
    def test_gold_changes_scores_not_request_or_proposals(self):
        with tempfile.TemporaryDirectory() as d:
            row=build_fixtures(Path(d)/'fixtures')[0];case=Case.model_validate(row)
            requests=[]
            class Transport:
                campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=2048,temperature=.1,transport='fake',thinking='adaptive')
                def request(self,payload,**kw):
                    requests.append(payload);return {'choices':[{'message':{'content':'{"status":"absent","proposal_id":null}'},'finish_reason':'stop'}]}
            for i,expected in enumerate(['found','absent']):
                store=Path(d)/str(i);store.mkdir();gold=json.loads(row['gold']);gold['expected']=expected
                altered=case.model_copy(update={'gold':json.dumps(gold)})
                result=run_sample(SimpleNamespace(storage=store,transport=Transport()),altered,Variant(id='som',instruction='select'))
                AdapterResult.model_validate(result)
            self.assertEqual(requests[0],requests[1]);self.assertNotIn('target_px',json.dumps(requests[0]))
    def test_exact_selection_mapping_and_abstention_score(self):
        g=dict(expected='found',target_px=[10,20,50,60],minimum_iou=.5,minimum_coverage=.8)
        self.assertTrue(grade('found',[10,20,50,60],g,[dict(box_px=[10,20,50,60])])['task_pass'])
        self.assertFalse(grade('absent',None,g,[])['task_pass'])
        g.update(expected='ambiguous',target_px=None)
        self.assertTrue(grade('ambiguous',None,g,[])['task_pass'])
    def test_source_manifest_resolves_dependencies(self):
        self.assertIn('opencv-python-headless',source_manifest()['dependencies'])
if __name__=='__main__':unittest.main()
