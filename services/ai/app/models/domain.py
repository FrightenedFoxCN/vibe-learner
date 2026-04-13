from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


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
    relationship: str = ""
    learner_address: str = ""
    system_prompt: str
    reference_hints: list[str] = Field(default_factory=list)
    slots: list[PersonaSlot] = Field(default_factory=list)
    available_emotions: list[str]
    available_actions: list[str]
    default_speech_style: str


class PersonaCardRecord(BaseModel):
    id: str
    title: str
    kind: str
    label: str
    content: str
    tags: list[str] = Field(default_factory=list)
    search_keywords: str = "自定义"
    source: str = "manual"
    source_note: str = ""
    created_at: str
    updated_at: str


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


def normalize_persona_narrative_mode(value: str) -> str:
    """Normalize legacy and localized narrative-mode content to internal codes."""
    text = (value or "").strip()
    lowered = text.lower()
    if "light_story" in lowered or "轻剧情" in text:
        return "light_story"
    return "grounded"


def persona_narrative_mode_label(value: str) -> str:
    return "轻剧情陪伴" if normalize_persona_narrative_mode(value) == "light_story" else "稳态导学"


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
    speech_style: str
    scene_hint: str
    line_segment_id: str
    timing_hint: str
    tool_name: str = ""
    tool_summary: str = ""
    delivery_cue: str = ""
    commentary: str = ""


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
    document_id: str = ""
    persona_id: str
    objective: str = Field(
        description=(
            "创建学习计划时记录的学习者原始目标文本。它用于补充计划意图，不是系统生成的计划标题或摘要。"
        )
    )
    scene_profile_summary: str = ""
    scene_profile: "SceneProfileRecord | None" = None

    @model_validator(mode="after")
    def populate_scene_summary_from_profile(self) -> "LearningGoalInput":
        if (not self.scene_profile_summary.strip()) and self.scene_profile is not None:
            self.scene_profile_summary = self.scene_profile.summary
        return self


class SceneProfileRecord(BaseModel):
    scene_name: str = ""
    scene_id: str
    title: str
    summary: str
    tags: list[str] = Field(default_factory=list)
    selected_path: list[str] = Field(default_factory=list)
    focus_object_names: list[str] = Field(default_factory=list)
    scene_tree: list["SceneLayerStateRecord"] = Field(default_factory=list)


class SceneObjectStateRecord(BaseModel):
    id: str
    name: str
    description: str
    interaction: str
    tags: str = ""
    reuse_id: str = ""
    reuse_hint: str = ""


class SceneLayerStateRecord(BaseModel):
    id: str
    title: str
    scope_label: str
    summary: str
    atmosphere: str
    rules: str
    entrance: str
    tags: str = ""
    reuse_id: str = ""
    reuse_hint: str = ""
    objects: list[SceneObjectStateRecord] = Field(default_factory=list)
    children: list["SceneLayerStateRecord"] = Field(default_factory=list)


class SceneSetupStateRecord(BaseModel):
    config_id: str = "default"
    updated_at: str
    scene_name: str = ""
    scene_summary: str = ""
    scene_layers: list[SceneLayerStateRecord] = Field(default_factory=list)
    selected_layer_id: str = ""
    collapsed_layer_ids: list[str] = Field(default_factory=list)
    scene_profile: SceneProfileRecord | None = None


class SceneLibraryRecord(SceneSetupStateRecord):
    scene_id: str
    created_at: str


class ReusableSceneNodeRecord(BaseModel):
    node_id: str
    node_type: str
    title: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    reuse_id: str = ""
    reuse_hint: str = ""
    source_scene_id: str = ""
    source_scene_name: str = ""
    layer_node: SceneLayerStateRecord | None = None
    object_node: SceneObjectStateRecord | None = None
    created_at: str
    updated_at: str


class SessionSceneRecord(SceneSetupStateRecord):
    scene_instance_id: str
    session_id: str
    document_id: str
    persona_id: str
    source_scene_id: str = ""
    source_scene_name: str = ""
    created_at: str


SceneLayerStateRecord.model_rebuild()
SceneProfileRecord.model_rebuild()


class StudyScheduleRecord(BaseModel):
    id: str
    unit_id: str
    title: str
    focus: str
    activity_type: str
    status: str = "planned"


class PlanProgressSummaryRecord(BaseModel):
    total_schedule_count: int = 0
    completed_schedule_count: int = 0
    in_progress_schedule_count: int = 0
    pending_schedule_count: int = 0
    blocked_schedule_count: int = 0
    completion_percent: int = 0


class PlanProgressEventRecord(BaseModel):
    id: str
    actor: str
    source: str
    schedule_ids: list[str] = Field(default_factory=list)
    status: str
    note: str = ""
    created_at: str


class PlanningQuestionRecord(BaseModel):
    id: str
    question: str
    reason: str = ""
    assumptions: list[str] = Field(default_factory=list)
    answer: str = ""
    status: str = "pending"
    source_tool_name: str = "ask_planning_question"
    created_at: str
    answered_at: str = ""


class PlanChapterProgressRecord(BaseModel):
    unit_id: str
    title: str
    objective_fragment: str = ""
    schedule_ids: list[str] = Field(default_factory=list)
    total_schedule_count: int = 0
    completed_schedule_count: int = 0
    in_progress_schedule_count: int = 0
    pending_schedule_count: int = 0
    blocked_schedule_count: int = 0
    completion_percent: int = 0
    status: str = "planned"


class LearningPlanRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    creation_mode: str = "document"
    course_title: str = Field(
        description="系统生成的教材贴合型课程标题，用于学习计划头部展示。"
    )
    objective: str = Field(
        description=(
            "创建学习计划时记录的学习者原始目标文本。它用于补充计划意图，不是计划头部标题。"
        )
    )
    scene_profile_summary: str = ""
    scene_profile: SceneProfileRecord | None = None
    overview: str = Field(
        description=(
            "One or two sentence learner-facing plan summary. Use this as body/summary text, not as the plan title."
        )
    )
    study_chapters: list[str] = Field(
        description="Ordered study-chapter list used by downstream navigation."
    )
    today_tasks: list[str] = Field(
        description="Actionable learner tasks for the current session or day."
    )
    study_units: list[StudyUnitRecord] = []
    schedule: list[StudyScheduleRecord] = []
    progress_summary: PlanProgressSummaryRecord = Field(default_factory=PlanProgressSummaryRecord)
    chapter_progress: list[PlanChapterProgressRecord] = Field(default_factory=list)
    progress_events: list[PlanProgressEventRecord] = Field(default_factory=list)
    planning_questions: list[PlanningQuestionRecord] = Field(default_factory=list)
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


class TokenUsageRecord(BaseModel):
    id: str
    feature: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    created_at: str


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
    openai_setting_web_search_enabled: bool = True
    openai_chat_api_key: str = ""
    openai_chat_base_url: str = ""
    openai_chat_model: str = "gpt-4.1-mini"
    openai_chat_temperature: float = 0.35
    openai_setting_temperature: float = 0.4
    openai_setting_max_tokens: int = 900
    openai_chat_max_tokens: int = 800
    openai_chat_history_messages: int = 8
    openai_chat_tool_max_rounds: int = 4
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model_multimodal: bool = False
    openai_timeout_seconds: int = 30
    openai_plan_model_multimodal: bool = False
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


class ChatToolCallTraceRecord(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments_json: str
    result_summary: str = ""
    result_json: str


class RichTextBlockRecord(BaseModel):
    kind: str
    content: str


class StudyChatResult(BaseModel):
    reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]
    rich_blocks: list[RichTextBlockRecord] = []
    interactive_question: InteractiveQuestion | None = None
    persona_slot_trace: list["PersonaSlotTraceRecord"] = []
    memory_trace: list["MemoryTraceHitRecord"] = []
    tool_calls: list[ChatToolCallTraceRecord] = []
    scene_profile: SceneProfileRecord | None = None


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
    call_back: bool = False
    answer_key: str | None = None
    accepted_answers: list[str] = []
    explanation: str = ""
    submitted_answer: str = ""
    is_correct: bool | None = None
    feedback_text: str = ""


class DialogueTurnRecord(BaseModel):
    learner_message: str
    assistant_reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]
    rich_blocks: list[RichTextBlockRecord] = []
    interactive_question: InteractiveQuestion | None = None
    persona_slot_trace: list[PersonaSlotTraceRecord] = []
    memory_trace: list[MemoryTraceHitRecord] = []
    tool_calls: list[ChatToolCallTraceRecord] = []
    scene_profile: SceneProfileRecord | None = None
    created_at: str


class StudySessionRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    plan_id: str | None = None
    scene_instance_id: str = ""
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
