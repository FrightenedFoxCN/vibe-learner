"""Isolated synthetic Planning admission and evidence-first comparison."""
import json
import time
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient
from app.models.api import LearningPlanCreateResponse, LearningPlanResponse
from app.services.plan_tool_runtime import PlanToolRuntime
from model_quality.ledger import GateClosed
from .common import Bridge, create_app, envelope, outcome, persona, settings, source_manifest, traces


class PlanningBridge(Bridge):
    def __init__(self, context, fake, variant):
        super().__init__(context, fake)
        self.variant = variant
        self.offered = set()

    def request(self, adapter, payload, *, request_kind, model):
        if request_kind != 'plan':
            raise GateClosed('unexpected_planning_provider_kind')
        payload = {**payload, 'max_tokens': self.context.transport.campaign.max_output_tokens, 'temperature': self.context.transport.campaign.temperature}
        self.offered.update(t.get('function', {}).get('name') for t in payload.get('tools', []))
        if self.variant.id == 'evidence-first' and self.calls == 0:
            if 'read_page_range_content' not in self.offered:
                raise GateClosed('planning_evidence_tool_unavailable')
            payload = {**payload, 'tool_choice': {'type': 'function', 'function': {'name': 'read_page_range_content'}}}
        # Parent gate accepts chat, while the production caller remains plan.
        return super().request(adapter, payload, request_kind='chat', model=model)


def run_sample(context, case, variant):
    if case.rubric != 'planning-grounded-boundary-v1':
        return {'status': 'data_failed', 'failure_owner': 'data', 'error_code': 'wrong_planning_rubric'}
    def fake(payload):
        if payload.get('tool_choice', {}).get('type') == 'function' if isinstance(payload.get('tool_choice'), dict) else False:
            return envelope(tools=[{'id': 'fake-read', 'type': 'function', 'function': {'name': 'read_page_range_content', 'arguments': '{"page_start":1,"page_end":2}'}}])
        original = json.loads(next(m['content'] for m in payload['messages'] if m['role'] == 'user'))
        units = original['study_units']
        return envelope(json.dumps({'schema_name': 'learning-plan-proposal', 'schema_version': 'learning-plan-proposal-v1',
            'course_title': 'Synthetic course', 'overview': 'Read and practice the supplied source.', 'today_tasks': ['Read the source.'],
            'schedule': [{'unit_id': u['unit_id'], 'title': u['title'], 'focus': 'Read definitions and work the provided examples.', 'activity_type': 'learn',
                'schedule_chapters': [{'title': u['title'], 'anchor_page_start': u['page_start'], 'anchor_page_end': u['page_end'],
                    'source_section_ids': u['source_section_ids'], 'content_slices': [{'page_start': u['page_start'], 'page_end': u['page_end'], 'source_section_ids': u['source_section_ids']}]}]} for u in units if u['include_in_plan']]}))
    config = settings(context)
    bridge = PlanningBridge(context, fake, variant)
    observed = []
    original_execute = PlanToolRuntime.execute_tool_call
    def execute(runtime, tool_call):
        result = original_execute(runtime, tool_call)
        observed.append({'name': result.tool_name, 'ok': result.result.get('ok') is True,
                         'error': result.result.get('error') if result.result.get('ok') is False else None})
        return result
    started = time.monotonic()
    evidence = {'domain': 'planning', 'case': case.id, 'variant': variant.id, 'source': case.source,
        'request': case.request, 'gold': json.loads(case.gold), 'observed_tools': observed,
        'limitation': 'Development fixtures; first-call evidence tool choice is experimental. No independent semantic quality certification.'}
    with bridge.installed(), patch.object(PlanToolRuntime, 'execute_tool_call', execute):
        app = create_app(settings=config)
        with TestClient(app) as client:
            created = client.post('/personas', json=persona()); created.raise_for_status()
            with fitz.open() as pdf:
                for text in case.source.split('\n---PAGE---\n'):
                    page = pdf.new_page()
                    if page.insert_textbox((55, 55, 540, 750), text, fontsize=12) < 0:
                        return outcome(context, {'source_fits': False}, evidence, status='data_failed')
                if any(not p.get_text().strip() for p in pdf):
                    return outcome(context, {'source_extractable': False}, evidence, status='data_failed')
                data = pdf.tobytes()
                page_count = len(pdf)
            uploaded = client.post('/documents', files={'file': ('synthetic-planning.pdf', data, 'application/pdf')}); uploaded.raise_for_status()
            did = uploaded.json()['id']
            processed = client.post(f'/documents/{did}/process', json={'force_ocr': False}); processed.raise_for_status()
            document = processed.json()
            request_id = 'planning-' + context.transport.sample[:32]
            response = client.post('/learning-plans', json={'client_request_id': request_id, 'persona_id': created.json()['id'],
                'objective': case.request, 'document_id': did, 'expected_document_updated_at': document['updated_at']})
            evidence['http_status'] = response.status_code
            op = app.state.container.plan_service.operation_repository.get_by_client_request_id(client_request_id=request_id)
            terminal = []
            if op:
                binding = app.state.container.plan_service.operation_repository.require_harness_operation(op.operation_id)
                terminal = traces(app.state.container, binding.harness_operation_id)
                evidence.update(operation_id=op.operation_id, harness_operation_id=binding.harness_operation_id, operation_status=op.status,
                    terminal_traces=[{'stage': t.stage, 'status': t.status, 'commit_status': t.commit_evidence.status} for t in terminal])
            plan = LearningPlanCreateResponse.model_validate(response.json()) if response.status_code == 200 else None
            public = LearningPlanResponse.model_validate(plan.model_dump()).model_dump(mode='json') if plan else None
            evidence['plan'] = public
            before = bridge.calls
            readback = client.get(f'/learning-plans/{plan.id}') if plan else None
            readback_equal = readback is not None and readback.status_code == 200 and readback.json() == public
        with TestClient(create_app(settings=config)) as restarted:
            after = restarted.get(f'/learning-plans/{plan.id}') if plan else None
            restart_equal = after is not None and after.status_code == 200 and after.json() == public
        generation = [t for t in terminal if t.stage == 'plan_generation']
        chapters = [chapter for row in (public or {}).get('schedule', []) for chapter in row.get('schedule_chapters', [])]
        page_ranges_valid = bool(chapters) and all(1 <= c['anchor_page_start'] <= c['anchor_page_end'] <= page_count and
            all(1 <= s['page_start'] <= s['page_end'] <= page_count for s in c['content_slices']) for c in chapters)
        metrics = {'committed': bool(op and op.status == 'committed'), 'readback_equal': readback_equal, 'restart_equal': restart_equal,
            'recovery_no_provider_calls': bridge.calls == before, 'page_ranges_valid': page_ranges_valid,
            'v3_generation_committed': len(generation) == 1 and generation[0].status in ('passed', 'repaired') and generation[0].commit_evidence.status == 'committed'}
        evidence.update(offered_tools=sorted(bridge.offered), wire_calls=bridge.calls, elapsed_minutes=(time.monotonic()-started)/60,
            bridge_error_class=type(bridge.failure).__name__ if bridge.failure else None,
            fake_error=str(bridge.failure) if bridge.failure and context.transport.campaign.transport == 'fake' else None,
            page_count=page_count, tools_succeeded=sum(t['ok'] for t in observed), tools_failed=sum(not t['ok'] for t in observed))
        status = 'uncertain' if op and op.status == 'uncertain' else 'infrastructure_failed' if bridge.failure else None
        evidence['bridge_response_projection']={'contract':'production-completed-tool-index-normalization','normalized_tool_indexes':bridge.normalized_tool_indexes}
        return outcome(context, metrics, evidence, status=status)
