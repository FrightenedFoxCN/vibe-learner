"""One-call reflection over a frozen direct book-page localization result."""
import base64,hashlib,io,json,time
from pathlib import Path

from PIL import Image

from model_quality.runner import atomic_json
from .visual_grounding import Direct,decode,grade,source_manifest
from .visual_grounding_book_detector import propose_book


def run_sample(context,case,variant):
    evidence={'version':'visual-grounding-reflection-v1','case':case.id,'variant':variant.id,
              'scope':'private book-page proposal-only reflection; no domain effects/commit'}
    def finish(status,metrics,code=None):
        evidence.update(status=status,metrics=metrics,error_code=code)
        atomic_json(context.storage/'reflection-evidence.json',evidence)
        return {'status':status,'failure_owner':None if status=='completed' else status.removesuffix('_failed'),
                'error_code':code,'metrics':metrics,
                'evidence':[{'path':'reflection-evidence.json','contract':'visual-grounding-reflection-v1'}]}
    try:
        source=json.loads(case.source);gold=json.loads(case.gold);png=Path(source['path']).read_bytes()
        if variant.id!='reflect-direct' or hashlib.sha256(png).hexdigest()!=source['sha256']:
            raise ValueError('invalid_source')
        image=Image.open(io.BytesIO(png));width,height=image.size
        if (width,height)!=(gold['width'],gold['height']):raise ValueError('dimensions')
        base=Direct.model_validate(source['base_prediction'])
        if base.status=='found':
            b=base.box
            if b is None or len(b)!=4 or not 0<=b[0]<b[2]<=1 or not 0<=b[1]<b[3]<=1:raise ValueError('base_box')
        elif base.box is not None:raise ValueError('base_abstain')
        _,ocr=propose_book(png)
    except (OSError,ValueError,KeyError):return finish('data_failed',{},'invalid_reflection_fixture')
    instruction=('Act as a visual localization verifier. Reinspect the full page and the requested target. '
        'The earlier result may be wrong. Check the exact figure/node label, relative position, similar neighboring '
        'figures, and whether the box encloses the whole requested element while excluding named distractors. '
        'Return one final JSON DATA INSTANCE: {"status":"found","box":[x0,y0,x1,y1]} using 0..1 full-page '
        'coordinates, or absent/ambiguous/unlocalized with box:null. No prose.')
    text=(case.request+f'\nFull page size: {width} x {height} pixels.'+
          '\nEarlier direct result to verify: '+json.dumps(base.model_dump(),ensure_ascii=False)+
          '\nUncorrected image-only OCR, in detector line order; verify against the image:\n'+
          '\n'.join(f'{i+1}: {line}' for i,line in enumerate(ocr['full_ocr_lines'])))
    content=[{'type':'text','text':text},{'type':'image_url','image_url':{'url':'data:image/png;base64,'+base64.b64encode(png).decode()}}]
    c=context.transport.campaign
    payload={'model':c.model,'max_tokens':c.max_output_tokens,'temperature':c.temperature,
             'messages':[{'role':'system','content':instruction},{'role':'user','content':content}],
             'response_format':{'type':'json_object'}}
    evidence.update(request=case.request,source_sha256=source['sha256'],base_prediction=base.model_dump(),
                    base_evidence_sha256=source['base_evidence_sha256'],ocr_lines=ocr['full_ocr_lines'],
                    wire_input={**payload,'thinking':{'type':c.thinking},'reasoning_split':True,'stream':False})
    atomic_json(context.storage/'reflection-evidence.json',evidence)
    fake={'choices':[{'message':{'content':json.dumps(base.model_dump())},'finish_reason':'stop'}],
          'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30}}
    started=time.monotonic();raw=context.transport.request(payload,fake_response=fake if c.transport=='fake' else None)
    evidence['provider_wall_seconds']=time.monotonic()-started
    try:
        if raw['choices'][0].get('finish_reason')!='stop':raise ValueError('incomplete')
        prediction=decode(raw['choices'][0]['message']['content'],Direct);box=None
        if prediction.status=='found':
            box=[prediction.box[0]*width,prediction.box[1]*height,prediction.box[2]*width,prediction.box[3]*height]
    except (ValueError,KeyError,IndexError,TypeError) as exc:
        evidence['decode_error_type']=type(exc).__name__
        return finish('candidate_failed',{'schema_valid':False},'invalid_reflection_output')
    metrics=grade(prediction.status,box,gold,[]);metrics['schema_valid']=True
    base_box=[base.box[0]*width,base.box[1]*height,base.box[2]*width,base.box[3]*height] if base.status=='found' else None
    base_metrics=grade(base.status,base_box,gold,[])
    metrics.update(base_iou=base_metrics['iou'],base_coverage=base_metrics['coverage'],
                   iou_delta=metrics['iou']-base_metrics['iou'],task_improved=metrics['task_pass'] and not base_metrics['task_pass'])
    evidence.update(prediction=prediction.model_dump(),box_px=box,gold=gold)
    return finish('completed' if metrics['task_pass'] else 'candidate_failed',metrics)
