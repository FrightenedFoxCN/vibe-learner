"""Reference adapter. Project adapters must use context.transport for EVERY wire.

Adapters execute in fresh processes. They own domain admission/read-back and use
context.storage/context.database for isolated state. No production imports here.
"""
from dataclasses import dataclass
from pathlib import Path

from .protocol import Case, Variant
from .transport import MeteredTransport


@dataclass(frozen=True)
class Context:
    transport: MeteredTransport
    storage: Path
    database: Path


def text_probe(context: Context, case: Case, variant: Variant) -> dict:
    if case.rubric != 'exact-text-v1':
        return {'status': 'data_failed', 'failure_owner': 'data', 'error_code': 'unsupported_text_rubric'}
    raw = context.transport.complete([
        {'role': 'system', 'content': variant.instruction},
        {'role': 'user', 'content': case.source + '\n\n' + case.request},
    ])
    choices = raw.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return {'status': 'candidate_failed', 'failure_owner': 'candidate', 'error_code': 'missing_choice'}
    choice = choices[0]
    message = choice.get('message')
    content = message.get('content') if isinstance(message, dict) else None
    # Persist objective measurements only. Raw text may include reasoning even
    # with reasoning_split requested; do not save it or a content digest.
    valid = isinstance(content, str) and '<think' not in content.lower() and choice.get('finish_reason') == 'stop'
    exact = valid and content == case.gold
    return {'status': 'completed' if exact else 'candidate_failed',
            'failure_owner': None if exact else 'candidate',
            'metrics': {'exact_text': exact, 'complete_text': valid},
            'scope': 'provider-proposal-only; no domain admission, commit or read-back'}


CAPACITY_SAFE = True
