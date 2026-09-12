"""Export immutable synthetic experiment evidence and its reproducible lab source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile
from .ledger import Ledger
from .runner import exclusive


def validate_source_snapshot(path, manifest):
    key=os.environ.get('K3_API_KEY','').encode()
    with zipfile.ZipFile(path) as archive:
        index=json.loads(archive.read('source-index.json'))
        if index['campaign']!=manifest['config']['id'] or index['git_revision']!=manifest['source']['git_revision']:
            raise ValueError('execution source identity mismatch')
        if set(archive.namelist())!=set(index['files'])|{'source-index.json'}:
            raise ValueError('unindexed execution source')
        for name,expected in index['files'].items():
            data=archive.read(name)
            if Path(name).is_absolute() or '..' in Path(name).parts or hashlib.sha256(data).hexdigest()!=expected:
                raise ValueError('execution source integrity mismatch')
            if key and key in data:
                raise ValueError('credential in execution source')


def export(campaigns, ledger_path, output, supplements=None):
    from contextlib import ExitStack
    entries = {}
    def add(name, path):
        data = path.read_bytes()
        key = os.environ.get('K3_API_KEY', '').encode()
        if key and key in data:
            raise ValueError('credential found in export input')
        if name in entries:
            raise ValueError('duplicate export entry')
        entries[name] = data
    with ExitStack() as stack:
        for root in sorted(p.resolve() for p in campaigns):
            stack.enter_context(exclusive(root/'campaign.lock'))
            manifest = json.loads((root/'manifest.json').read_text())
            if manifest['ledger_path'] != str(ledger_path.resolve()):
                raise ValueError('campaign ledger mismatch')
            report = json.loads((root/'report.json').read_text())
            if any(report['states'].get(state, 0) for state in ('pending','running')):
                raise ValueError('campaign must be terminal before export')
            prefix = manifest['config']['id']
            for name in ('manifest.json', 'report.json'):
                add(prefix+'/'+name, root/name)
            snapshot=root/'execution-source.zip'
            if snapshot.exists():
                validate_source_snapshot(snapshot,manifest)
                add(prefix+'/execution-source.zip',snapshot)
            for sample in report['samples']:
                for reference in (sample.get('result') or {}).get('evidence', []):
                    rel = Path(sample['case'])/sample['variant']/str(sample['repetition'])/'storage'/reference['path']
                    if not (root/rel).resolve().is_relative_to(root):
                        raise ValueError('evidence path escapes campaign')
                    add(prefix+'/'+rel.as_posix(), root/rel)
        ledger=Ledger(ledger_path)
        with ledger.transaction() as db:
            if db.execute("SELECT COUNT(*) FROM wires WHERE state='inflight'").fetchone()[0]:
                raise ValueError('ledger has in-flight requests')
            audit = {}
            for table in ('settings','budget_amendments','overload_restarts','scaling','scaling_events'):
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                    audit[table]=[dict(row) for row in db.execute('SELECT * FROM '+table)]
            wires=[dict(row) for row in db.execute('SELECT * FROM wires ORDER BY started,id')]
            audit['wire_count']=len(wires)
            audit['charged_or_reserved_tokens']=sum(row['charged'] for row in wires)
            audit['wires']=wires
        entries['ledger-audit.json']=json.dumps(audit,ensure_ascii=False,indent=2).encode()
        lab = Path(__file__).resolve().parent.parent
        for path in sorted(lab.rglob('*.py')):
            if path.relative_to(lab).parts[0] in ('model_quality','integrations','tests','integration_tests','examples'):
                add('lab-source/'+path.relative_to(lab).as_posix(),path)
        for name in ('README.md','pyproject.toml','uv.lock'):
            add('lab-source/'+name,lab/name)
        for name,path in (supplements or {}).items():
            if Path(name).is_absolute() or '..' in Path(name).parts or Path(name).suffix not in ('.md','.json','.txt'):
                raise ValueError('invalid supplemental document path')
            add(name,path)
        index = {name: {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)} for name,data in sorted(entries.items())}
        entries['index.json']=json.dumps({'version':'model-quality-export-v1','files':index,
            'scope':'Synthetic public receipts and allowlisted telemetry. No database, diagnostics, provider reasoning or credentials. Source is export-time; frozen execution hashes are in each manifest.'},indent=2).encode()
        key=os.environ.get('K3_API_KEY','').encode()
        if key and any(key in data for data in entries.values()):
            raise ValueError('credential found in export')
        with output.open('xb') as target, zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in sorted(entries.items()):
                archive.writestr(name,data)
    return {'path':str(output.resolve()),'sha256':hashlib.sha256(output.read_bytes()).hexdigest(), 'files':len(entries)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-dir',type=Path,action='append',required=True)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--include',type=Path,action='append',default=[])
    parser.add_argument('--include-root',type=Path)
    args=parser.parse_args()
    if args.include and args.include_root is None:
        parser.error('--include requires --include-root')
    supplements={}
    for path in args.include:
        resolved=path.resolve()
        if not resolved.is_relative_to(args.include_root.resolve()):
            parser.error('included document escapes --include-root')
        supplements[resolved.relative_to(args.include_root.resolve()).as_posix()]=resolved
    print(json.dumps(export(args.campaign_dir,args.ledger,args.output,supplements)))


if __name__=='__main__':
    main()
