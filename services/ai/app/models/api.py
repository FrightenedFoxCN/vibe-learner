from pydantic import BaseModel, Field

from app.models.domain import (
    CharacterStateEvent,
    ChatToolCallTraceRecord,
    Citation,
    DocumentDebugRecord,
    DocumentRecord,
    InteractiveQuestion,
    InteractiveQuestionOption,
    LearningGoalInput,
    LearningPlanRecord,
    ModelRecoveryRecord,
    PlanProgressEventRecord,
    PlanProgressSummaryRecord,
    PlanGenerationTraceRecord,
    PlanGenerationRoundRecord,
    PlanToolCallTraceRecord,
    PersonaProfile,
    PersonaCardRecord,
    PlanningQuestionRecord,
    PersonaSlot,
    SceneLibraryRecord,
    ReusableSceneNodeRecord,
    StreamEventRecord,
    StreamReportRecord,
    StudySessionRecord,
    SceneProfileRecord,
    SceneLayerStateRecord,
    SceneObjectStateRecord,
    SessionSceneRecord,
    SceneSetupStateRecord,
)


class CreatePersonaRequest(BaseModel):
    name: str
    summary: str
    relationship: str = ""
    learner_address: str = ""
    system_prompt: str
    reference_hints: list[str] = Field(default_factory=list)
    slots: list[PersonaSlot] = Field(default_factory=list)
    available_emotions: list[str] | None = None
    available_actions: list[str] | None = None
    default_speech_style: str | None = None


class UpdatePersonaRequest(BaseModel):
    name: str
    summary: str
    relationship: str = ""
    learner_address: str = ""
    system_prompt: str
    reference_hints: list[str] = Field(default_factory=list)
    slots: list[PersonaSlot] = Field(default_factory=list)
    available_emotions: list[str] | None = None
    available_actions: list[str] | None = None
    default_speech_style: str | None = None


class PersonaSettingAssistRequest(BaseModel):
    name: str
    summary: str
    slots: list[PersonaSlot] = Field(default_factory=list)
    rewrite_strength: float = Field(default=0.5, ge=0.0, le=1.0)


class PersonaSettingAssistResponse(BaseModel):
    slots: list[PersonaSlot]
    system_prompt_suggestion: str
    model_recoveries: list[ModelRecoveryRecord] = Field(default_factory=list)


class PersonaSlotAssistRequest(BaseModel):
    name: str
    summary: str
    slot: PersonaSlot
    rewrite_strength: float = Field(default=0.5, ge=0.0, le=1.0)


class PersonaSlotAssistResponse(BaseModel):
    slot: PersonaSlot
    model_recoveries: list[ModelRecoveryRecord] = Field(default_factory=list)


class PersonaResponse(PersonaProfile):
    pass


class PersonaListResponse(BaseModel):
    items: list[PersonaResponse]


class PersonaAssetsResponse(BaseModel):
    persona_id: str
    renderer: str
    asset_manifest: dict[str, object]


class CreatePersonaCardRequest(BaseModel):
    title: str
    kind: str
    label: str
    content: str
    tags: list[str] = Field(default_factory=list)
    search_keywords: str = "自定义"
    source: str = "manual"
    source_note: str = ""


class BatchCreatePersonaCardsRequest(BaseModel):
    items: list[CreatePersonaCardRequest] = Field(default_factory=list)


class PersonaCardGenerateRequest(BaseModel):
    mode: str
    input_text: str
    count: int | None = Field(default=None, ge=1)


class PersonaCardResponse(PersonaCardRecord):
    pass


class PersonaCardListResponse(BaseModel):
    items: list[PersonaCardResponse]


class PersonaCardGenerateResponse(BaseModel):
    mode: str
    used_model: str
    used_web_search: bool
    summary: str = ""
    relationship: str = ""
    learner_address: str = ""
    items: list[PersonaCardResponse]
    model_recoveries: list[ModelRecoveryRecord] = Field(default_factory=list)


class SceneTreeGenerateRequest(BaseModel):
    mode: str
    input_text: str
    layer_count: int | None = Field(default=None, ge=1)


class SceneTreeGenerateResponse(BaseModel):
    mode: str
    used_model: str
    used_web_search: bool
    scene_name: str
    scene_summary: str
    selected_layer_id: str = ""
    scene_layers: list[SceneLayerStateRecord] = Field(default_factory=list)
    model_recoveries: list[ModelRecoveryRecord] = Field(default_factory=list)


class DocumentResponse(DocumentRecord):
    pass


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]


class DocumentStatusResponse(DocumentRecord):
    pass


class DocumentDebugResponse(DocumentDebugRecord):
    pass


class PlanningSectionRefResponse(BaseModel):
    section_id: str
    title: str
    level: int
    page_start: int
    page_end: int


class PlanningOutlineNodeResponse(PlanningSectionRefResponse):
    children: list[PlanningSectionRefResponse]


class PlanningChunkExcerptResponse(BaseModel):
    chunk_id: str
    section_id: str
    page_start: int
    page_end: int
    char_count: int
    content: str


class PlanningStudyUnitContextResponse(BaseModel):
    unit_id: str
    title: str
    page_start: int
    page_end: int
    summary: str
    unit_kind: str
    include_in_plan: bool
    subsection_titles: list[str]
    related_section_ids: list[str]
    detail_tool_target_id: str


class StudyUnitPlanningDetailResponse(BaseModel):
    unit_id: str
    title: str
    page_start: int
    page_end: int
    summary: str
    unit_kind: str
    include_in_plan: bool
    related_section_ids: list[str]
    subsection_titles: list[str]
    related_sections: list[PlanningSectionRefResponse]
    chunk_count: int
    chunk_excerpts: list[PlanningChunkExcerptResponse]


class PlanningToolSpecResponse(BaseModel):
    name: str
    description: str


class DocumentPlanningContextResponse(BaseModel):
    document_id: str
    course_outline: list[PlanningOutlineNodeResponse]
    study_units: list[PlanningStudyUnitContextResponse]
    detail_map: dict[str, StudyUnitPlanningDetailResponse]
    available_tools: list[PlanningToolSpecResponse]


class ModelToolToggleRequest(BaseModel):
    stage_name: str
    tool_name: str
    enabled: bool


class UpdateModelToolConfigRequest(BaseModel):
    toggles: list[ModelToolToggleRequest]


class ModelToolConfigItemResponse(BaseModel):
    name: str
    label: str
    description: str
    category: str
    category_label: str
    enabled: bool
    available: bool
    effective_enabled: bool
    audit_basis: list[str]
    unavailable_reason: str = ""


class ModelToolStageResponse(BaseModel):
    name: str
    label: str
    description: str
    stage_enabled: bool
    audit_basis: list[str]
    stage_disabled_reason: str = ""
    tools: list[ModelToolConfigItemResponse]


class ModelToolConfigResponse(BaseModel):
    updated_at: str
    stages: list[ModelToolStageResponse]


class RuntimeSettingsResponse(BaseModel):
    updated_at: str
    plan_provider: str
    openai_api_key: str
    openai_api_key_configured: bool = False
    openai_base_url: str
    openai_plan_api_key: str
    openai_plan_api_key_configured: bool = False
    openai_plan_base_url: str
    openai_plan_model: str
    openai_setting_api_key: str
    openai_setting_api_key_configured: bool = False
    openai_setting_base_url: str
    openai_setting_model: str
    openai_setting_web_search_enabled: bool
    openai_chat_api_key: str
    openai_chat_api_key_configured: bool = False
    openai_chat_base_url: str
    openai_chat_model: str
    openai_chat_temperature: float
    openai_setting_temperature: float
    openai_setting_max_tokens: int
    openai_chat_max_tokens: int
    openai_chat_history_messages: int
    openai_chat_tool_max_rounds: int
    openai_embedding_model: str
    openai_chat_model_multimodal: bool
    openai_timeout_seconds: int
    openai_plan_model_multimodal: bool
    openai_plan_fallback_model: str
    openai_plan_fallback_disable_tools: bool
    show_debug_info: bool


class UpdateRuntimeSettingsRequest(BaseModel):
    plan_provider: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_plan_api_key: str | None = None
    openai_plan_base_url: str | None = None
    openai_plan_model: str | None = None
    openai_setting_api_key: str | None = None
    openai_setting_base_url: str | None = None
    openai_setting_model: str | None = None
    openai_setting_web_search_enabled: bool | None = None
    openai_chat_api_key: str | None = None
    openai_chat_base_url: str | None = None
    openai_chat_model: str | None = None
    openai_chat_temperature: float | None = None
    openai_setting_temperature: float | None = None
    openai_setting_max_tokens: int | None = None
    openai_chat_max_tokens: int | None = None
    openai_chat_history_messages: int | None = None
    openai_chat_tool_max_rounds: int | None = None
    openai_embedding_model: str | None = None
    openai_chat_model_multimodal: bool | None = None
    openai_timeout_seconds: int | None = None
    openai_plan_model_multimodal: bool | None = None
    openai_plan_fallback_model: str | None = None
    openai_plan_fallback_disable_tools: bool | None = None
    show_debug_info: bool | None = None


class RuntimeSessionSecretsRequest(BaseModel):
    openai_api_key: str | None = None
    openai_plan_api_key: str | None = None
    openai_setting_api_key: str | None = None
    openai_chat_api_key: str | None = None


class RuntimeSettingsProbeRequest(BaseModel):
    api_key: str
    base_url: str


class RuntimeCapabilitySignalResponse(BaseModel):
    status: str = "unknown"
    source: str = "unavailable"
    note: str = ""


class RuntimeModelCapabilityResponse(BaseModel):
    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)
    tool_types: list[str] = Field(default_factory=list)
    multimodal: RuntimeCapabilitySignalResponse = Field(default_factory=RuntimeCapabilitySignalResponse)
    web_search: RuntimeCapabilitySignalResponse = Field(default_factory=RuntimeCapabilitySignalResponse)


class RuntimeSettingsProbeResponse(BaseModel):
    available: bool
    models: list[str]
    capabilities: dict[str, RuntimeModelCapabilityResponse] = Field(default_factory=dict)
    error: str = ""


class StorageBucketSummaryResponse(BaseModel):
    bucket: str
    layer: str
    lifecycle: str
    item_count: int
    size_bytes: int = 0
    mutable: bool
    path: str = ""
    description: str = ""


class StorageSummaryResponse(BaseModel):
    buckets: list[StorageBucketSummaryResponse]
    orphaned_uploads: list[str] = Field(default_factory=list)


class StorageCleanupRequest(BaseModel):
    buckets: list[str] = Field(default_factory=list)
    document_id: str = ""
    session_id: str = ""


class StorageCleanupItemResponse(BaseModel):
    bucket: str
    removed_count: int


class StorageCleanupResponse(BaseModel):
    items: list[StorageCleanupItemResponse]


class PlanToolCallTraceResponse(PlanToolCallTraceRecord):
    pass


class PlanGenerationRoundTraceResponse(PlanGenerationRoundRecord):
    tool_calls: list[PlanToolCallTraceResponse]


class PlanGenerationTraceSummaryResponse(BaseModel):
    round_count: int
    tool_call_count: int
    latest_finish_reason: str = ""


class PlanGenerationTracePayloadResponse(PlanGenerationTraceRecord):
    rounds: list[PlanGenerationRoundTraceResponse]


class DocumentPlanningTraceResponse(BaseModel):
    document_id: str
    has_trace: bool
    summary: PlanGenerationTraceSummaryResponse
    trace: PlanGenerationTracePayloadResponse | None = None


class StreamEventResponse(StreamEventRecord):
    pass


class StreamReportResponse(StreamReportRecord):
    events: list[StreamEventResponse]


class ProcessDocumentRequest(BaseModel):
    force_ocr: bool = False


class StudyUnitTitleUpdateRequest(BaseModel):
    title: str = Field(min_length=1)


class LearningPlanCreateRequest(LearningGoalInput):
    pass


class LearningPlanUpdateRequest(BaseModel):
    course_title: str | None = Field(default=None, min_length=1)


class LearningPlanProgressUpdateRequest(BaseModel):
    schedule_ids: list[str] = Field(default_factory=list)
    status: str = Field(min_length=1)
    note: str = ""


class PlanningQuestionAnswerRequest(BaseModel):
    answer: str = Field(min_length=1)


class DocumentStudyUnitUpdateResponse(BaseModel):
    document: DocumentResponse
    plans: list["LearningPlanResponse"]


class LearningPlanResponse(LearningPlanRecord):
    pass


class LearningPlanListResponse(BaseModel):
    items: list[LearningPlanResponse]


class SceneSetupResponse(SceneSetupStateRecord):
    pass


class SceneLibraryResponse(SceneLibraryRecord):
    pass


class SceneLibraryListResponse(BaseModel):
    items: list[SceneLibraryResponse]


class CreateReusableSceneNodeRequest(BaseModel):
    node_type: str
    title: str = Field(min_length=1)
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    reuse_id: str = ""
    reuse_hint: str = ""
    source_scene_id: str = ""
    source_scene_name: str = ""
    layer_node: SceneLayerStateRecord | None = None
    object_node: SceneObjectStateRecord | None = None


class ReusableSceneNodeResponse(ReusableSceneNodeRecord):
    pass


class ReusableSceneNodeListResponse(BaseModel):
    items: list[ReusableSceneNodeResponse]


class SessionSceneResponse(SessionSceneRecord):
    pass


class UpdateSceneSetupRequest(BaseModel):
    scene_name: str = Field(min_length=1)
    scene_summary: str = Field(min_length=1)
    scene_layers: list[SceneLayerStateRecord] = Field(default_factory=list)
    selected_layer_id: str = ""
    collapsed_layer_ids: list[str] = Field(default_factory=list)
    scene_profile: SceneProfileRecord | None = None


class UpsertSceneLibraryRequest(BaseModel):
    scene_name: str = Field(min_length=1)
    scene_summary: str = Field(min_length=1)
    scene_layers: list[SceneLayerStateRecord] = Field(default_factory=list)
    selected_layer_id: str = ""
    collapsed_layer_ids: list[str] = Field(default_factory=list)
    scene_profile: SceneProfileRecord | None = None


class CreateStudySessionRequest(BaseModel):
    document_id: str
    persona_id: str
    plan_id: str | None = None
    scene_profile: SceneProfileRecord | None = None
    study_unit_id: str
    study_unit_title: str = ""
    theme_hint: str = ""


class UpdateStudySessionRequest(BaseModel):
    study_unit_id: str | None = None
    scene_profile: SceneProfileRecord | None = None


class StudySessionResponse(StudySessionRecord):
    pass


class ChatToolCallTraceResponse(ChatToolCallTraceRecord):
    pass


class StudySessionListResponse(BaseModel):
    items: list[StudySessionResponse]


class StudyChatRequest(BaseModel):
    message: str
    message_kind: str = "learner"
    follow_up_id: str = ""
    hidden_message_prefix: str = ""


class StudyChatResponse(BaseModel):
    reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]
    rich_blocks: list[dict[str, str]] = []
    interactive_question: InteractiveQuestion | None = None
    persona_slot_trace: list[dict[str, str]] = []
    memory_trace: list[dict[str, object]] = []
    tool_calls: list[ChatToolCallTraceResponse] = []
    scene_profile: SceneProfileRecord | None = None
    model_recoveries: list[ModelRecoveryRecord] = Field(default_factory=list)


class StudyChatExchangeResponse(StudyChatResponse):
    session: StudySessionResponse


class StudySessionPlanConfirmationDecisionRequest(BaseModel):
    decision: str = Field(min_length=1)
    note: str = ""


class StudySessionPlanConfirmationDecisionResponse(BaseModel):
    session: StudySessionResponse
    plan: LearningPlanResponse | None = None


class StudyQuestionAttemptRequest(BaseModel):
    question_type: str
    prompt: str
    topic: str = ""
    difficulty: str = "medium"
    options: list[InteractiveQuestionOption] = []
    call_back: bool = False
    answer_key: str | None = None
    accepted_answers: list[str] = []
    submitted_answer: str
    is_correct: bool
    explanation: str = ""


class ExerciseGenerateRequest(BaseModel):
    persona_id: str
    section_id: str
    topic: str


class ExerciseGenerateResponse(BaseModel):
    exercise_id: str
    section_id: str
    prompt: str
    exercise_type: str
    difficulty: str
    guidance: str
    character_events: list[CharacterStateEvent]


class SubmissionGradeRequest(BaseModel):
    persona_id: str
    exercise_id: str
    answer: str


class SubmissionGradeResponse(BaseModel):
    score: int
    diagnosis: list[str]
    recommendation: str
    character_events: list[CharacterStateEvent]


class TokenUsageDailyBucket(BaseModel):
    date: str
    feature: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TokenUsageCallRecord(BaseModel):
    id: str
    created_at: str
    feature: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class TokenUsageStatsResponse(BaseModel):
    buckets: list[TokenUsageDailyBucket]
    records: list[TokenUsageCallRecord] = []
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int


DocumentStudyUnitUpdateResponse.model_rebuild()
