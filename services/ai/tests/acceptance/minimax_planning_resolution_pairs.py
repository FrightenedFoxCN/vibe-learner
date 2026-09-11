"""Fixed-source/fixed-persona page resolution ablation; retain no source text."""
import base64
import argparse
import json
from pathlib import Path
from unittest.mock import patch
import fitz
import httpx
from app.services.provider_sdk import ProviderRequestAdapter
from tests.acceptance.minimax_planning_probe import run


def compare(source: Path, pdf: Path, output: Path, page: int, native_tool: bool = False, isolate_first_tool: bool = False):
    if isolate_first_tool and not native_tool:
        raise ValueError("First-tool isolation requires native tool mode")
    output.mkdir(parents=True, exist_ok=False)
    objective = json.loads((source / 'report.jsonl').read_text().splitlines()[0])['objective']
    original = ProviderRequestAdapter.request_chat_completion
    baseline = None
    rows = []
    cells = ([(None, False), (None, True), (None, True), (None, False)] if isolate_first_tool else
             [(dpi, False) for dpi in ([None, None] if native_tool else [100, 180, 180, 100])])
    for i, (dpi, isolate) in enumerate(cells):
        observed = {}
        sent_dimensions = []
        wire_requests = []
        def observe(adapter, payload, *, request_kind, model):
            nonlocal baseline
            if not observed:
                context = None
                for message in payload.get('messages', []):
                    if message.get('role') != 'user' or not isinstance(message.get('content'), str):
                        continue
                    try:
                        parsed = json.loads(message['content'])
                    except ValueError:
                        continue
                    if isinstance(parsed, dict) and 'learning_goal' in parsed and 'persona' in parsed:
                        # Same persona specification but each app operation has its own identities.
                        context = {k: v for k, v in parsed.items() if k != 'persona'}
                        break
                if baseline is None:
                    baseline = context
                observed['nonpersona_initial_context_equal'] = context is not None and context == baseline
            if isolate and not sent_dimensions:
                payload = {**payload, "tools": [t for t in payload.get("tools", [])
                    if t.get("function", {}).get("name") == "read_page_range_images"]}
            dimensions = []
            for message in payload.get('messages', []):
                content = message.get('content')
                if not isinstance(content, list):
                    continue
                for part in content:
                    url = part.get('image_url', {}).get('url', '') if part.get('type') == 'image_url' else ''
                    if url.startswith('data:image/png;base64,'):
                        pix = fitz.Pixmap(base64.b64decode(url.split(',', 1)[1]))
                        dimensions.append([pix.width, pix.height])
            sent_dimensions.append(dimensions)
            original_send = httpx.Client.send
            def observe_wire(client, request, *args, **kwargs):
                if request.url.host == 'api.minimax.cn' and request.url.path.endswith('/chat/completions'):
                    body = json.loads(request.content)
                    wire_requests.append({
                        'sdk_request_index': len(sent_dimensions)-1,
                        'tool_choice': body.get('tool_choice'),
                        'offered_tools': [t.get('function', {}).get('name') for t in body.get('tools', [])],
                        'image_parts': sum(part.get('type') == 'image_url'
                            for m in body.get('messages', []) if isinstance(m.get('content'), list)
                            for part in m['content'] if isinstance(part, dict)),
                    })
                return original_send(client, request, *args, **kwargs)
            with patch.object(httpx.Client, 'send', observe_wire):
                return original(adapter, payload, request_kind=request_kind, model=model)
        cell = output / f'{i}-{dpi}'
        with patch.object(ProviderRequestAdapter, 'request_chat_completion', observe):
            run(cell, 1, selected_case='document', pdf_path=pdf, objective_override=objective,
                multimodal=True, persona_variant='rigorous', persona_domain='text',
                page_evidence=None if native_tool else 'text_image', page_evidence_page=page, page_evidence_dpi=dpi or 144,
                initial_evidence_tool='read_page_range_images' if native_tool else None,
                controlled_page_evidence=not native_tool, prepared_source_root=source)
        row = json.loads((cell / 'report.jsonl').read_text())
        with fitz.open(pdf) as document:
            pix = document[page-1].get_pixmap(dpi=dpi or 144)
            observed['local_image_dimensions'] = [pix.width, pix.height]
        row['resolution_comparison'] = {**observed, 'cell': i, 'dpi': dpi, 'native_tool_path': native_tool,
            'sdk_image_dimensions_per_request': sent_dimensions,
            'first_tool_catalog_isolated': isolate, 'wire_requests': wire_requests,
            'limitation': 'Same rigorous persona definition; provider may resize images; local dimensions do not prove internal visual resolution.'}
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
        print(json.dumps({'cell':i,'dpi':dpi,'boundary_success':row['boundary_success']}),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--pdf', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--page', type=int, required=True)
    p.add_argument('--native-tool', action='store_true')
    p.add_argument('--isolate-first-tool', action='store_true')
    a=p.parse_args();compare(a.source.resolve(), a.pdf.resolve(), a.output.resolve(), a.page, a.native_tool, a.isolate_first_tool)
