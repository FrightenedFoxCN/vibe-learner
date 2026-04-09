from fastapi import APIRouter, File, UploadFile

from app.core.bootstrap import container
from app.models.api import (
    CreatePersonaRequest,
    CreateStudySessionRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentStatusResponse,
    ExerciseGenerateRequest,
    ExerciseGenerateResponse,
    LearningPlanCreateRequest,
    LearningPlanResponse,
    PersonaAssetsResponse,
    PersonaListResponse,
    PersonaResponse,
    StudyChatRequest,
    StudyChatResponse,
    StudySessionResponse,
    SubmissionGradeRequest,
    SubmissionGradeResponse,
)

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/documents", response_model=DocumentListResponse)
def list_documents() -> DocumentListResponse:
    return DocumentListResponse(items=container.document_service.list_documents())


@router.post("/documents", response_model=DocumentResponse)
def create_document(file: UploadFile = File(...)) -> DocumentResponse:
    document = container.document_service.create_document(file)
    return DocumentResponse.model_validate(document)


@router.post("/documents/{document_id}/process", response_model=DocumentResponse)
def process_document(document_id: str) -> DocumentResponse:
    document = container.document_service.process_document(document_id)
    return DocumentResponse.model_validate(document)


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(document_id: str) -> DocumentStatusResponse:
    document = container.document_service.require_document(document_id)
    return DocumentStatusResponse.model_validate(document)


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
    session = container.study_session_service.require_session(session_id)
    persona = container.persona_engine.require_persona(session.persona_id)
    response = container.pedagogy_orchestrator.generate_chat_reply(
        session_id=session_id,
        persona=persona,
        message=payload.message,
        section_id=session.section_id,
    )
    container.study_session_service.append_turn(
        session_id=session_id, learner_message=payload.message, result=response
    )
    return StudyChatResponse.model_validate(response)


@router.post("/study-sessions", response_model=StudySessionResponse)
def create_study_session(payload: CreateStudySessionRequest) -> StudySessionResponse:
    session = container.study_session_service.create_session(
        document_id=payload.document_id,
        persona_id=payload.persona_id,
        section_id=payload.section_id,
    )
    return StudySessionResponse.model_validate(session)


@router.post("/learning-plans", response_model=LearningPlanResponse)
def create_learning_plan(payload: LearningPlanCreateRequest) -> LearningPlanResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    document = container.document_service.require_document(payload.document_id)
    plan = container.plan_service.create_plan(
        goal=payload,
        document=document,
        persona_name=persona.name,
    )
    return LearningPlanResponse.model_validate(plan)


@router.get("/learning-plans/{plan_id}", response_model=LearningPlanResponse)
def get_learning_plan(plan_id: str) -> LearningPlanResponse:
    plan = container.plan_service.require_plan(plan_id)
    return LearningPlanResponse.model_validate(plan)


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
