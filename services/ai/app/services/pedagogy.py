from __future__ import annotations

import re

from app.models.domain import (
    Citation,
    DialogueTurnRecord,
    DocumentDebugRecord,
    ExerciseResult,
    PersonaProfile,
    PersonaSlotTraceRecord,
    StudyChatResult,
    MemoryTraceHitRecord,
    StudySessionRecord,
    SubmissionGradeResult,
    persona_sorted_slots,
)
from app.services.model_provider import ModelProvider
from app.services.performance import PerformanceMapper
from app.services.study_memory import build_memory_context, retrieve_memory_hits


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
        session_system_prompt: str = "",
        debug_report: DocumentDebugRecord | None = None,
        document_path: str | None = None,
        previous_turns: list[DialogueTurnRecord] | None = None,
        memory_sessions: list[StudySessionRecord] | None = None,
        active_scene_summary: str = "",
        active_scene_context: str = "",
        scene_tool_runtime=None,
    ) -> StudyChatResult:
        turns = previous_turns or []
        section_context = _build_section_context(debug_report=debug_report, section_id=section_id)
        conversation_history = _build_conversation_history(turns)
        memory_hits = retrieve_memory_hits(
            sessions=memory_sessions or [],
            current_session_id=session_id,
            active_section_id=section_id,
            query=message,
            active_scene_summary=active_scene_summary,
            embed_texts=self.model_provider.embed_texts,
        )
        memory_context = build_memory_context(memory_hits)
        memory_hit_payloads = [item.model_dump(mode="json") for item in memory_hits]
        raw_reply = self.model_provider.generate_chat(
            persona=persona,
            section_id=section_id,
            message=message,
            session_prompt=session_system_prompt,
            section_context=section_context,
            memory_context=memory_context,
            scene_context=active_scene_context,
            scene_tool_runtime=scene_tool_runtime,
            memory_trace_hits=memory_hit_payloads,
            conversation_history=conversation_history,
            debug_report=debug_report,
            document_path=document_path,
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
            speech_style=raw_reply.speech_style,
            delivery_cue=raw_reply.delivery_cue,
            commentary=raw_reply.state_commentary,
        )
        scene_hint = _build_scene_hint(section_id=section_id, citations=citations)
        for event in events:
            event.scene_hint = scene_hint
        tool_events = self.performance_mapper.map_tool_calls_to_events(
            persona=persona,
            tool_calls=raw_reply.tool_calls or [],
            line_segment_id=f"{session_id}:chat:{turn_index}",
        )
        slot_trace = _build_persona_slot_trace(persona=persona, message=message)
        memory_trace = _normalize_memory_trace(raw_reply.memory_trace, memory_hits)
        return StudyChatResult(
            reply=raw_reply.text,
            citations=citations,
            character_events=[*events, *tool_events],
            rich_blocks=raw_reply.rich_blocks or [],
            interactive_question=raw_reply.interactive_question,
            persona_slot_trace=slot_trace,
            memory_trace=memory_trace,
            tool_calls=raw_reply.tool_calls or [],
            scene_profile=raw_reply.scene_profile,
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
            speech_style=raw_reply.speech_style,
            delivery_cue=raw_reply.delivery_cue,
            commentary=raw_reply.state_commentary,
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
            speech_style=raw_reply.speech_style,
            delivery_cue=raw_reply.delivery_cue,
            commentary=raw_reply.state_commentary,
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
            f"章节：{section_title} ({section_id})\n"
            f"页码：{page_start}-{page_end}\n"
            f"教材摘录：\n{excerpt_text}"
        )
    return f"章节：{section_title} ({section_id})\n页码：{page_start}-{page_end}"


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


def _build_persona_slot_trace(*, persona: PersonaProfile, message: str) -> list[PersonaSlotTraceRecord]:
    tokens = set(_tokenize(message))
    scored: list[tuple[int, int, PersonaSlotTraceRecord]] = []
    for index, slot in enumerate(persona_sorted_slots(persona.slots)):
        content = slot.content.strip()
        if not content:
            continue
        content_lower = content.lower()
        score = sum(1 for token in tokens if token in content_lower)
        if score == 0 and slot.kind not in ("teaching_method", "thinking_style", "worldview"):
            continue
        reason = "命中提问关键词" if score > 0 else "作为人格基础策略默认参与"
        scored.append(
            (
                score,
                index,
                PersonaSlotTraceRecord(
                    kind=slot.kind,
                    label=slot.label,
                    content_excerpt=_truncate_for_prompt(content, limit=80),
                    reason=reason,
                ),
            )
        )
    scored.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    return [item[2] for item in scored[:4]]


def _normalize_memory_trace(
    raw_hits: list[dict[str, object]] | None,
    fallback: list[MemoryTraceHitRecord],
) -> list[MemoryTraceHitRecord]:
    if not raw_hits:
        return fallback
    result: list[MemoryTraceHitRecord] = []
    for item in raw_hits:
        try:
            result.append(
                MemoryTraceHitRecord(
                    session_id=str(item.get("session_id") or ""),
                    section_id=str(item.get("section_id") or ""),
                    scene_title=str(item.get("scene_title") or "未设置场景"),
                    score=float(item.get("score") or 0),
                    snippet=str(item.get("snippet") or ""),
                    created_at=str(item.get("created_at") or ""),
                    source=str(item.get("source") or "tool_call"),
                )
            )
        except Exception:
            continue
    return result or fallback
