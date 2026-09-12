"""Capture natural order failures privately, then replay identical repair requests.

Capture operations exercise the domain. Replays are provider diagnostics only;
source-bearing request snapshots must stay under the local temporary directory.
No response reasoning or credentials are written.
"""
import argparse
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from app.services.provider_planning import (RemotePlanningProvider,
    _decode_learning_plan_proposal, _validate_learning_plan_proposal_refs,
    PlanningProposalDecodeError)
from app.services.provider_sdk import ProviderRequestAdapter
from app.services.provider_payload import _extract_choice_content
from tests.acceptance.minimax_planning_probe import run
from tests.acceptance.planning_payload_observation import observe_planning_content
from tests.acceptance.minimax_planning_geometry_repair import GEOMETRY_REPAIR_HINT


def private_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, ensure_ascii=False)


def run_capture(source, pdf, output, objective, attempts=4):
    if not output.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        # /tmp is the explicit user-facing spelling on macOS, whose temp dir differs.
        if not output.resolve().is_relative_to(Path('/tmp').resolve()):
            raise ValueError('Source-bearing captures require a temporary output directory')
    output.mkdir(parents=True, exist_ok=False)
    original_request = ProviderRequestAdapter.request_chat_completion
    original_model = RemotePlanningProvider._run_plan_model
    captured = {}
    active = {}
    manifest = {'scope':'natural_planning_order_failure_capture', 'operations':[],
                'replay_scope':'Direct provider repair diagnostic, no new domain admission or commit'}

    def observe_model(provider, **kwargs):
        last = kwargs['messages'][-1].get('content')
        if isinstance(last, str) and '上一次最终计划未通过' in last:
            active['units'] = kwargs['tool_runtime'].current_study_units()
            active['tools_enabled'] = kwargs['tool_runtime'].has_tools()
        return original_model(provider, **kwargs)

    def observe_request(adapter, payload, *, request_kind, model):
        last = payload['messages'][-1].get('content')
        if (not captured and isinstance(last, str) and '上一次最终计划未通过' in last
                and 'not_ordered' in last):
            assert not active['tools_enabled'] and not payload.get('tools')
            captured.update(payload=copy.deepcopy(payload), units=list(active['units']),
                            adapter=replace(adapter, transport=replace(adapter.transport, token_usage_service=None)))
            private_json(output/'private-repair-input.json', {
                'payload':payload, 'units':[u.model_dump(mode='json') for u in active['units']],
                'limitation':'Source text and image input, local only; excludes credentials and response reasoning'})
        return original_request(adapter, payload, request_kind=request_kind, model=model)

    for index in range(attempts):
        active.clear()
        root = output/f'capture-{index}'
        with patch.object(RemotePlanningProvider, '_run_plan_model', observe_model), patch.object(ProviderRequestAdapter, 'request_chat_completion', observe_request):
            run(root,1,selected_case='document',pdf_path=pdf,objective_override=objective,
                multimodal=True,persona_domain='text',persona_method='explorer',
                page_evidence='text_image',page_evidence_page=2,page_evidence_dpi=100,
                controlled_page_evidence=True,prepared_source_root=source)
        row=json.loads((root/'report.jsonl').read_text().splitlines()[0])
        manifest['operations'].append({'index':index,'boundary_success':row['boundary_success'],
            'harness_operation_id':row['harness_operation_id'],'calls':len(row['calls']),
            'errors':[t['error_code'] for t in row['terminal_traces'] if t.get('error_code')]})
        (output/'capture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        if captured:
            break
    manifest['capture_outcome'] = 'target_observed' if captured else 'target_not_observed_within_attempt_limit'
    (output/'capture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    if not captured:
        return
    hint=GEOMETRY_REPAIR_HINT.split('保留原有章节')[0]
    proposal_content=next(m['content'] for m in reversed(captured['payload']['messages'][:-1]) if m['role']=='assistant')
    try:
        initial=_decode_learning_plan_proposal(proposal_content)
        _validate_learning_plan_proposal_refs(initial,captured['units'])
    except PlanningProposalDecodeError as exc:
        manifest['captured_initial_error']={'path':exc.path,'reason':exc.reason}
    else:
        raise AssertionError('Captured initial proposal must fail actual geometry validation')
    manifest['captured_initial_geometry']=[{'unit_id':s.unit_id,'chapters':[
        {'pages':[c.anchor_page_start,c.anchor_page_end], 'slices':[[v.page_start,v.page_end] for v in c.content_slices]}
        for c in s.schedule_chapters]} for s in initial.schedule]
    (output/'capture-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    with (output/'replay-report.jsonl').open('x') as stream:
        for index,candidate in enumerate([False,True,True,False]):
            payload=copy.deepcopy(captured['payload'])
            if candidate:
                payload['messages'][-1]['content']+=hint
            row={'scope':'natural_proposal_fixed_request_replay','index':index,'candidate':candidate,
                 'hint':hint if candidate else None,'same_request_except_feedback':True,
                 'proposal_valid':False,'limitation':'Direct SDK replay only, not domain commit evidence'}
            try:
                raw,elapsed=original_request(captured['adapter'],payload,request_kind='plan',model='MiniMax-M3')
                row.update(usage=raw.get('usage'),elapsed_ms=elapsed,finish_reason=raw['choices'][0].get('finish_reason'))
                content=_extract_choice_content(raw)
                row['content_envelope']=observe_planning_content(content)
                proposal=_decode_learning_plan_proposal(content)
                row['proposal']=proposal.model_dump(mode='json')
                _validate_learning_plan_proposal_refs(proposal,captured['units'])
                row['proposal_valid']=True
            except PlanningProposalDecodeError as exc:
                row['error']={'path':exc.path,'reason':exc.reason}
            except Exception as exc:
                row['error_class']=type(exc).__name__
            stream.write(json.dumps(row,ensure_ascii=False)+'\n');stream.flush()
            print(json.dumps({'replay':index,'candidate':candidate,'valid':row['proposal_valid']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','pdf','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--objective',required=True);p.add_argument('--attempts',type=int,default=4)
    a=p.parse_args()
    if not 1<=a.attempts<=8:p.error('attempts must be1..8')
    run_capture(a.source.resolve(),a.pdf.resolve(),a.output.resolve(),a.objective,a.attempts)
