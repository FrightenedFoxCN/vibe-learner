"""Real direct Tavern admission/commit/snapshot read-back, using synthetic inputs."""
import json

from fastapi.testclient import TestClient
from app.models.tavern import TavernTurnResponse

from .common import Bridge, create_app, envelope, outcome, persona, safe_traces, settings, source_manifest, traces


def run_sample(context, case, variant):
    if case.rubric != 'tavern-text-v1':
        return {'status': 'data_failed', 'failure_owner': 'data', 'error_code': 'wrong_tavern_rubric'}
    def fake(payload):
        return envelope(json.dumps({'text': case.gold, 'mood': 'calm', 'action': 'idle', 'speech_style': '',
            'delivery_cue': '', 'state_commentary': '', 'addressed_participant_ids': []}))
    config = settings(context)
    bridge = Bridge(context, fake)
    evidence = {'domain': 'tavern', 'fixture': 'synthetic-direct-v1'}
    with bridge.installed():
        app = create_app(settings=config)
        with TestClient(app) as client:
            created = client.post('/personas', json=persona())
            created.raise_for_status()
            pid = created.json()['id']
            room = client.post('/tavern/rooms', json={'title': '合成实验', 'persona_ids': [pid],
                              'idempotency_key': 'room-' + context.transport.sample[:32]})
            room.raise_for_status()
            rid = room.json()['room']['id']
            payload = {'input': {'kind': 'user_message', 'content': case.source + '\n' + case.request + '\n' + variant.instruction},
                'mode': 'direct', 'target_persona_ids': [pid], 'guidance': '',
                'idempotency_key': 'turn-' + context.transport.sample[:32], 'expected_room_revision': room.json()['room']['revision']}
            response = client.post(f'/tavern/rooms/{rid}/turns', json=payload)
            evidence['http_status'] = response.status_code
            if response.status_code != 200:
                return outcome(context, {'turn_response': False}, evidence, status='uncertain' if bridge.failure else 'infrastructure_failed')
            result = TavernTurnResponse.model_validate(response.json())
            binding = app.state.container.tavern_service.repository.require_harness_operation(result.run.id)
            terminal = traces(app.state.container, binding.harness_operation_id)
            evidence.update(run_id=result.run.id, harness_operation_id=binding.harness_operation_id,
                            terminal_traces=safe_traces(terminal), run_status=result.run.status)
            graphs = [app.state.container.tavern_service.repository.get_actor_commit_read_back(message_id=m.id) for m in result.generated_messages]
            graph_equal = len(graphs) == 1 and all(graph[0].id == m.id and graph[1].id == result.run.id and
                            graph[2].status.value == 'completed' for graph, m in zip(graphs, result.generated_messages))
            before = bridge.calls
            replay = client.post(f'/tavern/rooms/{rid}/turns', json=payload)
            readback = client.get(f'/tavern/rooms/{rid}')
            messages = readback.json().get('messages', [])
            equal = replay.status_code == 200 and replay.json() == response.json() and all(m.model_dump(mode='json') in messages for m in result.generated_messages)
            evidence['message_ids'] = [m.id for m in result.generated_messages]
        with TestClient(create_app(settings=config)) as restarted:
            after = restarted.get(f'/tavern/rooms/{rid}')
            restart_equal = after.status_code == 200 and after.json() == readback.json()
        metrics = {'committed': result.run.status.value == 'completed', 'readback_equal': equal,
                   'commit_graph_equal': graph_equal, 'restart_equal': restart_equal,
                   'replay_no_provider_calls': before == bridge.calls,
                   'text_exact': len(result.generated_messages) == 1 and result.generated_messages[0].content == case.gold,
                   'v3_committed': len(terminal) == 1 and all(t.status in ('passed', 'repaired') and t.commit_evidence.status == 'committed' for t in terminal)}
        return outcome(context, metrics, evidence, status='uncertain' if bridge.failure else None)
