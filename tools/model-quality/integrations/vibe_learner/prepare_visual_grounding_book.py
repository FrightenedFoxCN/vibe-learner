"""Freeze private local book-page experiments. Not public licensed/exportable."""
import argparse,hashlib,json,shutil
from pathlib import Path
from PIL import Image
from model_quality.protocol import Campaign

def main():
    p=argparse.ArgumentParser();p.add_argument('--review',type=Path,action='append',required=True);p.add_argument('--tasks',required=True);p.add_argument('--budget-from',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--id',required=True);p.add_argument('--transport',choices=['fake','minimax'],default='fake');a=p.parse_args()
    if a.output.exists() or a.fixtures.exists():raise ValueError('fresh_private_output_required')
    wanted=set(a.tasks.split(','));cases=[];a.fixtures.mkdir(parents=True)
    for review_path in a.review:
        review=json.loads(review_path.read_text());pdf=Path(review['pdf_path'])
        if hashlib.sha256(pdf.read_bytes()).hexdigest()!=review['pdf_sha256']:raise ValueError('private_pdf_changed')
        for page in review['candidates']:
            selected=[t for t in page['tasks'] if t['id'] in wanted]
            if not selected:continue
            image=Path(page['path']);png=image.read_bytes()
            if hashlib.sha256(png).hexdigest()!=page['png_sha256']:raise ValueError('reviewed_page_changed')
            width,height=Image.open(image).size
            if [width,height]!=page['image_size'] or max(width,height)>2048 or len(png)>524288:raise ValueError('page_limits')
            name=review['pdf_sha256'][:10]+'-p'+str(page['physical_page'])+'.png';dest=a.fixtures/name;shutil.copyfile(image,dest)
            for task in selected:
                box=task['target_px']
                if len(box)!=4 or not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height:raise ValueError('reviewed_gold_invalid')
                # Query is authored only from requested object type; no coordinates, figure locations or gold labels.
                query=task.get('detector_query') or ('a rectangular diagram node. a diagram.' if 'graph-' in task['id'] else 'a diagram. a rectangular region. a closed curve.')
                source={'detector':'book','path':str(dest.resolve()),'sha256':page['png_sha256'],'original_pdf_path':str(pdf),'original_pdf_sha256':review['pdf_sha256'],'physical_page':page['physical_page'],'printed_page':page.get('printed_page'),'render_scale':page.get('render_scale'),'image_size':[width,height],'query':query,'include_proposal_table':True,'privacy':'user-provided private document; public export forbidden','transforms':'exact reviewed full-page PNG; no crop/downscale/quantization'}
                gold={'expected':'found','target_px':box,'width':width,'height':height,'object_class':page['type'],'minimum_iou':.5,'minimum_coverage':.8,'tolerance_px':task.get('tolerance_px'),'annotation_scope':review['review_scope']}
                cases.append(dict(id=task['id'],family='book-'+review['pdf_sha256'][:10]+'-p'+str(page['physical_page']),lane='book',provenance='user-provided',source=json.dumps(source),request=task['request'],gold=json.dumps(gold),rubric='visual-grounding-v1'))
    if {c['id'] for c in cases}!=wanted:raise ValueError('selected_tasks_missing')
    d=dict(version='quality-campaign-v1',id=a.id,purpose='Private mixed text/diagram user-book pages: identical full image and actual image-only OCR across direct, closed-contour layout proposals, and GroundingDINO proposals; no public content export or heldout certification.',transport=a.transport,adapter='vibe_learner.visual_grounding_book:run_sample',concurrency=4,repetitions=1,seed=912,timeout_seconds=60,sample_deadline_seconds=240,sample_wire_limit=1,max_output_tokens=2048,input_reservation_tokens=750000,max_inline_images=2,max_inline_image_bytes=524288,max_inline_image_dimension=2048,thinking='adaptive',temperature=.1,budget=json.loads(a.budget_from.read_text())['budget'],cases=cases,variants=[dict(id=v,instruction=v) for v in ['direct','layout','dino']])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(Campaign.model_validate(d).model_dump_json(indent=2)+'\n')
if __name__=='__main__':main()
