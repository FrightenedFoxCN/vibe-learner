"""Capture the exact Vibe/Lab files named by an existing frozen campaign manifest.

This is read-only with respect to the campaign and does not patch running code.
A mismatch refuses the snapshot rather than relabeling newer code as old code.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile


def capture(campaign,repo,output):
    manifest=json.loads((campaign/'manifest.json').read_text());state=manifest['source']
    lab=repo/'tools/model-quality';adapter=lab/'integrations/vibe_learner'
    paths={}
    for name,value in state['runner_and_adapter_source'].items():
        path=adapter/(manifest['config']['adapter'].split(':')[0].split('.')[-1]+'.py') if name=='adapter' else lab/'model_quality'/name
        paths[path]=(value,path.relative_to(repo).as_posix())
    for name,value in state['adapter_source_manifest']['source_files'].items():
        path=adapter/name.removeprefix('adapter/') if name.startswith('adapter/') else repo/'services/ai'/name
        paths[path]=(value,path.relative_to(repo).as_posix())
    paths[lab/'uv.lock']=(state['lock_digest'],'tools/model-quality/uv.lock')
    entries={}
    key=os.environ.get('K3_API_KEY','').encode()
    for path,(expected,name) in paths.items():
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=expected:raise ValueError('frozen source changed: '+name)
        if key and key in data:raise ValueError('credential in source')
        entries[name]=data
    entries['source-index.json']=json.dumps({'campaign':manifest['config']['id'],'git_revision':state['git_revision'],
        'files':{name:hashlib.sha256(data).hexdigest() for name,data in sorted(entries.items())},
        'scope':'Exact files named by the execution manifest. Restore the recorded Git revision for other repository files; install locked dependencies. Not a runtime or database image.'},indent=2).encode()
    with output.open('xb') as stream,zipfile.ZipFile(stream,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(entries.items()):archive.writestr(name,data)
    return {'sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'files':len(entries),'path':str(output.resolve())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-dir',type=Path,required=True);parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    print(json.dumps(capture(args.campaign_dir,args.repo.resolve(),args.output)))


if __name__=='__main__':main()
