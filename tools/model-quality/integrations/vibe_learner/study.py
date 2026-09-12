"""Synthetic PDF -> Study admission -> typed memory effect -> restart read-back."""
import json

import fitz
from fastapi.testclient import TestClient
from app.models.api import StudyChatOperationReceiptResponse
from app.models.study_chat_effect import StudyChatCommittedEffectBatchV1

from .common import Bridge, create_app, envelope, outcome, persona, safe_traces, settings, source_manifest, traces


TEXTBOOK = '''Chapter 1 Linear Equations
A linear equation is ax + b = c, where a is nonzero.
Subtract b from both sides and divide by a.
For example, 2x + 3 = 11 gives x = 4.
Check by substitution: 2 times 4 plus 3 equals 11.
Dividing by zero is not allowed.
'''


def run_sample(context, case, variant):
    if case.rubric not in ('study-memory-v1', 'study-memory-final-v2', 'study-memory-facts-v1'):
        return {'status': 'data_failed', 'failure_owner': 'data', 'error_code': 'wrong_study_rubric'}
    def fake(payload):
        tool_messages = [m for m in payload['messages'] if m['role'] == 'tool']
        index = len(tool_messages)
        if index < 2:
            name = 'write_session_memory' if index == 0 else 'read_session_memory'
            if name not in {t.get('function', {}).get('name') for t in payload.get('tools', [])}:
                raise ValueError('fixture_tool_not_offered')
            args = {'key': 'experiment_reference', 'content': case.gold if case.rubric == 'study-memory-facts-v1' else case.source} if index == 0 else {'key': 'experiment_reference', 'limit': 6}
            return envelope(tools=[{'id': 'fixture-call-' + str(index), 'type': 'function',
                                   'function': {'name': name, 'arguments': json.dumps(args, ensure_ascii=False)}}])
        return envelope(json.dumps({'text': '已完成本轮核对。', 'mood': 'calm', 'action': 'idle', 'interactive_question': None}))
    config = settings(context)
    bridge = Bridge(context, fake)
    evidence = {'domain': 'study', 'fixture': 'synthetic-linear-equations-v1'}
    with bridge.installed():
        app = create_app(settings=config)
        with TestClient(app) as client:
            created = client.post('/personas', json=persona())
            created.raise_for_status()
            with fitz.open() as pdf:
                page = pdf.new_page()
                page.insert_text((55, 55), TEXTBOOK, fontsize=12)
                data = pdf.tobytes()
            uploaded = client.post('/documents', files={'file': ('synthetic.pdf', data, 'application/pdf')})
            uploaded.raise_for_status()
            doc_id = uploaded.json()['id']
            processed = client.post('/documents/' + doc_id + '/process', json={'force_ocr': False})
            processed.raise_for_status()
            document = processed.json()
            if not document['study_units']:
                return outcome(context, {'document_ready': False}, evidence, status='data_failed')
            initial = client.post('/study-sessions', json={'document_id': doc_id, 'persona_id': created.json()['id'],
                'study_unit_id': document['study_units'][0]['id']})
            initial.raise_for_status()
            session = initial.json()
            sid, request_id = session['id'], 'experiment-' + context.transport.sample[:32]
            payload = {'client_request_id': request_id, 'expected_session_revision': session['revision'],
                       'message': case.request + '\n' + variant.instruction + '\n记录原文：\n' + case.source}
            response = client.post(f'/study-sessions/{sid}/chat', json=payload)
            recovery = client.get(f'/study-sessions/{sid}/chat-operations/{request_id}')
            evidence['http_status'] = response.status_code
            if recovery.status_code != 200:
                return outcome(context, {'operation_readable': False}, evidence, status='infrastructure_failed')
            receipt = StudyChatOperationReceiptResponse.model_validate(recovery.json())
            evidence['receipt'] = receipt.model_dump(mode='json')
            binding = app.state.container.study_chat_operation_repository.require_harness_operation(receipt.operation_id)
            terminal = traces(app.state.container, binding.harness_operation_id)
            evidence.update(harness_operation_id=binding.harness_operation_id, terminal_traces=safe_traces(terminal))
            record = app.state.container.study_chat_operation_repository.get(session_id=sid, client_request_id=request_id)
            raw_batch = (record.response_payload or {}).get('_committed_effect_batch')
            batch = StudyChatCommittedEffectBatchV1.model_validate(raw_batch) if raw_batch else None
            evidence['effect_batch'] = {'operation_id': batch.operation_id, 'effect_batch_id': batch.effect_batch_id,
                                        'effect_count': len(batch.effects),
                                        'effect_kinds': [e.effect_kind for e in batch.effects]} if batch else None
            before = bridge.calls
            readback = client.get(f'/study-sessions/{sid}')
            public = receipt.result.session.model_dump(mode='json') if receipt.result else None
            readback_equal = readback.status_code == 200 and public is not None and readback.json() == public
        # New container/database connections, same isolated sample storage.
        with TestClient(create_app(settings=config)) as restarted:
            recovered = restarted.get(f'/study-sessions/{sid}/chat-operations/{request_id}')
            after = restarted.get(f'/study-sessions/{sid}')
            restart_equal = recovered.status_code == 200 and recovered.json() == recovery.json() and after.status_code == 200 and after.json() == public
        memory = [m for m in (public or {}).get('session_memory', []) if m['key'] == 'experiment_reference']
        memory_effects = [e for e in (batch.effects if batch else []) if e.effect_kind == 'memory_upsert' and e.key == 'experiment_reference']
        tool_names = [t['tool_name'] for turn in (public or {}).get('turns', []) for t in turn.get('tool_calls', [])]
        successful_tools = [t['tool_name'] for turn in (public or {}).get('turns', []) for t in turn.get('tool_calls', []) if json.loads(t['result_json']).get('ok') is True]
        evidence['observed_tool_names'] = tool_names
        evidence['successful_tool_names'] = successful_tools
        metrics = {'read_memory_tool_succeeded': 'read_session_memory' in successful_tools, 'committed': receipt.status == 'committed', 'readback_equal': readback_equal,
                   'restart_equal': restart_equal, 'recovery_no_provider_calls': bridge.calls == before,
                   'memory_exact': len(memory) == 1 and memory[0]['content'] == case.gold,
                   'typed_effect_batch': batch is not None and batch.operation_id == receipt.operation_id,
                   'memory_effect_exact': len(memory_effects) == 1 and memory_effects[0].session_id == sid and memory_effects[0].content == case.gold,
                   'v3_committed': bool(terminal) and all(t.status in ('passed', 'repaired') and t.commit_evidence.status == 'committed' for t in terminal)}
        evidence['memory_effects'] = [{'session_id':effect.session_id,'key':effect.key,'content':effect.content} for effect in memory_effects]
        if case.rubric == 'study-memory-final-v2':
            del metrics['memory_effect_exact']
            metrics['final_memory_effect_exact'] = bool(memory_effects) and memory_effects[-1].session_id == sid and memory_effects[-1].content == case.gold
        if case.rubric == 'study-memory-facts-v1':
            from .study_fixture import grade_json_answer
            gold_facts = json.loads(case.gold)
            del metrics['memory_exact']
            del metrics['memory_effect_exact']
            metrics['summary_facts_exact'] = len(memory) == 1 and grade_json_answer(memory[0]['content'], gold_facts)[1]
            metrics['summary_effect_facts_exact'] = bool(memory_effects) and memory_effects[-1].session_id == sid and grade_json_answer(memory_effects[-1].content, gold_facts)[1]
        status = 'uncertain' if receipt.status == 'uncertain' else 'infrastructure_failed' if bridge.failure else None
        return outcome(context, metrics, evidence, status=status)
