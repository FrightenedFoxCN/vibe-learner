"""Independent PERF-002 measurement. Run with the project's uv-managed Python."""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def child(port: int, root: Path):
    attempts = []
    evidence = root / 'health-evidence.json'
    def is_loopback(host):
        if host == 'localhost': return True
        try: return ipaddress.ip_address(str(host).split('%')[0]).is_loopback
        except ValueError: return False
    def audit(name, args):
        if name == 'socket.getaddrinfo':
            host = args[0]
            if host is not None and not is_loopback(host):
                attempts.append({'event': name, 'host': str(host)})
                raise PermissionError('independent acceptance forbids non-loopback DNS')
        elif name in {'socket.connect', 'socket.sendto'}:
            address = args[-1]
            if isinstance(address, tuple) and address and not is_loopback(address[0]):
                attempts.append({'event': name, 'host': str(address[0]), 'port': address[1]})
                raise PermissionError('independent acceptance forbids non-loopback network')
    sys.addaudithook(audit)
    sys.path.insert(0, str(SERVICE_ROOT))
    import uvicorn
    from app.app_factory import create_app
    from app.core.settings import Settings
    app = create_app(settings=Settings(
        database_url=f'sqlite:///{root / "runtime.sqlite3"}',
        storage_root=str(root / 'data'), plan_provider='mock',
        auto_migrate_local_data=False, ocr_engine='onnxtr',
    ))
    async def instrumented(scope, receive, send):
        async def observed_send(message):
            if (scope.get('type') == 'http' and scope.get('path') == '/health'
                and message['type'] == 'http.response.start'):
                modules = sorted(name for name in sys.modules
                                 if name in {'litellm', 'onnxtr'} or name.startswith(('litellm.', 'onnxtr.')))
                evidence.write_text(json.dumps({'pid': os.getpid(), 'http_status': message['status'],
                    'forbidden_modules': modules, 'non_loopback_attempts': list(attempts),
                    'local_cost_map_env_present': 'LITELLM_LOCAL_MODEL_COST_MAP' in os.environ,
                    'database_url': f'sqlite:///{root / "runtime.sqlite3"}',
                    'storage_root': str(root / 'data'), 'provider': 'mock'}), encoding='utf-8')
            await send(message)
        await app(scope, receive, observed_send)
    uvicorn.run(instrumented, host='127.0.0.1', port=port, log_level='warning', access_log=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--port', type=int)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.child:
        child(args.port, args.root)
        return 0
    if args.output is None: parser.error('--output is required')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    samples=[]
    report={'schema_version':'backend-startup-acceptance-v1','gate_seconds':2.0,
        'required_samples':10,'database_mode':'fresh empty SQLite and empty storage per process',
        'timing':'perf_counter immediately before Popen through first HTTP 200 /health JSON response fully read',
        'instrumentation':'CPython socket audit hooks installed before uvicorn/app import; non-loopback attempts recorded and denied; any attempt fails gate',
        'clock':'time.perf_counter','python':sys.version,'platform':platform.platform(),
        'samples':samples,'passed':False}
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    env=os.environ.copy()
    for key in list(env):
        if key.startswith('LITELLM_'): env.pop(key)
    env['PYTHONUNBUFFERED']='1'
    with tempfile.TemporaryDirectory(prefix='vibe-startup-independent-') as temp:
        for index in range(10):
            root=Path(temp)/f'sample-{index+1:02d}'; root.mkdir()
            with socket.socket() as available:
                available.bind(('127.0.0.1',0)); port=available.getsockname()[1]
            sample={'index':index+1,'empty_database_at_spawn':not (root/'runtime.sqlite3').exists(),
                    'empty_storage_at_spawn':not (root/'data').exists()}
            with (root/'process.log').open('w+') as log:
                start=time.perf_counter()
                process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--child','--port',str(port),'--root',str(root)],
                    cwd=SERVICE_ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
                try:
                    while time.perf_counter()-start < 15:
                        if process.poll() is not None: break
                        try:
                            with opener.open(f'http://127.0.0.1:{port}/health',timeout=0.1) as response:
                                payload=json.loads(response.read())
                                if response.status==200:
                                    sample['elapsed_seconds']=time.perf_counter()-start
                                    sample['health_response']=payload
                                    break
                        except (urllib.error.URLError, TimeoutError, ConnectionError): pass
                        time.sleep(0.01)
                    evidence=root/'health-evidence.json'
                    sample['evidence']=json.loads(evidence.read_text()) if evidence.exists() else None
                    sample['passed']=bool(sample.get('elapsed_seconds',float('inf'))<2.0 and sample['evidence']
                        and not sample['evidence']['forbidden_modules']
                        and not sample['evidence']['non_loopback_attempts']
                        and not sample['evidence']['local_cost_map_env_present'])
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
                    sample['process_exit_code']=process.returncode
                    log.flush(); log.seek(0); sample['process_log']=log.read()
            samples.append(sample)
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
            print(json.dumps({'index':sample['index'],'elapsed_seconds':sample.get('elapsed_seconds'),'passed':sample['passed']}),flush=True)
    report['passed']=len(samples)==10 and all(s['passed'] for s in samples)
    times=[s['elapsed_seconds'] for s in samples if 'elapsed_seconds' in s]
    report['summary']={'min_seconds':min(times) if times else None,'max_seconds':max(times) if times else None,
                       'mean_seconds':sum(times)/len(times) if times else None}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return 0 if report['passed'] else 1

if __name__=='__main__': raise SystemExit(main())
