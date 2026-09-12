"""Run each event-time Study sample in its own database, retaining seed failures."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services.provider_sdk import ProviderRequestAdapter
from tests.acceptance.minimax_study_probe import run


SCOPE_ORIGINAL = '默认保持在当前学习单元内回答，除非用户明确要求切换上下文。'
SCOPE_CANDIDATE = ('默认围绕当前学习单元教学；用户明确要求记录、检索或核对其他资料时，'
                   '处理该请求，不因资料不属于本章而拒绝或自动转回讲课。')


def compare(output, scope_comparison=False):
    output.mkdir(parents=True, exist_ok=False)
    cells = [('fr', False), ('fr', True), ('fr', True), ('fr', False)] if scope_comparison else [
        (language, False) for language in ('zh', 'fr', 'fr', 'zh')]
    with (output / 'report.jsonl').open('x') as stream:
        for index, (language, candidate) in enumerate(cells):
            case = 'cross_session_memory_event_time' + ('_fr' if language == 'fr' else '')
            cell = output / f'{index}-{language}'
            failure = None
            exposures = []
            original = ProviderRequestAdapter.request_chat_completion

            def observe(adapter, payload, *, request_kind, model):
                count = 0
                messages = []
                for message in payload.get('messages', []):
                    if message.get('role') == 'system' and isinstance(message.get('content'), str):
                        count += message['content'].count(SCOPE_ORIGINAL)
                        if candidate:
                            message = {**message, 'content': message['content'].replace(SCOPE_ORIGINAL, SCOPE_CANDIDATE)}
                    messages.append(message)
                if request_kind == 'chat':
                    if not exposures and count < 1:
                        raise ValueError('scope_experiment_initial_prompt_mismatch')
                    exposures.append({'original_occurrences': count, 'candidate_applied': candidate and count > 0})
                return original(adapter, {**payload, 'messages': messages}, request_kind=request_kind, model=model)

            try:
                if scope_comparison:
                    with patch.object(ProviderRequestAdapter, 'request_chat_completion', observe):
                        run(cell, 1, selected_case=case)
                else:
                    run(cell, 1, selected_case=case)
            except Exception as exc:
                # Keep the admitted seed receipts even if the main case never ran.
                failure = type(exc).__name__
            report = cell / 'report.jsonl'
            lines = report.read_text().splitlines() if report.exists() else []
            if lines:
                if len(lines) != 1:
                    raise ValueError('isolated_case_expected_one_row')
                row = json.loads(lines[0])
            else:
                row = {'case_id': case, 'boundary_success': False, 'calls': [],
                       'failure_stage': 'fixture_preparation', 'error_class': failure,
                       'memory_seed_operations': []}
                for path in sorted(cell.glob('memory-seeds-*.json')):
                    row['memory_seed_operations'].extend(json.loads(path.read_text()))
            seed_ids = {seed['receipt']['session_id'] for seed in row.get('memory_seed_operations', [])}
            result = (row.get('receipt') or {}).get('result') or {}
            hits = result.get('memory_trace', [])
            row['isolation'] = {'cell_index': index, 'source_subdirectory': cell.name,
                'independent_database': True, 'seed_session_ids': sorted(seed_ids),
                'unexpected_memory_session_ids': sorted({hit['session_id'] for hit in hits} - seed_ids),
                'limitation': 'One sample per database; original seed replies remain visible and may themselves contain errors.'}
            row['reported_chat_calls_including_seeds'] = len(row['calls']) + sum(
                len(seed['calls']) for seed in row.get('memory_seed_operations', []))
            if scope_comparison:
                row['scope_experiment'] = {'candidate': candidate, 'exposures': exposures,
                    'replacement': SCOPE_CANDIDATE if candidate else None,
                    'limitation': 'Adapter system-text intervention, one French case/persona; not production adoption.'}
            if failure:
                row['run_exception_class'] = failure
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({'cell': index, 'language': language, 'boundary_success': row['boundary_success'],
                              'calls': row['reported_chat_calls_including_seeds']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--scope-comparison', action='store_true')
    args = parser.parse_args()
    compare(args.output.resolve(), args.scope_comparison)
