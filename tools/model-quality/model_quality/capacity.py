"""Opt-in sustained native capacity probe. Use only a documented thread-safe adapter.

Unlike domain campaigns this tests read-only HTTP/proposal capacity, with no
monkeypatches or domain database writes. It does not assert a supplier hard limit.
"""
from __future__ import annotations

import argparse
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import json
import importlib
import math
import os
from pathlib import Path
import time

from .adapters import Context
from .ledger import GateClosed, Ledger
from .protocol import AdapterResult, Campaign, canonical, digest
from .runner import adapter_function, atomic_json, exclusive, source_state
from .transport import MeteredTransport


def summarize(wires, started, finished):
    events=[]
    latencies=[]
    for w in wires:
        events.append((w['started'],1))
        events.append((w['finished'] or finished,-1))
        meta=w['metadata'] or {}
        if meta.get('elapsed_ms') is not None:
            latencies.append(meta['elapsed_ms'])
    active=peak=0
    for _,change in sorted(events):
        active+=change
        peak=max(peak,active)
    latencies.sort()
    elapsed=max(.001,finished-started)
    statuses={}
    for w in wires:
        key=str((w['metadata'] or {}).get('http_status'))
        statuses[key]=statuses.get(key,0)+1
    errors=sum(w['state']=='uncertain' or (w['metadata'] or {}).get('http_status')!=200 for w in wires)
    return {'requests':len(wires),'elapsed_seconds':elapsed,'observed_peak_inflight':peak,
            'requests_per_second':len(wires)/elapsed, 'http_statuses':statuses,
            'infrastructure_error_rate': errors/len(wires) if wires else None,
            'p50_ms':latencies[math.ceil(len(latencies)*.50)-1] if latencies else None,
            'p95_ms':latencies[math.ceil(len(latencies)*.95)-1] if latencies else None,
            'charged_or_reserved_tokens':sum(w['charged'] for w in wires),
            'unknown_usage_requests':sum((w['metadata'] or {}).get('total_tokens') is None for w in wires)}


def select_stage(ledger, campaign, concurrency, reason):
    with ledger.transaction() as db:
        settings=db.execute('SELECT * FROM settings WHERE id=1').fetchone()
        budget=json.loads(settings['config'])['budget']
        if settings['stopped']:
            raise GateClosed(settings['stopped'])
        if concurrency>budget['max_inflight']:
            raise ValueError('stage exceeds global cap')
        if db.execute("SELECT COUNT(*) FROM wires WHERE state='inflight'").fetchone()[0]:
            raise ValueError('stage transition requires drained wires')
        previous=db.execute('SELECT policy,state FROM scaling WHERE id=1').fetchone()
        if previous and json.loads(previous['state'])['cooldown_until']>time.time():
            raise GateClosed('cooldown')
        state={'current':concurrency,'rate_factor':1.,'cooldown_until':0.,'window_started':time.time(),
               'healthy_windows':0,'bad_windows':0,'baseline_p95_ms':None,'capacity_campaign':campaign}
        policy=canonical({'initial':concurrency,'autoscale':None})
        db.execute('INSERT OR REPLACE INTO scaling VALUES(1,?,?)',(policy,canonical(state)))
        db.execute('INSERT INTO scaling_events(time,reason,state) VALUES(?,?,?)',(time.time(),reason,canonical(state)))
        return dict(previous) if previous else None


def restore_control(ledger, previous):
    with ledger.transaction() as db:
        if db.execute("SELECT COUNT(*) FROM wires WHERE state='inflight'").fetchone()[0]:
            raise ValueError('cannot restore with unsettled wires')
        if previous:
            db.execute('UPDATE scaling SET policy=?,state=? WHERE id=1',(previous['policy'],previous['state']))
            db.execute('INSERT INTO scaling_events(time,reason,state) VALUES(?,?,?)',(time.time(),'capacity_restore',previous['state']))
        else:
            db.execute('DELETE FROM scaling WHERE id=1')
        # Never clear authentication/overload stops or unknown reservations.


def run_window(c,ledger,output,level,index,seconds,min_completed,max_seconds):
    started=time.time()
    sequence=0
    results=[]
    adapter=adapter_function(c.adapter)
    prefix=f'c{level}-w{index}-'
    def sample(number):
        sid=prefix+str(number)
        context=Context(MeteredTransport(c,ledger,sid,time.monotonic()+c.sample_deadline_seconds),output,output/'unused.sqlite3')
        try:
            result=AdapterResult.model_validate(adapter(context,c.cases[0],c.variants[0])).model_dump()
            return {'id':sid,'status':result['status']}
        except Exception as exc:
            return {'id':sid,'status':'failed','error_class':type(exc).__name__}
        finally:
            ledger.recover(c.id,sid)
    last_print=started
    with ThreadPoolExecutor(max_workers=level) as pool:
        active={}
        stop_dispatch=False
        while active or not stop_dispatch:
            snapshot=ledger.snapshot(c.id)
            elapsed=time.time()-started
            if snapshot['stopped'] or elapsed>=max_seconds or elapsed>=seconds and len(results)>=min_completed:
                stop_dispatch=True
            while not stop_dispatch and len(active)<level:
                future=pool.submit(sample,sequence)
                active[future]=sequence
                sequence+=1
            if not active:
                break
            done,_=wait(active,timeout=.25,return_when=FIRST_COMPLETED)
            for future in done:
                results.append(future.result())
                del active[future]
            # Budget/deadline stops produce no wire; do not busy-loop new work.
            if done and any(r.get('error_class')=='GateClosed' for r in results[-len(done):]):
                stop_dispatch=True
            if time.time()-last_print>=15:
                print(canonical({'level':level,'window':index,'completed_samples':len(results),'seconds':round(time.time()-started,1)}),flush=True)
                last_print=time.time()
    finished=time.time()
    wires=[w for w in ledger.snapshot(c.id)['wires'] if w['sample'].startswith(prefix)]
    summary=summarize(wires,started,finished)
    summary.update(level=level,window=index,offered_seconds=seconds,dispatch_seconds=min(finished-started,elapsed),
                   completed_samples=len(results),proposal_successes=sum(r['status']=='completed' for r in results),
                   window_qualified=(finished-started)>=seconds and len(wires)>=min_completed and summary['observed_peak_inflight']>=level)
    atomic_json(output/f'{prefix}result.json',{'summary':summary,'samples':results,'wires':wires})
    print(canonical({'window_result':summary}),flush=True)
    return summary


def run_probe(c, output, ledger_path, levels, seconds=60., windows=2, minimum=30, max_window=180.):
    module=importlib.import_module(c.adapter.split(':')[0])
    if getattr(module,'CAPACITY_SAFE',False) is not True:
        raise ValueError('adapter must explicitly declare thread-safe read-only capacity support')
    if c.autoscale is not None or c.sample_wire_limit!=1:
        raise ValueError('capacity probe requires fixed stages and one wire per sample')
    if c.transport=='minimax' and (seconds<60 or windows<2 or minimum<30):
        raise ValueError('live capacity windows require 60 seconds, 30 completions, two windows')
    output=output.resolve(); ledger_path=ledger_path.resolve()
    output.mkdir(parents=True,exist_ok=False)
    ledger=Ledger(ledger_path)
    ledger.initialize(c.budget,c.transport)
    protocol={'config':c.model_dump(),'levels':levels,'window_seconds':seconds,'windows_per_stage':windows,
              'min_completed':minimum,'max_window_seconds':max_window,'source':source_state(c.adapter),
              'scope':'Thread-safe read-only proposal/native HTTP capacity; no domain commit or independent quality score.'}
    atomic_json(output/'manifest.json',protocol)
    ledger.bind_campaign(c.id,digest(protocol))
    all_windows=[]
    baseline=None
    last_stable=None
    reason='all_requested_levels_tested_hard_limit_unknown'
    with exclusive(ledger_path.with_suffix('.capacity.lock')):
        previous=select_stage(ledger,c.id,levels[0],'capacity_begin')
        atomic_json(output/'previous-control.json',previous)
        try:
            for level in levels:
                select_stage(ledger,c.id,level,'capacity_level_'+str(level))
                stage=[]
                for index in range(windows):
                    result=run_window(c,ledger,output,level,index,seconds,minimum,max_window)
                    stage.append(result); all_windows.append(result)
                    if ledger.snapshot()['stopped']:
                        reason='provider_stop'; break
                if reason=='provider_stop':
                    break
                if not all(w['window_qualified'] and w['infrastructure_error_rate']==0 and w['unknown_usage_requests']==0 for w in stage):
                    reason='window_or_infrastructure_limit'; break
                stage_p95=max(w['p95_ms'] for w in stage)
                if baseline is None:
                    baseline=stage_p95
                elif stage_p95>baseline*1.25:
                    reason='p95_regression_over_1_25x'; break
                last_stable=level
        except BaseException:
            reason='interrupted_or_runner_failure'
            raise
        finally:
            restore_control(ledger,previous)
            usage=ledger.snapshot(c.id)
            atomic_json(output/'report.json',{'campaign':c.id,'windows':all_windows,'last_stable_level':last_stable,
                'stop_reason':reason,'baseline_p95_ms':baseline,'provider_hard_limit':None,
                'usage':usage,'resource_window':{k:v for k,v in ledger.snapshot().items() if k!='wires'}})
    return all_windows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--levels',default='4,8,16,32,64')
    args=parser.parse_args()
    c=Campaign.model_validate_json(args.manifest.read_text())
    levels=[int(v) for v in args.levels.split(',')]
    if not levels or levels!=sorted(set(levels)) or min(levels)<1 or max(levels)>64:
        parser.error('levels must be increasing unique values in 1..64')
    run_probe(c,args.output,args.ledger,levels)


if __name__=='__main__':
    main()
