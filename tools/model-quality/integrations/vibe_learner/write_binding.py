"""Diagnostic source binding, applied only to an already requested valid write."""
from copy import deepcopy
import json
from unittest.mock import patch
from . import study
from .common import source_manifest
from .study_wire_shape import normalize_index


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate key')
        result[key]=value
    return result


def bind_source(raw,source):
    result=deepcopy(raw)
    for choice in result.get('choices',[]):
        for call in (choice.get('message') or {}).get('tool_calls') or []:
            function=call.get('function') if isinstance(call,dict) else None
            if not isinstance(function,dict) or set(function)!={'name','arguments'} or function['name']!='write_session_memory':continue
            try:args=json.loads(function['arguments'],object_pairs_hook=unique_object)
            except (ValueError,TypeError):continue
            if (isinstance(args,dict) and set(args)=={'key','content'} and args['key']=='experiment_reference'
                and isinstance(args['content'],str)):
                function['arguments']=json.dumps({**args,'content':source},ensure_ascii=False)
    return result


def run_sample(context,case,variant):
    if variant.id not in ('baseline','source-binding'):
        return {'status':'data_failed','failure_owner':'data','error_code':'unknown_binding_variant'}
    original=context.transport.request
    def request(payload,**kwargs):
        raw=normalize_index(original(payload,**kwargs))
        return bind_source(raw,case.source) if variant.id=='source-binding' else raw
    with patch.object(context.transport,'request',request):
        return study.run_sample(context,case,variant)
