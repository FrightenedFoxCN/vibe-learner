"""Rebuild/check the single pinned local vision runtime; no model inference.

Run --requirements with ordinary Python to print the complete installed lock.
Create an isolated venv and install those requirements; then run --download
with that venv's Python. Downloads only the frozen safetensors/config/tokenizer
allowlist using token=False, never repository code or pickle weights.
"""
import argparse,hashlib,os
from pathlib import Path
from visual_grounding_runtime import WEIGHTS,ENVIRONMENT

def main():
    p=argparse.ArgumentParser();p.add_argument('--requirements',action='store_true');p.add_argument('--download',action='store_true');a=p.parse_args()
    if a.requirements:
        for name,version in sorted(ENVIRONMENT['packages'].items()):print(f'{name}=={version}')
        return
    if a.download:
        os.environ['HF_HUB_DISABLE_XET']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1';os.environ['HF_HUB_DOWNLOAD_TIMEOUT']='120'
        from huggingface_hub import hf_hub_download
    for row in WEIGHTS:
        path=Path(row['path'])
        if a.download:hf_hub_download(row['repo'],row['file'],revision=row['revision'],local_dir=path.parent,token=False)
        if path.stat().st_size!=row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:raise ValueError('locked_resource_digest_mismatch')
        print('verified',row['repo'],row['revision'],row['file'])
if __name__=='__main__':main()
