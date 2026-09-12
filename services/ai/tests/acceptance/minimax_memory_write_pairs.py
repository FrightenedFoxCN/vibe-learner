"""Compare faithful summaries and verbatim storage through real Study effects."""
import argparse
import json
from pathlib import Path

from tests.acceptance.minimax_study_probe import MEMORY_SOURCE_FACTS, run


def compare(output):
    output.mkdir(parents=True, exist_ok=False)
    with (output / 'report.jsonl').open('x') as stream:
        for index, variant in enumerate(('summary', 'verbatim', 'verbatim', 'summary')):
            cell = output / f'{index}-{variant}'
            run(cell, 1, selected_case='memory_source_' + variant)
            row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
            result = (row.get('receipt') or {}).get('result') or {}
            memories = result.get('session', {}).get('session_memory', [])
            selected = [m for m in memories if m['key'] == 'rdv_reference']
            row['memory_write_comparison'] = {'cell': index, 'variant': variant,
                'independent_database': True, 'source_text': MEMORY_SOURCE_FACTS,
                'matching_memory_count': len(selected),
                'stored_contents': [m['content'] for m in selected],
                'exact_source_equal': len(selected) == 1 and selected[0]['content'] == MEMORY_SOURCE_FACTS,
                'tool_names': [t['tool_name'] for t in result.get('tool_calls', [])],
                'limitation': 'Different requested storage modes on one synthetic source; exact equality is required only for verbatim mode. No production change.'}
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
            stream.flush()
            print(json.dumps({'cell': index, 'variant': variant, 'boundary_success': row['boundary_success'],
                'calls': len(row['calls']), 'exact_source_equal': row['memory_write_comparison']['exact_source_equal']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    compare(parser.parse_args().output.resolve())
