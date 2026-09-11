"""Experimental contiguous original-text window; no production adoption."""
import math
import re
from app.services.study_memory import _tokenize, _truncate


def query_window(text: str, query: str, limit: int = 800) -> str:
    compact = ' '.join(text.strip().split())
    if len(compact) <= limit:
        return compact
    # Keep sentence boundaries and adjacent qualifiers rather than joining
    # unrelated matching phrases. Long unpunctuated spans still use a prefix.
    spans = list(re.finditer(r'[^。！？.!?]+[。！？.!?]*', compact))
    tokens = set(_tokenize(query))
    if not spans or not tokens:
        return _truncate(compact, limit)
    def score(i):
        words = set(_tokenize(spans[i].group()))
        return len(words & tokens) / math.sqrt(max(1, len(words)))
    best = max(range(len(spans)), key=score)
    if score(best) == 0 or spans[best].end() - spans[best].start() > limit - 6:
        return _truncate(compact, limit)
    left = right = best
    budget = limit - 6
    # Expand contiguously, prioritizing the preceding sentence so a matching
    # quote can retain its surrounding cancellation/archive qualification.
    while True:
        changed = False
        if left and spans[right].end() - spans[left-1].start() <= budget:
            left -= 1; changed = True
        if right+1 < len(spans) and spans[right+1].end() - spans[left].start() <= budget:
            right += 1; changed = True
        if not changed:
            break
    start, end = spans[left].start(), spans[right].end()
    return ('...' if start else '') + compact[start:end] + ('...' if end < len(compact) else '')


def query_windows(text: str, query: str, limit: int = 800) -> str:
    """Up to three disjoint sentence neighborhoods with normalized-text offsets."""
    compact = ' '.join(text.strip().split())
    if len(compact) <= limit:
        return compact
    spans = list(re.finditer(r'[^。！？.!?]+[。！？.!?]*', compact))
    tokens = set(_tokenize(query))
    ranked = []
    for i, span in enumerate(spans):
        words = set(_tokenize(span.group()))
        overlap = len(words & tokens)
        if overlap:
            ranked.append((overlap / math.sqrt(max(1, len(words))), i))
    selected = []
    seen = set()
    for _, i in sorted(ranked, key=lambda item: (-item[0], item[1])):
        if spans[i].group() in seen or any(a <= i <= b for a, b in selected):
            continue
        if spans[i].end() - spans[i].start() > 200:
            continue
        a = b = i
        if a and spans[b].end() - spans[a-1].start() <= 200:
            a -= 1
        if b+1 < len(spans) and spans[b+1].end() - spans[a].start() <= 200:
            b += 1
        if any(not (b < left or a > right) for left, right in selected):
            a = b = i
        selected.append((a, b)); seen.add(spans[i].group())
        if len(selected) == 3:
            break
    if not selected:
        return _truncate(compact, limit)
    result = '原文节选（位置为规范化文本字符，未覆盖全文）：'
    for a, b in sorted(selected):
        start, end = spans[a].start(), spans[b].end()
        part = f'\n[字符{start}:{end}] ' + compact[start:end]
        if len(result) + len(part) > limit:
            break
        result += part
    return result
