"""Live ABBA comparison of bounded tool collection followed by plan drafting."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

import httpx

from tests.acceptance.minimax_planning_probe import run


def compare(source, pdf, output, objective, tool_rounds=3, prepared_document_id=None, policy_comparison=False):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for index, candidate in enumerate((False, True, True, False)):
        threshold = tool_rounds if candidate or policy_comparison else None
        policy = 'none' if policy_comparison and candidate else 'omit'
        wire_requests = []
        original_send = httpx.Client.send

        def observe_send(client, request, *args, **kwargs):
            if request.url.host == 'api.minimax.cn' and request.url.path.endswith('/chat/completions'):
                try:
                    body = json.loads(request.content)
                    wire_requests.append({
                        'tool_choice': body.get('tool_choice'),
                        'offered_tools': [t.get('function', {}).get('name') for t in body.get('tools', [])],
                        'response_format': body.get('response_format'),
                        'image_parts': sum(p.get('type') == 'image_url'
                            for m in body.get('messages', []) if isinstance(m.get('content'), list)
                            for p in m['content'] if isinstance(p, dict))})
                except (ValueError, TypeError, httpx.RequestNotRead):
                    wire_requests.append({'observation_error': 'body_unavailable_or_invalid'})
            return original_send(client, request, *args, **kwargs)

        cell = output / f'{index}-{"candidate" if candidate else "baseline"}'
        with patch.object(httpx.Client, 'send', observe_send):
            run(cell, 1, selected_case='document', pdf_path=pdf,
                objective_override=objective, multimodal=True,
                persona_domain='text', persona_method='explorer',
                prepared_source_root=source, prepared_document_id=prepared_document_id,
                finalize_after_tool_rounds=threshold, finalization_tool_policy=policy)
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['finalization_comparison'] = {
            'candidate': candidate, 'tool_round_threshold': threshold, 'tool_policy': policy,
            'policy_comparison': policy_comparison,
            'wire_requests': wire_requests,
            'limitation': 'Experimental SDK control and drafting reminder after tool-response rounds. Policy comparison uses omission versus retained tools with tool_choice none at the same threshold. Existing domain validation, repair and time budget remain. Independent model trajectories; not a fixed-request causal comparison or runtime disabling.'}
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
    parser.add_argument('--policy-comparison', action='store_true')
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.output.resolve(),
            args.objective, args.tool_rounds, args.prepared_document_id, args.policy_comparison)
