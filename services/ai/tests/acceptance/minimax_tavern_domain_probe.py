"""Real M3 Tavern admission, actor commits, transcript read-back and replay."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.core.settings import Settings
from app.models.tavern import TavernTurnResponse
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.provider_sdk import ProviderRequestAdapter
from tests.test_persona_lifecycle import create_request


CONSTRAINT_CASES = {
    'budget_conflict': '有人提出：单程出行60分钟（含步行和乘车），原路返回，再坐下休息20分钟；饮料20元，加上去程和回程各20元交通费。',
    'budget_feasible': '有人提出：单程出行35分钟（含步行和乘车），原路返回，再坐下休息30分钟；饮料20元，加上去程和回程各10元交通费。',
}


PROMPT_INTERVENTIONS = {
    'format_check': '输出前检查content里的用户格式要求：列表条数按实际Markdown列表项计数，不按话题组数计数；将相关说明合并到允许的条目内，不另加列表项、开场或结尾。',
    'feasibility_check': '提出调整建议时，区分已知条件、建议的预算上限和仍需核实的现实条件。不能仅把已知价格或耗时改成较小数字就声称方案可执行；说明可采取的调整及其适用条件，分别核对不同单位的限制。',
}


def run(root, repetitions, constraint_case=None, chat_max_tokens=800, thinking_mode=None, prompt_intervention=None):
    root.mkdir(parents=True, exist_ok=False)
    settings = Settings(storage_root=str(root / 'data'), database_url=f"sqlite:///{root / 'domain.db'}",
        plan_provider='litellm', ocr_engine='disabled', openai_api_key=os.environ['K3_API_KEY'],
        openai_base_url='https://api.minimax.cn/v1', openai_chat_model='MiniMax-M3',
        openai_plan_model='MiniMax-M3', openai_setting_model='MiniMax-M3', openai_timeout_seconds=90,
        openai_chat_max_tokens=chat_max_tokens)
    app = create_app(settings=settings)
    calls = []
    original = ProviderRequestAdapter.request_chat_completion

    def observe(adapter, payload, *, request_kind, model):
        started = time.perf_counter()
        if thinking_mode:
            payload = {**payload, 'extra_body': {**payload.get('extra_body', {}), 'thinking': {'type': thinking_mode}}}
        if prompt_intervention:
            messages = [dict(message) for message in payload['messages']]
            system = next(message for message in messages if message['role'] == 'system')
            system['content'] += '\n' + PROMPT_INTERVENTIONS[prompt_intervention]
            payload = {**payload, 'messages': messages}
        call = {'kind': request_kind, 'model': model, 'max_tokens': payload.get('max_tokens'),
                'thinking_mode': thinking_mode or 'provider_default'}
        calls.append(call)
        try:
            original_send = httpx.Client.send
            def observe_wire(client, request, *args, **kwargs):
                if request.url.host == 'api.minimax.cn' and request.url.path.endswith('/chat/completions'):
                    body = json.loads(request.content)
                    call.setdefault('wire_requests', []).append({
                        'thinking_type': (body.get('thinking') or {}).get('type'),
                        'max_tokens':body.get('max_tokens'),
                        'max_completion_tokens':body.get('max_completion_tokens')})
                return original_send(client, request, *args, **kwargs)
            with patch.object(httpx.Client, 'send', observe_wire):
                raw, elapsed = original(adapter, payload, request_kind=request_kind, model=model)
            call['usage'] = raw.get('usage')
            choice = (raw.get('choices') or [{}])[0]
            call['finish_reason'] = choice.get('finish_reason')
            content = (choice.get('message') or {}).get('content')
            call['content_shape'] = {'type':type(content).__name__}
            if isinstance(content, str):
                call['content_shape'].update(characters=len(content), empty=not content.strip())
                try:
                    decoded = json.loads(content)
                except json.JSONDecodeError:
                    call['content_shape']['strict_json_object'] = False
                else:
                    call['content_shape']['strict_json_object'] = isinstance(decoded, dict)
            return raw, elapsed
        except Exception as exc:
            call['error_class'] = type(exc).__name__
            call['upstream_status'] = getattr(exc, 'status_code', None)
            message = str(getattr(exc, 'upstream_message', ''))
            call['error_mentions_thinking'] = 'thinking' in message
            call['error_mentions_unsupported_params'] = 'UnsupportedParamsError' in message
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
                if constraint_case:
                    content = ('这是第一次讨论周末安排，我们所在城市尚未确定。我总共只有120分钟，预算50元。'
                        + CONSTRAINT_CASES[constraint_case] +
                        '这些时间和费用都计入总限额，交通耗时已包含在单程时间里，不额外添加。'
                        '请先判断这份安排是否可行，写清总时间与总费用；若超限，给出同时符合两项限制的调整，保留往返和休息。'
                        '每位发言者只用两条Markdown无序列表，不要开场或结尾。'
                        '根据你自己的判断回应，不要默认别人或前一位发言者算得对；不编造具体城市地点、价格或共同经历，不替另一位说话。')
                targets = [personas[repetition % 2]['id']] if mode == 'direct' else [p['id'] for p in reversed(personas)]
                payload = {'input': {'kind': 'user_message', 'content': content}, 'mode': mode,
                    'target_persona_ids': targets, 'guidance': '', 'idempotency_key': f'quality-turn-{mode}-{repetition}',
                    'expected_room_revision': room.json()['room']['revision']}
                calls.clear()
                row = {'scope': 'live_tavern_admission_actor_commit_readback', 'model': 'MiniMax-M3',
                    'git_revision': revision, 'prompt_intervention':prompt_intervention,
                    'prompt_intervention_text':PROMPT_INTERVENTIONS.get(prompt_intervention),
                    'experimental_override_scope':'SDK payload after production preflight; not a registered production prompt contract', 'constraint_case': constraint_case, 'mode': mode,
                    'configured_chat_max_tokens':chat_max_tokens, 'thinking_mode':thinking_mode or 'provider_default', 'repetition': repetition, 'request': payload,
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
                    row['readback'] = client.get(f'/tavern/rooms/{room_id}').json()
                stream.write(json.dumps(row, ensure_ascii=False) + '\n'); stream.flush()
                print(json.dumps({'mode': mode, 'repetition': repetition, 'boundary_success': row['boundary_success']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--constraint-case', choices=CONSTRAINT_CASES)
    parser.add_argument('--chat-max-tokens', type=int, default=800)
    parser.add_argument('--thinking-mode', choices=('adaptive','disabled'))
    parser.add_argument('--prompt-intervention', choices=PROMPT_INTERVENTIONS)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error('repetitions must be between 1 and 20')
    run(args.root.resolve(), args.repetitions, args.constraint_case, args.chat_max_tokens, args.thinking_mode, args.prompt_intervention)
