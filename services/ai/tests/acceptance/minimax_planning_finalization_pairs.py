"""Live ABBA comparison of bounded tool collection followed by plan drafting."""
import argparse
import json
from pathlib import Path

from tests.acceptance.minimax_planning_probe import run


def compare(source, pdf, output, objective, tool_rounds=3, prepared_document_id=None):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for index, candidate in enumerate((False, True, True, False)):
        cell = output / f'{index}-{"candidate" if candidate else "baseline"}'
        run(cell, 1, selected_case='document', pdf_path=pdf,
            objective_override=objective, multimodal=True,
            persona_domain='text', persona_method='explorer',
            prepared_source_root=source, prepared_document_id=prepared_document_id,
            finalize_after_tool_rounds=tool_rounds if candidate else None)
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['finalization_comparison'] = {
            'candidate': candidate, 'tool_round_threshold': tool_rounds if candidate else None,
            'limitation': 'Experimental SDK tool removal and drafting reminder after tool-response rounds. Existing domain validation, repair and time budget remain. Not a production scheduling change or guarantee that finalization fits the budget.'}
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        print(json.dumps({'cell': index, 'committed': row['boundary_success'],
                          'calls': len(row['calls'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--objective', required=True)
    parser.add_argument('--tool-rounds', type=int, choices=range(1, 13), default=3)
    parser.add_argument('--prepared-document-id')
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.output.resolve(),
            args.objective, args.tool_rounds, args.prepared_document_id)
