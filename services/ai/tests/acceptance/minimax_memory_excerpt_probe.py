"""Compare bounded memory excerpts on identical prior synthetic conversations."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.core.settings import Settings
from app.models.api import StudyChatOperationReceiptResponse
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services import study_memory
from app.services.provider_sdk import ProviderRequestAdapter


def run(source, output, repetitions, role_split=False, production=False, temporal=False):
    source_row = json.loads((source / 'report.jsonl').read_text().splitlines()[0])
    seed_ids = {s['receipt']['session_id'] for s in source_row['memory_seed_operations']}
    source_session = source_row['receipt']['result']['session']
    output.mkdir(parents=True, exist_ok=False)
    original_embed = study_memory._embed
    original_build = study_memory._build_candidates
    original_request = ProviderRequestAdapter.request_chat_completion
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    with (output / 'report.jsonl').open('x') as stream:
        for repetition in range(repetitions):
            variants = ('complete1600', 'learner800_assistant160', 'learner800') if role_split else ('head180', 'head_tail180', 'complete1600')
            if production:
                variants = ('production',)
            if temporal:
                variants = ('without_time', 'production')
            if repetition % 2:
                variants = tuple(reversed(variants))
            for variant in variants:
                root = output / f'{repetition}-{variant}'
                shutil.copytree(source, root)
                calls, candidates, local_embeddings = [], [], []

                def observe_local_embed(text):
                    local_embeddings.append({"input_chars": len(text)})
                    return original_embed(text)

                def excerpt(text, limit):
                    compact = ' '.join(text.strip().split())
                    if variant == 'complete1600':
                        return compact if len(compact) <= 1600 else compact[:1597] + '...'
                    if len(compact) <= limit:
                        return compact
                    if variant == 'head_tail180':
                        return compact[:(limit - 3)//2] + '...' + compact[-(limit - 3 - (limit - 3)//2):]
                    return compact[:limit-3] + '...'

                def build(*, sessions, current_session_id):
                    selected = original_build(sessions=[s for s in sessions if s.id in seed_ids], current_session_id=current_session_id)
                    if variant in {'head180', 'head_tail180', 'complete1600'}:
                        by_id = {s.id: s for s in sessions}
                        for candidate in selected:
                            turn = next(t for t in by_id[candidate.session_id].turns if t.created_at == candidate.created_at)
                            candidate.snippet = excerpt(study_memory._merge_turn(turn), 180)
                    if variant in {'learner800_assistant160', 'learner800'}:
                        by_id = {s.id: s for s in sessions}
                        def capped(text, limit):
                            compact = ' '.join(text.strip().split())
                            return compact if len(compact) <= limit else compact[:limit-3] + '...'
                        for candidate in selected:
                            turn = next(t for t in by_id[candidate.session_id].turns if t.created_at == candidate.created_at)
                            candidate.snippet = '用户原话：' + capped(turn.learner_message, 800)
                            if variant == 'learner800_assistant160':
                                candidate.snippet += '\n助手回复：' + capped(turn.assistant_reply, 160)
                    candidates[:] = [{'session_id': c.session_id, 'snippet': c.snippet, 'created_at': c.created_at} for c in selected]
                    return selected

                def observe(adapter, payload, *, request_kind, model):
                    if variant == 'without_time':
                        messages = []
                        for message in payload.get('messages', []):
                            content = message.get('content')
                            if isinstance(content, str):
                                content = re.sub(r' \| created_at=[^|]* \| snippet=', ' | snippet=', content)
                                if message.get('role') == 'tool':
                                    try:
                                        result = json.loads(content)
                                        if isinstance(result, dict) and result.get('tool_name') == 'retrieve_memory_context':
                                            for hit in result.get('hits', []):
                                                hit.pop('created_at', None)
                                            content = json.dumps(result, ensure_ascii=False)
                                    except (ValueError, TypeError):
                                        pass
                                message = {**message, 'content': content}
                            messages.append(message)
                        payload = {**payload, 'messages': messages}
                    started = time.perf_counter()
                    raw, elapsed = original_request(adapter, payload, request_kind=request_kind, model=model)
                    message = (raw.get('choices') or [{}])[0].get('message') or {}
                    calls.append({'kind': request_kind, 'model': model, 'usage': raw.get('usage'),
                        'requested_tools': [c['function']['name'] for c in message.get('tool_calls') or []],
                        'elapsed_ms': round((time.perf_counter()-started)*1000),
                        'memory_time_mentions_sdk': sum(str(m.get('content', '')).count('created_at') for m in payload.get('messages', []))})
                    return raw, elapsed

                settings = Settings(storage_root=str(root/'data'), database_url=f"sqlite:///{root/'domain.db'}",
                    plan_provider='litellm', ocr_engine='disabled', openai_api_key=os.environ['K3_API_KEY'],
                    openai_base_url='https://api.minimax.cn/v1', openai_chat_model='MiniMax-M3',
                    openai_plan_model='MiniMax-M3', openai_setting_model='MiniMax-M3', openai_timeout_seconds=90)
                app = create_app(settings=settings)
                with patch.object(study_memory, '_embed', observe_local_embed), patch.object(study_memory, '_build_candidates', build), patch.object(ProviderRequestAdapter, 'request_chat_completion', observe), TestClient(app) as client:
                    session = client.post('/study-sessions', json={key: source_session[key] for key in ('document_id', 'persona_id', 'study_unit_id')})
                    session.raise_for_status(); session = session.json()
                    response = client.post(f"/study-sessions/{session['id']}/chat", json={'client_request_id': f'excerpt-{variant}-{repetition}',
                        'expected_session_revision': session['revision'], 'message': source_row['message']})
                    row = {'scope': 'live_study_operation_receipt_readback', 'model': 'MiniMax-M3', 'git_revision': revision,
                        'case_id': 'memory_excerpt_comparison', 'variant': variant, 'repetition': repetition,
                        'source_seed_session_ids': sorted(seed_ids), 'calls': calls, 'candidate_excerpts': candidates,
                        'local_fallback_embeddings': local_embeddings,
                        'http_status': response.status_code, 'boundary_success': False,
                        'trace_limitation': ('Production excerpt with fixed seed-session selection' if production else 'Experimental excerpt construction and fixed seed-session selection') + '; production domain admission/commit. Embedding requests not instrumented.'}
                    if temporal:
                        row['case_id'] = 'memory_record_time_comparison'
                        row['trace_limitation'] = 'Same saved seed conversations and production excerpts with fixed seed selection; without_time removes record time only from SDK initial context/tool messages. SDK observation is not wire evidence.'
                    if response.status_code == 200:
                        receipt = StudyChatOperationReceiptResponse.model_validate(response.json())
                        row['receipt'] = receipt.model_dump(mode='json')
                        binding = app.state.container.study_chat_operation_repository.require_harness_operation(receipt.operation_id)
                        row['harness_operation_id'] = binding.harness_operation_id
                        traces = HarnessRuntimeRepository(app.state.container.database).list_operation_traces(binding.harness_operation_id)
                        row['terminal_traces'] = [e.terminal_trace.model_dump(mode='json') for e in traces if e.terminal_trace]
                        readback = client.get(f"/study-sessions/{session['id']}")
                        row['boundary_success'] = receipt.status == 'committed' and receipt.result is not None and readback.json() == receipt.result.session.model_dump(mode='json') and len(row['terminal_traces']) == 1 and row['terminal_traces'][0]['commit_evidence']['status'] == 'committed'
                    stream.write(json.dumps(row, ensure_ascii=False)+'\n'); stream.flush()
                    print(json.dumps({'variant': variant, 'repetition': repetition, 'boundary_success': row['boundary_success']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=2)
    parser.add_argument('--role-split', action='store_true')
    parser.add_argument('--production', action='store_true')
    parser.add_argument('--temporal', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error('repetitions must be between 1 and 20')
    run(args.source.resolve(), args.output.resolve(), args.repetitions, args.role_split, args.production, args.temporal)
