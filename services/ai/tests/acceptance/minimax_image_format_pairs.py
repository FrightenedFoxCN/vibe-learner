"""Synthetic page-image tool format transfer; explicit per-case shape, not production."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from tests.acceptance import minimax_study_probe as probe


def compare(output: Path):
    output.mkdir(parents=True, exist_ok=False)
    original = probe._chat_prompt_sections
    rows = []
    conditions = [(2, False), (2, True), (3, True), (3, False),
                  (3, False), (3, True), (2, True), (2, False)]
    for i, (count, candidate) in enumerate(conditions):
        numeral = {2: '两', 3: '三'}[count]
        request = ('请先调用 read_page_range_images 查看教材 PDF 第1页，核对例题 2x+3=11，'
                   f'再用恰好{numeral}条 Markdown 无序列表说明求解和代入检验。'
                   '不要开场白和结尾，不要出题。')
        suffix = (f'\n本实验用户明确要求恰好{numeral}条Markdown无序列表。text字段必须恰好{count}行，'
                  '每行以减号和空格开头；不得再有标题、开场、结尾、空白行或嵌套列表。'
                  '不得为了行数限制遗漏求解依据和代入检验。称呼可置于列表项内，动作和情绪放在各自字段。')
        def sections():
            return {key: value + (suffix if candidate and key in {'system', 'tool_followup', 'recovery'} else '')
                    for key, value in original().items()}
        root = output / f'{i}-{count}-{int(candidate)}'
        with patch.object(probe, '_chat_prompt_sections', sections), patch.dict(probe.CASES, document_image_tool=request):
            probe.run(root, 1, 'document_image_tool', multimodal=True)
        row = json.loads((root / 'report.jsonl').read_text())
        row.update(format_condition='shape_only' if candidate else 'baseline', required_lines=count,
                   experimental_shape_instruction=suffix if candidate else None)
        row['trace_limitation'] = 'Synthetic identical page content with independent document/session identities; explicit case-specific shape candidate; no production adoption. SDK image parts are not wire evidence.'
        rows.append(row)
        (output / 'report.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in rows))
        print(json.dumps({'cell': i, 'lines': count, 'candidate': candidate, 'boundary_success': row['boundary_success']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    compare(parser.parse_args().output.resolve())
