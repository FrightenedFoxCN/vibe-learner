import hashlib,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from model_quality.protocol import AdapterResult,Case,Variant
from vibe_learner.visual_grounding_reflection import run_sample


class ReflectionTests(unittest.TestCase):
    def test_reflection_gets_base_prediction_but_not_gold(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);page=root/'page.png';Image.new('RGB',(100,100),'white').save(page)
            source={'path':str(page),'sha256':hashlib.sha256(page.read_bytes()).hexdigest(),
                    'base_prediction':{'status':'found','box':[.1,.1,.3,.3]},'base_evidence_sha256':'a'*64}
            case=Case(id='reflect',family='page',lane='book',provenance='user-provided',source=json.dumps(source),
                request='Locate the lower diagram.',gold=json.dumps({'expected':'found','target_px':[60,60,90,90],
                'width':100,'height':100,'minimum_iou':.5,'minimum_coverage':.8}),rubric='visual-grounding-v1')
            seen=[]
            class Transport:
                campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=100,temperature=.1,transport='fake',thinking='adaptive')
                def request(self,payload,**kwargs):seen.append(payload);return {'choices':[{'message':{'content':'{"status":"found","box":[0.6,0.6,0.9,0.9]}'},'finish_reason':'stop'}],'usage':{'total_tokens':1}}
            storage=root/'storage';storage.mkdir()
            result=run_sample(SimpleNamespace(storage=storage,transport=Transport()),case,Variant(id='reflect-direct',instruction='reflect'))
            self.assertTrue(AdapterResult.model_validate(result).metrics['task_improved'])
            wire=json.dumps(seen,ensure_ascii=False)
            self.assertIn('Earlier direct result',wire);self.assertNotIn('target_px',wire);self.assertEqual(len(seen),1)

if __name__=='__main__':unittest.main()
