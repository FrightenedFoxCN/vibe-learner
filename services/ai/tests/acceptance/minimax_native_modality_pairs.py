"""Compare native Planning image-tool availability on one prepared document."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services.plan_tool_runtime import PlanToolRuntime
from tests.acceptance.minimax_planning_probe import run


def compare(source, pdf, output, objective, prepared_document_id=None):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    original = PlanToolRuntime.execute_tool_call
    for index, multimodal in enumerate((False, True, True, False)):
        reads = []

        def observe(runtime, tool_call):
            execution = original(runtime, tool_call)
            result = execution.provider_result
            if execution.tool_name in {'read_page_range_content', 'read_page_range_images'}:
                entry = {'tool_name': execution.tool_name, 'ok': result.get('ok'),
                         'error': result.get('error')}
                if result.get('ok') is True:
                    for key in ('page_start', 'page_end', 'chunk_count', 'image_count', 'page_numbers'):
                        if key in result:
                            entry[key] = result[key]
                    if isinstance(result.get('content'), str):
                        entry['returned_characters'] = len(result['content'])
                reads.append(entry)
            return execution

        cell = output / f'{index}-{"image" if multimodal else "text"}'
        with patch.object(PlanToolRuntime, 'execute_tool_call', observe):
            run(cell, 1, selected_case='document', pdf_path=pdf,
                objective_override=objective, multimodal=multimodal,
                persona_domain='text', persona_method='explorer',
                prepared_source_root=source, prepared_document_id=prepared_document_id)
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['native_modality_experiment'] = {
            'requested_image_tool_available': multimodal, 'reads': reads,
            'limitation': 'Availability intervention, not forced image acquisition. Catalog differs between groups; actual image exposure and source accuracy require separate review. No injected images or source transcription.'}
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        print(json.dumps({'cell': index, 'committed': row['boundary_success'],
                          'calls': len(row['calls'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--objective', required=True)
    parser.add_argument('--prepared-document-id')
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.output.resolve(),
            args.objective, args.prepared_document_id)
