"""Synthetic scene task completion, separate from Chat/Harness commit success."""
import argparse
from collections import Counter
import json
from pathlib import Path


def review(paths):
    rows = []
    for path in paths:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get('case_id') not in {'scene_object_lifecycle', 'scene_navigation'}:
                continue
            result = (row.get('receipt') or {}).get('result') or {}
            scene = result.get('session', {}).get('scene_profile') or {}
            nodes, objects = [], []

            def visit(tree):
                for node in tree:
                    nodes.append(node)
                    objects.extend(node.get('objects', []))
                    visit(node.get('children', []))

            visit(scene.get('scene_tree', []))
            successes = Counter()
            errors = Counter()
            last_read = last_mutation = -1
            for index, tool in enumerate(result.get('tool_calls', [])):
                payload = json.loads(tool['result_json'])
                if payload.get('ok') is True:
                    successes[tool['tool_name']] += 1
                    if tool['tool_name'] == 'read_scene_overview':
                        last_read = index
                    elif tool['tool_name'] in {'add_scene', 'move_to_scene', 'add_object', 'update_object_description', 'delete_object'}:
                        last_mutation = index
                else:
                    errors[payload.get('error', 'unknown')] += 1
            board = [obj for obj in objects if obj['name'] == '白板']
            cards = [obj for obj in objects if obj['name'] == '验算卡']
            corners = [node for node in nodes if node['title'] == '验算角']
            if row['case_id'] == 'scene_object_lifecycle':
                state_ok = len(board) == 1 and board[0]['description'] == '写有方程 2x+3=11 的白板' and not cards
                required = ['read_scene_overview', 'update_object_description', 'add_object', 'delete_object']
            else:
                state_ok = len(corners) == 1 and scene.get('scene_id') == corners[0]['id'] and corners[0]['summary'] == '专门核对方程解的安静角落'
                required = ['read_scene_overview', 'add_scene', 'move_to_scene']
            rows.append({'source': path.name, 'operation_id': row.get('harness_operation_id'),
                'case_id': row['case_id'], 'repetition': row['repetition'], 'boundary_success': row['boundary_success'],
                'final_state_matches_task': state_ok, 'required_tools_succeeded': all(successes[t] > 0 for t in required),
                'readback_after_last_mutation': last_read > last_mutation >= 0,
                'successful_tools': dict(successes), 'tool_errors': dict(errors),
                'provider_requests': len(row['calls']), 'elapsed_ms': row['elapsed_ms'],
                'reply': result.get('reply'), 'final_scene_title': scene.get('title')})
    return {'scope': 'synthetic scene fixture state/tool review', 'limitations': [
        'Developer-authored fixture checks, not independent review.',
        'Final state and successful tool receipts do not prove every ordering or all dialogue claims.',
        'Provider identity diagnostics exist only for instrumented runs, never inferred from redacted public traces.'], 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, nargs='+', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(review(args.evidence), ensure_ascii=False, indent=2) + '\n')
