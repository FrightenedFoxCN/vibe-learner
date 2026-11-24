"""Reviewed Study grounding algorithms; never infer source authorization from prose."""

from __future__ import annotations

import re
import unicodedata


_STOP = frozenset(
    "the a an is are of to in and for with what when who which how does do this that current note unrelated only return answer unknown de la le les un une des du et est en pour quelle quel qui ce cette au aux avec par son sa source sans rapport".split()
)


def citation_tokens(text: str) -> set[str]:
    value = unicodedata.normalize("NFKC", text).casefold()
    han = re.findall(r"[\u4e00-\u9fff]+", value)
    words = re.findall(r"[^\W_]+", re.sub(r"[\u4e00-\u9fff]+", " ", value))
    tokens = {word for word in words if len(word) > 1 and word not in _STOP}
    for run in han:
        tokens.update(run[i : i + 2] for i in range(max(1, len(run) - 1)))
    return tokens
