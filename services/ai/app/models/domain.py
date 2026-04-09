from pydantic import BaseModel, Field


class PersonaProfile(BaseModel):
    id: str
    name: str
    source: str
    summary: str
    system_prompt: str
    teaching_style: list[str]
    narrative_mode: str
    encouragement_style: str
    correction_style: str
    available_emotions: list[str]
    available_actions: list[str]
    default_speech_style: str


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
    objective: str
    deadline: str
    study_days_per_week: int
    session_minutes: int


class StudyScheduleRecord(BaseModel):
    id: str
    unit_id: str
    title: str
    scheduled_date: str
    focus: str
    activity_type: str
    estimated_minutes: int
    status: str = "planned"


class LearningPlanRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    objective: str
    deadline: str
    overview: str
    weekly_focus: list[str]
    today_tasks: list[str]
    study_units: list[StudyUnitRecord] = []
    schedule: list[StudyScheduleRecord] = []
    created_at: str


class PlanToolCallTraceRecord(BaseModel):
    tool_call_id: str
    tool_name: str
    arguments_json: str
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


class StudyChatResult(BaseModel):
    reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]


class DialogueTurnRecord(BaseModel):
    learner_message: str
    assistant_reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]
    created_at: str


class StudySessionRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    section_id: str
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
