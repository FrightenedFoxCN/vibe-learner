"""Compare initial-prompt timestamp wording with explicit activity durations."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services.provider_sdk import ProviderRequestAdapter
from tests.acceptance.minimax_planning_probe import run


ORIGINAL = '不要输出 plan、schedule 或 schedule_chapter 的 ID、revision、状态或时间；这些提交身份由应用在校验后分配。'
CANDIDATE = ('不要输出 plan、schedule 或 schedule_chapter 的 ID、revision、状态或创建/更新时间戳；'
             '这些提交身份由应用在校验后分配。学习活动的持续时长不属于时间戳，应按用户目标明确分配，'
             '并说明复盘、自测是否包含在阶段时长内。')


def compare(source, pdf, transcription, output, objective):
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    original_request = ProviderRequestAdapter.request_chat_completion
    for index, candidate in enumerate((False, True, True, False)):
        exposures = []

        def observe(adapter, payload, *, request_kind, model):
            messages = []
            occurrences = 0
            for message in payload.get('messages', []):
                if message.get('role') == 'system' and isinstance(message.get('content'), str):
                    occurrences += message['content'].count(ORIGINAL)
                    if candidate:
                        message = {**message, 'content': message['content'].replace(ORIGINAL, CANDIDATE)}
                messages.append(message)
            if not exposures and occurrences != 1:
                raise ValueError('initial_timing_experiment_prompt_mismatch')
            exposures.append({'original_occurrences': occurrences, 'candidate_applied': candidate and occurrences > 0})
            return original_request(adapter, {**payload, 'messages': messages},
                                    request_kind=request_kind, model=model)

        cell = output / f'{index}-{"candidate" if candidate else "baseline"}'
        with patch.object(ProviderRequestAdapter, 'request_chat_completion', observe):
            run(cell, 1, selected_case='document', pdf_path=pdf, objective_override=objective,
                multimodal=True, persona_domain='text', persona_method='explorer',
                page_evidence='text_image', page_evidence_page=1, page_evidence_dpi=144,
                controlled_page_evidence=True, prepared_source_root=source,
                transcription_file=transcription, transcription_source='experimental_native_vision_ocr')
        row = json.loads((cell / 'report.jsonl').read_text().splitlines()[0])
        row['initial_timing_experiment'] = {'candidate': candidate, 'exposures': exposures,
            'replacement': CANDIDATE if candidate else None,
            'limitation': 'Initial system wording intervention only; repair prompt, schemas, tool limits and commit validation unchanged. One source/persona; not independent certification.'}
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
        print(json.dumps({'cell': index, 'committed': row['boundary_success'], 'calls': len(row['calls'])}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'pdf', 'transcription', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--objective', required=True)
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.transcription.resolve(),
            args.output.resolve(), args.objective)
