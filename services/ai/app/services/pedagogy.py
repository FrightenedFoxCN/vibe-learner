from __future__ import annotations

import re

from app.models.domain import (
    Citation,
    DialogueTurnRecord,
    DocumentDebugRecord,
    ExerciseResult,
    PersonaProfile,
    StudyChatResult,
    SubmissionGradeResult,
)
from app.services.model_provider import ModelProvider
from app.services.performance import PerformanceMapper


class PedagogyOrchestrator:
    def __init__(
        self, *, model_provider: ModelProvider, performance_mapper: PerformanceMapper
    ) -> None:
        self.model_provider = model_provider
        self.performance_mapper = performance_mapper

    def generate_chat_reply(
        self,
        *,
        session_id: str,
        persona: PersonaProfile,
        message: str,
        section_id: str,
        debug_report: DocumentDebugRecord | None = None,
        previous_turns: list[DialogueTurnRecord] | None = None,
    ) -> StudyChatResult:
        turns = previous_turns or []
        section_context = _build_section_context(debug_report=debug_report, section_id=section_id)
        conversation_history = _build_conversation_history(turns)
        raw_reply = self.model_provider.generate_chat(
            persona=persona,
            section_id=section_id,
            message=message,
            section_context=section_context,
            conversation_history=conversation_history,
        )
        citations = _build_grounded_citations(
            debug_report=debug_report,
            section_id=section_id,
            message=message,
        )
        turn_index = len(turns)
        events = self.performance_mapper.map_text_to_events(
            persona=persona,
            text=raw_reply.text,
            mood=raw_reply.mood,
            action=raw_reply.action,
            line_segment_id=f"{session_id}:chat:{turn_index}",
        )
        scene_hint = _build_scene_hint(section_id=section_id, citations=citations)
        for event in events:
            event.scene_hint = scene_hint
        return StudyChatResult(
            reply=raw_reply.text,
            citations=citations,
            character_events=events,
        )

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ExerciseResult:
        raw_reply = self.model_provider.generate_exercise(
            persona=persona, section_id=section_id, topic=topic
        )
        events = self.performance_mapper.map_text_to_events(
            persona=persona,
            text=raw_reply.text,
            mood=raw_reply.mood,
            action=raw_reply.action,
            line_segment_id=f"{section_id}:exercise:0",
        )
        return ExerciseResult(
            exercise_id=f"exercise-{section_id}",
            section_id=section_id,
            prompt=raw_reply.text,
            exercise_type="short_answer",
            difficulty="medium",
            guidance="先回忆教材定义，再写出一个对应示例。",
            character_events=events,
        )

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> SubmissionGradeResult:
        raw_reply = self.model_provider.grade_submission(
            persona=persona, exercise_id=exercise_id, answer=answer
        )
        events = self.performance_mapper.map_text_to_events(
            persona=persona,
            text=raw_reply.text,
            mood=raw_reply.mood,
            action=raw_reply.action,
            line_segment_id=f"{exercise_id}:grade:0",
        )
        score = 88 if len(answer.strip()) > 24 else 61
        diagnosis = (
            ["概念覆盖较全", "示例支撑充足"]
            if score > 80
            else ["定义不够完整", "缺少教材中的例子"]
        )
        recommendation = "回看本章定义段落后，再补写一个和教材一致的例子。"
        return SubmissionGradeResult(
            score=score,
            diagnosis=diagnosis,
            recommendation=recommendation,
            character_events=events,
        )


def _build_conversation_history(turns: list[DialogueTurnRecord]) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for turn in turns[-6:]:
        learner_text = turn.learner_message.strip()
        assistant_text = turn.assistant_reply.strip()
        if learner_text:
            history.append({"role": "user", "content": learner_text})
        if assistant_text:
            history.append({"role": "assistant", "content": assistant_text})
    return history


def _build_scene_hint(*, section_id: str, citations: list[Citation]) -> str:
    if not citations:
        return f"study_session:{section_id}:overview"
    start = min(citation.page_start for citation in citations)
    end = max(citation.page_end for citation in citations)
    return f"study_session:{section_id}:p{start}-{end}"


def _build_section_context(*, debug_report: DocumentDebugRecord | None, section_id: str) -> str:
    if debug_report is None:
        return f"Section ID: {section_id}"

    section_title = section_id
    page_start = 0
    page_end = 0
    related_ids = {section_id}

    study_unit = next((unit for unit in debug_report.study_units if unit.id == section_id), None)
    if study_unit is not None:
        section_title = study_unit.title
        page_start = study_unit.page_start
        page_end = study_unit.page_end
        related_ids.update(study_unit.source_section_ids)

    parsed_section = next((section for section in debug_report.sections if section.id == section_id), None)
    if parsed_section is not None and section_title == section_id:
        section_title = parsed_section.title
        page_start = parsed_section.page_start
        page_end = parsed_section.page_end

    chunks = [
        chunk
        for chunk in debug_report.chunks
        if chunk.section_id in related_ids
    ]
    if not chunks and page_start > 0 and page_end > 0:
        chunks = [
            chunk
            for chunk in debug_report.chunks
            if chunk.page_end >= page_start and chunk.page_start <= page_end
        ]
    excerpts = [
        _truncate_for_prompt(chunk.content or chunk.text_preview, limit=220)
        for chunk in chunks[:2]
        if (chunk.content or chunk.text_preview).strip()
    ]
    excerpt_text = "\n".join(f"- {line}" for line in excerpts)
    if excerpt_text:
        return (
            f"Section: {section_title} ({section_id})\n"
            f"Pages: {page_start}-{page_end}\n"
            f"Grounding excerpts:\n{excerpt_text}"
        )
    return f"Section: {section_title} ({section_id})\nPages: {page_start}-{page_end}"


def _build_grounded_citations(
    *,
    debug_report: DocumentDebugRecord | None,
    section_id: str,
    message: str,
) -> list[Citation]:
    if debug_report is None:
        return [
            Citation(
                section_id=section_id,
                title=section_id,
                page_start=1,
                page_end=1,
            )
        ]

    title = section_id
    page_start = 1
    page_end = 1
    related_ids = {section_id}

    unit = next((item for item in debug_report.study_units if item.id == section_id), None)
    if unit is not None:
        title = unit.title
        page_start = unit.page_start
        page_end = unit.page_end
        related_ids.update(unit.source_section_ids)

    section = next((item for item in debug_report.sections if item.id == section_id), None)
    if section is not None and title == section_id:
        title = section.title
        page_start = section.page_start
        page_end = section.page_end

    tokens = set(_tokenize(message))
    candidate_chunks = [
        chunk
        for chunk in debug_report.chunks
        if chunk.section_id in related_ids
    ]
    if not candidate_chunks:
        candidate_chunks = [
            chunk
            for chunk in debug_report.chunks
            if chunk.page_end >= page_start and chunk.page_start <= page_end
        ]

    scored_chunks = []
    for chunk in candidate_chunks:
        chunk_text = f"{chunk.text_preview}\n{chunk.content}".lower()
        score = sum(1 for token in tokens if token in chunk_text)
        scored_chunks.append((score, chunk.page_start, chunk.page_end))

    scored_chunks.sort(key=lambda item: (item[0], -(item[2] - item[1])), reverse=True)

    citations: list[Citation] = []
    seen_ranges: set[tuple[int, int]] = set()
    for _, start, end in scored_chunks[:3]:
        key = (start, end)
        if key in seen_ranges:
            continue
        seen_ranges.add(key)
        citations.append(
            Citation(
                section_id=section_id,
                title=title,
                page_start=start,
                page_end=end,
            )
        )

    if citations:
        return citations

    return [
        Citation(
            section_id=section_id,
            title=title,
            page_start=page_start,
            page_end=page_end,
        )
    ]


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-zA-Z0-9\u4e00-\u9fff]{2,}", text.lower())]


def _truncate_for_prompt(text: str, *, limit: int) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."
