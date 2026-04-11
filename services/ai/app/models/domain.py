from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


PERSONA_SLOT_KINDS = [
    "worldview",
    "past_experiences",
    "thinking_style",
    "teaching_method",
    "narrative_mode",
    "encouragement_style",
    "correction_style",
    "custom",
]

PERSONA_SLOT_KIND_LABELS: dict[str, str] = {
    "worldview": "世界观起点",
    "past_experiences": "过往经历",
    "thinking_style": "思维风格",
    "teaching_method": "教学方法",
    "narrative_mode": "叙事模式",
    "encouragement_style": "鼓励策略",
    "correction_style": "纠错策略",
    "custom": "自定义",
}


class PersonaSlot(BaseModel):
    kind: str
    label: str
    content: str
    weight: float = 1.0
    locked: bool = False
    sort_order: int = 0


class PersonaProfile(BaseModel):
    id: str
    name: str
    source: str
    summary: str
    system_prompt: str
    slots: list[PersonaSlot] = Field(default_factory=list)
    available_emotions: list[str]
    available_actions: list[str]
    default_speech_style: str


def persona_slot_content(persona: PersonaProfile, kind: str, default: str = "") -> str:
    """Return the content of the first slot matching ``kind``, or ``default``."""
    for slot in persona_sorted_slots(persona.slots):
        if slot.kind == kind:
            return slot.content
    return default


def persona_slot_list(persona: PersonaProfile, kind: str) -> list[str]:
    """Return a comma-split list of values from the first slot matching ``kind``."""
    content = persona_slot_content(persona, kind)
    if not content:
        return []
    return [s.strip() for s in content.split(",") if s.strip()]


def persona_sorted_slots(slots: list[PersonaSlot]) -> list[PersonaSlot]:
    """Sort slots by assembly order: sort_order asc, then weight desc, then stable label."""
    return sorted(
        slots,
        key=lambda slot: (
            int(slot.sort_order),
            -float(slot.weight),
            slot.label,
        ),
    )


class CharacterStateEvent(BaseModel):
    emotion: str
    action: str
    intensity: float = Field(ge=0.0, le=1.0)
    speech_style: str
    scene_hint: str
    line_segment_id: str
    timing_hint: str


class Citation(BaseModel):
    section_id: str
    title: str
    page_start: int
    page_end: int


class DocumentSection(BaseModel):
    id: str
    document_id: str
    title: str
    page_start: int
    page_end: int
    level: int


class StudyUnitRecord(BaseModel):
    id: str
    document_id: str
    title: str
    page_start: int
    page_end: int
    unit_kind: str = "chapter"
    include_in_plan: bool = True
    source_section_ids: list[str] = []
    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class HeadingCandidate(BaseModel):
    page_number: int
    text: str
    font_size: float
    confidence: float


class DocumentPageRecord(BaseModel):
    page_number: int
    char_count: int
    word_count: int
    text_preview: str
    dominant_font_size: float
    extraction_source: str = "text"
    heading_candidates: list[HeadingCandidate]


class DocumentChunkRecord(BaseModel):
    id: str
    document_id: str
    section_id: str
    page_start: int
    page_end: int
    char_count: int
    text_preview: str
    content: str = ""


class ParseWarning(BaseModel):
    code: str
    message: str
    page_number: int | None = None


class DocumentDebugRecord(BaseModel):
    document_id: str
    parser_name: str
    processed_at: str
    page_count: int
    total_characters: int
    extraction_method: str
    ocr_applied: bool = False
    ocr_language: str | None = None
    pages: list[DocumentPageRecord]
    sections: list[DocumentSection]
    study_units: list[StudyUnitRecord] = []
    chunks: list[DocumentChunkRecord]
    warnings: list[ParseWarning]
    dominant_language_hint: str


class DocumentRecord(BaseModel):
    id: str
    title: str
    original_filename: str
    stored_path: str
    status: str
    ocr_status: str
    created_at: str
    updated_at: str
    sections: list[DocumentSection] = []
    study_units: list[StudyUnitRecord] = []
    study_unit_count: int = 0
    page_count: int = 0
    chunk_count: int = 0
    preview_excerpt: str = ""
    debug_ready: bool = False


class LearningGoalInput(BaseModel):
    document_id: str
    persona_id: str
    objective: str = Field(
        description=(
            "Learner-authored study goal captured at plan creation time. This is supporting goal text for the plan, "
            "not the generated header title or summary."
        )
    )
    scene_profile_summary: str = ""


class SceneProfileRecord(BaseModel):
    scene_id: str
    title: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    selected_path: list[str] = Field(default_factory=list)
    focus_object_names: list[str] = Field(default_factory=list)


class StudyScheduleRecord(BaseModel):
    id: str
    unit_id: str
    title: str
    focus: str
    activity_type: str
    status: str = "planned"


class LearningPlanRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    course_title: str = Field(
        description="Generated textbook-grounded course title for display in the learning plan header."
    )
    objective: str = Field(
        description=(
            "Learner-authored study goal captured at plan creation time. This is supporting goal text, not the plan header title."
        )
    )
    scene_profile_summary: str = ""
    overview: str = Field(
        description=(
            "One or two sentence learner-facing plan summary. Use this as body/summary text, not as the plan title."
        )
    )
    weekly_focus: list[str] = Field(
        description="Ordered main study themes (coarse-grained), suitable for a vertical learning sequence."
    )
    today_tasks: list[str] = Field(
        description="Actionable learner tasks for the current session or day."
    )
    study_units: list[StudyUnitRecord] = []
    schedule: list[StudyScheduleRecord] = []
    created_at: str


class PlanToolCallTraceRecord(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments_json: str
    result_summary: str = ""
    result_json: str


class PlanGenerationRoundRecord(BaseModel):
    round_index: int
    finish_reason: str = ""
    assistant_content: str = ""
    thinking: str = ""
    elapsed_ms: int = 0
    timeout_seconds: int = 0
    tool_calls: list[PlanToolCallTraceRecord] = []


class PlanGenerationTraceRecord(BaseModel):
    document_id: str
    plan_id: str | None = None
    model: str
    created_at: str
    rounds: list[PlanGenerationRoundRecord] = []


class ModelToolConfigRecord(BaseModel):
    config_id: str = "default"
    updated_at: str
    stage_tool_enabled: dict[str, dict[str, bool]] = Field(default_factory=dict)


class RuntimeSettingsRecord(BaseModel):
    config_id: str = "default"
    updated_at: str
    plan_provider: str = "mock"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_plan_api_key: str = ""
    openai_plan_base_url: str = ""
    openai_plan_model: str = "gpt-4.1-mini"
    openai_setting_api_key: str = ""
    openai_setting_base_url: str = ""
    openai_setting_model: str = "gpt-4.1-mini"
    openai_chat_api_key: str = ""
    openai_chat_base_url: str = ""
    openai_chat_model: str = "gpt-4.1-mini"
    openai_chat_temperature: float = 0.35
    openai_setting_temperature: float = 0.4
    openai_setting_max_tokens: int = 900
    openai_chat_max_tokens: int = 800
    openai_chat_history_messages: int = 8
    openai_chat_tool_max_rounds: int = 4
    openai_chat_tools_enabled: bool = True
    openai_chat_memory_tool_enabled: bool = True
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model_multimodal: bool = False
    openai_timeout_seconds: int = 30
    openai_plan_model_multimodal: bool = False
    openai_plan_tools_enabled: bool = True
    openai_plan_fallback_model: str = ""
    openai_plan_fallback_disable_tools: bool = True
    show_debug_info: bool = True


class StreamEventRecord(BaseModel):
    stage: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class StreamReportRecord(BaseModel):
    document_id: str
    stream_kind: str
    status: str = "idle"
    created_at: str
    updated_at: str
    events: list[StreamEventRecord] = Field(default_factory=list)


class StudyChatResult(BaseModel):
    reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]
    interactive_question: InteractiveQuestion | None = None
    persona_slot_trace: list["PersonaSlotTraceRecord"] = []
    memory_trace: list["MemoryTraceHitRecord"] = []


class PersonaSlotTraceRecord(BaseModel):
    kind: str
    label: str
    content_excerpt: str
    reason: str


class MemoryTraceHitRecord(BaseModel):
    session_id: str
    section_id: str
    scene_title: str
    score: float
    snippet: str
    created_at: str
    source: str = "retriever"


class InteractiveQuestionOption(BaseModel):
    key: str
    text: str


class InteractiveQuestion(BaseModel):
    question_type: str
    prompt: str
    difficulty: str = "medium"
    topic: str = ""
    options: list[InteractiveQuestionOption] = []
    answer_key: str | None = None
    accepted_answers: list[str] = []
    explanation: str = ""


class DialogueTurnRecord(BaseModel):
    learner_message: str
    assistant_reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]
    interactive_question: InteractiveQuestion | None = None
    persona_slot_trace: list[PersonaSlotTraceRecord] = []
    memory_trace: list[MemoryTraceHitRecord] = []
    created_at: str


class StudySessionRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    scene_profile: SceneProfileRecord | None = None
    section_id: str
    section_title: str = ""
    theme_hint: str = ""
    session_system_prompt: str = ""
    status: str
    turns: list[DialogueTurnRecord]
    created_at: str
    updated_at: str


class ExerciseResult(BaseModel):
    exercise_id: str
    section_id: str
    prompt: str
    exercise_type: str
    difficulty: str
    guidance: str
    character_events: list[CharacterStateEvent]


class SubmissionGradeResult(BaseModel):
    score: int
    diagnosis: list[str]
    recommendation: str
    character_events: list[CharacterStateEvent]
