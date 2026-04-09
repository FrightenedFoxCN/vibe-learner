from pydantic import BaseModel

from app.models.domain import (
    CharacterStateEvent,
    Citation,
    DocumentRecord,
    LearningGoalInput,
    LearningPlanRecord,
    PersonaProfile,
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


class LearningPlanCreateRequest(LearningGoalInput):
    pass


class LearningPlanResponse(LearningPlanRecord):
    pass


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
