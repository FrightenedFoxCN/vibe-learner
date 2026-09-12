"""Public-image adapter to the pinned, no-remote-code local vision subprocess."""
import hashlib,json,subprocess
from pathlib import Path
from .visual_grounding_runtime import WEIGHTS,ENVIRONMENT,RUNTIME_PYTHON,MODEL_ROOT

def grounded_proposals(context,source,variant):
    for row in WEIGHTS:
        p=Path(row['path'])
        if p.stat().st_size!=row['bytes'] or hashlib.sha256(p.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('weights_changed')
    worker=Path(__file__).with_name('visual_grounding_grounded_worker.py')
    run=subprocess.run([RUNTIME_PYTHON,str(worker),'--image',source['path'],'--query',source['query'],'--output',str(context.storage),'--model-root',MODEL_ROOT],capture_output=True,text=True,timeout=100,check=True)
    data=json.loads((context.storage/'grounded-detector.json').read_text());proposals=[]
    if data['environment_actual']!=ENVIRONMENT:raise ValueError('runtime_environment_changed')
    for item in data['proposals']:
        p=dict(item)
        if variant=='sam':
            if not p['mask_box_px']:continue
            p['box_px']=p['mask_box_px'];p['kind']='sam2_mask_tightbox'
        proposals.append(p)
    data['runtime_stderr']=run.stderr[:3000]
    data['environment']=ENVIRONMENT
    # Total is required compute, including weight load. Parent wall time also includes checks/spawn.
    return proposals,data

from .visual_grounding import run_sample,source_manifest
