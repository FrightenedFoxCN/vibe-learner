"""Read-only lane aggregation. Semantic review remains separate from JSON exactness."""
import argparse
from collections import Counter,defaultdict
import json
import math
from pathlib import Path


def percentile(values,q):
    return sorted(values)[max(0,math.ceil(len(values)*q)-1)] if values else None


def summarize(root):
    manifest=json.loads((root/'manifest.json').read_text());r=json.loads((root/'report.json').read_text())
    cases={case['id']:case for case in manifest['config']['cases']}
    wire_by_sample=defaultdict(list)
    for wire in r['campaign_usage']['wires']:wire_by_sample[wire['sample']].append(wire)
    groups={};audit=[];paired={}
    for sample in r['samples']:
        case=cases[sample['case']];lane=case['lane'];variant=sample['variant'];key=lane+'/'+variant
        g=groups.setdefault(key,{'samples':0,'states':Counter(),'metric_passes':Counter(),'metric_observed':Counter(),
            'wire_count':0,'tokens':0,'call_kinds':Counter(),'http_statuses':Counter(),'tool_errors':Counter(),
            'receipt_errors':Counter(),'wire_ms':[],'sample_seconds':[],'seed_operations':0,'seed_commits':0})
        g['samples']+=1;g['states'][sample['state']]+=1
        metrics=(sample.get('result') or {}).get('metrics',{})
        g['metric_passes'].update(k for k,v in metrics.items() if v is True)
        g['metric_observed'].update(metrics.keys())
        g['sample_seconds'].append(sample['elapsed_seconds'])
        wires=wire_by_sample[sample['sample_id']]
        for wire in wires:
            metadata=wire['metadata'] or {};g['wire_count']+=1;g['tokens']+=wire['charged']
            g['call_kinds'][metadata.get('call_kind','unknown')]+=1;g['http_statuses'][str(metadata.get('http_status'))]+=1
            if metadata.get('elapsed_ms') is not None:g['wire_ms'].append(metadata['elapsed_ms'])
        item={k:sample[k] for k in ('case','variant','repetition','state','sample_id')};item['lane']=lane;item['metrics']=metrics
        evidence=root/sample['case']/variant/str(sample['repetition'])/'storage/domain-evidence.json'
        if evidence.exists():
            e=json.loads(evidence.read_text())
            operations=e.get('operations',[])
            if lane in ('verbatim','summary'):operations=[{'receipt':e.get('receipt',{})}]
            if lane=='temporal':
                g['seed_operations']+=min(len(operations),len(json.loads(case['source'])['records']))
                g['seed_commits']+=sum(op['receipt']['status']=='committed' for op in operations[:len(json.loads(case['source'])['records'])])
            for operation in operations:
                receipt=operation['receipt']
                if receipt.get('error_code'):g['receipt_errors'][receipt['error_code']]+=1
                session=(receipt.get('result') or {}).get('session') or {}
                for turn in session.get('turns',[]):
                    for tool in turn.get('tool_calls',[]):
                        result=json.loads(tool['result_json'])
                        if result.get('error'):g['tool_errors'][result['error']]+=1
            if operations:
                final_receipt=operations[-1]['receipt'];session=(final_receipt.get('result') or {}).get('session') or {}
                turn=(session.get('turns') or [{}])[-1]
                item.update(reply=turn.get('assistant_reply'),citations=turn.get('citations',[]),
                            receipt_error=final_receipt.get('error_code'),decoded_answer=e.get('decoded_answer'))
                if lane in ('verbatim','summary'):
                    memory=[m for m in session.get('session_memory',[]) if m['key']=='experiment_reference']
                    item['final_memory_content']=memory[0]['content'] if len(memory)==1 else None
                    item['memory_effect_count']=len(e.get('memory_effects',[]))
                    if lane=='verbatim':
                        item['character_exact_recomputed']=len(memory)==1 and memory[0]['content']==case['gold']
                        item['agrees_with_adapter_memory_metric']=item['character_exact_recomputed']==metrics.get('memory_exact')
                if lane=='temporal':
                    item['retrieval']=e.get('retrieval',[])
        audit.append(item)
        paired.setdefault(sample['case'],{})[variant]={'state':sample['state'],'metrics':metrics}
    for g in groups.values():
        g['wire_p50_ms']=percentile(g['wire_ms'],.5);g['wire_p95_ms']=percentile(g.pop('wire_ms'),.95)
        g['sample_p50_seconds']=percentile(g['sample_seconds'],.5);g['sample_p95_seconds']=percentile(g.pop('sample_seconds'),.95)
    pairs={}
    for name,arms in paired.items():
        other=[name for name in arms if name!='baseline']
        if len(other)!=1:raise ValueError('expected one paired contrast')
        baseline=arms['baseline']['state']=='completed';candidate=arms[other[0]]['state']=='completed'
        lane=cases[name]['lane'];p=pairs.setdefault(lane,Counter())
        p['both_pass' if baseline and candidate else 'baseline_only' if baseline else 'candidate_only' if candidate else 'neither_pass']+=1
    events=[]
    for wire in r['campaign_usage']['wires']:events.extend([(wire['started'],1),(wire['finished'] or wire['started'],-1)])
    active=peak=0
    for _,delta in sorted(events):active+=delta;peak=max(peak,active)
    return {'version':'priority-lane-audit-v1','campaign':r['campaign'],'config':manifest['config'],
        'states':r['states'],'groups':groups,'paired_joint_outcomes':pairs,'observed_peak_wire_inflight':peak,
        'wire_count':r['campaign_usage']['wire_count'],'tokens_charged_or_reserved':r['campaign_usage']['charged_or_reserved_tokens'],
        'unknown_usage_requests':r['campaign_usage']['unknown_usage_requests'],'sample_audit':audit,
        'scope':'Development experiments. JSON exactness is requested-format-plus-facts; narrative semantics requires separate review. No independent holdout, no release certification.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.write_text(json.dumps(summarize(args.campaign_dir),ensure_ascii=False,indent=2)+'\n')
    print(args.output.resolve())


if __name__=='__main__':main()
