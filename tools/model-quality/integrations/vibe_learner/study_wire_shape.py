"""Diagnostic native-provider envelope normalization, never a production policy."""
from copy import deepcopy
from unittest.mock import patch
from . import study
from .common import source_manifest


def normalize_index(raw):
    result=deepcopy(raw)
    for choice in result.get('choices', []):
        for call in (choice.get('message') or {}).get('tool_calls') or []:
            if (isinstance(call,dict) and set(call) == {'id','type','function','index'}
                and type(call['index']) is int and call['index'] >= 0):
                del call['index']
    return result


def run_sample(context,case,variant):
    if variant.id not in ('baseline','strip-index'):
        return {'status':'data_failed','failure_owner':'data','error_code':'unknown_shape_variant'}
    original=context.transport.request
    def request(payload, **kwargs):
        raw=original(payload,**kwargs)
        return normalize_index(raw) if variant.id=='strip-index' else raw
    with patch.object(context.transport,'request',request):
        return study.run_sample(context,case,variant)
