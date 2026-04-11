from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Callable

from app.models.domain import DialogueTurnRecord, MemoryTraceHitRecord, StudySessionRecord

_VECTOR_SIZE = 384


@dataclass
class _MemoryCandidate:
    session_id: str
    section_id: str
    scene_title: str
    snippet: str
    created_at: str
    vector: list[float]


def retrieve_memory_hits(
    *,
    sessions: list[StudySessionRecord],
    current_session_id: str,
    active_section_id: str,
    query: str,
    active_scene_summary: str,
    top_k: int = 5,
    embed_texts: Callable[[list[str]], list[list[float]]] | None = None,
) -> list[MemoryTraceHitRecord]:
    candidates = _build_candidates(sessions=sessions, current_session_id=current_session_id)
    if not candidates:
        return []

    vectors = _embed_query_and_candidates(
        query=query,
        candidates=candidates,
        embed_texts=embed_texts,
    )
    if vectors is None:
        return []
    query_vector, candidate_vectors = vectors

    scored: list[tuple[float, _MemoryCandidate]] = []
    for candidate, candidate_vector in zip(candidates, candidate_vectors):
        score = _cosine(query_vector, candidate_vector)
        if score <= 0:
            continue
        if candidate.section_id == active_section_id:
            score += 0.08
        if active_scene_summary and candidate.scene_title != "未设置场景":
            score += 0.03
        scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    results: list[MemoryTraceHitRecord] = []
    for score, candidate in scored[:top_k]:
        results.append(
            MemoryTraceHitRecord(
                session_id=candidate.session_id,
                section_id=candidate.section_id,
                scene_title=candidate.scene_title,
                score=round(score, 4),
                snippet=candidate.snippet,
                created_at=candidate.created_at,
                source="retriever",
            )
        )
    return results


def build_memory_context(hits: list[MemoryTraceHitRecord]) -> str:
    if not hits:
        return ""
    lines = [
        (
            f"- score={hit.score:.4f} | session={hit.session_id} | section={hit.section_id} "
            f"| scene={hit.scene_title} | snippet={hit.snippet}"
        )
        for hit in hits
    ]
    return "Retrieved cross-session memory:\n" + "\n".join(lines)


def _build_candidates(
    *,
    sessions: list[StudySessionRecord],
    current_session_id: str,
) -> list[_MemoryCandidate]:
    candidates: list[_MemoryCandidate] = []
    for session in sessions:
        if session.id == current_session_id:
            continue
        scene_title = session.scene_profile.title if session.scene_profile else "未设置场景"
        for turn in session.turns:
            merged = _merge_turn(turn)
            if not merged:
                continue
            candidates.append(
                _MemoryCandidate(
                    session_id=session.id,
                    section_id=session.section_id,
                    scene_title=scene_title,
                    snippet=_truncate(merged, 180),
                    created_at=turn.created_at,
                    vector=[],
                )
            )
    return candidates


def _merge_turn(turn: DialogueTurnRecord) -> str:
    learner = turn.learner_message.strip()
    assistant = turn.assistant_reply.strip()
    merged = f"{learner}\n{assistant}".strip()
    return merged


def _embed(text: str) -> list[float]:
    tokens = _tokenize(text)
    vec = [0.0] * _VECTOR_SIZE
    if not tokens:
        return vec
    for token in tokens:
        idx = hash(token) % _VECTOR_SIZE
        vec[idx] += 1.0
    norm = math.sqrt(sum(value * value for value in vec))
    if norm <= 0:
        return vec
    return [value / norm for value in vec]


def _embed_query_and_candidates(
    *,
    query: str,
    candidates: list[_MemoryCandidate],
    embed_texts: Callable[[list[str]], list[list[float]]] | None,
) -> tuple[list[float], list[list[float]]] | None:
    texts = [query, *[candidate.snippet for candidate in candidates]]
    if embed_texts is not None:
        try:
            embeddings = embed_texts(texts)
            if len(embeddings) == len(texts) and embeddings[0]:
                return embeddings[0], embeddings[1:]
        except Exception:
            pass

    query_vector = _embed(query)
    if not any(query_vector):
        return None
    candidate_vectors = [_embed(candidate.snippet) for candidate in candidates]
    return query_vector, candidate_vectors


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", text.lower())]


def _truncate(text: str, limit: int) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
