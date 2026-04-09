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


class StudyChatResult(BaseModel):
    reply: str
    citations: list[Citation]
    character_events: list[CharacterStateEvent]


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
