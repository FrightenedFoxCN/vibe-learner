"""Real Planning comparison of estimator scope disclosure, with unchanged scores."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import patch

import app.services.plan_tool_runtime as runtime
from tests.acceptance.minimax_planning_probe import run


SCOPE_HINT = (
    '此分数只反映当前学习单元与子标题元数据，不评审你草拟的最终计划；'
    '只改变focus或重复调用不会使分数自动提高。'
    '若已核对材料且原文没有更细目录，可据真实页码组织活动并明确证据边界，'
    '不为提分杜撰子标题或反复拆分；最终计划仍须满足用户目标、引用与结构规则。'
)


def compare(source, pdf, output, objective):
    output.mkdir(parents=True, exist_ok=False)
    original = runtime._execute_estimate_plan_completion
    rows = []
    for index, candidate in enumerate([False, True, True, False]):
        estimates = []

        def observe(arguments, context):
            result = original(arguments, context)
            if candidate:
                result = replace(result, payload={**result.payload,
                    'recommendations': [SCOPE_HINT, *result.payload['recommendations']]})
            estimates.append({'unit_ranges': [[u.page_start, u.page_end] for u in context.study_units if u.include_in_plan],
                'score': result.payload['completion_score'], 'signals': result.payload['signals'],
                'missing_items': result.payload['missing_items'], 'scope_hint_sent': candidate})
            return result

        cell = output / f'{index}-{"candidate" if candidate else "baseline"}'
        with patch.object(runtime, '_execute_estimate_plan_completion', observe):
            run(cell, 1, selected_case='document', pdf_path=pdf, objective_override=objective,
                multimodal=True, persona_domain='text', persona_method='explorer',
                page_evidence='text_image', page_evidence_page=2,
                controlled_page_evidence=True, prepared_source_root=source)
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['estimator_scope_experiment'] = {'candidate': candidate,
            'hint': SCOPE_HINT if candidate else None, 'estimates': estimates,
            'limitation': 'Experimental recommendation added before existing result adapter; scores, signals, schema and ceilings unchanged.'}
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        print(json.dumps({'cell': index, 'committed': row['boundary_success'], 'estimates': len(estimates)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--objective', required=True)
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.output.resolve(), args.objective)
