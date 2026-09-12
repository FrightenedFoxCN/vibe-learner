"""Request an initial estimate and observe safe tool metadata in model requests.

Diagnostic scheduling only; does not change production tool admission.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services.provider_sdk import ProviderRequestAdapter
from tests.acceptance.minimax_planning_probe import run


def probe(source, pdf, transcription, output, objective):
    output.mkdir(parents=True, exist_ok=False)
    original = ProviderRequestAdapter.request_chat_completion
    rows = []
    for index in range(2):
        observations = []

        def observe(adapter, payload, *, request_kind, model):
            estimates = []
            for message in payload.get('messages', []):
                if message.get('role') != 'tool':
                    continue
                try:
                    value = json.loads(message.get('content', ''))
                except (ValueError, TypeError):
                    continue
                if isinstance(value, dict) and value.get('tool_name') == 'estimate_plan_completion':
                    estimates.append({key: value.get(key) for key in
                                      ('completion_score', 'completion_label', 'signals', 'missing_items')})
            forced = not observations
            if forced:
                payload = {**payload, 'tool_choice': {'type': 'function',
                           'function': {'name': 'estimate_plan_completion'}}}
            observations.append({'forced_initial_estimate': forced, 'estimate_results_in_request': estimates})
            return original(adapter, payload, request_kind=request_kind, model=model)

        cell = output / str(index)
        with patch.object(ProviderRequestAdapter, 'request_chat_completion', observe):
            run(cell, 1, selected_case='document', pdf_path=pdf, objective_override=objective,
                multimodal=True, persona_domain='text', persona_method='explorer',
                page_evidence='text_image', page_evidence_page=1, page_evidence_dpi=144,
                controlled_page_evidence=True, prepared_source_root=source,
                transcription_file=transcription, transcription_source='experimental_native_vision_ocr')
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['estimate_exposure_observations'] = observations
        row['scheduling_limitation'] = ('Initial tool_choice override requested at adapter wrapper; provider may not obey. '
            'Base probe call metadata is captured before this wrapper override; no HTTP wire observation. '
            'Two repetitions; no baseline or production scheduling adoption.')
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        print(json.dumps({'cell': index, 'committed': row['boundary_success'], 'calls': len(row['calls'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'transcription', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--objective', required=True)
    args = parser.parse_args()
    probe(args.source.resolve(), args.pdf.resolve(), args.transcription.resolve(),
          args.output.resolve(), args.objective)
