"""Synthetic incremental compression diagnostic; no production Harness adoption.

Compare prose memory with typed source-linked state across three compressions.
Only decoded synthetic final answers and usage are retained, never reasoning.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport
from app.services.provider_payload import _extract_choice_content, _extract_json_payload


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Prose(Strict):
    memory: str = Field(min_length=1, max_length=450)


class Fact(Strict):
    value: str
    status: Literal['active', 'revoked', 'unknown']
    source_id: str


class State(Strict):
    meeting: Fact
    code: Fact
    preference: Fact


class Answer(Strict):
    meeting: str
    code: str
    code_status: Literal['active', 'revoked', 'unknown']
    address: str
    relationship: str


def segments(rep):
    updates = [
        f'[u1] 我叫阿岚。我们是平等同行，不是师生。以后只用中文。下次在桥南第{rep+4}号摊位碰头，暗号青纸船{rep+27}。',
        f'[u2] 地点改为北门第{rep+9}号长椅，旧地点作废。撤销暗号，不设新暗号。',
        f'[u3] 归档引用旧记录「桥南第{rep+4}号摊位，青纸船{rep+27}」，只作历史记录，不恢复。新地点照旧、暗号仍撤销。称呼改为林舟，不再叫阿岚；平等同行关系不变。',
    ]
    return [[{'role':'user','content':update}] + [
        {'role':'user','content':f'[maintenance-{stage}-{i}] '+('维修记录：检查伞骨铰链和连接点，记录磨损程度，无新增会面或称呼约定。'*12)}
        for i in range(15)] for stage,update in enumerate(updates)]


def run(output, repetitions):
    sdk=ProviderSDK.load(); key=os.environ['K3_API_KEY']; endpoint='https://api.minimax.cn/v1'
    adapter=ProviderRequestAdapter(api_key=key,base_url=endpoint,plan_api_key=key,plan_base_url=endpoint,
        setting_api_key=key,setting_base_url=endpoint,chat_api_key=key,chat_base_url=endpoint,
        timeout_seconds=90,completion=sdk.completion,responses=sdk.responses,embedding=sdk.embedding,
        providers=frozenset({'openai','anthropic','minimax'}),transport=ProviderTransport(timeout_seconds=90,sdk=sdk.error_types))
    revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    output.parent.mkdir(parents=True,exist_ok=True)

    def call(messages, contract):
        row={}; start=time.perf_counter(); decoded=None
        try:
            raw,_=adapter.request_chat_completion({'model':'MiniMax-M3','messages':messages,
                'temperature':0.2,'max_tokens':3072,'response_format':{'type':'json_object'}},request_kind='chat',model='MiniMax-M3')
            row.update(usage=raw.get('usage'),finish_reason=raw['choices'][0].get('finish_reason'))
            content=_extract_choice_content(raw)
            try:
                obj=json.loads(content); row['strict_json_valid']=True
            except (ValueError,TypeError):
                row['strict_json_valid']=False
                obj=_extract_json_payload(content)
            decoded=contract.model_validate(obj)
            row['contract_valid']=True;row['reply']=decoded.model_dump()
        except Exception as exc:
            row['error_class']=type(exc).__name__;row['contract_valid']=False
        row['elapsed_ms']=round((time.perf_counter()-start)*1000)
        return row,decoded

    with output.open('x') as stream:
        def save(row):
            row.update(git_revision=revision,scope='synthetic_incremental_compression',fixture_version='updates-revocation-address-v1',
                limitation='Direct provider diagnostic; no domain admission or production compression adoption.')
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
            print(json.dumps({k:row.get(k) for k in ['repetition','variant','stage','contract_valid','facts_correct']}),flush=True)
        for rep in range(repetitions):
            chunks=segments(rep); expected={'meeting':f'北门第{rep+9}号长椅','code':'未知','code_status':'revoked','address':'林舟','relationship':'平等同行'}
            question={'role':'user','content':'只输出JSON，meeting写当前碰头地点；code写有效暗号，没有有效暗号写未知；code_status区分active、revoked、unknown；address写当前称呼；relationship写双方关系。'}
            for variant in (['prose','state'] if rep%2==0 else ['state','prose']):
                memory=None
                for stage,chunk in enumerate(chunks):
                    contract=Prose if variant=='prose' else State
                    instruction=('保留最新有效地点、暗号撤销状态、称呼和语言关系偏好。归档引用不恢复旧约定。只输出JSON，不加围栏，字符串引用使用「」。'+
                        ('键memory，450字以内。' if variant=='prose' else '键meeting、code、preference，各有value、status(active/revoked/unknown)、source_id。source_id引用输入u1/u2/u3；撤销仍保留来源，preference包含当前称呼、语言和关系。'))
                    context=([{'role':'user','content':'此前记忆：'+json.dumps(memory,ensure_ascii=False)}] if memory else [])+chunk
                    row,result=call([{'role':'system','content':instruction}]+context,contract)
                    row.update(repetition=rep,variant=variant,stage=stage);save(row)
                    if result is None:break
                    memory=result.model_dump()
                else:
                    row,_=call([{'role':'system','content':'依据提供资料回答，不推测缺失约定。'} ,{'role':'user','content':json.dumps(memory,ensure_ascii=False)},question],Answer)
                    row.update(repetition=rep,variant=variant,stage='answer',expected=expected,facts_correct=row.get('reply')==expected);save(row)
            row,_=call([{'role':'system','content':'依据提供资料回答，不推测缺失约定。'}]+[m for c in chunks for m in c]+[question],Answer)
            row.update(repetition=rep,variant='full_history',stage='answer',expected=expected,facts_correct=row.get('reply')==expected);save(row)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--repetitions',type=int,default=2)
    args=p.parse_args()
    if not 1<=args.repetitions<=10:p.error('repetitions must be 1..10')
    run(args.output.resolve(),args.repetitions)
