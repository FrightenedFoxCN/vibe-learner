"""Compare date preservation with distinct event/record time preservation.

Two synthetic fixtures, including French delayed reporting and an undated event.
No domain admission, model reasoning retention, or production compression.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

from pydantic import BaseModel, ConfigDict, ValidationError

from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport
from app.services.provider_payload import _extract_choice_content
from tests.acceptance.minimax_temporal_compression_probe import BASE, PRESERVE, Memory, fixture


SEPARATE = ('不要将取消、改约、归档或转述合并为一个事件。每个事件分别保留对应人物、'
            '事件发生时刻与记录该事件的消息时刻；只有一项时间有依据时不要补齐另一项，'
            '没有时间依据的事件明确标记时间未知。')


class EventAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    cancelled_at: str
    cancellation_recorded_at: str
    archived_at: str
    replacement_meeting_at: str
    same_event: bool | None
    other_cancelled_at: str


def cases():
    common = ('返回cancelled_at（取消发生时刻）、cancellation_recorded_at（记录取消的消息时刻）、'
              'archived_at（归档旧约的时刻）、replacement_meeting_at（新见面时刻）、'
              'same_event（取消与归档是否同一事件，布尔值；无依据写null）、'
              'other_cancelled_at（另一组人物取消见面的发生时刻）。'
              '时间使用YYYY-MM-DD HH:MM；缺失写未知，不能用消息时间填补未知事件时间。')
    french_events = [
        '[2026-06-01 09:00] Camille : Avec Léa, rendez-vous le 2026-06-08 à 14:30, porte nord.',
        '[2026-06-04 18:15] Camille : Je consigne maintenant notre décision prise le 2026-06-03 à 10:15 : nous avons annulé le rendez-vous du 8 juin. Nous avons fixé le nouveau au 2026-06-10 à 16:00, même endroit.',
        '[2026-06-05 11:20] Léa : Mon autre rendez-vous avec Noé a été annulé. Je ne connais ni la date ni l’heure de cette annulation. Cela ne modifie pas mon rendez-vous avec Camille.',
        '[2026-06-06 20:45] Camille : Archivage de l’ancien rendez-vous du 2026-06-08 à 14:30, sans le rétablir. Il avait déjà été annulé ; le nouveau rendez-vous du 10 juin reste valable.',
    ]
    french = []
    for stage, event in enumerate(french_events):
        french.append({'role': 'user', 'content': event})
        french.extend({'role': 'user', 'content': f'[atelier-{stage}-{i}] ' +
                       'Vérifier les pieds de table. Aucune nouvelle information sur les rendez-vous. ' * 10}
                      for i in range(12))
    return [
        ('zh_archive', fixture(), '核对林舟与阿岚的旧约和新约，另一组为阿岚与小夏。' + common,
         {'cancelled_at': '2026-03-04 18:15', 'cancellation_recorded_at': '2026-03-04 18:15',
          'archived_at': '2026-03-06 20:45', 'replacement_meeting_at': '2026-03-10 16:00',
          'same_event': False, 'other_cancelled_at': '未知'}),
        ('fr_delayed_record', french, '核对Camille与Léa的旧约和新约，另一组为Léa与Noé。' + common,
         {'cancelled_at': '2026-06-03 10:15', 'cancellation_recorded_at': '2026-06-04 18:15',
          'archived_at': '2026-06-06 20:45', 'replacement_meeting_at': '2026-06-10 16:00',
          'same_event': False, 'other_cancelled_at': '未知'}),
    ]


def run(output, replay_source=None):
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
    with output.open('x') as stream:
        def call(messages, instruction, contract, case_id, variant, repetition, stage, expected):
            system = instruction + '\n只输出符合以下schema的JSON，不加围栏或说明：' + json.dumps(contract.model_json_schema(), ensure_ascii=False)
            row = {'scope': 'synthetic_event_time_pairs', 'git_revision': revision,
                   'case_id': case_id, 'variant': variant, 'repetition': repetition,
                   'stage': stage, 'max_tokens': 4096,
                   'replay_source': replay_source.name if replay_source else None,
                   'limitation': 'Two synthetic fixtures; maintainer-designed comparison, not independent certification.'}
            start = time.perf_counter()
            decoded = None
            try:
                raw, _ = adapter.request_chat_completion({'model': 'MiniMax-M3',
                    'messages': [{'role': 'system', 'content': system}] + messages,
                    'temperature': 0.2, 'max_tokens': 4096, 'response_format': {'type': 'json_object'}},
                    request_kind='chat', model='MiniMax-M3')
                row['usage'] = raw.get('usage')
                row['finish_reason'] = raw['choices'][0].get('finish_reason')
                content = _extract_choice_content(raw)
                row['content_envelope'] = {'characters': len(content), 'starts_with_fence': content.lstrip().startswith('```')}
                obj = json.loads(content)
                row['strict_json_valid'] = True
                row['echoes_json_schema'] = obj == contract.model_json_schema()
                decoded = contract.model_validate(obj)
                row['reply'] = decoded.model_dump()
                row['contract_valid'] = True
                if stage == 'answer':
                    row['fields_correct'] = {k: row['reply'][k] == v for k, v in expected.items()}
            except ValidationError as exc:
                row['error_class'] = 'ValidationError'
                row['validation_errors'] = [{'path': list(e['loc']), 'type': e['type']}
                    for e in exc.errors(include_input=False, include_url=False)]
                row['contract_valid'] = False
            except json.JSONDecodeError as exc:
                row['error_class'] = 'JSONDecodeError'
                row['json_error_offset'] = exc.pos
                row['contract_valid'] = False
            except Exception as exc:
                row['error_class'] = type(exc).__name__
                row['contract_valid'] = False
            row['elapsed_ms'] = round((time.perf_counter() - start) * 1000)
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({k: row.get(k) for k in ('case_id', 'variant', 'repetition', 'stage', 'contract_valid', 'fields_correct')}), flush=True)
            return decoded

        if replay_source:
            definitions = {name: (question, expected) for name, _, question, expected in cases()}
            rows = [json.loads(line) for line in replay_source.read_text().splitlines()]
            for row in rows:
                if row['stage'] != 'compress' or not row.get('contract_valid'):
                    continue
                memory = Memory.model_validate(row['reply'])
                question, expected = definitions[row['case_id']]
                call([{'role': 'user', 'content': memory.memory}], question, EventAnswer,
                     row['case_id'], row['variant'], row['repetition'], 'answer', expected)
            return

        for case_id, history, question, expected in cases():
            for repetition in range(2):
                variants = ('dates', 'separate_events') if repetition == 0 else ('separate_events', 'dates')
                for variant in variants:
                    memory = call(history, BASE + PRESERVE + (SEPARATE if variant == 'separate_events' else ''),
                                  Memory, case_id, variant, repetition, 'compress', expected)
                    if memory is not None:
                        call([{'role': 'user', 'content': memory.memory}], question,
                             EventAnswer, case_id, variant, repetition, 'answer', expected)
                call(history, question, EventAnswer, case_id, 'full_history', repetition, 'answer', expected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--replay-source', type=Path)
    args = parser.parse_args()
    run(args.output.resolve(), args.replay_source.resolve() if args.replay_source else None)
