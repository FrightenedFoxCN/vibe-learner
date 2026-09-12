"""Pinned offline GroundingDINO/SAM2 image worker, run by isolated Python.

Inputs are an image and a manually declared query derived from the user task.
No gold boxes, expected presence, generated fixture primitives or grader inputs.
"""
import argparse,base64,hashlib,importlib.metadata,json,os,platform,time,warnings
from pathlib import Path

def run(image_path,query,output,model_root):
    os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    import torch,numpy as np
    from PIL import Image
    from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection,Sam2Model,Sam2Processor
    torch.set_num_threads(2);output.mkdir(parents=True,exist_ok=True)
    start=time.monotonic();image=Image.open(image_path).convert('RGB');w,h=image.size
    processor=AutoProcessor.from_pretrained(model_root/'grounding-dino-tiny',local_files_only=True,trust_remote_code=False)
    model,di=AutoModelForZeroShotObjectDetection.from_pretrained(model_root/'grounding-dino-tiny',local_files_only=True,trust_remote_code=False,use_safetensors=True,output_loading_info=True);model.eval()
    sp=Sam2Processor.from_pretrained(model_root/'sam2-hiera-tiny',local_files_only=True,trust_remote_code=False)
    sm,si=Sam2Model.from_pretrained(model_root/'sam2-hiera-tiny',local_files_only=True,trust_remote_code=False,use_safetensors=True,output_loading_info=True);sm.eval()
    # Do not accept missing image weights. Unexpected video-specific extras must remain explicit.
    for name,info in [('dino',di),('sam',si)]:
        if info.get('missing_keys') or info.get('mismatched_keys') or info.get('error_msgs'):raise RuntimeError(name+'_weights_incomplete')
        extras=info.get('unexpected_keys',[])
        if extras and (name!='sam' or any(not any(t in k for t in ['memory','object_pointer','temporal','no_mem','obj_ptr']) for k in extras)):raise RuntimeError(name+'_unexpected_weights')
    data={'method':'grounding-dino-tiny+sam2-hiera-tiny-v1','device':'cpu','threads':2,'query':query,'threshold':.4,'text_threshold':.3,'image_sha256':hashlib.sha256(image_path.read_bytes()).hexdigest(),'loading_seconds':time.monotonic()-start,'loading_info':{'dino':di,'sam2':si},'sam2_config_type_warning':'Official facebook/sam2-hiera-tiny config is sam2_video; official image usage loads Sam2Model. Kept unchanged.','proposals':[]}
    start=time.monotonic();inputs=processor(images=image,text=query,return_tensors='pt')
    with torch.inference_mode():raw=model(**inputs)
    result=processor.post_process_grounded_object_detection(raw,inputs.input_ids,threshold=.4,text_threshold=.3,target_sizes=[(h,w)])[0]
    data['detection_seconds']=time.monotonic()-start
    boxes=[]
    for box,score,label in zip(result['boxes'].tolist(),result['scores'].tolist(),result['text_labels']):
        clipped=[max(0.,min(float(w),box[0])),max(0.,min(float(h),box[1])),max(0.,min(float(w),box[2])),max(0.,min(float(h),box[3]))]
        if clipped[0]>=clipped[2] or clipped[1]>=clipped[3]:continue
        boxes.append(clipped);data['proposals'].append({'id':len(boxes),'kind':'grounding_dino','text':label,'confidence':score,'raw_detector_box_px':box,'box_px':clipped})
    if len(boxes)>40:raise RuntimeError('too_many_proposals')
    data['segmentation_seconds']=0.
    if boxes:
        start=time.monotonic();inputs=sp(images=image,input_boxes=[boxes],return_tensors='pt')
        with torch.inference_mode():raw=sm(**inputs)
        restored=sp.post_process_masks(raw.pred_masks.cpu(),inputs['original_sizes'])[0]
        for i,(candidate,quality) in enumerate(zip(restored,raw.iou_scores[0])):
            chosen=int(quality.argmax());arr=candidate[chosen].numpy().astype('uint8')*255;path=output/f'mask-{i+1}.png';Image.fromarray(arr).save(path)
            ys,xs=np.nonzero(arr);tight=[int(xs.min()),int(ys.min()),int(xs.max()+1),int(ys.max()+1)] if len(xs) else None
            data['proposals'][i].update(mask_file=path.name,mask_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),mask_png_base64=base64.b64encode(path.read_bytes()).decode(),mask_area_pixels=int((arr>0).sum()),mask_box_px=tight,predicted_mask_iou=float(quality[chosen]),mask_selection='highest_model_predicted_iou; never gold',mask_candidates=quality.tolist())
        data['segmentation_seconds']=time.monotonic()-start
    data['environment_actual']={'python':platform.python_version(),'packages':{x.metadata['Name']:x.version for x in importlib.metadata.distributions()}}
    data['total_seconds']=data['loading_seconds']+data['detection_seconds']+data['segmentation_seconds']
    (output/'grounded-detector.json').write_text(json.dumps(data,indent=2)+'\n');return data

def main():
    p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--query',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model-root',type=Path,default=Path('/private/tmp/m3-grounded-models'));a=p.parse_args()
    run(a.image,a.query,a.output,a.model_root)
if __name__=='__main__':main()
