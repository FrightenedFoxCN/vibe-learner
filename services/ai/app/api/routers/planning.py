from app.models.plan_revision import (
    PlanRevisionRequestV1,
    PlanRevisionDecisionV1,
    PlanRevisionResponseV1,
)
from app.persistence.plan_revision_repository import PlanRevisionRepository
from app.api.ndjson_workflow import NdjsonWorkflow

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.diagnostics import reference_resource
from app.core.bootstrap import Container
from app.api.dependencies import get_container
from fastapi import Depends, HTTPException
from app.models.api import (
    LearningPlanCreateRequest,
    LearningPlanListResponse,
    LearningPlanOperationResponse,
    LearningPlanProgressUpdateRequest,
    LearningPlanResponse,
    LearningPlanCreateResponse,
    LearningPlanUpdateRequest,
    PlanningQuestionAnswerRequest,
)
from app.models.harness import HarnessStage
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.study_unit_revision import (
    StudyUnitRevisionDecisionV1,
    StudyUnitRevisionResponseV1,
)
from app.services.model_recovery import (
    reset_model_recovery_state,
)
from app.services.stream_interrupts import StreamInterruptedError
from app.services.stream_reports import (
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)


from app.api._shared import (
    logger,
    _into_response,
    _require_domain_harness_trace,
    _learning_plan_stream_subject,
    _learning_plan_stream_storage_id,
    _learning_plan_stream_committed_evidence,
    _stream_failure_evidence,
    _runtime_error_retry_attempts,
    _map_plan_generation_error,
    _plan_revision_service,
    _stringify_error,
)

router = APIRouter()


@router.get(
    "/learning-plans/{plan_id}/study-unit-revision",
    response_model=StudyUnitRevisionResponseV1,
)
def get_study_unit_revision(
    plan_id: str, *, container: Container = Depends(get_container)
):
    return container.study_unit_revision_service.repository.get(plan_id)


@router.post(
    "/learning-plans/{plan_id}/study-unit-revision/{operation_id}/decision",
    response_model=StudyUnitRevisionResponseV1,
)
def decide_study_unit_revision(
    plan_id: str,
    operation_id: str,
    payload: StudyUnitRevisionDecisionV1,
    *,
    container: Container = Depends(get_container),
):
    return container.study_unit_revision_service.decide(
        plan_id, operation_id, payload.decision
    )


@router.post("/learning-plans", response_model=LearningPlanCreateResponse)
def create_learning_plan(
    payload: LearningPlanCreateRequest, *, container: Container = Depends(get_container)
) -> LearningPlanCreateResponse:
    reset_model_recovery_state()
    stream_document_id = _learning_plan_stream_storage_id(payload)
    domain_operation_id = ""

    def remember_operation(operation_id: str) -> None:
        nonlocal domain_operation_id
        domain_operation_id = operation_id

    recorder = StreamReportRecorder(
        store=container.store,
        category=LEARNING_PLAN_STREAM_CATEGORY,
        document_id=stream_document_id,
        stream_kind="learning_plan",
        subject=_learning_plan_stream_subject(payload),
    )
    logger.info(
        "learning_plans.create document_id=%s persona_id=%s",
        payload.document_id,
        payload.persona_id,
    )
    persona = container.persona_engine.require_persona(payload.persona_id)
    recorder.emit(
        "learning_plan_started",
        {
            "document_id": payload.document_id,
            "persona_id": payload.persona_id,
            "creation_mode": "document" if payload.document_id else "goal_only",
        },
    )
    try:
        plan = container.plan_service.create_plan(
            goal=payload,
            client_request_id=payload.client_request_id,
            expected_document_updated_at=payload.expected_document_updated_at,
            persona=persona,
            progress_callback=recorder.callback,
            operation_admitted_callback=remember_operation,
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
                "retry_attempts": _runtime_error_retry_attempts(exc),
            },
            terminal_evidence=_stream_failure_evidence(
                operation_id=domain_operation_id,
                domain="learning_plan",
                container=container,
            ),
        )
        logger.warning(
            "learning_plans.create_failed document_id=%s persona_id=%s detail=%s status_code=%s internal_error_code=%s retry_attempts=%s",
            payload.document_id,
            payload.persona_id,
            http_error.detail,
            http_error.status_code,
            str(exc),
            _runtime_error_retry_attempts(exc),
        )
        raise http_error from exc
    except Exception as exc:
        recorder.emit(
            "stream_error",
            {
                "document_id": payload.document_id,
                "detail": _stringify_error(exc),
            },
            terminal_evidence=_stream_failure_evidence(
                operation_id=domain_operation_id,
                domain="learning_plan",
                container=container,
            ),
        )
        raise
    harness_trace = _require_domain_harness_trace(
        domain_operation_kind=HarnessDomainOperationKind.LEARNING_PLAN_GENERATION,
        domain_operation_id=domain_operation_id,
        stage=HarnessStage.PLAN_GENERATION,
        container=container,
    )
    reference_resource("learning_plan", plan.id)
    plan_commit_projection = plan.model_dump(mode="json")
    plan_projection = {
        **plan_commit_projection,
        "harness_trace": harness_trace.model_dump(mode="json", exclude_none=False),
    }
    recorder.emit(
        "stream_completed",
        {
            "document_id": payload.document_id,
            "plan_id": plan.id,
            "creation_mode": plan.creation_mode,
        },
        terminal_evidence=_learning_plan_stream_committed_evidence(
            operation_id=domain_operation_id,
            plan_payload=plan_projection,
            container=container,
        ),
        committed_projection=plan_projection,
    )
    return LearningPlanCreateResponse.model_validate(plan_projection)


@router.get("/learning-plans", response_model=LearningPlanListResponse)
def list_learning_plans(
    *, container: Container = Depends(get_container)
) -> LearningPlanListResponse:
    plans = container.plan_service.list_plans()
    return LearningPlanListResponse(
        items=[_into_response(LearningPlanResponse, plan) for plan in plans]
    )


@router.get(
    "/learning-plan-operations/{client_request_id}",
    response_model=LearningPlanOperationResponse,
)
def get_learning_plan_operation(
    client_request_id: str,
    *,
    container: Container = Depends(get_container),
) -> LearningPlanOperationResponse:
    operation = container.plan_service.require_operation(
        client_request_id=client_request_id
    )
    projection = operation.committed_projection
    return LearningPlanOperationResponse(
        operation_id=operation.operation_id,
        client_request_id=operation.client_request_id,
        document_id=operation.document_id,
        persona_id=operation.persona_id,
        status=operation.status.value,
        projection_state=operation.projection_state.value,
        provider_started_at=operation.provider_started_at,
        plan_id=operation.plan_id,
        error_code=operation.error_code,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
        completed_at=operation.completed_at,
        plan=(
            _into_response(LearningPlanResponse, projection.plan)
            if projection is not None
            else None
        ),
    )


@router.post("/learning-plans/stream")
def create_learning_plan_stream(
    payload: LearningPlanCreateRequest,
    *,
    container: Container = Depends(get_container),
) -> StreamingResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    stream_document_id = _learning_plan_stream_storage_id(payload)
    interrupt_handle = container.stream_interrupt_registry.create(
        stream_kind="learning_plan",
        target_id=stream_document_id,
    )
    recorder = StreamReportRecorder(
        store=container.store,
        category=LEARNING_PLAN_STREAM_CATEGORY,
        document_id=stream_document_id,
        stream_kind="learning_plan",
        subject=_learning_plan_stream_subject(payload),
        operation_id=interrupt_handle.stream_id,
    )
    stream = NdjsonWorkflow(interrupt_handle, recorder)
    domain_operation_id = ""

    def remember_operation(operation_id: str) -> None:
        nonlocal domain_operation_id
        domain_operation_id = operation_id

    def emit_cancelled() -> None:
        stream.emit(
            "stream_cancelled",
            {
                "document_id": payload.document_id,
                "detail": "stream_interrupted",
            },
            terminal_evidence=_stream_failure_evidence(
                operation_id=domain_operation_id,
                domain="learning_plan",
                container=container,
            ),
        )

    def run() -> None:
        reset_model_recovery_state()
        try:
            stream.report(
                "learning_plan_started",
                {
                    "document_id": payload.document_id,
                    "persona_id": payload.persona_id,
                    "creation_mode": "document" if payload.document_id else "goal_only",
                },
            )
            plan = container.plan_service.create_plan(
                goal=payload,
                client_request_id=payload.client_request_id,
                expected_document_updated_at=payload.expected_document_updated_at,
                persona=persona,
                progress_callback=stream.report,
                interrupt_check=interrupt_handle.raise_if_cancelled,
                before_commit=stream.before_commit,
                operation_admitted_callback=remember_operation,
            )
            # A returned plan is already committed (including a replay).
            interrupt_handle.mark_completed()
            harness_trace = _require_domain_harness_trace(
                domain_operation_kind=HarnessDomainOperationKind.LEARNING_PLAN_GENERATION,
                domain_operation_id=domain_operation_id,
                stage=HarnessStage.PLAN_GENERATION,
                container=container,
            )
            reference_resource("learning_plan", plan.id)
            plan_commit_projection = plan.model_dump(mode="json")
            plan_projection = {
                **plan_commit_projection,
                "harness_trace": harness_trace.model_dump(
                    mode="json", exclude_none=False
                ),
            }
            stream.emit(
                "stream_completed",
                {
                    "document_id": payload.document_id,
                    "plan_id": plan.id,
                    "creation_mode": plan.creation_mode,
                },
                terminal_evidence=_learning_plan_stream_committed_evidence(
                    operation_id=domain_operation_id,
                    plan_payload=plan_projection,
                    container=container,
                ),
                committed_projection=plan_projection,
            )
        except StreamInterruptedError:
            interrupt_handle.claim_terminal()
            emit_cancelled()
        except RuntimeError as exc:
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                http_error = _map_plan_generation_error(exc)
                stream.emit(
                    "stream_error",
                    {
                        "document_id": payload.document_id,
                        "detail": http_error.detail,
                        "status_code": http_error.status_code,
                        "internal_error_code": str(exc),
                        "retry_attempts": _runtime_error_retry_attempts(exc),
                    },
                    terminal_evidence=_stream_failure_evidence(
                        operation_id=domain_operation_id,
                        domain="learning_plan",
                        container=container,
                    ),
                )
        except Exception as exc:
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                stream.emit(
                    "stream_error",
                    {
                        "document_id": payload.document_id,
                        "detail": _stringify_error(exc),
                        **(
                            {"status_code": exc.status_code}
                            if isinstance(exc, HTTPException)
                            else {}
                        ),
                    },
                    terminal_evidence=_stream_failure_evidence(
                        operation_id=domain_operation_id,
                        domain="learning_plan",
                        container=container,
                    ),
                )

    return stream.start(run)


@router.post(
    "/learning-plans/{plan_id}/revisions", response_model=PlanRevisionResponseV1
)
def create_plan_revision(
    plan_id: str,
    payload: PlanRevisionRequestV1,
    *,
    container: Container = Depends(get_container),
):
    return _plan_revision_service(container).create(plan_id, payload)


@router.get("/learning-plans/{plan_id}/revision-history")
def plan_revision_history(
    plan_id: str, *, container: Container = Depends(get_container)
) -> dict[str, list[int]]:
    return {"revisions": PlanRevisionRepository(container.database).history(plan_id)}


@router.get(
    "/learning-plans/{plan_id}/revisions/{request_id}",
    response_model=PlanRevisionResponseV1,
)
def get_plan_revision(
    plan_id: str, request_id: str, *, container: Container = Depends(get_container)
):
    return PlanRevisionRepository(container.database).get(plan_id, request_id)


@router.post(
    "/learning-plans/{plan_id}/revisions/{request_id}/decision",
    response_model=PlanRevisionResponseV1,
)
def decide_plan_revision(
    plan_id: str,
    request_id: str,
    payload: PlanRevisionDecisionV1,
    *,
    container: Container = Depends(get_container),
):
    return _plan_revision_service(container).decide(
        plan_id, request_id, payload.decision
    )


@router.get("/learning-plans/{plan_id}", response_model=LearningPlanResponse)
def get_learning_plan(
    plan_id: str, *, container: Container = Depends(get_container)
) -> LearningPlanResponse:
    plan = container.plan_service.require_plan(plan_id)
    return _into_response(LearningPlanResponse, plan)


@router.patch("/learning-plans/{plan_id}", response_model=LearningPlanResponse)
def update_learning_plan(
    plan_id: str,
    payload: LearningPlanUpdateRequest,
    *,
    container: Container = Depends(get_container),
) -> LearningPlanResponse:
    plan = container.plan_service.update_plan(
        plan_id=plan_id,
        expected_revision=payload.expected_revision,
        course_title=payload.course_title,
    )
    return _into_response(LearningPlanResponse, plan)


@router.patch("/learning-plans/{plan_id}/progress", response_model=LearningPlanResponse)
def update_learning_plan_progress(
    plan_id: str,
    payload: LearningPlanProgressUpdateRequest,
    *,
    container: Container = Depends(get_container),
) -> LearningPlanResponse:
    plan = container.plan_service.update_progress(
        plan_id=plan_id,
        expected_revision=payload.expected_revision,
        schedule_ids=payload.schedule_ids,
        status=payload.status,
        note=payload.note,
        actor="user",
        source="ui",
    )
    return _into_response(LearningPlanResponse, plan)


@router.patch(
    "/learning-plans/{plan_id}/planning-questions/{question_id}",
    response_model=LearningPlanResponse,
)
def answer_learning_plan_question(
    plan_id: str,
    question_id: str,
    payload: PlanningQuestionAnswerRequest,
    *,
    container: Container = Depends(get_container),
) -> LearningPlanResponse:
    plan = container.plan_service.answer_planning_question(
        plan_id=plan_id,
        expected_revision=payload.expected_revision,
        question_id=question_id,
        answer=payload.answer,
    )
    return _into_response(LearningPlanResponse, plan)


@router.delete("/learning-plans/{plan_id}")
def delete_learning_plan(
    plan_id: str,
    expected_revision: int | None = None,
    *,
    container: Container = Depends(get_container),
) -> dict[str, str]:
    container.plan_service.delete_plan(plan_id, expected_revision=expected_revision)
    return {"deleted_plan_id": plan_id}
