import json
from pathlib import Path
import queue
import threading

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.bootstrap import container
from app.models.api import (
    CreatePersonaRequest,
    CreateStudySessionRequest,
    DocumentDebugResponse,
    DocumentListResponse,
    DocumentPlanningContextResponse,
    DocumentPlanningTraceResponse,
    DocumentResponse,
    StreamReportResponse,
    DocumentStatusResponse,
    ExerciseGenerateRequest,
    ExerciseGenerateResponse,
    LearningPlanCreateRequest,
    LearningPlanListResponse,
    LearningPlanResponse,
    PersonaAssetsResponse,
    ProcessDocumentRequest,
    PersonaSettingAssistRequest,
    PersonaSettingAssistResponse,
    PersonaListResponse,
    PersonaResponse,
    StudyChatRequest,
    StudyChatResponse,
    StudyChatExchangeResponse,
    StudyQuestionAttemptRequest,
    StudySessionListResponse,
    StudySessionResponse,
    UpdatePersonaRequest,
    UpdateStudySessionRequest,
    SubmissionGradeRequest,
    SubmissionGradeResponse,
)
from app.models.domain import PlanGenerationTraceRecord
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)
from app.services.plan_prompt import build_learning_plan_context
from app.services.plan_tool_runtime import get_learning_plan_tool_specs
from app.services.study_session_prompt import build_study_session_system_prompt

router = APIRouter()
logger = get_logger("vibe_learner.routes")


def _into_response(response_model: type[BaseModel], value: BaseModel | dict) -> BaseModel:
    payload = value.model_dump() if isinstance(value, BaseModel) else value
    return response_model.model_validate(payload)


def _map_plan_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "openai_plan_request_rate_limit":
        return HTTPException(status_code=503, detail="plan_model_rate_limited")
    if detail == "openai_plan_request_timeout":
        return HTTPException(status_code=504, detail="plan_model_timeout")
    if detail == "openai_plan_request_network_error":
        return HTTPException(status_code=502, detail="plan_model_network_error")
    if detail.startswith("openai_plan_request_failed:"):
        return HTTPException(status_code=502, detail="plan_model_upstream_error")
    if detail == "plan_model_invalid_json":
        return HTTPException(status_code=502, detail="plan_model_invalid_json")
    if detail == "plan_model_invalid_payload":
        return HTTPException(status_code=502, detail="plan_model_invalid_payload")
    if detail == "plan_model_empty_response":
        return HTTPException(status_code=502, detail="plan_model_empty_response")
    if detail == "plan_model_tool_loop_exhausted":
        return HTTPException(status_code=502, detail="plan_model_tool_loop_exhausted")
    return HTTPException(status_code=500, detail="plan_generation_failed")


def _map_chat_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "openai_chat_request_rate_limit":
        return HTTPException(status_code=503, detail="chat_model_rate_limited")
    if detail == "openai_chat_request_timeout":
        return HTTPException(status_code=504, detail="chat_model_timeout")
    if detail == "openai_chat_request_network_error":
        return HTTPException(status_code=502, detail="chat_model_network_error")
    if detail.startswith("openai_chat_request_failed:"):
        return HTTPException(status_code=502, detail="chat_model_upstream_error")
    if detail == "chat_model_invalid_payload":
        return HTTPException(status_code=502, detail="chat_model_invalid_payload")
    return HTTPException(status_code=500, detail="chat_generation_failed")


def _map_setting_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "openai_setting_request_rate_limit":
        return HTTPException(status_code=503, detail="setting_model_rate_limited")
    if detail == "openai_setting_request_timeout":
        return HTTPException(status_code=504, detail="setting_model_timeout")
    if detail == "openai_setting_request_network_error":
        return HTTPException(status_code=502, detail="setting_model_network_error")
    if detail.startswith("openai_setting_request_failed:"):
        return HTTPException(status_code=502, detail="setting_model_upstream_error")
    if detail == "setting_model_invalid_json":
        return HTTPException(status_code=502, detail="setting_model_invalid_json")
    if detail == "setting_model_invalid_payload":
        return HTTPException(status_code=502, detail="setting_model_invalid_payload")
    return HTTPException(status_code=500, detail="setting_generation_failed")


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/documents", response_model=DocumentListResponse)
def list_documents() -> DocumentListResponse:
    return DocumentListResponse(
        items=[
            _into_response(DocumentResponse, document)
            for document in container.document_service.list_documents()
        ]
    )


@router.post("/documents", response_model=DocumentResponse)
def create_document(file: UploadFile = File(...)) -> DocumentResponse:
    logger.info(
        "documents.create filename=%s content_type=%s",
        file.filename,
        file.content_type,
    )
    document = container.document_service.create_document(file)
    return _into_response(DocumentResponse, document)


@router.post("/documents/{document_id}/process", response_model=DocumentResponse)
def process_document(
    document_id: str, payload: ProcessDocumentRequest | None = None
) -> DocumentResponse:
    recorder = StreamReportRecorder(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
    )
    logger.info(
        "documents.process document_id=%s force_ocr=%s",
        document_id,
        payload.force_ocr if payload else False,
    )
    try:
        document = container.document_service.process_document(
            document_id,
            force_ocr=(payload.force_ocr if payload else False),
            progress_callback=recorder.callback,
        )
    except Exception as exc:
        recorder.emit(
            "stream_error",
            {
                "document_id": document_id,
                "error": _stringify_error(exc),
            },
        )
        raise
    recorder.emit(
        "stream_completed",
        {
            "document_id": document.id,
            "status": document.status,
        },
    )
    return _into_response(DocumentResponse, document)


@router.post("/documents/{document_id}/process/stream")
def process_document_stream(
    document_id: str, payload: ProcessDocumentRequest | None = None
) -> StreamingResponse:
    force_ocr = payload.force_ocr if payload else False
    event_queue: queue.Queue[dict[str, object] | None] = queue.Queue()
    recorder = StreamReportRecorder(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
    )

    def report(stage: str, event_payload: dict[str, object]) -> None:
        recorder.emit(stage, event_payload)
        event_queue.put({"stage": stage, "payload": event_payload})

    def run() -> None:
        try:
            document = container.document_service.process_document(
                document_id,
                force_ocr=force_ocr,
                progress_callback=report,
            )
            recorder.emit(
                "stream_completed",
                {
                    "document_id": document.id,
                    "status": document.status,
                },
            )
            event_queue.put(
                {
                    "stage": "stream_completed",
                    "payload": {
                        "document_id": document.id,
                        "status": document.status,
                    },
                    "document": document.model_dump(mode="json"),
                }
            )
        except Exception as exc:
            recorder.emit(
                "stream_error",
                {
                    "document_id": document_id,
                    "error": _stringify_error(exc),
                },
            )
            event_queue.put(
                {
                    "stage": "stream_error",
                    "payload": {
                        "document_id": document_id,
                        "error": str(exc),
                    },
                }
            )
        finally:
            event_queue.put(None)

    threading.Thread(target=run, daemon=True).start()

    def generate():
        while True:
            item = event_queue.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(document_id: str) -> DocumentStatusResponse:
    document = container.document_service.require_document(document_id)
    return _into_response(DocumentStatusResponse, document)


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: str) -> FileResponse:
    document = container.document_service.require_document(document_id)
    path = Path(document.stored_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="document_file_not_found")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/documents/{document_id}/debug", response_model=DocumentDebugResponse)
def get_document_debug(document_id: str) -> DocumentDebugResponse:
    report = container.document_service.require_debug_report(document_id)
    return _into_response(DocumentDebugResponse, report)


@router.get("/documents/{document_id}/process-events", response_model=StreamReportResponse)
def get_document_process_events(document_id: str) -> StreamReportResponse:
    report = StreamReportRecorder.load(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
    )
    return _into_response(StreamReportResponse, report)


@router.get(
    "/documents/{document_id}/planning-context",
    response_model=DocumentPlanningContextResponse,
)
def get_document_planning_context(document_id: str) -> DocumentPlanningContextResponse:
    document = container.document_service.require_document(document_id)
    report = container.document_service.require_debug_report(document_id)
    study_units = document.study_units or report.study_units
    planning_context = build_learning_plan_context(
        study_units=study_units,
        debug_report=report,
    )
    payload = {
        "document_id": document_id,
        "course_outline": planning_context["course_outline"],
        "study_units": planning_context["study_units"],
        "detail_map": planning_context["detail_map"],
        "available_tools": get_learning_plan_tool_specs(
            study_units=study_units,
            detail_map=planning_context["detail_map"],
            debug_report=report,
            document_path=document.stored_path,
            multimodal_enabled=container.model_provider.supports_page_image_tools(),
        ),
    }
    return _into_response(DocumentPlanningContextResponse, payload)


@router.get(
    "/documents/{document_id}/planning-trace",
    response_model=DocumentPlanningTraceResponse,
)
def get_document_planning_trace(document_id: str) -> DocumentPlanningTraceResponse:
    trace = container.store.load_item("planning_trace", document_id, PlanGenerationTraceRecord)
    if trace is not None:
        tool_call_count = sum(len(round_record.tool_calls) for round_record in trace.rounds)
        latest_finish_reason = trace.rounds[-1].finish_reason if trace.rounds else ""
        return DocumentPlanningTraceResponse(
            document_id=document_id,
            has_trace=True,
            summary={
                "round_count": len(trace.rounds),
                "tool_call_count": tool_call_count,
                "latest_finish_reason": latest_finish_reason,
            },
            trace=trace.model_dump(mode="json"),
        )
    return DocumentPlanningTraceResponse(
        document_id=document_id,
        has_trace=False,
        summary={
            "round_count": 0,
            "tool_call_count": 0,
            "latest_finish_reason": "",
        },
        trace=None,
    )


@router.get("/documents/{document_id}/plan-events", response_model=StreamReportResponse)
def get_document_plan_events(document_id: str) -> StreamReportResponse:
    report = StreamReportRecorder.load(
        store=container.store,
        category=LEARNING_PLAN_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="learning_plan",
    )
    return _into_response(StreamReportResponse, report)


@router.get("/personas", response_model=PersonaListResponse)
def list_personas() -> PersonaListResponse:
    personas = container.persona_engine.list_personas()
    return PersonaListResponse(
        items=[_into_response(PersonaResponse, persona) for persona in personas]
    )


@router.post("/personas", response_model=PersonaResponse)
def create_persona(payload: CreatePersonaRequest) -> PersonaResponse:
    persona = container.persona_engine.create_persona(payload)
    return _into_response(PersonaResponse, persona)


@router.patch("/personas/{persona_id}", response_model=PersonaResponse)
def update_persona(persona_id: str, payload: UpdatePersonaRequest) -> PersonaResponse:
    persona = container.persona_engine.update_persona(persona_id, payload)
    return _into_response(PersonaResponse, persona)


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


@router.post("/personas/assist-setting", response_model=PersonaSettingAssistResponse)
def assist_persona_setting(payload: PersonaSettingAssistRequest) -> PersonaSettingAssistResponse:
    try:
        result = container.model_provider.assist_persona_setting(
            name=payload.name,
            summary=payload.summary,
            slots=payload.slots,
            rewrite_strength=payload.rewrite_strength,
        )
    except RuntimeError as exc:
        http_error = _map_setting_generation_error(exc)
        logger.warning(
            "persona.assist_setting.model_failed detail=%s internal_error_code=%s fallback=local",
            http_error.detail,
            str(exc),
        )
        result = container.persona_engine.assist_setting(
            name=payload.name,
            summary=payload.summary,
            slots=payload.slots,
        )
    return PersonaSettingAssistResponse(**result)


@router.post("/study-sessions/{session_id}/chat", response_model=StudyChatExchangeResponse)
def study_chat(session_id: str, payload: StudyChatRequest) -> StudyChatExchangeResponse:
    session = container.study_session_service.require_session(session_id)
    persona = container.persona_engine.require_persona(session.persona_id)
    document = container.document_service.require_document(session.document_id)
    debug_report = None
    try:
        debug_report = container.document_service.require_debug_report(session.document_id)
    except HTTPException:
        debug_report = None

    try:
        response = container.pedagogy_orchestrator.generate_chat_reply(
            session_id=session_id,
            persona=persona,
            message=payload.message,
            section_id=session.section_id,
            session_system_prompt=session.session_system_prompt,
            debug_report=debug_report,
            document_path=document.stored_path,
            previous_turns=session.turns,
        )
    except RuntimeError as exc:
        http_error = _map_chat_generation_error(exc)
        logger.exception(
            "study_chat.error session_id=%s public_detail=%s internal_error_code=%s",
            session_id,
            http_error.detail,
            str(exc),
        )
        raise http_error from exc
    session = container.study_session_service.append_turn(
        session_id=session_id, learner_message=payload.message, result=response
    )
    return StudyChatExchangeResponse(
        **response.model_dump(mode="json"),
        session=_into_response(StudySessionResponse, session),
    )


@router.get("/study-sessions", response_model=StudySessionListResponse)
def list_study_sessions(
    document_id: str | None = None,
    persona_id: str | None = None,
    section_id: str | None = None,
) -> StudySessionListResponse:
    sessions = container.study_session_service.list_sessions(
        document_id=document_id,
        persona_id=persona_id,
        section_id=section_id,
    )
    return StudySessionListResponse(
        items=[_into_response(StudySessionResponse, session) for session in sessions]
    )


@router.post("/study-sessions/{session_id}/attempt", response_model=StudySessionResponse)
def record_study_question_attempt(
    session_id: str,
    payload: StudyQuestionAttemptRequest,
) -> StudySessionResponse:
    answer = payload.submitted_answer.strip()
    learner_message = (
        f"[练习作答] {payload.question_type} · {payload.topic or '章节练习'}\n"
        f"我的答案: {answer or '（空）'}"
    )
    verdict = "回答正确" if payload.is_correct else "回答不正确"
    explanation = payload.explanation.strip()
    assistant_reply = (
        f"{verdict}。"
        if not explanation
        else f"{verdict}。解析：{explanation}"
    )
    session = container.study_session_service.append_attempt_turn(
        session_id=session_id,
        learner_message=learner_message,
        assistant_reply=assistant_reply,
    )
    return _into_response(StudySessionResponse, session)


@router.patch("/study-sessions/{session_id}", response_model=StudySessionResponse)
def update_study_session(
    session_id: str, payload: UpdateStudySessionRequest
) -> StudySessionResponse:
    session = container.study_session_service.update_section(
        session_id=session_id,
        section_id=payload.section_id,
    )
    return _into_response(StudySessionResponse, session)


@router.post("/study-sessions", response_model=StudySessionResponse)
def create_study_session(payload: CreateStudySessionRequest) -> StudySessionResponse:
    logger.info(
        "study_sessions.create document_id=%s persona_id=%s section_id=%s",
        payload.document_id,
        payload.persona_id,
        payload.section_id,
    )
    persona = container.persona_engine.require_persona(payload.persona_id)
    document = container.document_service.require_document(payload.document_id)
    section_title = payload.section_title.strip() or _resolve_section_title(
        document=document,
        section_id=payload.section_id,
    )
    theme_hint = payload.theme_hint.strip()
    session_system_prompt = build_study_session_system_prompt(
        persona_name=persona.name,
        persona_system_prompt=persona.system_prompt,
        document_title=document.title,
        section_id=payload.section_id,
        section_title=section_title,
        theme_hint=theme_hint,
    )
    session = container.study_session_service.create_session(
        document_id=payload.document_id,
        persona_id=payload.persona_id,
        section_id=payload.section_id,
        section_title=section_title,
        theme_hint=theme_hint,
        session_system_prompt=session_system_prompt,
    )
    return _into_response(StudySessionResponse, session)


def _resolve_section_title(*, document, section_id: str) -> str:
    for section in document.sections:
        if section.id == section_id:
            return section.title
    for unit in document.study_units:
        if unit.id == section_id:
            return unit.title
    return section_id


@router.post("/learning-plans", response_model=LearningPlanResponse)
def create_learning_plan(payload: LearningPlanCreateRequest) -> LearningPlanResponse:
    recorder = StreamReportRecorder(
        store=container.store,
        category=LEARNING_PLAN_STREAM_CATEGORY,
        document_id=payload.document_id,
        stream_kind="learning_plan",
    )
    logger.info(
        "learning_plans.create document_id=%s persona_id=%s",
        payload.document_id,
        payload.persona_id,
    )
    persona = container.persona_engine.require_persona(payload.persona_id)
    document = container.document_service.require_document(payload.document_id)
    debug_report = (
        container.document_service.require_debug_report(payload.document_id)
        if document.debug_ready
        else None
    )
    recorder.emit(
        "learning_plan_started",
        {
            "document_id": payload.document_id,
            "persona_id": payload.persona_id,
        },
    )
    try:
        plan = container.plan_service.create_plan(
            goal=payload,
            document=document,
            persona_name=persona.name,
            persona=persona,
            debug_report=debug_report,
            progress_callback=recorder.callback,
        )
    except RuntimeError as exc:
        http_error = _map_plan_generation_error(exc)
        recorder.emit(
            "stream_error",
            {
                "document_id": payload.document_id,
                "detail": http_error.detail,
                "status_code": http_error.status_code,
                "internal_error_code": str(exc),
            },
        )
        logger.warning(
            "learning_plans.create_failed document_id=%s persona_id=%s detail=%s status_code=%s internal_error_code=%s",
            payload.document_id,
            payload.persona_id,
            http_error.detail,
            http_error.status_code,
            str(exc),
        )
        raise http_error from exc
    recorder.emit(
        "stream_completed",
        {
            "document_id": payload.document_id,
            "plan_id": plan.id,
        },
    )
    return _into_response(LearningPlanResponse, plan)


@router.get("/learning-plans", response_model=LearningPlanListResponse)
def list_learning_plans() -> LearningPlanListResponse:
    plans = container.plan_service.list_plans()
    return LearningPlanListResponse(
        items=[_into_response(LearningPlanResponse, plan) for plan in plans]
    )


@router.post("/learning-plans/stream")
def create_learning_plan_stream(
    payload: LearningPlanCreateRequest,
) -> StreamingResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    document = container.document_service.require_document(payload.document_id)
    debug_report = (
        container.document_service.require_debug_report(payload.document_id)
        if document.debug_ready
        else None
    )
    event_queue: queue.Queue[dict[str, object] | None] = queue.Queue()
    recorder = StreamReportRecorder(
        store=container.store,
        category=LEARNING_PLAN_STREAM_CATEGORY,
        document_id=payload.document_id,
        stream_kind="learning_plan",
    )

    def report(stage: str, event_payload: dict[str, object]) -> None:
        recorder.emit(stage, event_payload)
        event_queue.put({"stage": stage, "payload": event_payload})

    def run() -> None:
        try:
            report(
                "learning_plan_started",
                {
                    "document_id": payload.document_id,
                    "persona_id": payload.persona_id,
                },
            )
            plan = container.plan_service.create_plan(
                goal=payload,
                document=document,
                persona_name=persona.name,
                persona=persona,
                debug_report=debug_report,
                progress_callback=report,
            )
            recorder.emit(
                "stream_completed",
                {
                    "document_id": payload.document_id,
                    "plan_id": plan.id,
                },
            )
            event_queue.put(
                {
                    "stage": "stream_completed",
                    "payload": {
                        "document_id": payload.document_id,
                        "plan_id": plan.id,
                    },
                    "plan": plan.model_dump(mode="json"),
                }
            )
        except RuntimeError as exc:
            http_error = _map_plan_generation_error(exc)
            recorder.emit(
                "stream_error",
                {
                    "document_id": payload.document_id,
                    "detail": http_error.detail,
                    "status_code": http_error.status_code,
                    "internal_error_code": str(exc),
                },
            )
            event_queue.put(
                {
                    "stage": "stream_error",
                    "payload": {
                        "document_id": payload.document_id,
                        "detail": http_error.detail,
                        "status_code": http_error.status_code,
                        "internal_error_code": str(exc),
                    },
                }
            )
        except Exception as exc:
            recorder.emit(
                "stream_error",
                {
                    "document_id": payload.document_id,
                    "detail": str(exc),
                },
            )
            event_queue.put(
                {
                    "stage": "stream_error",
                    "payload": {
                        "document_id": payload.document_id,
                        "detail": str(exc),
                    },
                }
            )
        finally:
            event_queue.put(None)

    threading.Thread(target=run, daemon=True).start()

    def generate():
        while True:
            item = event_queue.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/learning-plans/{plan_id}", response_model=LearningPlanResponse)
def get_learning_plan(plan_id: str) -> LearningPlanResponse:
    plan = container.plan_service.require_plan(plan_id)
    return _into_response(LearningPlanResponse, plan)


@router.post("/exercises/generate", response_model=ExerciseGenerateResponse)
def generate_exercise(payload: ExerciseGenerateRequest) -> ExerciseGenerateResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.pedagogy_orchestrator.generate_exercise(
        persona=persona,
        section_id=payload.section_id,
        topic=payload.topic,
    )
    return _into_response(ExerciseGenerateResponse, response)


@router.post("/submissions/grade", response_model=SubmissionGradeResponse)
def grade_submission(payload: SubmissionGradeRequest) -> SubmissionGradeResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.pedagogy_orchestrator.grade_submission(
        persona=persona,
        exercise_id=payload.exercise_id,
        answer=payload.answer,
    )
    return _into_response(SubmissionGradeResponse, response)


def _stringify_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail is not None:
        return str(detail)
    return str(exc)
