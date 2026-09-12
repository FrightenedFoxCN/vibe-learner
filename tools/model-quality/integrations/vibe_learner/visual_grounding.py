"""Proposal-only visual grounding. All M3 calls use the shared metered transport."""
import base64,hashlib,importlib.metadata,io,json,math,re,subprocess,time
from pathlib import Path
from PIL import Image
from pydantic import BaseModel,ConfigDict,StrictInt,ValidationError
from typing import Literal
from model_quality.runner import atomic_json
from .visual_grounding_detector import propose,mark,TESSERACT

class Selection(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    status:Literal['found','absent','ambiguous','unlocalized']
    proposal_id:StrictInt|None
class Direct(BaseModel):
    model_config=ConfigDict(strict=True,extra='forbid')
    status:Literal['found','absent','ambiguous','unlocalized']
    box:list[float]|None

def source_manifest():
    from .common import source_manifest as common_source_manifest
    from .visual_grounding_fixtures import FONT
    manifest=common_source_manifest()
    resources=[FONT,Path(TESSERACT),Path('/opt/homebrew/share/tessdata/eng.traineddata')]
    manifest['visual_external_resources']={str(p.resolve()):hashlib.sha256(p.read_bytes()).hexdigest() for p in resources}
    manifest['visual_external_resources_packaged']=False
    manifest['dependencies'].update({k:importlib.metadata.version(k) for k in ('pillow','opencv-python-headless','numpy')})
    from .visual_grounding_runtime import WEIGHTS,ENVIRONMENT,RUNTIME_PYTHON
    manifest['visual_grounded_runtime']={'weights':WEIGHTS,'environment':ENVIRONMENT,'python_path':RUNTIME_PYTHON,'weights_packaged':False}
    manifest['tesseract_version']=subprocess.check_output([TESSERACT,'--version']).decode().splitlines()[0]
    return manifest

def decode(content,cls):
    if isinstance(content,str):
        fence=re.fullmatch(r'\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*',content,re.DOTALL)
        if fence:content=fence.group(1)
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('duplicate_key')
            d[k]=v
        return d
    obj=json.loads(content,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite')))
    result=cls.model_validate(obj)
    if isinstance(result,Direct):
        if result.status=='found':
            b=result.box
            if b is None or len(b)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in obj['box']) or not 0<=b[0]<b[2]<=1 or not 0<=b[1]<b[3]<=1:raise ValueError('invalid_box')
        elif result.box is not None:raise ValueError('abstain_box')
    elif (result.status=='found' and (result.proposal_id is None or result.proposal_id<1)) or (result.status!='found' and result.proposal_id is not None):raise ValueError('invalid_selection')
    return result

def overlap(box,target):
    if box is None or target is None:return {'iou':0.,'coverage':0.}
    i=max(0,min(box[2],target[2])-max(box[0],target[0]))*max(0,min(box[3],target[3])-max(box[1],target[1]))
    a=(box[2]-box[0])*(box[3]-box[1]);g=(target[2]-target[0])*(target[3]-target[1])
    return {'iou':i/(a+g-i),'coverage':i/g}

def grade(status,box,gold,proposals):
    o=overlap(box,gold['target_px']);found=gold['expected']=='found'
    ok=status==gold['expected'] and (not found or o['iou']>=gold['minimum_iou'] and o['coverage']>=gold['minimum_coverage'])
    recalls=[overlap(p['box_px'],gold['target_px']) for p in proposals]
    return {'task_pass':ok,**o,
      'abstain_correct':status==gold['expected'] if not found else None,
      'proposal_recall_at_threshold':any(x['iou']>=gold['minimum_iou'] and x['coverage']>=gold['minimum_coverage'] for x in recalls) if found else None,
      'best_proposal_iou':max((x['iou'] for x in recalls),default=0.) if found else None}

def provider_proposal_table(proposals):
    return [{'id':p['id'],'label':p.get('text',''),'box_px':p['box_px'],'confidence':p.get('confidence'),'kind':p['kind']} for p in proposals]

def run_sample(context,case,variant):
    evidence={'version':'visual-grounding-v1','case':case.id,'variant':variant.id,'scope':'synthetic proposal-only; no domain admission/effects/commit; SoM-inspired OCR/geometric proposal selection, not original SoM reproduction'}
    def finish(status,metrics,code=None):
        evidence.update(status=status,metrics=metrics,error_code=code);atomic_json(context.storage/'visual-evidence.json',evidence)
        return {'status':status,'failure_owner':None if status=='completed' else status.removesuffix('_failed'),'error_code':code,'metrics':metrics,'evidence':[{'path':'visual-evidence.json','contract':'visual-grounding-v1'}]}
    try:
        source=json.loads(case.source);png=Path(source['path']).read_bytes();gold=json.loads(case.gold)
        if hashlib.sha256(png).hexdigest()!=source['sha256']:return finish('data_failed',{},'source_digest_changed')
        im=Image.open(io.BytesIO(png));width,height=im.size
        if (width,height)!=(gold['width'],gold['height']):return finish('data_failed',{},'gold_dimensions')
        if variant.id not in ('direct','som','dino','sam','layout'):return finish('data_failed',{},'variant_unknown')
    except (OSError,ValueError,KeyError):return finish('data_failed',{},'invalid_fixture')
    try:
        if source.get('detector')=='book':
            from .visual_grounding_book import book_proposals
            proposals,detector=book_proposals(context,source,variant.id)
        elif source.get('detector')=='grounded':
            from .visual_grounding_natural import grounded_proposals
            proposals,detector=grounded_proposals(context,source,variant.id)
        else:proposals,detector=propose(png)
    except (OSError,ValueError,subprocess.SubprocessError):return finish('infrastructure_failed',{},'local_detector_failed')
    evidence['source_provenance']=source
    evidence.update(source_image={'sha256':source['sha256'],'bytes':len(png),'width':width,'height':height},proposals=proposals,detector=detector,request=case.request)
    if source.get('detector')=='grounded':evidence['scope']='public-licensed proposal-only; no domain admission/effects/commit; pinned offline GroundingDINO/SAM2 proposals with model selection; no mask GT or heldout certification'
    if source.get('detector')=='book':evidence['scope']='user-provided private book page; proposal-only, no domain effects/commit; full image and real OCR shared by all arms; never export page content in public bundles'
    images=[png];cls=Direct
    instruction='Locate the requested region in the original image. Return one JSON DATA INSTANCE, not a schema: {"status":"found","box":[x0,y0,x1,y1]} with 0..1 coordinates relative to the FULL image (left/top origin); box tightly encloses the entire requested target. If no match return {"status":"absent","box":null}; if multiple indistinguishable matches return {"status":"ambiguous","box":null}. No prose.'
    if variant.id in ('som','dino','sam','layout'):
        try:images.append(mark(png,proposals,max_bytes=getattr(context.transport.campaign,'max_inline_image_bytes',32768)))
        except ValueError:return finish('infrastructure_failed',{},'mark_failed')
        cls=Selection
        instruction='Image 1 is original; image 2 adds numbered local detector proposals. Select only the one proposal tightly covering the requested target. Return a JSON DATA INSTANCE, not schema: {"status":"found","proposal_id":N}. If the target is truly absent use {"status":"absent","proposal_id":null}. If the target is visible but NO proposal tightly covers it, return {"status":"unlocalized","proposal_id":null}; never equate missing proposals with absent objects. If multiple indistinguishable matches use {"status":"ambiguous","proposal_id":null}. Do not guess coordinates. Numbers on image 2 are proposal IDs, not source content. No prose.'
    image_meta=[]
    for index,b in enumerate(images):
        name='source.png' if index==0 else 'marked.png'
        (context.storage/name).write_bytes(b)
        image_meta.append({'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'file':name})
    content=[{'type':'text','text':case.request+f'\nFull original image size: {width} x {height} pixels.'}]
    if source.get('detector')=='book':
        content[0]['text']+='\nUncorrected full-page image-only Tesseract OCR, in detector line order; use image to verify, OCR may be wrong:\n'+'\n'.join(f'{i+1}: {line}' for i,line in enumerate(detector['full_ocr_lines']))
    if source.get('include_proposal_table') and variant.id in ('dino','sam','layout'):
        table=provider_proposal_table(proposals);evidence['provider_proposal_table']=table
        content[0]['text']+='\nComplete detector proposal table (all candidates; labels are detector predictions, not truth): '+json.dumps(table,ensure_ascii=False)
    for b in images:content.append({'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(b).decode()}})
    c=context.transport.campaign
    payload={'model':c.model,'max_tokens':c.max_output_tokens,'temperature':c.temperature,'messages':[{'role':'system','content':instruction},{'role':'user','content':content}],'response_format':{'type':'json_object'}}
    evidence.update(wire_images=image_meta,wire_input={**payload,'thinking':{'type':c.thinking},'reasoning_split':True,'stream':False})
    atomic_json(context.storage/'visual-evidence.json',evidence)
    fake={'choices':[{'message':{'content':json.dumps({'status':'absent','box':None} if cls is Direct else {'status':'absent','proposal_id':None})},'finish_reason':'stop'}],'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}
    start=time.monotonic();raw=context.transport.request(payload,fake_response=fake if c.transport=='fake' else None);evidence['provider_wall_seconds']=time.monotonic()-start
    try:
        raw_content=raw['choices'][0]['message'].get('content')
        evidence['raw_fenced']=isinstance(raw_content,str) and raw_content.lstrip().startswith('```')
        if raw['choices'][0].get('finish_reason')!='stop':raise ValueError('incomplete_response')
        prediction=decode(raw['choices'][0]['message']['content'],cls);box=None
        if prediction.status=='found':
            if cls is Direct:box=[prediction.box[0]*width,prediction.box[1]*height,prediction.box[2]*width,prediction.box[3]*height]
            else:
                matches=[p for p in proposals if p['id']==prediction.proposal_id]
                if len(matches)!=1:raise ValueError('unknown_proposal_id')
                box=matches[0]['box_px']
        evidence.update(prediction=prediction.model_dump(),box_px=box,box_normalized=[box[0]/width,box[1]/height,box[2]/width,box[3]/height] if box else None)
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        evidence['decode_error_type']=type(exc).__name__
        if hasattr(exc,'errors'):evidence['decode_errors']=[{'type':e['type'],'loc':list(e['loc'])} for e in exc.errors()]
        return finish('candidate_failed',{'schema_valid':False},'invalid_grounding_output')
    # Gold is used only here for scoring. It never enters detector, prompt or fake reply.
    metrics=grade(prediction.status,box,gold,proposals);metrics['schema_valid']=True;metrics['honest_unlocalized']=prediction.status=='unlocalized' and gold['expected']=='found' and not metrics['proposal_recall_at_threshold'];evidence['gold']=gold
    return finish('completed' if metrics['task_pass'] else 'candidate_failed',metrics)
