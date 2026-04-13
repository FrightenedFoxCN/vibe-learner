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


class PdfRectRecord(BaseModel):
    x: float = Field(default=0.0, ge=0.0, le=1.0)
    y: float = Field(default=0.0, ge=0.0, le=1.0)
    width: float = Field(default=0.0, ge=0.0, le=1.0)
    height: float = Field(default=0.0, ge=0.0, le=1.0)


class ProjectedPdfOverlayRecord(BaseModel):
    id: str
    kind: str
    page_number: int
    rects: list[PdfRectRecord] = Field(default_factory=list)
    label: str = ""
    quote_text: str = ""
    color: str = "#FACC15"
    created_at: str


class SessionProjectedPdfRecord(BaseModel):
    source_kind: str
    source_id: str
    title: str
    page_number: int = 1
    page_count: int = 0
    image_url: str = ""
    overlays: list[ProjectedPdfOverlayRecord] = Field(default_factory=list)
    updated_at: str


class Citation(BaseModel):
    section_id: str = ""
    title: str
    page_start: int
    page_end: int
    source_kind: str = "document"
    source_id: str = ""


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
    ocr_status: str = "completed"
    ocr_applied: bool = False
    ocr_language: str | None = None
    ocr_engine: str | None = None
    ocr_model_id: str | None = None
    ocr_applied_page_count: int = 0
    ocr_warnings: list[str] = Field(default_factory=list)
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


class ScheduleChapterContentSliceRecord(BaseModel):
    page_start: int
    page_end: int
    source_section_ids: list[str] = Field(default_factory=list)


class ScheduleChapterRecord(BaseModel):
    id: str
    title: str
    anchor_page_start: int
    anchor_page_end: int
    source_section_ids: list[str] = Field(default_factory=list)
    content_slices: list[ScheduleChapterContentSliceRecord] = Field(default_factory=list)


def _normalize_schedule_chapter_payload(
    *,
    unit_id: str,
    title: str,
    page_start: int,
    page_end: int,
    source_section_ids: list[str],
) -> dict[str, Any]:
    normalized_sources = [str(item).strip() for item in source_section_ids if str(item).strip()]
    return {
        "id": f"{unit_id}:schedule-chapter:1",
        "title": title.strip() or unit_id,
        "anchor_page_start": page_start,
        "anchor_page_end": page_end,
        "source_section_ids": normalized_sources,
        "content_slices": [
            {
                "page_start": page_start,
                "page_end": page_end,
                "source_section_ids": normalized_sources,
            }
        ],
    }


def _legacy_study_chapter_title_map(payload: dict[str, Any]) -> dict[str, str]:
    raw_chapters = payload.get("study_chapters")
    if not isinstance(raw_chapters, list):
        return {}
    chapter_labels = [str(item).strip() for item in raw_chapters if str(item).strip()]
    if not chapter_labels:
        return {}
    unit_ids: list[str] = []
    raw_study_units = payload.get("study_units")
    if isinstance(raw_study_units, list):
        unit_ids = [
            str(item.get("id") or "").strip()
            for item in raw_study_units
            if isinstance(item, dict) and bool(item.get("include_in_plan", True)) and str(item.get("id") or "").strip()
        ]
    if not unit_ids:
        seen: set[str] = set()
        raw_schedule = payload.get("schedule")
        if isinstance(raw_schedule, list):
            for item in raw_schedule:
                if not isinstance(item, dict):
                    continue
                unit_id = str(item.get("unit_id") or "").strip()
                if not unit_id or unit_id in seen:
                    continue
                seen.add(unit_id)
                unit_ids.append(unit_id)
    return {
        unit_id: chapter_labels[index]
        for index, unit_id in enumerate(unit_ids)
        if index < len(chapter_labels)
    }


class StudyScheduleRecord(BaseModel):
    id: str
    unit_id: str
    title: str
    focus: str
    activity_type: str
    status: str = "planned"
    schedule_chapters: list[ScheduleChapterRecord] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_schedule_chapters(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if value.get("schedule_chapters") is not None:
            return value
        unit_id = str(value.get("unit_id") or "").strip()
        page_start = int(value.get("_unit_page_start") or 0)
        page_end = int(value.get("_unit_page_end") or 0)
        if not unit_id or page_start <= 0 or page_end <= 0:
            return value
        source_section_ids = value.get("_unit_source_section_ids")
        if not isinstance(source_section_ids, list):
            source_section_ids = []
        legacy_title = str(value.get("_legacy_study_chapter_title") or "").strip()
        fallback_title = (
            legacy_title
            or str(value.get("focus") or "").strip()
            or str(value.get("title") or "").strip()
            or unit_id
        )
        value["schedule_chapters"] = [
            _normalize_schedule_chapter_payload(
                unit_id=unit_id,
                title=fallback_title,
                page_start=page_start,
                page_end=page_end,
                source_section_ids=[str(item) for item in source_section_ids],
            )
        ]
        return value


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


class StudyUnitProgressRecord(BaseModel):
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
    today_tasks: list[str] = Field(
        description="Actionable learner tasks for the current session or day."
    )
    study_units: list[StudyUnitRecord] = []
    schedule: list[StudyScheduleRecord] = []
    progress_summary: PlanProgressSummaryRecord = Field(default_factory=PlanProgressSummaryRecord)
    study_unit_progress: list[StudyUnitProgressRecord] = Field(default_factory=list)
    progress_events: list[PlanProgressEventRecord] = Field(default_factory=list)
    planning_questions: list[PlanningQuestionRecord] = Field(default_factory=list)
    created_at: str

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_learning_plan_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if value.get("study_unit_progress") is None and value.get("chapter_progress") is not None:
            value["study_unit_progress"] = value.get("chapter_progress")

        study_units = value.get("study_units")
        study_unit_by_id: dict[str, dict[str, Any]] = {}
        if isinstance(study_units, list):
            for raw_unit in study_units:
                if not isinstance(raw_unit, dict):
                    continue
                unit_id = str(raw_unit.get("id") or "").strip()
                if not unit_id:
                    continue
                study_unit_by_id[unit_id] = raw_unit

        legacy_title_map = _legacy_study_chapter_title_map(value)
        raw_schedule = value.get("schedule")
        if isinstance(raw_schedule, list):
            next_schedule: list[dict[str, Any]] = []
            for raw_item in raw_schedule:
                if not isinstance(raw_item, dict):
                    next_schedule.append(raw_item)
                    continue
                if raw_item.get("schedule_chapters") is None:
                    unit_id = str(raw_item.get("unit_id") or "").strip()
                    unit = study_unit_by_id.get(unit_id, {})
                    page_start = int(unit.get("page_start") or 0)
                    page_end = int(unit.get("page_end") or 0)
                    if unit_id and page_start > 0 and page_end > 0:
                        source_section_ids = unit.get("source_section_ids")
                        raw_item = {
                            **raw_item,
                            "_unit_page_start": page_start,
                            "_unit_page_end": page_end,
                            "_unit_source_section_ids": (
                                source_section_ids if isinstance(source_section_ids, list) else []
                            ),
                            "_legacy_study_chapter_title": legacy_title_map.get(unit_id, ""),
                        }
                next_schedule.append(raw_item)
            value["schedule"] = next_schedule
        return value



class PlanToolCallTraceRecord(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments_json: str
    result_summary: str = ""
    result_json: str


class ModelRecoveryRecord(BaseModel):
    recovery_id: str
    category: str
    reason: str
    strategy: str
    attempts: int = 1
    note: str = ""
    created_at: str


class PlanGenerationRoundRecord(BaseModel):
    round_index: int
    finish_reason: str = ""
    assistant_content: str = ""
    thinking: str = ""
    elapsed_ms: int = 0
    timeout_seconds: int = 0
    tool_calls: list[PlanToolCallTraceRecord] = []
    recoveries: list[ModelRecoveryRecord] = []


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


class LearnerAttachmentRecord(BaseModel):
    attachment_id: str
    name: str
    mime_type: str
    kind: str
    size_bytes: int = 0
    image_url: str = ""
    text_excerpt: str = ""
    source: str = "learner_upload"
    stored_path: str = ""
    page_count: int = 0
    previewable: bool = False


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
    model_recoveries: list[ModelRecoveryRecord] = []


class PersonaSlotTraceRecord(BaseModel):
    kind: str
    label: str
    content_excerpt: str
    reason: str


class MemoryTraceHitRecord(BaseModel):
    session_id: str
    study_unit_id: str
    scene_title: str
    score: float
    snippet: str
    created_at: str
    source: str = "retriever"

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_scope_field(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if value.get("study_unit_id") is None and value.get("section_id") is not None:
            value["study_unit_id"] = value.get("section_id")
        return value


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
    learner_message_kind: str = "learner"
    learner_attachments: list[LearnerAttachmentRecord] = []
    assistant_reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]
    rich_blocks: list[RichTextBlockRecord] = []
    interactive_question: InteractiveQuestion | None = None
    persona_slot_trace: list[PersonaSlotTraceRecord] = []
    memory_trace: list[MemoryTraceHitRecord] = []
    tool_calls: list[ChatToolCallTraceRecord] = []
    scene_profile: SceneProfileRecord | None = None
    model_recoveries: list[ModelRecoveryRecord] = []
    created_at: str


class SessionFollowUpRecord(BaseModel):
    id: str
    trigger_kind: str = "scheduled_reply"
    status: str = "pending"
    delay_seconds: int = 0
    due_at: str
    hidden_message: str
    reason: str = ""
    created_at: str
    completed_at: str = ""
    canceled_at: str = ""


class SessionMemoryRecord(BaseModel):
    id: str
    key: str
    content: str
    source: str = "tool_call"
    created_at: str
    updated_at: str


class SessionAffinityEventRecord(BaseModel):
    id: str
    delta: int
    reason: str = ""
    source: str = "tool_call"
    created_at: str


class SessionAffinityStateRecord(BaseModel):
    score: int = 0
    level: str = "neutral"
    summary: str = ""
    updated_at: str = ""
    events: list[SessionAffinityEventRecord] = Field(default_factory=list)


class SessionPlanConfirmationRecord(BaseModel):
    id: str
    tool_name: str
    action_type: str
    plan_id: str = ""
    title: str
    summary: str = ""
    preview_lines: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    created_at: str
    resolved_at: str = ""
    resolution_note: str = ""


class StudySessionRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    plan_id: str | None = None
    scene_instance_id: str = ""
    scene_profile: SceneProfileRecord | None = None
    study_unit_id: str
    study_unit_title: str = ""
    theme_hint: str = ""
    session_system_prompt: str = ""
    status: str
    turns: list[DialogueTurnRecord]
    prepared_study_unit_ids: list[str] = Field(default_factory=list)
    pending_follow_ups: list[SessionFollowUpRecord] = Field(default_factory=list)
    session_memory: list[SessionMemoryRecord] = Field(default_factory=list)
    affinity_state: SessionAffinityStateRecord = Field(default_factory=SessionAffinityStateRecord)
    plan_confirmations: list[SessionPlanConfirmationRecord] = Field(default_factory=list)
    projected_pdf: SessionProjectedPdfRecord | None = None
    created_at: str
    updated_at: str

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_session_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if value.get("study_unit_id") is None and value.get("section_id") is not None:
            value["study_unit_id"] = value.get("section_id")
        if value.get("study_unit_title") is None and value.get("section_title") is not None:
            value["study_unit_title"] = value.get("section_title")
        if (
            value.get("prepared_study_unit_ids") is None
            and value.get("prepared_section_ids") is not None
        ):
            value["prepared_study_unit_ids"] = value.get("prepared_section_ids")
        return value


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
