"""All project dependencies stay outside model_quality's generic core."""
from contextlib import contextmanager
import json
import logging
import os
from pathlib import Path
import time
from unittest.mock import patch

from app.app_factory import create_app
from app.core.settings import Settings
from app.models.api import CreatePersonaRequest
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.provider_sdk import ProviderRequestAdapter
from app.services.provider_transport import _normalize_completed_tool_indexes

from model_quality.ledger import GateClosed
from model_quality.runner import atomic_json


def persona():
    return CreatePersonaRequest(name='实验导师', summary='温和简洁，忠实核对用户给出的合成资料。',
        relationship='导师与成年学习者', learner_address='小林', system_prompt='不要编造经历；遵守本轮任务范围。',
        reference_hints=[], slots=[{'kind': 'teaching_method', 'label': '方法', 'content': '直接说明核对结果，不额外出题。',
            'weight': 50, 'locked': False, 'sort_order': 0}], available_emotions=['calm'],
        available_actions=['idle'], default_speech_style='简洁').model_dump(mode='json')


def settings(context):
    c = context.transport.campaign
    return Settings(storage_root=str(context.storage / 'domain'), database_url='sqlite:///' + str(context.database),
        plan_provider='litellm', ocr_engine='disabled', openai_api_key=os.environ.get('K3_API_KEY', 'fake-only'),
        openai_base_url='https://api.minimax.cn/v1', openai_chat_model=c.model,
        openai_plan_model=c.model, openai_setting_model=c.model, openai_timeout_seconds=c.timeout_seconds,
        openai_chat_temperature=c.temperature, openai_chat_max_tokens=c.max_output_tokens,
        openai_setting_web_search_enabled=False, openai_chat_model_multimodal=False,
        openai_plan_model_multimodal=False)


class Bridge:
    def __init__(self, context, fake):
        self.context, self.fake = context, fake
        self.calls = 0
        self.failure = None
        self.call_kind = 'generation'
        self.normalized_tool_indexes = 0

    def request(self, adapter, payload, *, request_kind, model):
        started = time.monotonic()
        if request_kind not in ('chat', 'tavern', 'study_chat', 'tavern_actor'):
            raise GateClosed('unexpected_domain_provider_kind')
        self.calls += 1
        try:
            simulated = self.fake(payload) if self.context.transport.campaign.transport == 'fake' else None
            raw = self.context.transport.request(payload, call_kind=self.call_kind, fake_response=simulated)
            # Native wire telemetry is recorded before projection. Reuse the
            # exact production response projection; do not relax domain decode
            # or duplicate its index/type/unknown-field rules in the lab.
            normalized = _normalize_completed_tool_indexes(raw)
            original_choices, projected_choices = raw.get('choices'), normalized.get('choices')
            paired_choices = zip(original_choices, projected_choices) if isinstance(original_choices, list) and isinstance(projected_choices, list) else ()
            for original_choice, projected_choice in paired_choices:
                if not isinstance(original_choice, dict) or not isinstance(projected_choice, dict):
                    continue
                original_message, projected_message = original_choice.get('message'), projected_choice.get('message')
                if not isinstance(original_message, dict) or not isinstance(projected_message, dict):
                    continue
                original_calls, projected_calls = original_message.get('tool_calls'), projected_message.get('tool_calls')
                if not isinstance(original_calls, list) or not isinstance(projected_calls, list):
                    continue
                self.normalized_tool_indexes += sum(isinstance(a, dict) and isinstance(b, dict) and 'index' in a and 'index' not in b
                                                    for a, b in zip(original_calls, projected_calls))
            return normalized, round((time.monotonic()-started)*1000)
        except Exception as exc:
            self.failure = exc
            raise

    @contextmanager
    def installed(self):
        bridge = self
        def complete(adapter, payload, *, request_kind, model):
            return bridge.request(adapter, payload, request_kind=request_kind, model=model)
        def forbidden(*args, **kwargs):
            raise GateClosed('unmetered_provider_endpoint_disabled')
        # No legacy SDK/embedding/responses path may escape the wire gate.
        with patch.object(ProviderRequestAdapter, 'request_chat_completion', complete), \
             patch.object(ProviderRequestAdapter, 'request_response', forbidden), \
             patch.object(ProviderRequestAdapter, 'request_embeddings', forbidden):
            yield


def envelope(content=None, tools=None):
    message = {'role': 'assistant', 'content': content}
    if tools:
        message['tool_calls'] = tools
    return {'model': 'MiniMax-M3', 'choices': [{'message': message, 'finish_reason': 'tool_calls' if tools else 'stop'}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}


def traces(container, operation_id):
    return [e.terminal_trace for e in HarnessRuntimeRepository(container.database).list_operation_traces(operation_id) if e.terminal_trace]


def safe_traces(values):
    # Preserve only typed lifecycle summaries, not protected payloads or reasoning.
    return [{'status': t.status, 'commit_status': t.commit_evidence.status,
             'commit_scope': 'primary_output_only'} for t in values]


def outcome(context, metrics, evidence, *, status=None):
    success = all(metrics.values())
    if status is None:
        status = 'completed' if success else 'candidate_failed'
    evidence.update(version='vibe-domain-readback-v1', metrics=metrics,
                    scope='Synthetic project adapter. Primary output lifecycle and specified rubric only; no independent quality certification.')
    atomic_json(context.storage/'domain-evidence.json', evidence)
    return {'status': status, 'failure_owner': None if status == 'completed' else 'infrastructure' if status == 'uncertain' else status.removesuffix('_failed'),
            'metrics': metrics, 'scope': 'domain-primary-output-readback',
            'evidence': [{'path': 'domain-evidence.json', 'contract': 'vibe-domain-readback-v1'}]}


def source_manifest():
    import hashlib
    import importlib.metadata
    import app
    app_root = Path(app.__file__).resolve().parent
    adapter_root = Path(__file__).resolve().parent
    files = {str(p.relative_to(app_root.parent)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(app_root.rglob('*.py'))}
    files.update({'adapter/' + p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(adapter_root.glob('*.py'))})
    lock = app_root.parent / 'uv.lock'
    files['uv.lock'] = hashlib.sha256(lock.read_bytes()).hexdigest()
    return {'source_files': files, 'dependencies': {name: importlib.metadata.version(name) for name in
            ('fastapi', 'sqlalchemy', 'PyMuPDF', 'litellm', 'httpx')}}
