"""SQLite transaction gate shared by all worker processes and campaigns.

Every attempted wire request reserves before dispatch. Unknown usage and crashed
requests retain their reservation forever; resume never silently retries them.
"""
from __future__ import annotations

from contextlib import contextmanager
import json
import random
from pathlib import Path
import sqlite3
import time
import uuid

from .protocol import Budget, canonical


class GateClosed(RuntimeError):
    pass


class WaitForCapacity(RuntimeError):
    pass


class Ledger:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self, budget: Budget, transport: str):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, config TEXT NOT NULL, stopped TEXT)')
            db.execute('''CREATE TABLE IF NOT EXISTS wires (
                id TEXT PRIMARY KEY, campaign TEXT NOT NULL, sample TEXT NOT NULL,
                started REAL NOT NULL, finished REAL, state TEXT NOT NULL,
                reserved INTEGER NOT NULL, charged INTEGER NOT NULL, metadata TEXT)''')
            db.execute('CREATE INDEX IF NOT EXISTS wires_started ON wires(started)')
            db.execute('CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, binding TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS scaling (id INTEGER PRIMARY KEY, policy TEXT NOT NULL, state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS scaling_events (id INTEGER PRIMARY KEY, time REAL NOT NULL, reason TEXT NOT NULL, state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS budget_amendments (id INTEGER PRIMARY KEY, time REAL NOT NULL, reason TEXT NOT NULL, previous TEXT NOT NULL, updated TEXT NOT NULL)')
            config = canonical({'budget': budget.model_dump(), 'transport': transport})
            old = db.execute('SELECT config FROM settings WHERE id=1').fetchone()
            if old and old['config'] != config:
                raise ValueError('shared ledger budget/transport is immutable; do not reset resource-window accounting')
            db.execute('INSERT OR IGNORE INTO settings(id,config) VALUES(1,?)', (config,))

    def bind_campaign(self, campaign: str, binding: str):
        with self.transaction() as db:
            row = db.execute('SELECT binding FROM campaigns WHERE id=?', (campaign,)).fetchone()
            if row and row['binding'] != binding:
                raise ValueError('campaign identity already bound to a different configuration or output')
            db.execute('INSERT OR IGNORE INTO campaigns VALUES(?,?)', (campaign, binding))

    def configure_scaling(self, initial: int, policy):
        with self.transaction() as db:
            encoded = canonical({'initial': initial, 'autoscale': policy.model_dump() if policy else None})
            row = db.execute('SELECT policy FROM scaling WHERE id=1').fetchone()
            if row:
                if row['policy'] != encoded:
                    raise ValueError('resource-window scaling policy is immutable')
                return
            now = time.time()
            state = {'current': initial, 'rate_factor': 1., 'cooldown_until': 0.,
                     'window_started': now, 'healthy_windows': 0, 'bad_windows': 0, 'baseline_p95_ms': None}
            db.execute('INSERT INTO scaling VALUES(1,?,?)', (encoded, canonical(state)))
            db.execute('INSERT INTO scaling_events(time,reason,state) VALUES(?,?,?)', (now, 'initial', canonical(state)))

    def tick_scaling(self, backlog: int):
        from .scaling import observe
        with self.transaction() as db:
            row = db.execute('SELECT * FROM scaling WHERE id=1').fetchone()
            state = json.loads(row['state'])
            policy = json.loads(row['policy'])['autoscale']
            stopped = db.execute('SELECT stopped FROM settings WHERE id=1').fetchone()[0]
            if policy and not stopped:
                rows = db.execute('SELECT * FROM wires WHERE finished>?', (state['window_started'],)).fetchall()
                wires = [{**dict(r), 'metadata': json.loads(r['metadata']) if r['metadata'] else None} for r in rows]
                state, reason = observe(state, policy, wires, time.time(), backlog)
                if reason:
                    db.execute('UPDATE scaling SET state=? WHERE id=1', (canonical(state),))
                    db.execute('INSERT INTO scaling_events(time,reason,state) VALUES(?,?,?)', (time.time(), reason, canonical(state)))
                    if reason == 'infrastructure_pause':
                        db.execute("UPDATE settings SET stopped='infrastructure_pause' WHERE id=1")
                        stopped = 'infrastructure_pause'
            return {**state, 'stopped': stopped}

    def amend_budget(self, budget: Budget, reason: str):
        # Explicit operator action. Never clears stops, charges or uncertain rows.
        if not reason.strip() or len(reason) > 500:
            raise ValueError('budget amendment reason required')
        with self.transaction() as db:
            row = db.execute('SELECT config FROM settings WHERE id=1').fetchone()
            old = json.loads(row['config'])
            new = {'transport': old['transport'], 'budget': budget.model_dump()}
            for key in ('token_limit', 'wire_limit', 'expires_at'):
                if new['budget'][key] < old['budget'][key]:
                    raise ValueError('amendments may only extend cumulative caps/expiry')
            if db.execute("SELECT COUNT(*) FROM wires WHERE state='inflight'").fetchone()[0]:
                raise ValueError('cannot amend budget with requests in flight')
            db.execute('INSERT INTO budget_amendments(time,reason,previous,updated) VALUES(?,?,?,?)',
                       (time.time(), reason, row['config'], canonical(new)))
            db.execute('UPDATE settings SET config=? WHERE id=1', (canonical(new),))

    def reopen_overload(self, *, concurrency: int, reason: str):
        """Explicit operator restart for a drained overload stop, retaining all costs.

        Other stops require their own diagnosis. Never retry historical samples.
        New campaigns must bind the new fixed-concurrency policy.
        """
        if not reason.strip() or len(reason) > 500:
            raise ValueError('restart reason required')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
            budget = json.loads(row['config'])['budget']
            if row['stopped'] != 'provider_overload':
                raise ValueError('only provider_overload may be reopened')
            if type(concurrency) is not int or not 1 <= concurrency <= min(4, budget['max_inflight']):
                raise ValueError('restart concurrency must be between one and four')
            if db.execute("SELECT COUNT(*) FROM wires WHERE state='inflight'").fetchone()[0]:
                raise ValueError('cannot reopen with requests in flight')
            now = time.time()
            if now >= budget['expires_at'] - budget['stop_buffer_seconds']:
                raise ValueError('resource window expired; explicit budget amendment required')
            for wire in db.execute('SELECT finished,metadata FROM wires WHERE metadata IS NOT NULL'):
                metadata = json.loads(wire['metadata'])
                if metadata.get('http_status') in (429, 529):
                    if now < (wire['finished'] or now) + max(60, metadata.get('retry_after_seconds') or 0):
                        raise ValueError('overload cooldown has not elapsed')
            control = db.execute('SELECT * FROM scaling WHERE id=1').fetchone()
            previous = dict(control) if control else None
            if control and json.loads(control['state']).get('capacity_campaign'):
                raise ValueError('capacity controller still owns the ledger')
            policy = canonical({'initial': concurrency, 'autoscale': None})
            state = {'current': concurrency, 'rate_factor': 1., 'cooldown_until': now,
                     'window_started': now, 'healthy_windows': 0, 'bad_windows': 0, 'baseline_p95_ms': None}
            db.execute('CREATE TABLE IF NOT EXISTS overload_restarts (id INTEGER PRIMARY KEY, time REAL NOT NULL, reason TEXT NOT NULL, previous TEXT NOT NULL, updated TEXT NOT NULL)')
            db.execute('INSERT INTO overload_restarts(time,reason,previous,updated) VALUES(?,?,?,?)',
                       (now, reason, canonical({'stopped': row['stopped'], 'control': previous}), canonical({'policy': policy, 'state': state})))
            db.execute('INSERT OR REPLACE INTO scaling VALUES(1,?,?)', (policy, canonical(state)))
            db.execute('INSERT INTO scaling_events(time,reason,state) VALUES(?,?,?)', (now, 'operator_overload_restart', canonical(state)))
            db.execute('UPDATE settings SET stopped=NULL WHERE id=1')

    def reserve(self, campaign: str, sample: str, tokens: int, sample_wire_limit: int = 1) -> str:
        with self.transaction() as db:
            now = time.time()
            if type(tokens) is not int or tokens <= 0:
                raise ValueError('positive reservation required')
            count = db.execute('SELECT COUNT(*) FROM wires WHERE campaign=? AND sample=?', (campaign, sample)).fetchone()[0]
            if count >= sample_wire_limit:
                raise GateClosed('sample_wire_budget')
            settings = db.execute('SELECT * FROM settings WHERE id=1').fetchone()
            budget = json.loads(settings['config'])['budget']
            if settings['stopped']:
                raise GateClosed(settings['stopped'])
            if now >= budget['expires_at'] - budget['stop_buffer_seconds']:
                raise GateClosed('expiry_buffer')
            totals = db.execute('SELECT COUNT(*) AS n, COALESCE(SUM(charged),0) AS tokens FROM wires').fetchone()
            if totals['n'] >= budget['wire_limit'] or totals['tokens'] + tokens > budget['token_limit']:
                raise GateClosed('resource_budget')
            control = db.execute('SELECT state FROM scaling WHERE id=1').fetchone()
            control = json.loads(control['state']) if control else None
            if control and control.get('capacity_campaign') not in (None, campaign):
                raise GateClosed('capacity_probe_exclusive')
            if control and now < control['cooldown_until']:
                raise WaitForCapacity('cooldown')
            factor = control['rate_factor'] if control else 1.
            # Sliding 60s window is deliberately more conservative than a bucket.
            recent = db.execute('SELECT COUNT(*) AS n, COALESCE(SUM(MAX(reserved,charged)),0) AS tokens FROM wires WHERE started>?', (now - 60,)).fetchone()
            active = db.execute("SELECT COUNT(*) FROM wires WHERE state='inflight'").fetchone()[0]
            if recent['n'] >= max(1, int(budget['rpm'] * factor)) or recent['tokens'] + tokens > min(budget['tpm'], max(tokens, int(budget['tpm'] * factor))) or active >= min(budget['max_inflight'], control['current'] if control else budget['max_inflight']):
                raise WaitForCapacity('rate_or_inflight')
            wire = uuid.uuid4().hex
            db.execute('INSERT INTO wires(id,campaign,sample,started,state,reserved,charged) VALUES(?,?,?,?,?,?,?)',
                       (wire, campaign, sample, now, 'inflight', tokens, tokens))
            return wire

    def finish(self, wire: str, metadata: dict, actual_tokens: int | None, *, uncertain=False, stop_reason=None):
        with self.transaction() as db:
            row = db.execute('SELECT * FROM wires WHERE id=?', (wire,)).fetchone()
            if row is None or row['state'] != 'inflight':
                raise ValueError('wire completion is fenced')
            charged = actual_tokens if actual_tokens is not None else row['reserved']
            db.execute('UPDATE wires SET finished=?,state=?,charged=?,metadata=? WHERE id=?',
                       (time.time(), 'uncertain' if uncertain else 'finished', charged, canonical(metadata), wire))
            if charged > row['reserved']:
                stop_reason = 'reservation_underestimated'
            if stop_reason == 'provider_overload':
                control = db.execute('SELECT * FROM scaling WHERE id=1').fetchone()
                policy = json.loads(control['policy'])['autoscale'] if control else None
                if policy:
                    state = json.loads(control['state'])
                    state['current'] = max(policy['min_concurrency'], state['current'] // 2)
                    state['rate_factor'] = max(.125, state['rate_factor'] / 2)
                    state['healthy_windows'] = 0
                    state['cooldown_until'] = max(state['cooldown_until'], time.time() + max(5, metadata.get('retry_after_seconds') or 0) + random.uniform(0, 1))
                    db.execute('UPDATE scaling SET state=? WHERE id=1', (canonical(state),))
                    db.execute('INSERT INTO scaling_events(time,reason,state) VALUES(?,?,?)', (time.time(), 'overload_down', canonical(state)))
                    stop_reason = None
            if stop_reason:
                db.execute('UPDATE settings SET stopped=? WHERE id=1', (stop_reason,))

    def recover(self, campaign: str, sample: str):
        with self.transaction() as db:
            return db.execute("UPDATE wires SET state='uncertain',finished=? WHERE campaign=? AND sample=? AND state='inflight'",
                              (time.time(), campaign, sample)).rowcount

    def snapshot(self, campaign: str | None = None):
        with self.transaction() as db:
            settings = db.execute('SELECT stopped FROM settings WHERE id=1').fetchone()
            rows = db.execute('SELECT * FROM wires' + (' WHERE campaign=?' if campaign else '') + ' ORDER BY started,id',
                              (campaign,) if campaign else ()).fetchall()
            has_scaling = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='scaling_events'").fetchone()
            events = [{'time': r['time'], 'reason': r['reason'], 'state': json.loads(r['state'])} for r in db.execute('SELECT * FROM scaling_events ORDER BY id')] if has_scaling else []
            return {'scaling_events': events, 'stopped': settings['stopped'], 'wire_count': len(rows),
                    'charged_or_reserved_tokens': sum(r['charged'] for r in rows),
                    'unknown_usage_requests': sum(not r['metadata'] or json.loads(r['metadata']).get('total_tokens') is None for r in rows),
                    'wires': [{**dict(r), 'metadata': json.loads(r['metadata']) if r['metadata'] else None} for r in rows]}
