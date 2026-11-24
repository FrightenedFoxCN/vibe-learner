from app.models.output_language import OutputLanguagePreference
from app.services.output_language import plan_output_language
from app.services.study_chat_context import _resolve_session_document
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import Response

from app.core.diagnostics import reference_resource
from app.core.bootstrap import Container
from app.api.dependencies import get_container
from fastapi import Depends
from app.models.api import (
    CreateStudySessionRequest,
    ExerciseGenerateRequest,
    ExerciseGenerateResponse,
    LearningPlanResponse,
    StudyChatRequest,
    StudyChatOperationReceiptResponse,
    StudySessionPlanConfirmationDecisionRequest,
    StudySessionPlanConfirmationDecisionResponse,
    StudyQuestionAttemptRequest,
    StudyQuestionAttemptResponse,
    StudySessionListResponse,
    StudySessionResponse,
    UpdateStudySessionRequest,
    SubmissionGradeRequest,
    SubmissionGradeResponse,
)
from app.persistence.study_chat_operation_repository import StudyChatOperationNotFound
from app.services.study_chat_attachments import read_study_chat_attachment_inputs
from app.services.study_chat_attachments import render_pdf_page_png_bytes
from app.services.study_session_prompt import build_study_session_system_prompt
from app.models.domain import StudySessionRecord
from app.services.study_sessions import StudySessionContext


from app.api._shared import (
    logger,
    _into_response,
    _study_chat_operation_response,
    _resolve_study_unit_title,
    _resolve_study_unit_theme_hint,
    _resolve_session_document_title,
    _invoke_study_chat,
)

router = APIRouter()


@router.get("/study-sessions/{session_id}/attachments/{attachment_id}/file")
def get_study_session_attachment_file(
    session_id: str,
    attachment_id: str,
    *,
    container: Container = Depends(get_container),
) -> FileResponse:
    attachment = container.study_session_service.require_attachment(
        session_id=session_id,
        attachment_id=attachment_id,
    )
    path = Path(attachment.stored_path)
    if not attachment.stored_path or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="session_attachment_file_not_found")
    return FileResponse(
        path=path,
        media_type=attachment.mime_type or "application/octet-stream",
        filename=attachment.name,
        headers={"Content-Disposition": "inline"},
    )


@router.get(
    "/study-sessions/{session_id}/attachments/{attachment_id}/pages/{page_number}/image"
)
def get_study_session_attachment_page_image(
    session_id: str,
    attachment_id: str,
    page_number: int,
    *,
    container: Container = Depends(get_container),
) -> Response:
    attachment = container.study_session_service.require_attachment(
        session_id=session_id,
        attachment_id=attachment_id,
    )
    path = Path(attachment.stored_path)
    if (
        attachment.kind != "pdf"
        or not attachment.stored_path
        or not path.exists()
        or not path.is_file()
    ):
        raise HTTPException(status_code=404, detail="session_attachment_file_not_found")
    image_bytes = render_pdf_page_png_bytes(
        pdf_path=str(path),
        page_number=page_number,
    )
    return Response(content=image_bytes, media_type="image/png")


@router.post(
    "/study-sessions/{session_id}/chat",
    response_model=StudyChatOperationReceiptResponse,
)
def study_chat(
    session_id: str,
    payload: StudyChatRequest,
    *,
    container: Container = Depends(get_container),
) -> StudyChatOperationReceiptResponse:
    return _invoke_study_chat(
        container,
        session_id=session_id,
        client_request_id=payload.client_request_id,
        expected_session_revision=payload.expected_session_revision,
        message=payload.message,
        message_kind=payload.message_kind,
        follow_up_id=payload.follow_up_id,
        hidden_message_prefix=payload.hidden_message_prefix,
        output_language=payload.output_language,
    )


@router.post(
    "/study-sessions/{session_id}/chat-with-attachments",
    response_model=StudyChatOperationReceiptResponse,
)
def study_chat_with_attachments(
    session_id: str,
    client_request_id: str = Form(...),
    expected_session_revision: int = Form(...),
    message: str = Form(...),
    message_kind: str = Form("learner"),
    follow_up_id: str = Form(""),
    hidden_message_prefix: str = Form(""),
    output_language: OutputLanguagePreference | None = Form(None),
    files: list[UploadFile] | None = File(default=None),
    *,
    container: Container = Depends(get_container),
) -> StudyChatOperationReceiptResponse:
    attachment_inputs = read_study_chat_attachment_inputs(files or [])
    return _invoke_study_chat(
        container,
        session_id=session_id,
        client_request_id=client_request_id,
        expected_session_revision=expected_session_revision,
        message=message,
        message_kind=message_kind,
        follow_up_id=follow_up_id,
        hidden_message_prefix=hidden_message_prefix,
        output_language=output_language,
        attachment_inputs=attachment_inputs,
    )


@router.get(
    "/study-sessions/{session_id}/chat-operations/{client_request_id}",
    response_model=StudyChatOperationReceiptResponse,
)
def get_study_chat_operation(
    session_id: str,
    client_request_id: str,
    *,
    container: Container = Depends(get_container),
) -> StudyChatOperationReceiptResponse:
    try:
        receipt = container.study_chat_application().get_receipt(
            session_id=session_id,
            client_request_id=client_request_id,
        )
    except StudyChatOperationNotFound as exc:
        raise HTTPException(
            status_code=404, detail="study_chat_operation_not_found"
        ) from exc
    return _study_chat_operation_response(receipt)


@router.post(
    "/study-sessions/{session_id}/follow-ups/cancel",
    response_model=StudySessionResponse,
)
def cancel_study_session_follow_ups(
    session_id: str, *, container: Container = Depends(get_container)
) -> StudySessionResponse:
    session = container.study_session_service.cancel_pending_follow_ups(
        session_id=session_id
    )
    return _into_response(StudySessionResponse, session)


@router.post(
    "/study-sessions/{session_id}/plan-confirmations/{confirmation_id}",
    response_model=StudySessionPlanConfirmationDecisionResponse,
)
def resolve_study_session_plan_confirmation(
    session_id: str,
    confirmation_id: str,
    payload: StudySessionPlanConfirmationDecisionRequest,
    *,
    container: Container = Depends(get_container),
) -> StudySessionPlanConfirmationDecisionResponse:
    decision = payload.decision.strip().lower()
    if decision not in {"approve", "reject"}:
        raise HTTPException(status_code=422, detail="invalid_confirmation_decision")
    refreshed_session, updated_plan = container.plan_service.resolve_confirmation(
        session_id=session_id,
        confirmation_id=confirmation_id,
        decision=decision,
        note=payload.note,
    )
    return StudySessionPlanConfirmationDecisionResponse(
        session=_into_response(StudySessionResponse, refreshed_session),
        plan=_into_response(LearningPlanResponse, updated_plan)
        if updated_plan is not None
        else None,
    )


@router.get("/study-sessions", response_model=StudySessionListResponse)
def list_study_sessions(
    document_id: str | None = None,
    persona_id: str | None = None,
    plan_id: str | None = None,
    study_unit_id: str | None = None,
    section_id: str | None = None,
    *,
    container: Container = Depends(get_container),
) -> StudySessionListResponse:
    resolved_study_unit_id = study_unit_id or section_id
    sessions = container.study_session_service.list_sessions(
        document_id=document_id,
        persona_id=persona_id,
        plan_id=plan_id,
        study_unit_id=resolved_study_unit_id,
    )
    return StudySessionListResponse(
        items=[_into_response(StudySessionResponse, session) for session in sessions]
    )


@router.get("/study-sessions/{session_id}", response_model=StudySessionResponse)
def get_study_session(
    session_id: str, *, container: Container = Depends(get_container)
) -> StudySessionResponse:
    session = container.study_session_service.require_session(session_id)
    return _into_response(StudySessionResponse, session)


@router.post(
    "/study-sessions/{session_id}/attempt",
    response_model=StudyQuestionAttemptResponse,
)
def record_study_question_attempt(
    session_id: str,
    payload: StudyQuestionAttemptRequest,
    *,
    container: Container = Depends(get_container),
) -> StudyQuestionAttemptResponse:
    result = container.study_session_service.record_question_attempt(
        session_id=session_id,
        turn_id=payload.turn_id,
        expected_session_revision=payload.expected_session_revision,
        client_attempt_id=payload.client_attempt_id,
        submitted_answer=payload.submitted_answer,
    )
    response = StudyQuestionAttemptResponse.model_validate(
        result.model_dump(mode="json")
    )
    reference_resource(
        "study_session", response.session_id, revision=response.committed_revision
    )
    return response


@router.patch("/study-sessions/{session_id}", response_model=StudySessionResponse)
def update_study_session(
    session_id: str,
    payload: UpdateStudySessionRequest,
    *,
    container: Container = Depends(get_container),
) -> StudySessionResponse:
    if (
        payload.study_unit_id is None
        and "scene_profile" not in payload.model_fields_set
    ):
        raise HTTPException(status_code=400, detail="update_payload_empty")

    current_session = container.study_session_service.require_session(session_id)
    # These IDs are immutable across Session revisions. Mutable Session context
    # is derived below from each attempt's snapshot, not the route's pre-read.
    persona = container.persona_engine.require_persona(current_session.persona_id)
    active_plan = None
    if current_session.plan_id:
        try:
            active_plan = container.plan_service.require_plan(current_session.plan_id)
        except HTTPException:
            active_plan = None
    document = _resolve_session_document(
        current_session.document_id,
        active_plan,
        document_service=container.document_service,
    )
    document_title = _resolve_session_document_title(
        document=document, plan=active_plan
    )

    def resolve_context(session: StudySessionRecord) -> StudySessionContext:
        study_unit_title = _resolve_study_unit_title(
            document=document, plan=active_plan, study_unit_id=session.study_unit_id
        )
        theme_hint = _resolve_study_unit_theme_hint(
            plan=active_plan,
            study_unit_id=session.study_unit_id,
            fallback=session.theme_hint,
        )
        return StudySessionContext(
            study_unit_title=study_unit_title,
            theme_hint=theme_hint,
            system_prompt=build_study_session_system_prompt(
                persona_name=persona.name,
                persona_relationship=persona.relationship,
                persona_learner_address=persona.learner_address,
                document_title=document_title,
                study_unit_id=session.study_unit_id,
                study_unit_title=study_unit_title,
                theme_hint=theme_hint,
                scene_profile=session.scene_profile,
            ),
        )

    session = container.study_session_service.update_session(
        session_id=session_id,
        study_unit_id=payload.study_unit_id,
        has_scene_profile="scene_profile" in payload.model_fields_set,
        scene_profile=payload.scene_profile,
        resolve_context=resolve_context,
    )
    return _into_response(StudySessionResponse, session)


@router.post("/study-sessions", response_model=StudySessionResponse)
def create_study_session(
    payload: CreateStudySessionRequest, *, container: Container = Depends(get_container)
) -> StudySessionResponse:
    session_id = f"session-{uuid4().hex[:10]}"
    logger.info(
        "study_sessions.create document_id=%s persona_id=%s study_unit_id=%s scene_id=%s",
        payload.document_id,
        payload.persona_id,
        payload.study_unit_id,
        payload.scene_profile.scene_id if payload.scene_profile else "",
    )
    persona = container.persona_engine.require_persona(payload.persona_id)
    plan_id = payload.plan_id.strip() if payload.plan_id else None
    plan = None
    resolved_document_id = payload.document_id
    if plan_id:
        plan = container.plan_service.require_plan(plan_id)
        if plan.persona_id != payload.persona_id:
            raise HTTPException(status_code=400, detail="plan_session_binding_mismatch")
        if (
            plan.document_id
            and payload.document_id
            and plan.document_id != payload.document_id
        ):
            raise HTTPException(status_code=400, detail="plan_session_binding_mismatch")
        if not resolved_document_id and plan.document_id:
            resolved_document_id = plan.document_id
    document = _resolve_session_document(
        resolved_document_id, plan, document_service=container.document_service
    )
    study_unit_title = payload.study_unit_title.strip() or _resolve_study_unit_title(
        document=document,
        plan=plan,
        study_unit_id=payload.study_unit_id,
    )
    theme_hint = _resolve_study_unit_theme_hint(
        plan=plan,
        study_unit_id=payload.study_unit_id,
        fallback=payload.theme_hint.strip(),
    )
    bound_scene = container.session_scene_service.prepare_scene_for_session(
        session_id=session_id,
        document_id=resolved_document_id,
        persona_id=payload.persona_id,
        scene_profile=payload.scene_profile,
    )
    session_scene_profile = bound_scene.scene_profile if bound_scene else None
    session_system_prompt = build_study_session_system_prompt(
        persona_name=persona.name,
        persona_relationship=persona.relationship,
        persona_learner_address=persona.learner_address,
        document_title=_resolve_session_document_title(document=document, plan=plan),
        study_unit_id=payload.study_unit_id,
        study_unit_title=study_unit_title,
        theme_hint=theme_hint,
        scene_profile=session_scene_profile,
    )
    session = container.study_session_service.create_session(
        session_id=session_id,
        document_id=resolved_document_id,
        persona_id=payload.persona_id,
        plan_id=plan_id,
        new_scene=bound_scene,
        study_unit_id=payload.study_unit_id,
        study_unit_title=study_unit_title,
        theme_hint=theme_hint,
        session_system_prompt=session_system_prompt,
        output_language=payload.output_language or plan_output_language(plan),
    )
    reference_resource("study_session", session.id, revision=session.revision)
    return _into_response(StudySessionResponse, session)


@router.post("/stream-runs/{stream_id}/cancel")
def cancel_stream_run(
    stream_id: str, *, container: Container = Depends(get_container)
) -> dict[str, object]:
    handle = container.stream_interrupt_registry.cancel(stream_id=stream_id)
    return {
        "stream_id": handle.stream_id,
        "stream_kind": handle.stream_kind,
        "target_id": handle.target_id,
        "cancelled": handle.cancelled(),
        "cancelled_at": handle.cancelled_at,
    }


@router.post("/exercises/generate", response_model=ExerciseGenerateResponse)
def generate_exercise(
    payload: ExerciseGenerateRequest, *, container: Container = Depends(get_container)
) -> ExerciseGenerateResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.capture_pedagogy_orchestrator().generate_exercise(
        persona=persona,
        section_id=payload.section_id,
        topic=payload.topic,
    )
    return _into_response(ExerciseGenerateResponse, response)


@router.post("/submissions/grade", response_model=SubmissionGradeResponse)
def grade_submission(
    payload: SubmissionGradeRequest, *, container: Container = Depends(get_container)
) -> SubmissionGradeResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.capture_pedagogy_orchestrator().grade_submission(
        persona=persona,
        exercise_id=payload.exercise_id,
        answer=payload.answer,
    )
    return _into_response(SubmissionGradeResponse, response)
