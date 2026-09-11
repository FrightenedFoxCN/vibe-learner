"""Bounded query-relevant original text slices for cross-session retrieval."""
import math
import re
from typing import Callable

def select_memory_excerpt(text: str, query: str, *, tokenize: Callable[[str], list[str]], limit: int = 800) -> str:
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
