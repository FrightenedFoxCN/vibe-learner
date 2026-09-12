"""Experimental neighborhood backoff; never used by production retrieval."""
import math
import re
from typing import Callable

def candidate_select_memory_excerpt(text: str, query: str, *, tokenize: Callable[[str], list[str]], limit: int = 800) -> str:
    """Select sentence neighborhoods by total rendered cost, then expand them."""
    compact = ' '.join(text.strip().split())
    if len(compact) <= limit:
        return compact
    spans = list(re.finditer(r'[^。！？.!?]+[。！？.!?]*', compact))
    tokens = set(tokenize(query))
    ranked = []
    for i, span in enumerate(spans):
        words = set(tokenize(span.group()))
        if words & tokens:
            ranked.append((len(words & tokens) / math.sqrt(max(1, len(words))), i))
    if not ranked:
        return compact[:limit - 3] + "..."

    def merge(items):
        merged = []
        for a, b in sorted(items):
            if merged and a <= merged[-1][1] + 1:
                merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
            else:
                merged.append((a, b))
        return merged

    def render(items):
        out = '原文节选（位置为规范化文本字符，未覆盖全文）：'
        for a, b in items:
            start, end = spans[a].start(), spans[b].end()
            out += f'\n[字符{start}:{end}] ' + compact[start:end]
        return out

    last = max(ranked, key=lambda item: item[1])
    ordered = [last] + sorted((item for item in ranked if item != last), key=lambda item: (-item[0], item[1]))
    selected = []
    for _, i in ordered:
        if any(a <= i <= b for a, b in selected):
            continue
        # Preserve nearby qualification, not just the matching sentence.
        proposal = merge(selected + [(max(0, i - 2), min(len(spans) - 1, i + 1))])
        if len(render(proposal)) <= limit:
            selected = proposal
        else:
            # Try smaller whole-sentence neighborhoods; this can omit a long
            # adjacent qualification and therefore requires semantic review.
            for start, end in ((max(0, i - 1), min(len(spans) - 1, i + 1)),
                               (i, min(len(spans) - 1, i + 1)), (i, i)):
                smaller = merge(selected + [(start, end)])
                if len(render(smaller)) <= limit:
                    selected = smaller
                    break
    if not selected:
        return compact[:limit - 3] + "..."
    # Only spend remaining budget on context after all matching regions have
    # had a chance to enter. Every accepted proposal remains a source slice.
    while True:
        expanded = False
        for a, b in list(selected):
            proposal = merge(selected + [(max(0, a - 1), min(len(spans) - 1, b + 1))])
            if proposal != selected and len(render(proposal)) <= limit:
                selected = proposal; expanded = True
        if not expanded:
            return render(selected)


def diagnose():
    from app.services.memory_excerpt import select_memory_excerpt
    from app.services.study_memory import _tokenize
    from tests.acceptance.minimax_memory_selector_limits import CASES

    cases = [*CASES,
        ('nearby_archive_qualification', '地点白桦，暗号已撤销。' + '整理材料' * 600
         + '。以下只引用旧记录，不恢复约定。地点青石，暗号晴鸟。归档引用完毕。',
         '地点和暗号', '不恢复约定'),
        ('long_qualifier_before_quote', '地点白桦，暗号已撤销。'
         + '以下只是小说，不是真实约定，' + '整理材料' * 600 + '。地点青石，暗号晴鸟。',
         '地点和暗号', '不是真实约定')]
    rows = []
    for name, text, query, expected in cases:
        for variant, fn in [('baseline', select_memory_excerpt),
                            ('candidate', candidate_select_memory_excerpt)]:
            out = fn(text, query, tokenize=_tokenize)
            rows.append({'case': name, 'variant': variant, 'input_chars': len(text),
                         'excerpt_chars': len(out), 'expected_fragment': expected,
                         'retained': expected in out, 'excerpt': out})
    return rows


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(diagnose(), stream, ensure_ascii=False, indent=2)
        stream.write('\n')
