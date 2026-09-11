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
