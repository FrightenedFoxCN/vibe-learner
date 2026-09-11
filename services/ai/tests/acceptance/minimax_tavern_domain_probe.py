"""Real M3 Tavern admission, actor commits, transcript read-back and replay."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.core.settings import Settings
from app.models.tavern import TavernTurnResponse
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.provider_sdk import ProviderRequestAdapter
from tests.test_persona_lifecycle import create_request


def run(root, repetitions):
    root.mkdir(parents=True, exist_ok=False)
    settings = Settings(storage_root=str(root / 'data'), database_url=f"sqlite:///{root / 'domain.db'}",
        plan_provider='litellm', ocr_engine='disabled', openai_api_key=os.environ['K3_API_KEY'],
        openai_base_url='https://api.minimax.cn/v1', openai_chat_model='MiniMax-M3',
        openai_plan_model='MiniMax-M3', openai_setting_model='MiniMax-M3', openai_timeout_seconds=90)
    app = create_app(settings=settings)
    calls = []
    original = ProviderRequestAdapter.request_chat_completion

    def observe(adapter, payload, *, request_kind, model):
        started = time.perf_counter()
        call = {'kind': request_kind, 'model': model}
        calls.append(call)
        try:
            raw, elapsed = original(adapter, payload, request_kind=request_kind, model=model)
            call['usage'] = raw.get('usage')
            call['finish_reason'] = (raw.get('choices') or [{}])[0].get('finish_reason')
            return raw, elapsed
        except Exception as exc:
            call['error_class'] = type(exc).__name__
            raise
        finally:
            call['elapsed_ms'] = round((time.perf_counter() - started) * 1000)

    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    with patch.object(ProviderRequestAdapter, 'request_chat_completion', observe), TestClient(app) as client, (root / 'report.jsonl').open('x') as stream:
        personas = []
        for name, summary in [('顾言', '严谨克制的数学老师，先检查限制再提出建议，说话简洁。'),
                              ('林岚', '热爱旅行的摄影师，喜欢观察光线与城市细节，主动提出可尝试的路线，语气轻快。')]:
            payload = create_request(name).model_dump(mode='json')
            payload.update(summary=summary, relationship='初次见面的成年朋友', learner_address='小林')
            response = client.post('/personas', json=payload)
            response.raise_for_status()
            personas.append(response.json())
        runtime = HarnessRuntimeRepository(app.state.container.database)
        for repetition in range(repetitions):
            for mode in ('direct', 'facilitated'):
                room = client.post('/tavern/rooms', json={'title': '周末散步讨论', 'persona_ids': [p['id'] for p in personas],
                    'idempotency_key': f'quality-room-{mode}-{repetition}'} )
                room.raise_for_status()
                room_id = room.json()['room']['id']
                content = '这是我们第一次讨论周末安排。我只有两小时，预算50元，想在城里散步放松。每位发言者只用两条Markdown无序列表给出建议，不要开场白或结尾，不要编造我们共同经历过的事，也不要替另一位说话。'
                targets = [personas[repetition % 2]['id']] if mode == 'direct' else [p['id'] for p in reversed(personas)]
                payload = {'input': {'kind': 'user_message', 'content': content}, 'mode': mode,
                    'target_persona_ids': targets, 'guidance': '', 'idempotency_key': f'quality-turn-{mode}-{repetition}',
                    'expected_room_revision': room.json()['room']['revision']}
                calls.clear()
                row = {'scope': 'live_tavern_admission_actor_commit_readback', 'model': 'MiniMax-M3',
                    'git_revision': revision, 'mode': mode, 'repetition': repetition, 'request': payload,
                    'persona_inputs': [{'id': p['id'], 'name': p['name'], 'summary': p['summary']} for p in personas],
                    'calls': calls, 'boundary_success': False}
                response = client.post(f'/tavern/rooms/{room_id}/turns', json=payload)
                row['http_status'] = response.status_code
                if response.status_code == 200:
                    result = TavernTurnResponse.model_validate(response.json())
                    row['result'] = result.model_dump(mode='json')
                    binding = app.state.container.tavern_service.repository.require_harness_operation(result.run.id)
                    row['harness_operation_id'] = binding.harness_operation_id
                    executions = runtime.list_operation_traces(binding.harness_operation_id)
                    row['terminal_traces'] = [e.terminal_trace.model_dump(mode='json') for e in executions if e.terminal_trace]
                    before_replay = len(calls)
                    replay = client.post(f'/tavern/rooms/{room_id}/turns', json=payload)
                    readback = client.get(f'/tavern/rooms/{room_id}')
                    row['replay_equal'] = replay.status_code == 200 and replay.json() == response.json()
                    row['replay_provider_calls'] = len(calls) - before_replay
                    row['readback'] = readback.json()
                    committed = readback.json().get('messages', [])
                    row['messages_readback_equal'] = all(m.model_dump(mode='json') in committed for m in result.generated_messages)
                    row['boundary_success'] = (result.run.status.value == 'completed' and row['replay_equal'] and row['replay_provider_calls'] == 0
                        and row['messages_readback_equal'] and len(result.generated_messages) == len(targets)
                        and len(row['terminal_traces']) == len(targets) and all(t['status'] in {'passed', 'repaired'}
                            and t['commit_evidence']['status'] == 'committed' for t in row['terminal_traces']))
                else:
                    row['error'] = response.json()
                    row['runs_readback'] = client.get(f'/tavern/rooms/{room_id}/runs').json()
                stream.write(json.dumps(row, ensure_ascii=False) + '\n'); stream.flush()
                print(json.dumps({'mode': mode, 'repetition': repetition, 'boundary_success': row['boundary_success']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error('repetitions must be between 1 and 20')
    run(args.root.resolve(), args.repetitions)
