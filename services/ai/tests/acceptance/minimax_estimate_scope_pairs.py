"""Real Planning comparison of estimator scope disclosure, with unchanged scores."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import app.services.plan_tool_runtime as runtime
from tests.acceptance.minimax_planning_probe import run
from app.services.provider_sdk import ProviderRequestAdapter


SCOPE_HINT = (
    '此分数只反映当前学习单元与子标题元数据，不评审你草拟的最终计划；'
    '只改变focus或重复调用不会使分数自动提高。'
    '若已核对材料且原文没有更细目录，可据真实页码组织活动并明确证据边界，'
    '不为提分杜撰子标题或反复拆分；最终计划仍须满足用户目标、引用与结构规则。'
)


def compare(source, pdf, output, objective, placement='result', prepared_document_id=None, native_tools=False):
    output.mkdir(parents=True, exist_ok=False)
    original = runtime._execute_estimate_plan_completion
    original_request = ProviderRequestAdapter.request_chat_completion
    rows = []
    for index, candidate in enumerate([False, True, True, False]):
        estimates = []
        definition_exposures = []

        def observe(arguments, context):
            result = original(arguments, context)
            if candidate and placement == 'result':
                result = replace(result, payload={**result.payload,
                    'recommendations': [SCOPE_HINT, *result.payload['recommendations']]})
            estimates.append({'unit_ranges': [[u.page_start, u.page_end] for u in context.study_units if u.include_in_plan],
                'score': result.payload['completion_score'], 'signals': result.payload['signals'],
                'missing_items': result.payload['missing_items'], 'scope_hint_sent': candidate and placement == 'result'})
            return result

        def observe_request(adapter, payload, *, request_kind, model):
            tools = []
            for tool in payload.get('tools', []):
                if tool.get('function', {}).get('name') == 'estimate_plan_completion':
                    definition_exposures.append(candidate and placement == 'description')
                    if candidate and placement == 'description':
                        function = tool['function']
                        tool = {**tool, 'function': {**function,
                            'description': function.get('description', '') + SCOPE_HINT}}
                tools.append(tool)
            if 'tools' in payload:
                payload = {**payload, 'tools': tools}
            return original_request(adapter, payload, request_kind=request_kind, model=model)

        cell = output / f'{index}-{"candidate" if candidate else "baseline"}'
        with patch.object(runtime, '_execute_estimate_plan_completion', observe), patch.object(ProviderRequestAdapter, 'request_chat_completion', observe_request):
            run(cell, 1, selected_case='document', pdf_path=pdf, objective_override=objective,
                multimodal=True, persona_domain='text', persona_method='explorer',
                page_evidence=None if native_tools else 'text_image', page_evidence_page=2,
                controlled_page_evidence=not native_tools, prepared_source_root=source,
                prepared_document_id=prepared_document_id)
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['estimator_scope_experiment'] = {'candidate': candidate,
            'hint': SCOPE_HINT if candidate else None, 'estimates': estimates,
            'placement':placement,'native_tools':native_tools,'definition_exposures':definition_exposures,
            'limitation': 'Experimental scope text in result or SDK tool description; scores, signals, argument/result schema and ceilings unchanged. Not registered production description adoption.'}
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        print(json.dumps({'cell': index, 'committed': row['boundary_success'], 'estimates': len(estimates)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--objective', required=True)
    parser.add_argument('--placement', choices=('result','description'), default='result')
    parser.add_argument('--prepared-document-id')
    parser.add_argument('--native-tools', action='store_true')
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.output.resolve(), args.objective, args.placement, args.prepared_document_id, args.native_tools)
