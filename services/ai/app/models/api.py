from pydantic import BaseModel

from app.models.domain import (
    CharacterStateEvent,
    Citation,
    DocumentDebugRecord,
    DocumentRecord,
    LearningGoalInput,
    LearningPlanRecord,
    PlanGenerationTraceRecord,
    PlanGenerationRoundRecord,
    PlanToolCallTraceRecord,
    PersonaProfile,
    StreamEventRecord,
    StreamReportRecord,
    StudySessionRecord,
)


class CreatePersonaRequest(BaseModel):
    name: str
    summary: str
    system_prompt: str
    teaching_style: list[str]
    narrative_mode: str
    encouragement_style: str
    correction_style: str


class PersonaResponse(PersonaProfile):
    pass


class PersonaListResponse(BaseModel):
    items: list[PersonaResponse]


class PersonaAssetsResponse(BaseModel):
    persona_id: str
    renderer: str
    asset_manifest: dict[str, object]


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


class LearningPlanCreateRequest(LearningGoalInput):
    pass


class LearningPlanResponse(LearningPlanRecord):
    pass


class LearningPlanListResponse(BaseModel):
    items: list[LearningPlanResponse]


class CreateStudySessionRequest(BaseModel):
    document_id: str
    persona_id: str
    section_id: str


class StudySessionResponse(StudySessionRecord):
    pass


class StudyChatRequest(BaseModel):
    message: str


class StudyChatResponse(BaseModel):
    reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]


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
