"""Experiment-only wire policy contrast; production provider code is untouched."""
from unittest.mock import patch
from . import study
from .common import source_manifest


def run_sample(context, case, variant):
    if variant.id not in ('baseline', 'adaptive', 'force-write-first'):
        return {'status':'data_failed','failure_owner':'data','error_code':'unknown_policy_variant'}
    transport = context.transport
    original_campaign, original_request = transport.campaign, transport.request
    # Both arms retain the same output ceiling; adaptive reasoning shares it.
    transport.campaign = original_campaign.model_copy(update={'thinking': 'adaptive' if variant.id == 'adaptive' else 'disabled'})
    calls = 0
    def request(payload, **kwargs):
        nonlocal calls
        calls += 1
        if variant.id == 'force-write-first' and calls == 1:
            payload = {**payload, 'tool_choice': {'type':'function','function':{'name':'write_session_memory'}}}
        return original_request(payload, **kwargs)
    try:
        with patch.object(transport, 'request', request):
            return study.run_sample(context, case, variant)
    finally:
        transport.campaign = original_campaign
