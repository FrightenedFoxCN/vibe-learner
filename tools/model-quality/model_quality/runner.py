"""Fresh-process scheduler and durable sample checkpoints, independent of pytest/Harness."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import fcntl
import hashlib
import importlib
import importlib.metadata
import json
import math
import multiprocessing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from .adapters import Context
from .ledger import GateClosed, Ledger
from .protocol import AdapterResult, Campaign, canonical, digest
from .transport import ENDPOINT, MeteredTransport, WireFailure


@contextmanager
def exclusive(path: Path):
    with path.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('campaign or sample is still owned by a live process') from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class Checkpoints:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self, samples):
        with self.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS samples (
                id TEXT PRIMARY KEY, identity TEXT NOT NULL, family TEXT NOT NULL,
                state TEXT NOT NULL, result TEXT, started REAL, finished REAL)''')
            for sid, identity, case, _ in samples:
                db.execute('INSERT OR IGNORE INTO samples(id,identity,family,state) VALUES(?,?,?,?)',
                           (sid, canonical(identity), case.family, 'pending'))

    def rows(self):
        with self.connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM samples ORDER BY id')]

    def start(self, sid):
        with self.connection() as db:
            changed = db.execute("UPDATE samples SET state='running',started=? WHERE id=? AND state='pending'", (time.time(), sid)).rowcount
            if changed != 1:
                raise RuntimeError('sample admission is fenced')

    def finish(self, sid, result):
        with self.connection() as db:
            changed = db.execute("UPDATE samples SET state=?,result=?,finished=? WHERE id=? AND state='running'",
                                 (result['status'], canonical(result), time.time(), sid)).rowcount
            if changed != 1:
                raise RuntimeError('sample completion is fenced')

    def running(self, sid):
        with self.connection() as db:
            row = db.execute('SELECT state FROM samples WHERE id=?', (sid,)).fetchone()
            return row is not None and row['state'] == 'running'


def adapter_function(path):
    module, name = path.split(':')
    return getattr(importlib.import_module(module), name)


def source_state(adapter):
    root = Path(__file__).resolve().parent
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))}
    module = importlib.import_module(adapter.split(':')[0])
    files['adapter'] = hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL, text=True).strip()
        diff = subprocess.check_output(['git', 'diff', '--binary', 'HEAD'], stderr=subprocess.DEVNULL)
        dirty_digest = hashlib.sha256(diff).hexdigest()
    except subprocess.CalledProcessError:
        revision, dirty_digest = None, None
    return {'git_revision': revision, 'tracked_dirty_digest': dirty_digest,
            'runner_and_adapter_source': files, 'python': sys.version,
            'dependencies': {name: importlib.metadata.version(name) for name in ('pydantic', 'pydantic-core', 'certifi')},
            'lock_digest': hashlib.sha256((root.parent / 'uv.lock').read_bytes()).hexdigest() if (root.parent / 'uv.lock').exists() else None,
            'adapter_source_manifest': module.source_manifest() if callable(getattr(module, 'source_manifest', None)) else None,
            'limitations': 'External dependencies are frozen only when the adapter supplies source_manifest().'}


def worker(config, ledger_path, output_path, sample_id):
    # No inherited global monkeypatches or shared domain state (spawn context).
    c = Campaign.model_validate(config)
    root = Path(output_path)
    checkpoint = Checkpoints(root / 'checkpoints.sqlite3')
    sid, identity, case, variant = next(s for s in c.samples() if s[0] == sample_id)
    cell = root / case.id / variant.id / str(identity['repetition'])
    ledger = Ledger(Path(ledger_path))
    with exclusive(cell / 'worker.lock'):
        if not checkpoint.running(sid):
            return
        os.chdir(cell)
        os.environ['MODEL_QUALITY_SAMPLE_DIR'] = str(cell)
        os.environ['MODEL_QUALITY_DATABASE_URL'] = 'sqlite:///' + str(cell / 'domain.sqlite3')
        deadline = time.monotonic() + c.sample_deadline_seconds
        context = Context(MeteredTransport(c, ledger, sid, deadline), cell / 'storage', cell / 'domain.sqlite3')
        try:
            result = adapter_function(c.adapter)(context, case, variant)
            try:
                result = AdapterResult.model_validate(result).model_dump()
                canonical(result)
                for ref in result['evidence']:
                    json.loads((context.storage / ref['path']).read_text())
            except (ValueError, OSError):
                result = {'status': 'metric_failed', 'failure_owner': 'metric', 'error_code': 'invalid_adapter_result'}
        except GateClosed as exc:
            result = {'status': 'stopped', 'failure_owner': 'infrastructure', 'error_code': str(exc)}
        except WireFailure as exc:
            result = {'status': 'uncertain' if exc.uncertain else 'infrastructure_failed',
                      'failure_owner': 'infrastructure', 'error_code': exc.code}
        except Exception as exc:
            # Error strings/tracebacks can contain provider keys and source content.
            result = {'status': 'infrastructure_failed', 'failure_owner': 'infrastructure', 'error_class': type(exc).__name__}
        if ledger.recover(c.id, sid):
            result = {'status': 'uncertain', 'failure_owner': 'infrastructure', 'error_code': 'unsettled_wire_no_replay'}
        result.update(sample_id=sid, pid=os.getpid())
        checkpoint.finish(sid, result)


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def report(c, checkpoint, ledger, output):
    rows = checkpoint.rows()
    samples = [{**json.loads(row['identity']), 'sample_id': row['id'], 'family': row['family'],
                'state': row['state'], 'result': json.loads(row['result']) if row['result'] else None,
                'elapsed_seconds': row['finished'] - row['started'] if row['finished'] and row['started'] else None}
               for row in rows]
    pairs = {}
    for sample in samples:
        key = sample['case'] + ':' + str(sample['repetition'])
        pairs.setdefault(key, {})[sample['variant']] = sample['state']
    wire = ledger.snapshot(c.id)
    latencies = sorted(r['metadata']['elapsed_ms'] for r in wire['wires'] if r['metadata'] and 'elapsed_ms' in r['metadata'])
    report_data = {'wire_latency_ms': {str(p): latencies[math.ceil(len(latencies)*p/100)-1] if latencies else None for p in (50, 95)},
                  'percentile_method': 'nearest-rank',
                  'aggregation_source_digest': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'failure_owners': dict(Counter(s['result'].get('failure_owner') for s in samples if s['result'] and s['result'].get('failure_owner'))),
                  'version': 'quality-report-v1', 'campaign': c.id, 'transport': c.transport,
                  'scope': 'research infrastructure; not Harness evidence or independent quality certification',
                  'expected_samples': len(samples), 'independent_families': len({s['family'] for s in samples}),
                  'states': dict(Counter(s['state'] for s in samples)), 'pairs': pairs,
                  'samples': samples, 'campaign_usage': wire,
                  'resource_window_usage': {k: v for k, v in ledger.snapshot().items() if k != 'wires'},
                  'billing_limit_certified': False}
    atomic_json(output / 'report.json', report_data)
    return report_data


def run(c: Campaign, output: Path, ledger_path: Path, *, resume=False):
    output, ledger_path = output.resolve(), ledger_path.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with exclusive(output / 'campaign.lock'):
        manifest = {'config': c.model_dump(), 'config_digest': digest(c.model_dump()),
                    'source': source_state(c.adapter), 'ledger_path': str(ledger_path),
                    'endpoint': ENDPOINT if c.transport == 'minimax' else None,
                    'credential_env': 'K3_API_KEY', 'scope': 'standalone research campaign'}
        path = output / 'manifest.json'
        if path.exists():
            if not resume:
                raise ValueError('campaign exists; use --resume')
            if json.loads(path.read_text()) != manifest:
                raise ValueError('resume requires identical config, source and ledger')
        else:
            if resume:
                raise ValueError('cannot resume a missing campaign')
            if (output / 'checkpoints.sqlite3').exists():
                raise ValueError('orphan checkpoint directory')
            atomic_json(path, manifest)
        ledger = Ledger(ledger_path)
        ledger.initialize(c.budget, c.transport)
        ledger.configure_scaling(c.concurrency, c.autoscale)
        ledger.bind_campaign(c.id, digest({'manifest': manifest, 'output': str(output)}))
        checkpoint = Checkpoints(output / 'checkpoints.sqlite3')
        samples = list(c.samples())
        checkpoint.initialize(samples)
        for sid, identity, case, variant in samples:
            cell = output / case.id / variant.id / str(identity['repetition'])
            (cell / 'storage').mkdir(parents=True, exist_ok=True)
            # Fresh domain DB exists even for adapters that need no domain tables.
            sqlite3.connect(cell / 'domain.sqlite3').close()
            if checkpoint.running(sid):
                with exclusive(cell / 'worker.lock'):
                    ledger.recover(c.id, sid)
                    checkpoint.finish(sid, {'status': 'uncertain', 'failure_owner': 'infrastructure',
                                            'error_code': 'interrupted_no_replay'})
        states = {row['id']: row['state'] for row in checkpoint.rows()}
        pending = [sample for sample in samples if states[sample[0]] == 'pending']
        if pending and c.transport == 'minimax' and not os.environ.get('K3_API_KEY', '').strip():
            raise ValueError('K3_API_KEY is required for live dispatch')
        ctx = multiprocessing.get_context('spawn')
        active = {}
        try:
            while pending or active:
                scaling = ledger.tick_scaling(len(pending))
                if scaling['stopped'] or time.time() >= c.budget.expires_at - c.budget.stop_buffer_seconds:
                    for sid, _, _, _ in pending:
                        checkpoint.start(sid)
                        checkpoint.finish(sid, {'status': 'stopped', 'failure_owner': 'infrastructure', 'error_code': scaling['stopped'] or 'expiry_buffer'})
                    pending.clear()
                limit = scaling['current'] if c.autoscale else c.concurrency
                # Cooling down holds pending work; admitted samples still perform read-back.
                can_dispatch = not c.autoscale or time.time() >= scaling['cooldown_until']
                while pending and can_dispatch and len(active) < limit:
                    sid, _, _, _ = pending.pop(0)
                    checkpoint.start(sid)
                    process = ctx.Process(target=worker, args=(c.model_dump(), str(ledger_path), str(output), sid))
                    active[sid] = (process, time.monotonic())
                    process.start()
                for sid, (process, started) in list(active.items()):
                    if process.is_alive() and time.monotonic() - started > c.sample_deadline_seconds + 6:
                        process.kill()
                    elif process.is_alive() and time.monotonic() - started > c.sample_deadline_seconds + 5:
                        process.terminate()
                    if not process.is_alive():
                        process.join()
                        if checkpoint.running(sid):
                            ledger.recover(c.id, sid)
                            checkpoint.finish(sid, {'status': 'uncertain', 'failure_owner': 'infrastructure',
                                                    'error_code': 'worker_exit_no_replay', 'exit_code': process.exitcode})
                        del active[sid]
                        snapshot = report(c, checkpoint, ledger, output)
                        print(canonical({'campaign': c.id, 'states': snapshot['states']}), flush=True)
                if active or pending:
                    time.sleep(0.05)
        finally:
            for sid, (process, _) in active.items():
                if process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                    process.join(timeout=5)
                    if process.is_alive():
                        process.kill()
                        process.join()
                ledger.recover(c.id, sid)
                if checkpoint.running(sid):
                    checkpoint.finish(sid, {'status': 'uncertain', 'failure_owner': 'infrastructure', 'error_code': 'runner_interrupted'})
            final = report(c, checkpoint, ledger, output)
        return final


def report_only(c: Campaign, output: Path, ledger_path: Path):
    output, ledger_path = output.resolve(), ledger_path.resolve()
    with exclusive(output / 'campaign.lock'):
        manifest = json.loads((output / 'manifest.json').read_text())
        if Campaign.model_validate(manifest['config']).model_dump() != c.model_dump() or manifest['ledger_path'] != str(ledger_path):
            raise ValueError('report config or ledger mismatch')
        checkpoint = Checkpoints(output / 'checkpoints.sqlite3')
        if {row['id'] for row in checkpoint.rows()} != {s[0] for s in c.samples()}:
            raise ValueError('report sample set mismatch')
        return report(c, checkpoint, Ledger(ledger_path), output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--ledger', type=Path, required=True, help='Reuse one absolute ledger path for the whole resource window')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--resume', action='store_true')
    mode.add_argument('--report-only', action='store_true', help='Rebuild report without workers, API key or recovery mutations')
    args = parser.parse_args()
    try:
        c = Campaign.model_validate_json(args.manifest.read_text())
        result = report_only(c, args.output, args.ledger) if args.report_only else run(c, args.output, args.ledger, resume=args.resume)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        # Validation errors may echo manifest content. Keep terminal errors redacted.
        print(canonical({'error_class': type(exc).__name__, 'status': 'runner_failed'}), file=sys.stderr)
        return 2
    return 0 if set(result['states']) <= {'completed'} else 1
