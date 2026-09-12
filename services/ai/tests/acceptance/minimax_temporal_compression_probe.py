"""Synthetic date-binding compression comparison; not a domain Harness eval.

Preserves decoded synthetic outputs and usage only, never provider reasoning.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from pydantic import BaseModel, ConfigDict, Field

from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport
from app.services.provider_payload import _extract_choice_content


class Memory(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    memory: str = Field(min_length=1, max_length=450)


class Dates(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    current_meeting_at: str
    rescheduled_at: str
    original_meeting_at: str
    archived_at: str
    second_person_meeting_at: str


BASE = '将对话压缩为450字以内的记忆，保留后续回答所需的人物、事件、关系与最新有效约定；引用旧记录不恢复旧约定。'
PRESERVE = '逐项保留日期和时刻，并绑定到对应人物及事件，区分消息发生时间、约定的见面时间、改约时间和归档时间。'


def fixture():
    events = [
        '[2026-03-01 09:00] 林舟：我与阿岚约在2026-03-08 14:30于北门长椅见面。',
        '[2026-03-04 18:15] 林舟：我与阿岚的见面改到2026-03-10 16:00，地点不变；3月8日的约定取消。',
        '[2026-03-05 11:20] 阿岚：另与小夏约在2026-03-09 10:00于南门见面，与林舟的约定无关。',
        '[2026-03-06 20:45] 林舟：归档旧记录“2026-03-08 14:30北门长椅”，只留历史，不恢复旧约；3月10日的新约不变。',
    ]
    messages = []
    for stage, event in enumerate(events):
        messages.append({'role': 'user', 'content': event})
        messages.extend({'role': 'user', 'content': f'[work-{stage}-{i}] ' +
                         '检查桌椅连接部件并记录磨损；此条没有新增或变更任何见面安排。' * 10}
                        for i in range(12))
    return messages


EXPECTED = {'current_meeting_at': '2026-03-10 16:00', 'rescheduled_at': '2026-03-04 18:15',
            'original_meeting_at': '2026-03-08 14:30', 'archived_at': '2026-03-06 20:45',
            'second_person_meeting_at': '2026-03-09 10:00'}
QUESTION = ('current_meeting_at写林舟与阿岚当前约定的见面时间；rescheduled_at写提出改约的消息时间；'
            'original_meeting_at写两人取消的原见面时间；archived_at写归档旧约的消息时间；'
            'second_person_meeting_at写阿岚与小夏的见面时间。格式统一YYYY-MM-DD HH:MM，缺失写未知，不猜测。')


def run(output):
    sdk = ProviderSDK.load()
    key = os.environ['K3_API_KEY']
    endpoint = 'https://api.minimax.cn/v1'
    adapter = ProviderRequestAdapter(api_key=key, base_url=endpoint, plan_api_key=key,
        plan_base_url=endpoint, setting_api_key=key, setting_base_url=endpoint,
        chat_api_key=key, chat_base_url=endpoint, timeout_seconds=90,
        completion=sdk.completion, responses=sdk.responses, embedding=sdk.embedding,
        providers=frozenset({'openai', 'anthropic', 'minimax'}),
        transport=ProviderTransport(timeout_seconds=90, sdk=sdk.error_types))
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    output.parent.mkdir(parents=True, exist_ok=True)
    history = fixture()
    with output.open('x') as stream:
        def call(messages, contract, variant, repetition, stage):
            instruction = '只输出符合以下schema的JSON对象，不要Markdown围栏：' + json.dumps(contract.model_json_schema(), ensure_ascii=False)
            row = {'scope': 'synthetic_temporal_compression', 'git_revision': revision,
                   'variant': variant, 'repetition': repetition, 'stage': stage,
                   'limitation': 'One synthetic fixture, direct provider calls; not independent certification or production compression.'}
            start = time.perf_counter()
            decoded = None
            try:
                raw, _ = adapter.request_chat_completion({'model': 'MiniMax-M3',
                    'messages': [{'role': 'system', 'content': instruction}] + messages,
                    'temperature': 0.2, 'max_tokens': 2048, 'response_format': {'type': 'json_object'}},
                    request_kind='chat', model='MiniMax-M3')
                row['usage'] = raw.get('usage')
                row['finish_reason'] = raw['choices'][0].get('finish_reason')
                obj = json.loads(_extract_choice_content(raw))
                row['strict_json_valid'] = True
                decoded = contract.model_validate(obj)
                row['reply'] = decoded.model_dump()
                row['contract_valid'] = True
                if contract is Dates:
                    row['fields_correct'] = {k: row['reply'][k] == v for k, v in EXPECTED.items()}
            except Exception as exc:
                row['error_class'] = type(exc).__name__
                row['contract_valid'] = False
            row['elapsed_ms'] = round((time.perf_counter() - start) * 1000)
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({k: row.get(k) for k in ('variant', 'repetition', 'stage', 'contract_valid', 'fields_correct')}), flush=True)
            return decoded

        for repetition in range(2):
            order = ('baseline', 'preserve_dates') if repetition == 0 else ('preserve_dates', 'baseline')
            for variant in order:
                summary = call([{'role': 'system', 'content': BASE + (PRESERVE if variant == 'preserve_dates' else '')}] + history,
                               Memory, variant, repetition, 'compress')
                if summary is not None:
                    call([{'role': 'user', 'content': summary.memory}, {'role': 'user', 'content': QUESTION}],
                         Dates, variant, repetition, 'answer')
            call(history + [{'role': 'user', 'content': QUESTION}], Dates, 'full_history', repetition, 'answer')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output.resolve())
