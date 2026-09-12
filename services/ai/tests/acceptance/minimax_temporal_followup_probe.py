"""Reuse temporal summaries for an additional cancellation-versus-archive query."""
import argparse
import json
import os
from pathlib import Path
import time

from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport
from app.services.provider_payload import _extract_choice_content
from tests.acceptance.minimax_temporal_compression_probe import fixture


def run(source, output):
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    sdk = ProviderSDK.load()
    key = os.environ['K3_API_KEY']
    endpoint = 'https://api.minimax.cn/v1'
    adapter = ProviderRequestAdapter(api_key=key, base_url=endpoint, plan_api_key=key,
        plan_base_url=endpoint, setting_api_key=key, setting_base_url=endpoint,
        chat_api_key=key, chat_base_url=endpoint, timeout_seconds=90,
        completion=sdk.completion, responses=sdk.responses, embedding=sdk.embedding,
        providers=frozenset({'openai', 'anthropic', 'minimax'}),
        transport=ProviderTransport(timeout_seconds=90, sdk=sdk.error_types))
    question = ('林舟与阿岚原定3月8日的见面，究竟在哪条消息的时刻已被取消？'
                '取消与归档是同一个事件吗？仅依据资料，缺失写未知。只输出JSON对象，'
                'cancelled_at和archived_at均为YYYY-MM-DD HH:MM字符串，same_event为布尔值；'
                '时间缺失写未知，无法确定是否同一事件时same_event写null。不要Markdown围栏或解释。')
    inputs = [(r['repetition'], r['variant'], [{'role': 'user', 'content': r['reply']['memory']}])
              for r in rows if r['stage'] == 'compress' and r.get('contract_valid')]
    # Interleave full-history references; summaries are reused without regeneration.
    inputs.insert(2, (0, 'full_history', fixture()))
    inputs.append((1, 'full_history', fixture()))
    with output.open('x') as stream:
        for repetition, variant, context in inputs:
            row = {'scope': 'synthetic_temporal_followup', 'source_report': source.name,
                   'repetition': repetition, 'variant': variant, 'max_tokens': 4096,
                   'limitation': 'Post hoc query prompted by manual summary review; not a held-out preregistered benchmark.'}
            start = time.perf_counter()
            try:
                raw, _ = adapter.request_chat_completion({'model': 'MiniMax-M3',
                    'messages': [{'role': 'system', 'content': question}] + context,
                    'temperature': 0.2, 'max_tokens': 4096, 'response_format': {'type': 'json_object'}},
                    request_kind='chat', model='MiniMax-M3')
                row['usage'] = raw.get('usage')
                row['finish_reason'] = raw['choices'][0].get('finish_reason')
                reply = json.loads(_extract_choice_content(raw))
                valid = (isinstance(reply, dict) and set(reply) == {'cancelled_at', 'archived_at', 'same_event'}
                         and isinstance(reply['cancelled_at'], str) and isinstance(reply['archived_at'], str)
                         and (reply['same_event'] is None or type(reply['same_event']) is bool))
                row['contract_valid'] = valid
                if valid:
                    row['reply'] = reply
                    row['fields_correct'] = {'cancelled_at': reply['cancelled_at'] == '2026-03-04 18:15',
                        'archived_at': reply['archived_at'] == '2026-03-06 20:45', 'same_event': reply['same_event'] is False}
            except Exception as exc:
                row['error_class'] = type(exc).__name__
                row['contract_valid'] = False
            row['elapsed_ms'] = round((time.perf_counter() - start) * 1000)
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({k: row.get(k) for k in ('variant', 'repetition', 'contract_valid', 'fields_correct')}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source.resolve(), args.output.resolve())
