"""Compare source verification against an existing model-written document summary.

Each cell clones the same completed source. Source context is compared in memory;
only equality and a known error marker are retained, never full source text.
"""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services.provider_sdk import ProviderRequestAdapter
from tests.acceptance.minimax_planning_image_pairs import OBJECTIVE
from tests.acceptance.minimax_planning_probe import run

SUMMARY_VERIFICATION = (
    "\nStudy Unit标题和摘要是先前模型生成的导航材料，可能含识字或解释错误，不能当作原文。"
    "涉及原文概念、引文或左右栏位置时，先与本次提供的页图或可用正文核对；冲突时以清晰的原页为准。"
    "无法辨认的词不要猜写成结论，可安排学习者回页核对。人格决定活动方式，不改变原文事实。"
)


def omit_generated_summaries(payload):
    """Remove summary fields only from known planning context/tool JSON bodies."""
    def strip(value):
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k != 'summary'}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value

    messages = []
    for message in payload.get('messages', []):
        content = message.get('content')
        if message.get('role') not in ('user', 'tool') or not isinstance(content, str):
            messages.append(message)
            continue
        try:
            parsed = json.loads(content)
        except ValueError:
            messages.append(message)
            continue
        if isinstance(parsed, dict) and 'learning_goal' in parsed and 'study_units' in parsed:
            parsed = {**parsed, 'study_units': strip(parsed['study_units'])}
        elif message.get('role') == 'tool' and isinstance(parsed, dict) and parsed.get('schema_version') == 'planning-tool-result-v1':
            parsed = strip(parsed)
        else:
            messages.append(message)
            continue
        messages.append({**message, 'content': json.dumps(parsed, ensure_ascii=False)})
    return {**payload, 'messages': messages}


def compare(source: Path, pdf: Path, output: Path, remove_summaries=False):
    output.mkdir(parents=True, exist_ok=False)
    original = ProviderRequestAdapter.request_chat_completion
    baseline = None
    observations = []
    current = {}

    def observe(adapter, payload, *, request_kind, model):
        nonlocal baseline
        if not current.get('observed'):
            current['observed'] = True
            context = None
            for m in payload.get('messages', []):
                if m.get('role') != 'user' or not isinstance(m.get('content'), str):
                    continue
                try:
                    candidate = json.loads(m['content'])
                except ValueError:
                    continue
                if isinstance(candidate, dict) and 'learning_goal' in candidate and 'persona' in candidate:
                    context = {k: v for k, v in candidate.items() if k != 'persona'}
                    break
            if baseline is None and context is not None:
                baseline = context
            current['nonpersona_initial_context_equal'] = context is not None and context == baseline
            current['known_error_marker_present'] = context is not None and '期待性' in json.dumps(context, ensure_ascii=False)
            current['measurement_error'] = None if context is not None else 'initial_context_not_found'
            current['offered_tools'] = [t.get('function', {}).get('name') for t in payload.get('tools', [])]
        if remove_summaries and current['candidate']:
            payload = omit_generated_summaries(payload)
        elif current['candidate']:
            payload = {**payload, 'messages': [
                {**m, 'content': m['content'] + SUMMARY_VERIFICATION} if m.get('role') == 'system' else m
                for m in payload.get('messages', [])]}
        current.setdefault('request_marker_roles', []).append([
            m.get('role') for m in payload.get('messages', [])
            if isinstance(m.get('content'), str) and '期待性' in m['content']])
        return original(adapter, payload, request_kind=request_kind, model=model)

    with patch.object(ProviderRequestAdapter, 'request_chat_completion', observe):
        for persona, candidate in [('rigorous', False), ('explorer', True), ('rigorous', True), ('explorer', False)]:
            current = {'persona': persona, 'candidate': candidate}
            cell = output / f'{persona}-{int(candidate)}'
            run(cell, 1, selected_case='document', pdf_path=pdf, objective_override=OBJECTIVE,
                ocr_engine='onnxtr', multimodal=True, persona_variant=persona, page_evidence='text_image',
                page_evidence_page=1, persona_domain='text', controlled_page_evidence=True,
                prepared_source_root=source)
            row = json.loads((cell / 'report.jsonl').read_text())
            row['summary_verification_variant'] = ('omit-generated-summary-fields-v1' if remove_summaries else 'source-verification-suffix-v1') if candidate else 'production'
            row['experimental_summary_suffix'] = SUMMARY_VERIFICATION if candidate and not remove_summaries else None
            (cell / 'report.jsonl').write_text(json.dumps(row, ensure_ascii=False) + '\n')
            current.update(operation_id=row.get('harness_operation_id'), boundary_success=row['boundary_success'])
            observations.append(dict(current))
            (output / 'comparison.json').write_text(json.dumps({
                'scope': 'Experimental summary field removal' if remove_summaries else 'Experimental summary verification suffix with fixed source and page image',
                'candidate_suffix': None if remove_summaries else SUMMARY_VERIFICATION,
                'remove_summaries': remove_summaries,
                'limitations': ['One sample per persona/condition; not independent quality certification.',
                    'Image injection and prompt suffix are experimental, not production artifact replay.'],
                'rows': observations}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--remove-summaries', action='store_true')
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.output.resolve(), args.remove_summaries)
