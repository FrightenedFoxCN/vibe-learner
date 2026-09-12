"""Validate public licenses/hashes and freeze a small natural-image diagnostic."""
import argparse,hashlib,json,shutil
from pathlib import Path
from urllib.parse import urlparse
from model_quality.protocol import Campaign

TASKS=[('natural-cat','chelsea','visible cat overall','Locate the whole visible cat, not only its face.','a cat.'),
 ('natural-person','astronaut','visible person excluding separate held helmet','Locate the visible person, excluding the separate helmet being held.','a person. a helmet.'),
 ('natural-cup','coffee','coffee cup including handle, excluding saucer and spoon','Locate the coffee cup including its handle, excluding the saucer and spoon.','a coffee cup. a saucer. a spoon.'),
 ('natural-dog-absent','coffee','dog','Locate a dog. If no dog is visible, return absent.','a dog.'),
 ('natural-saucer','coffee','visible saucer outer extents, not cup or spoon','Locate the entire saucer below the coffee cup. Define box edges by the saucer outer visible boundary, not the cup or spoon; the bounding box may enclose overlapping objects.','a coffee cup. a saucer. a spoon.'),
 ('natural-helmet','astronaut','handheld helmet only, excluding person','Locate the separate helmet held by the person, excluding the person.','a person. a helmet.')]

def main():
    p=argparse.ArgumentParser();p.add_argument('--budget-from',type=Path,required=True);p.add_argument('--input-manifest',type=Path,required=True);p.add_argument('--gold',type=Path,action='append',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--transport',default='fake',choices=['fake','minimax']);p.add_argument('--cases',default='');p.add_argument('--id',default='m3-natural-grounding-20260912-v1');a=p.parse_args()
    if a.output.exists() or a.fixtures.exists():raise ValueError('fresh_paths_required')
    inputs={d['name']:d for d in json.loads(a.input_manifest.read_text())};gold=[]
    for path in a.gold:gold.extend(json.loads(path.read_text())['cases'])
    assets={};a.fixtures.mkdir(parents=True)
    for name,d in inputs.items():
        parsed=urlparse(d['source_url'])
        if parsed.scheme!='https' or parsed.netloc!='raw.githubusercontent.com' or '/scikit-image/v0.25.2/skimage/data/' not in parsed.path or d['license'] not in ['NASA public domain','CC0']:raise ValueError('unreviewed_public_source')
        original=Path('/private/tmp/m3-natural-'+name+'.png');png=Path(d['path'])
        if hashlib.sha256(original.read_bytes()).hexdigest()!=d['source_sha256'] or hashlib.sha256(png.read_bytes()).hexdigest()!=d['input_sha256']:raise ValueError('asset_digest')
        if d.get('dither')!='NONE' or d.get('quantize_colors')!=32 or len(png.read_bytes())>32768:raise ValueError('unreviewed_transform')
        dest=a.fixtures/(name+'.png');shutil.copyfile(png,dest);assets[name]={**d,'path':str(dest.resolve()),'sha256':d['input_sha256'],'license_evidence':'https://github.com/scikit-image/scikit-image/blob/v0.25.2/skimage/data/_fetchers.py','transforms':{'original_size':d['original_size'],'input_size':d['input_size'],'max_dimension':d['max_dimension'],'quantize_colors':32,'dither':'NONE'},'detector':'grounded'}
    cases=[];requested=set(a.cases.split(',')) if a.cases else None
    for ident,name,key,request,query in TASKS:
        if requested and ident not in requested:continue
        matches=[g for g in gold if g['image']==name and g['target']==key]
        if len(matches)!=1:raise ValueError('unique_gold_required_'+ident)
        g=matches[0];source=assets[name]
        if g['input_sha256']!=source['sha256']:raise ValueError('gold_image_mismatch')
        width,height=source['input_size'];box=g['bbox']
        if box is not None and (len(box)!=4 or not 0<=box[0]<box[2]<=width or not 0<=box[1]<box[3]<=height):raise ValueError('gold_box_invalid')
        score={'expected':'absent' if box is None else 'found','target_px':box,'width':width,'height':height,'object_class':key,'minimum_iou':.5,'minimum_coverage':.8,'tolerance_px':g.get('tolerance_px'), 'annotation_ambiguity':g.get('ambiguity'),'review_scope':'coarse same-task independent visual bbox; no mask GT; famous demo images not held-out'}
        cases.append(dict(id=ident,family=name,lane='natural',provenance='public-licensed',source=json.dumps({**source,'query':query}),request=request,gold=json.dumps(score),rubric='visual-grounding-v1'))
    c=dict(version='quality-campaign-v1',id=a.id,purpose='Public licensed natural-image development diagnostic: M3 direct versus real pinned CPU GroundingDINO boxes and SAM2 mask-derived boxes with M3 numbered selection; no expert/heldout certification.',transport=a.transport,adapter='vibe_learner.visual_grounding_natural:run_sample',concurrency=4,repetitions=1,seed=912,timeout_seconds=60,sample_deadline_seconds=240,sample_wire_limit=1,max_output_tokens=2048,input_reservation_tokens=100000,max_inline_images=2,thinking='adaptive',temperature=.1,budget=json.loads(a.budget_from.read_text())['budget'],cases=cases,variants=[dict(id=x,instruction=x) for x in ['direct','dino','sam']])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(Campaign.model_validate(c).model_dump_json(indent=2)+'\n')
if __name__=='__main__':main()
