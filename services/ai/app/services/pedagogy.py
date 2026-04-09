from __future__ import annotations

from app.models.domain import Citation, ExerciseResult, PersonaProfile, StudyChatResult, SubmissionGradeResult
from app.services.model_provider import ModelProvider
from app.services.performance import PerformanceMapper


class PedagogyOrchestrator:
    def __init__(
        self, *, model_provider: ModelProvider, performance_mapper: PerformanceMapper
    ) -> None:
        self.model_provider = model_provider
        self.performance_mapper = performance_mapper

    def generate_chat_reply(
        self, *, session_id: str, persona: PersonaProfile, message: str, section_id: str
    ) -> StudyChatResult:
        raw_reply = self.model_provider.generate_chat(
            persona=persona, section_id=section_id, message=message
        )
        events = self.performance_mapper.map_text_to_events(
            persona=persona,
            text=raw_reply.text,
            mood=raw_reply.mood,
            action=raw_reply.action,
            line_segment_id=f"{session_id}:chat:0",
        )
        return StudyChatResult(
            reply=raw_reply.text,
            citations=[
                Citation(
                    section_id=section_id,
                    title=f"Section {section_id}",
                    page_start=12,
                    page_end=18,
                )
            ],
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
