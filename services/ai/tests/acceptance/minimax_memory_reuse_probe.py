"""Reuse one previously generated memory; compare against the matching full history.

Direct provider diagnostic only. Does not regenerate memory or claim production
adoption. Cache counts are reported values, not monetary billing estimates.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport
from app.services.provider_payload import _extract_choice_content, _extract_json_payload
from tests.acceptance.minimax_incremental_memory_probe import StatusAnswer, segments


def run(source, output, queries):
    rows=[json.loads(line) for line in source.read_text().splitlines()]
    selected=[r for r in rows if r['repetition']==0 and r['variant']=='state' and isinstance(r['stage'],int)]
    if [r['stage'] for r in selected]!=[0,1,2,3] or not all(r['contract_valid'] for r in selected):
        raise ValueError('Requires a complete successful four-stage renewal state chain')
    memory=selected[-1]['reply']
    sdk=ProviderSDK.load();key=os.environ['K3_API_KEY'];url='https://api.minimax.cn/v1'
    adapter=ProviderRequestAdapter(api_key=key,base_url=url,plan_api_key=key,plan_base_url=url,
        setting_api_key=key,setting_base_url=url,chat_api_key=key,chat_base_url=url,
        timeout_seconds=90,completion=sdk.completion,responses=sdk.responses,embedding=sdk.embedding,
        providers=frozenset({'openai','anthropic','minimax'}),transport=ProviderTransport(timeout_seconds=90,sdk=sdk.error_types))
    system={'role':'system','content':'依据提供资料回答，不推测缺失约定。严格输出JSON，不加围栏。输出schema：'+json.dumps(StatusAnswer.model_json_schema(),ensure_ascii=False)}
    prompts=['现在的有效约定是什么？','旧暗号归档后，我们当前按什么约定行动？','最后一次更新后，帮我核对目前有效的信息。']
    suffix='只返回JSON：meeting写当前碰头地点；code写当前有效暗号，没有有效暗号写未知；code_status按schema区分状态；address写当前对用户的称呼，不是地点；relationship写双方关系。'
    expected={'meeting':'北门第9号长椅','code':'红风筝51','code_status':'active','address':'林舟'}
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x') as stream:
        stream.write(json.dumps({'scope':'synthetic_memory_reuse_setup','source_file':source.name,
            'source_repetition':0,'source_variant':'state','summary_calls':len(selected),
            'summary_usage':[r.get('usage') for r in selected],
            'summary_elapsed_ms':sum(r['elapsed_ms'] for r in selected)},ensure_ascii=False)+'\n');stream.flush()
        for i in range(queries):
            for variant in (['full','memory'] if i%2==0 else ['memory','full']):
                context=[m for chunk in segments(0,True) for m in chunk] if variant=='full' else [{'role':'user','content':json.dumps(memory,ensure_ascii=False)}]
                row={'scope':'synthetic_memory_reuse','git_revision':revision,'query_index':i,'variant':variant,'field_mapping':'explicit-domain-meanings-v2',
                    'limitation':'Same synthetic source; direct provider requests, no domain admission or production adoption.'}
                start=time.perf_counter()
                try:
                    raw,_=adapter.request_chat_completion({'model':'MiniMax-M3','messages':[system]+context+[{'role':'user','content':prompts[i%len(prompts)]+suffix}],
                        'temperature':0.2,'max_tokens':3072,'response_format':{'type':'json_object'}},request_kind='chat',model='MiniMax-M3')
                    row.update(usage=raw.get('usage'),finish_reason=raw['choices'][0].get('finish_reason'))
                    content=_extract_choice_content(raw)
                    try:obj=json.loads(content);row['strict_json_valid']=True
                    except (ValueError,TypeError):obj=_extract_json_payload(content);row['strict_json_valid']=False
                    reply=StatusAnswer.model_validate(obj).model_dump();row['reply']=reply
                    checks={k:reply[k]==v for k,v in expected.items()}
                    checks['relationship']=reply['relationship'] in ['平等同行','平等同行关系','平等同行，非师生','平等同行（非师生）']
                    row.update(field_checks=checks,semantic_pass=all(checks.values()))
                except Exception as exc:row['error_class']=type(exc).__name__
                row['elapsed_ms']=round((time.perf_counter()-start)*1000)
                stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
                print(json.dumps({k:row.get(k) for k in ['variant','query_index','semantic_pass','elapsed_ms']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--queries',type=int,default=6)
    args=p.parse_args()
    if not 1<=args.queries<=12:p.error('queries must be 1..12')
    run(args.source.resolve(),args.output.resolve(),args.queries)
