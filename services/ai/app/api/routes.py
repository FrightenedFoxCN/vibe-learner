from fastapi import APIRouter

from app.core.bootstrap import container
from app.models.api import (
    CreatePersonaRequest,
    ExerciseGenerateRequest,
    ExerciseGenerateResponse,
    PersonaAssetsResponse,
    PersonaListResponse,
    PersonaResponse,
    StudyChatRequest,
    StudyChatResponse,
    SubmissionGradeRequest,
    SubmissionGradeResponse,
)

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/personas", response_model=PersonaListResponse)
def list_personas() -> PersonaListResponse:
    personas = container.persona_engine.list_personas()
    return PersonaListResponse(items=personas)


@router.post("/personas", response_model=PersonaResponse)
def create_persona(payload: CreatePersonaRequest) -> PersonaResponse:
    persona = container.persona_engine.create_persona(payload)
    return PersonaResponse.model_validate(persona)


@router.get("/personas/{persona_id}/assets", response_model=PersonaAssetsResponse)
def get_persona_assets(persona_id: str) -> PersonaAssetsResponse:
    persona = container.persona_engine.require_persona(persona_id)
    return PersonaAssetsResponse(
        persona_id=persona.id,
        renderer="placeholder",
        asset_manifest={
            "portrait": f"/assets/{persona.id}/portrait.png",
            "expressions": [],
            "live2d_model": None,
        },
    )


@router.post("/study-sessions/{session_id}/chat", response_model=StudyChatResponse)
def study_chat(session_id: str, payload: StudyChatRequest) -> StudyChatResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.pedagogy_orchestrator.generate_chat_reply(
        session_id=session_id,
        persona=persona,
        message=payload.message,
        section_id=payload.section_id,
    )
    return StudyChatResponse.model_validate(response)


@router.post("/exercises/generate", response_model=ExerciseGenerateResponse)
def generate_exercise(payload: ExerciseGenerateRequest) -> ExerciseGenerateResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.pedagogy_orchestrator.generate_exercise(
        persona=persona,
        section_id=payload.section_id,
        topic=payload.topic,
    )
    return ExerciseGenerateResponse.model_validate(response)


@router.post("/submissions/grade", response_model=SubmissionGradeResponse)
def grade_submission(payload: SubmissionGradeRequest) -> SubmissionGradeResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.pedagogy_orchestrator.grade_submission(
        persona=persona,
        exercise_id=payload.exercise_id,
        answer=payload.answer,
    )
    return SubmissionGradeResponse.model_validate(response)
