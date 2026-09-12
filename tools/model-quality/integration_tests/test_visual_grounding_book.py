import hashlib,io,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image,ImageDraw
from model_quality.protocol import Case,Variant,AdapterResult
from vibe_learner.visual_grounding import run_sample
from vibe_learner.visual_grounding_book_detector import propose_book

class BookGroundingTests(unittest.TestCase):
    def test_closed_boundary_proposal_comes_from_pixels(self):
        im=Image.new('RGB',(240,200),'white');ImageDraw.Draw(im).rectangle((40,40,180,140),outline='black',width=2);b=io.BytesIO();im.save(b,format='PNG')
        ps,meta=propose_book(b.getvalue())
        self.assertTrue(any(p['kind']=='closed_rectangle' and p['box_px'][0]<=42 and p['box_px'][2]>=178 for p in ps))
        blank=io.BytesIO();Image.new('RGB',(240,200),'white').save(blank,format='PNG')
        self.assertEqual(propose_book(blank.getvalue())[0],[])
    def test_every_arm_gets_same_ocr_without_gold_or_pdf_text(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'source.png';Image.new('RGB',(100,100),'white').save(p);source={'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'detector':'book','query':'a rectangle.','include_proposal_table':True}
            case=Case(id='private-page',family='page',lane='book',provenance='user-provided',source=json.dumps(source),request='Find a rectangle.',gold=json.dumps({'expected':'found','target_px':[20,20,60,60],'width':100,'height':100,'minimum_iou':.5,'minimum_coverage':.8}),rubric='visual-grounding-v1')
            captures=[]
            class Transport:
                campaign=SimpleNamespace(model='MiniMax-M3',max_output_tokens=100,temperature=.1,transport='fake',thinking='adaptive',max_inline_image_bytes=524288)
                def request(self,payload,**kwargs):
                    captures.append(payload);return kwargs['fake_response']
            ps=[{'id':1,'kind':'closed_rectangle','text':'OCR text','box_px':[20,20,60,60]}]
            for v in ['direct','layout','dino']:
                store=Path(temp)/v;store.mkdir()
                with patch('vibe_learner.visual_grounding_book.propose_book',return_value=(ps,{'full_ocr_lines':['Uncorrected OCR','1.2'], 'method':'test'})),patch('vibe_learner.visual_grounding_book.grounded_proposals',return_value=(ps,{})):
                    result=run_sample(SimpleNamespace(storage=store,transport=Transport()),case,Variant(id=v,instruction=v));AdapterResult.model_validate(result)
            texts=[x['messages'][1]['content'][0]['text'].split('\nComplete detector proposal table')[0] for x in captures]
            self.assertEqual(texts[0],texts[1]);self.assertEqual(texts[1],texts[2]);self.assertNotIn('target_px',json.dumps(captures))
            self.assertTrue(all('1: Uncorrected OCR\n2: 1.2' in t for t in texts))
if __name__=='__main__':unittest.main()
