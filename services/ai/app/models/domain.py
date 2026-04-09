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


class DocumentRecord(BaseModel):
    id: str
    title: str
    original_filename: str
    stored_path: str
    status: str
    ocr_status: str
    created_at: str
    updated_at: str
    sections: list[DocumentSection]


class LearningGoalInput(BaseModel):
    document_id: str
    persona_id: str
    objective: str
    deadline: str
    study_days_per_week: int
    session_minutes: int


class LearningPlanRecord(BaseModel):
    id: str
    document_id: str
    persona_id: str
    objective: str
    deadline: str
    overview: str
    weekly_focus: list[str]
    today_tasks: list[str]
    created_at: str


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
