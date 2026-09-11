from __future__ import annotations

from dataclasses import dataclass
from typing import Callable
from typing import Any, Literal
from app.models.domain import (
    ChatToolCallTraceRecord,
    DocumentDebugRecord,
    LearningGoalInput,
    LearningPlanRecord,
    PlanGenerationTraceRecord,
    PlanningQuestionRecord,
    PersonaProfile,
    PersonaSlot,
    RichTextBlockRecord,
    SceneProfileRecord,
    StudyUnitRecord,
)
from app.models.planning import PlanScheduleChapterProposalV1
from app.models.study_chat_operation import StudyChatMessageKind
from app.models.tavern import TavernActorReply, TavernMessageRecord, TavernParticipantRecord
from app.models.study_question import StudyQuestionProposalV1


@dataclass
class ModelReply:
    text: str
    mood: str
    action: str
    speech_style: str = ""
    delivery_cue: str = ""
    state_commentary: str = ""
    rich_blocks: list[RichTextBlockRecord] | None = None
    interactive_question: StudyQuestionProposalV1 | None = None
    memory_trace: list[dict[str, Any]] | None = None
    tool_calls: list[ChatToolCallTraceRecord] | None = None
    scene_profile: SceneProfileRecord | None = None


@dataclass
class PlanScheduleItem:
    unit_id: str
    title: str
    focus: str
    activity_type: str
    schedule_chapters: list[PlanScheduleChapterProposalV1]


@dataclass
class PlanModelReply:
    course_title: str
    overview: str
    today_tasks: list[str]
    schedule: list[PlanScheduleItem]
    revised_study_units: list[StudyUnitRecord] | None = None
    planning_questions: list[PlanningQuestionRecord] | None = None
    debug_trace: PlanGenerationTraceRecord | None = None


class PlanningModelCapability:
    def generate_plan_revision(self, *, plan, instruction: str):
        raise NotImplementedError

    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
        planning_questions: list[PlanningQuestionRecord] | None = None,
        existing_plan: LearningPlanRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
    ) -> PlanModelReply:
        raise NotImplementedError

    def supports_page_image_tools(self) -> bool:
        return False

    def plan_tools_runtime_enabled(self) -> bool:
        return False


class StudyModelCapability:
    def generate_chat(
        self,
        *,
        persona: PersonaProfile,
        section_id: str,
        message: str,
        message_kind: StudyChatMessageKind = "learner",
        session_prompt: str = "",
        section_context: str = "",
        memory_context: str = "",
        attachment_context: str = "",
        learner_multimodal_parts: list[dict[str, Any]] | None = None,
        scene_context: str = "",
        active_plan_context: str = "",
        session_state_context: str = "",
        session_tool_runtime: Any | None = None,
        scene_tool_runtime: Any | None = None,
        plan_tool_runtime: Any | None = None,
        memory_trace_hits: list[dict[str, Any]] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        debug_report: DocumentDebugRecord | None = None,
        document_path: str | None = None,
    ) -> ModelReply:
        raise NotImplementedError

    def supports_chat_page_image_tools(self) -> bool:
        return False

    def chat_tools_runtime_enabled(self) -> bool:
        return False

    def chat_memory_tool_runtime_enabled(self) -> bool:
        return False


class TavernModelCapability:
    def generate_tavern_actor_reply(
        self,
        *,
        persona: PersonaProfile,
        participants: list[TavernParticipantRecord],
        scene_profile: SceneProfileRecord | None,
        recent_messages: list[TavernMessageRecord],
        user_message: str,
        guidance: str,
        allowed_target_ids: list[str],
        turn_kind: str = "user_message",
        required_target_id: str = "",
        should_continue: Callable[[], bool] | None = None,
    ) -> TavernActorReply:
        raise NotImplementedError


class PersonaModelCapability:
    def assist_persona_setting(
        self,
        *,
        name: str,
        summary: str,
        slots: list[PersonaSlot],
        rewrite_strength: float,
    ) -> dict[str, object]:
        raise NotImplementedError

    def assist_persona_slot(
        self,
        *,
        name: str,
        summary: str,
        slot: PersonaSlot,
        rewrite_strength: float,
    ) -> dict[str, object]:
        raise NotImplementedError

    def generate_persona_cards_from_keywords(
        self,
        *,
        keywords: str,
        count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError

    def generate_persona_cards_from_text(
        self,
        *,
        text: str,
        count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError


class SceneModelCapability:
    def generate_scene_tree_from_keywords(
        self,
        *,
        keywords: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError

    def generate_scene_tree_from_text(
        self,
        *,
        text: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError


class EmbeddingModelCapability:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return []


class ImageModelCapability:
    def generate_projected_image(
        self,
        *,
        prompt: str,
        size: str = "1024x1024",
    ) -> dict[str, str]:
        raise RuntimeError("chat_image_generation_unsupported")

    def supports_chat_generated_image_tools(self) -> bool:
        return False


class ExerciseModelCapability:
    exercise_implementation: Literal["local_heuristic", "remote", "unsupported"] = "unsupported"

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ModelReply:
        raise NotImplementedError

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> ModelReply:
        raise NotImplementedError


class TeachingModelCapability(StudyModelCapability, EmbeddingModelCapability, ExerciseModelCapability):
    """Tutor operations require chat, memory embeddings and local exercises."""


class ModelProvider(
    TeachingModelCapability, PlanningModelCapability, TavernModelCapability,
    PersonaModelCapability, SceneModelCapability, ImageModelCapability,
):
    """Compatibility aggregate; domain services should accept a narrow capability."""
