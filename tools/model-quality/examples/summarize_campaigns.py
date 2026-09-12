"""Read-only post-hoc audit of synthetic memory experiments; no model grader."""
import argparse
from collections import Counter
import difflib
import json
import math
from pathlib import Path


def percentile(values, q):
    return sorted(values)[max(0,math.ceil(len(values)*q)-1)] if values else None


def analyze(root):
    manifest=json.loads((root/'manifest.json').read_text())
    report=json.loads((root/'report.json').read_text())
    cases={case['id']:case for case in manifest['config']['cases']}
    wires=report['campaign_usage']['wires']
    variants={}
    audit=[]
    for sample in report['samples']:
        name=sample['variant']
        group=variants.setdefault(name,{'states':Counter(),'metrics_passed':Counter(),'tool_error_codes':Counter(),
            'wire_count':0,'tokens':0,'wire_ms':[],'sample_seconds':[], 'successful_memory_writes':0,'successful_memory_reads':0})
        group['states'][sample['state']]+=1
        group['sample_seconds'].append(sample['elapsed_seconds'])
        group['metrics_passed'].update(k for k,v in (sample.get('result') or {}).get('metrics',{}).items() if v is True)
        for wire in wires:
            if wire['sample']==sample['sample_id']:
                group['wire_count']+=1;group['tokens']+=wire['charged']
                if (wire['metadata'] or {}).get('elapsed_ms') is not None:group['wire_ms'].append(wire['metadata']['elapsed_ms'])
        evidence=root/sample['case']/name/str(sample['repetition'])/'storage/domain-evidence.json'
        item={k:sample[k] for k in ('case','variant','repetition','state','sample_id')}
        if evidence.exists():
            e=json.loads(evidence.read_text()); session=((e.get('receipt') or {}).get('result') or {}).get('session') or {}
            memory=[m for m in session.get('session_memory',[]) if m['key']=='experiment_reference']
            exact=len(memory)==1 and memory[0]['content']==cases[sample['case']]['gold']
            item['memory_exact_recomputed']=exact
            item['agrees_with_adapter_memory_metric']=exact==e['metrics']['memory_exact']
            item['receipt_error_code']=(e.get('receipt') or {}).get('error_code')
            outcomes=[]
            for turn in session.get('turns',[]):
                for tool in turn.get('tool_calls',[]):
                    result=json.loads(tool['result_json'])
                    outcomes.append({'name':tool['tool_name'],'ok':result.get('ok'), 'error':result.get('error')})
                    if result.get('error'):group['tool_error_codes'][result['error']]+=1
            item['tool_outcomes']=outcomes
            group['successful_memory_writes']+=any(t['name']=='write_session_memory' and t['ok'] is True for t in outcomes)
            group['successful_memory_reads']+=any(t['name']=='read_session_memory' and t['ok'] is True for t in outcomes)
            if len(memory)==1 and not exact:
                expected,actual=cases[sample['case']]['gold'],memory[0]['content']
                item['character_differences']=[{'operation':tag,'expected':expected[a:b],'actual':actual[c:d]}
                    for tag,a,b,c,d in difflib.SequenceMatcher(a=expected,b=actual,autojunk=False).get_opcodes() if tag!='equal']
        audit.append(item)
    for group in variants.values():
        group['wire_p50_ms']=percentile(group['wire_ms'],.5);group['wire_p95_ms']=percentile(group.pop('wire_ms'),.95)
        group['sample_p50_seconds']=percentile(group['sample_seconds'],.5);group['sample_p95_seconds']=percentile(group.pop('sample_seconds'),.95)
    events=[]
    for wire in wires:
        events.extend([(wire['started'],1),(wire['finished'] or wire['started'],-1)])
    active=peak=0
    for _,delta in sorted(events):active+=delta;peak=max(peak,active)
    return {'campaign':report['campaign'],'config':manifest['config'],'states':report['states'],
        'variants':variants,'observed_peak_wire_inflight':peak,'wire_count':len(wires),
        'http_statuses':dict(Counter(str((w['metadata'] or {}).get('http_status')) for w in wires)),
        'tokens_charged_or_reserved':sum(w['charged'] for w in wires),
        'unknown_usage_requests':report['campaign_usage']['unknown_usage_requests'],
        'raw_tool_shapes':dict(Counter(json.dumps(shape,sort_keys=True) for w in wires for shape in (w['metadata'] or {}).get('tool_call_shapes',[]))),
        'sample_audit':audit,
        'scope':'Post-hoc deterministic regrade from persisted public receipts, not independent human or held-out model quality certification. Historical executed-tool metric means observed call; use successful_memory_reads/writes here.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-dir',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result={'version':'m3-memory-parallel-audit-v1','campaigns':[analyze(root) for root in args.campaign_dir]}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(args.output.resolve())


if __name__=='__main__':
    main()
