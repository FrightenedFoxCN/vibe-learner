"""Compare identical page images with and without supplementary native OCR."""
import argparse
import json
from pathlib import Path

from tests.acceptance.minimax_planning_probe import run


def compare(source, pdf, transcription, output, objective, persona_method='explorer'):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for index, candidate in enumerate((False, True, True, False)):
        cell = output / f'{index}-{"native-ocr" if candidate else "image"}'
        run(cell, 1, selected_case='document', pdf_path=pdf,
            objective_override=objective, multimodal=True,
            persona_domain='text', persona_method=persona_method,
            page_evidence='text_image', page_evidence_page=1, page_evidence_dpi=144,
            controlled_page_evidence=True, prepared_source_root=source,
            transcription_file=transcription if candidate else None,
            transcription_source='experimental_native_vision_ocr')
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['native_ocr_comparison'] = {
            'candidate': candidate, 'persona_method': persona_method,
            'image_dpi': 144, 'page': 1,
            'limitation': 'Same prepared snapshot and injected page image; candidate adds local OCR text. Five-tool catalog in both conditions. Not a production OCR replacement or independent certification.'}
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        print(json.dumps({'cell': index, 'committed': row['boundary_success'],
                          'calls': len(row['calls'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'transcription', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--objective', required=True)
    parser.add_argument('--persona-method', choices=('rigorous', 'explorer'), default='explorer')
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.transcription.resolve(),
            args.output.resolve(), args.objective, args.persona_method)
