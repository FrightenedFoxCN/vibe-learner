"""Reviewed Study grounding algorithms; never infer source authorization from prose."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


_STOP = frozenset('the a an is are of to in and for with what when who which how does do this that current note unrelated only return answer unknown de la le les un une des du et est en pour quelle quel qui ce cette au aux avec par son sa source sans rapport'.split())


def citation_tokens(text: str) -> set[str]:
    value = unicodedata.normalize('NFKC', text).casefold()
    han = re.findall(r'[\u4e00-\u9fff]+', value)
    words = re.findall(r'[^\W_]+', re.sub(r'[\u4e00-\u9fff]+', ' ', value))
    tokens = {word for word in words if len(word) > 1 and word not in _STOP}
    for run in han:
        tokens.update(run[i:i + 2] for i in range(max(1, len(run) - 1)))
    return tokens


@dataclass(frozen=True)
class StudyVerbatimMemorySourceV1:
    """Application-owned source from the authorized current learner message only."""

    key: str
    content: str


def parse_verbatim_memory(message: str, message_kind: str) -> StudyVerbatimMemorySourceV1 | None:
    if message_kind != 'learner' or not message.startswith('/remember-verbatim'):
        return None
    match = re.fullmatch(r'/remember-verbatim ([A-Za-z0-9_-]{1,120})\n([\s\S]+)\n/end-remember', message)
    if match is None:
        raise ValueError('verbatim_memory_command_invalid')
    key, content = match.groups()
    # V1 memory effects require trimmed content. Refuse rather than alter a source.
    if not content or content != content.strip() or len(content) > 4000:
        raise ValueError('verbatim_memory_source_invalid')
    return StudyVerbatimMemorySourceV1(key=key, content=content)
