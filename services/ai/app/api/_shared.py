from app.persistence.plan_revision_repository import PlanRevisionRepository
from app.services.plan_revision import PlanRevisionService
from app.services.study_chat_errors import (
    StudyChatApplicationError,
    map_chat_generation_error,
)
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.diagnostics import reference_resource
from app.core.bootstrap import Container
from app.models.api import (
    LearningPlanCreateRequest,
    StudyChatExchangeResponse,
    StudyChatOperationReceiptResponse,
)
from app.models.harness import HarnessStage, canonical_harness_digest
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.stream import (
    DOCUMENT_STREAM_PROJECTION_CONTRACT,
    LEARNING_PLAN_STREAM_PROJECTION_CONTRACT,
    StreamSubjectRefV1,
    StreamTerminalEvidenceV1,
)
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.model_recovery import (
    consume_model_recovery_state,
)

logger = get_logger("vibe_learner.routes")


def _into_response(
    response_model: type[BaseModel], value: BaseModel | dict
) -> BaseModel:
    payload = value.model_dump() if isinstance(value, BaseModel) else value
    return response_model.model_validate(payload)


def _into_response_with_model_recoveries(
    response_model: type[BaseModel],
    value: BaseModel | dict,
) -> BaseModel:
    payload = value.model_dump() if isinstance(value, BaseModel) else dict(value)
    recoveries = consume_model_recovery_state()
    if recoveries:
        existing = list(payload.get("model_recoveries") or [])
        identities = {item["recovery_id"] for item in existing}
        payload["model_recoveries"] = existing + [
            item.model_dump(mode="json")
            for item in recoveries
            if item.recovery_id not in identities
        ]
    return response_model.model_validate(payload)


def _require_domain_harness_trace(
    *,
    domain_operation_kind: HarnessDomainOperationKind,
    domain_operation_id: str,
    stage: HarnessStage,
    container: Container,
):
    if not domain_operation_id:
        raise RuntimeError("harness_domain_operation_identity_missing")
    domain_repository = (
        container.document_service.process_repository
        if domain_operation_kind == HarnessDomainOperationKind.DOCUMENT_PROCESS
        else container.plan_service.operation_repository
    )
    binding = domain_repository.harness_operations.require_domain(
        domain_operation_kind=domain_operation_kind,
        domain_operation_id=domain_operation_id,
    )
    traces = HarnessRuntimeRepository(domain_repository.database).list_operation_traces(
        binding.harness_operation_id
    )
    terminal = [
        item.terminal_trace
        for item in traces
        if item.stage == stage
        and item.trace_slot == 0
        and item.terminal_trace is not None
    ]
    if len(terminal) != 1:
        raise RuntimeError("harness_domain_terminal_trace_missing")
    return terminal[0]


def _document_stream_subject(document_id: str) -> StreamSubjectRefV1:
    return StreamSubjectRefV1(subject_type="document", subject_id=document_id)


def _learning_plan_stream_subject(
    payload: LearningPlanCreateRequest,
) -> StreamSubjectRefV1:
    if payload.document_id:
        return StreamSubjectRefV1(
            subject_type="document",
            subject_id=payload.document_id,
        )
    return StreamSubjectRefV1(
        subject_type="learning_plan_request",
        subject_id=payload.client_request_id,
    )


def _learning_plan_stream_storage_id(payload: LearningPlanCreateRequest) -> str:
    """Return a filesystem-safe report key without changing domain identity."""

    if payload.document_id:
        return payload.document_id
    request_digest = canonical_harness_digest(
        {"client_request_id": payload.client_request_id}
    )
    return f"learning-plan-request-{request_digest[:24]}"


def _document_stream_committed_evidence(
    *,
    operation_id: str,
    document_payload: dict[str, object],
    container: Container,
) -> StreamTerminalEvidenceV1:
    operation = container.document_service.process_repository.require(
        operation_id=operation_id,
        validate_read_back=True,
    )
    projection_digest = canonical_harness_digest(document_payload)
    committed_document_payload = {
        key: value for key, value in document_payload.items() if key != "harness_trace"
    }
    if (
        operation.status.value != "committed"
        or operation.document_id != committed_document_payload.get("id")
        or operation.document_digest
        != canonical_harness_digest(committed_document_payload)
    ):
        raise RuntimeError("document_stream_commit_read_back_mismatch")
    return StreamTerminalEvidenceV1(
        commit_status="committed",
        domain_operation_id=operation.operation_id,
        domain_operation_status=operation.status.value,
        resource_type="document",
        resource_id=operation.document_id,
        commit_contract_version=operation.commit_contract_version,
        projection_contract_version=DOCUMENT_STREAM_PROJECTION_CONTRACT,
        projection_digest=projection_digest,
    )


def _learning_plan_stream_committed_evidence(
    *,
    operation_id: str,
    plan_payload: dict[str, object],
    container: Container,
) -> StreamTerminalEvidenceV1:
    operation = container.plan_service.operation_repository.require(
        operation_id=operation_id,
        validate_current=False,
    )
    projection = operation.committed_projection
    projection_digest = canonical_harness_digest(plan_payload)
    committed_plan_payload = {
        key: value for key, value in plan_payload.items() if key != "harness_trace"
    }
    if (
        operation.status.value != "committed"
        or projection is None
        or operation.plan_id != committed_plan_payload.get("id")
        or projection.plan_digest != canonical_harness_digest(committed_plan_payload)
    ):
        raise RuntimeError("learning_plan_stream_commit_read_back_mismatch")
    return StreamTerminalEvidenceV1(
        commit_status="committed",
        domain_operation_id=operation.operation_id,
        domain_operation_status=operation.status.value,
        resource_type="learning_plan",
        resource_id=operation.plan_id,
        commit_contract_version=operation.commit_contract_version,
        projection_contract_version=LEARNING_PLAN_STREAM_PROJECTION_CONTRACT,
        projection_digest=projection_digest,
    )


def _stream_failure_evidence(
    *,
    operation_id: str,
    domain: Literal["document_process", "learning_plan"],
    container: Container,
) -> StreamTerminalEvidenceV1:
    if not operation_id:
        return StreamTerminalEvidenceV1(
            commit_status="not_committed",
            domain_operation_status="not_admitted",
        )
    try:
        if domain == "document_process":
            operation = container.document_service.process_repository.require(
                operation_id=operation_id,
                validate_read_back=False,
            )
        else:
            operation = container.plan_service.operation_repository.require(
                operation_id=operation_id,
                validate_current=False,
            )
    except Exception:
        return StreamTerminalEvidenceV1(
            commit_status="uncertain",
            domain_operation_id=operation_id,
            domain_operation_status="read_back_failed",
        )
    status = operation.status.value
    commit_status = (
        "uncertain"
        if status in {"running", "uncertain", "committed"}
        else "not_committed"
    )
    return StreamTerminalEvidenceV1(
        commit_status=commit_status,
        domain_operation_id=operation.operation_id,
        domain_operation_status=status,
    )


def _map_openai_upstream_error(detail_prefix: str, exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if not detail.startswith("openai_") or "_request_failed:" not in detail:
        return HTTPException(status_code=502, detail=f"{detail_prefix}_upstream_error")

    tail = detail.split("_request_failed:", 1)[1]
    parts = tail.split(":", 2)
    status_code = parts[0] if parts and parts[0].isdigit() else "unknown"
    upstream_code = parts[1] if len(parts) > 1 and parts[1] else "unknown"
    return HTTPException(
        status_code=502,
        detail=f"{detail_prefix}_upstream_error:{status_code}:{upstream_code}",
    )


def _runtime_error_retry_attempts(exc: RuntimeError) -> int:
    attempts = getattr(exc, "attempts", 1)
    return attempts if isinstance(attempts, int) and attempts > 0 else 1


def _map_plan_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "mock_output_language_not_supported":
        return HTTPException(
            status_code=422,
            detail="本地演示模板不支持该语言，请选择列表中的语言或配置模型后重试。",
        )
    if detail == "openai_plan_request_unsupported_params":
        return HTTPException(status_code=422, detail="plan_model_unsupported_params")
    if detail == "openai_plan_request_rate_limit":
        return HTTPException(status_code=503, detail="plan_model_rate_limited")
    if detail == "openai_plan_request_timeout":
        return HTTPException(status_code=504, detail="plan_model_timeout")
    if detail == "openai_plan_request_network_error":
        return HTTPException(status_code=502, detail="plan_model_network_error")
    if detail.startswith("openai_plan_request_failed:"):
        return _map_openai_upstream_error("plan_model", exc)
    if detail == "plan_model_content_filter":
        return HTTPException(status_code=502, detail="plan_model_content_filter")
    if detail == "plan_model_invalid_json":
        return HTTPException(status_code=502, detail="plan_model_invalid_json")
    if detail == "plan_model_invalid_payload":
        return HTTPException(status_code=502, detail="plan_model_invalid_payload")
    if detail.startswith("plan_proposal_schema_invalid:"):
        return HTTPException(status_code=502, detail="plan_model_invalid_payload")
    if detail.startswith("plan_proposal_invariant_failed:"):
        return HTTPException(status_code=502, detail="plan_model_invalid_payload")
    if detail == "plan_proposal_repair_empty_response":
        return HTTPException(status_code=502, detail="plan_model_empty_response")
    if detail == "plan_model_empty_response":
        return HTTPException(status_code=502, detail="plan_model_empty_response")
    if detail == "plan_model_tool_loop_exhausted":
        return HTTPException(status_code=502, detail="plan_model_tool_loop_exhausted")
    return HTTPException(status_code=500, detail="plan_generation_failed")


def _map_chat_generation_error(exc: RuntimeError) -> HTTPException:
    error = map_chat_generation_error(exc)
    return HTTPException(status_code=error.status_code, detail=error.detail)


def _map_setting_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "openai_setting_request_unsupported_params":
        return HTTPException(status_code=422, detail="setting_model_unsupported_params")
    if detail == "openai_setting_request_rate_limit":
        return HTTPException(status_code=503, detail="setting_model_rate_limited")
    if detail == "openai_setting_request_timeout":
        return HTTPException(status_code=504, detail="setting_model_timeout")
    if detail == "openai_setting_request_network_error":
        return HTTPException(status_code=502, detail="setting_model_network_error")
    if detail.startswith("openai_setting_request_failed:"):
        return _map_openai_upstream_error("setting_model", exc)
    if detail == "setting_model_content_filter":
        return HTTPException(status_code=502, detail="setting_model_content_filter")
    if detail == "setting_model_empty_response":
        return HTTPException(status_code=502, detail="setting_model_empty_response")
    if detail == "setting_model_output_truncated":
        return HTTPException(status_code=502, detail="setting_model_output_truncated")
    if detail == "setting_model_invalid_json":
        return HTTPException(status_code=502, detail="setting_model_invalid_json")
    if detail == "setting_model_invalid_payload":
        return HTTPException(status_code=502, detail="setting_model_invalid_payload")
    if detail == "setting_persona_card_count_mismatch":
        return HTTPException(
            status_code=502, detail="setting_persona_card_count_mismatch"
        )
    if detail.startswith("setting_scene_proposal_invalid:"):
        return HTTPException(status_code=502, detail="setting_model_invalid_payload")
    return HTTPException(status_code=500, detail="setting_generation_failed")


def _map_persona_card_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "setting_keyword_generation_requires_openai":
        return HTTPException(
            status_code=400, detail="keyword_generation_requires_openai"
        )
    return _map_setting_generation_error(exc)


def _study_chat_operation_response(receipt) -> StudyChatOperationReceiptResponse:
    payload = receipt.model_dump(mode="json")
    if receipt.result is not None:
        payload["result"] = StudyChatExchangeResponse.model_validate(
            receipt.result
        ).model_dump(mode="json")
    response = StudyChatOperationReceiptResponse.model_validate(payload)
    if response.status == "committed" and response.result is not None:
        reference_resource(
            "study_session",
            response.result.session.id,
            revision=response.result.session.revision,
        )
    return response


def _resolve_study_unit_title(*, document, plan, study_unit_id: str) -> str:
    if document is not None:
        for section in document.sections:
            if section.id == study_unit_id:
                return section.title
        for unit in document.study_units:
            if unit.id == study_unit_id:
                return unit.title
    if plan is not None:
        for unit in plan.study_units:
            if unit.id == study_unit_id or study_unit_id in unit.source_section_ids:
                return unit.title
        for item in plan.schedule:
            if item.unit_id == study_unit_id and item.title.strip():
                return item.title
    return study_unit_id


def _resolve_study_unit_theme_hint(
    *, plan, study_unit_id: str, fallback: str = ""
) -> str:
    if plan is None:
        return fallback
    for progress in plan.study_unit_progress:
        if progress.unit_id == study_unit_id and progress.objective_fragment.strip():
            return progress.objective_fragment.strip()
    for item in plan.schedule:
        if item.unit_id == study_unit_id and item.focus.strip():
            return item.focus.strip()
        if item.unit_id == study_unit_id:
            for chapter in item.schedule_chapters:
                if chapter.title.strip():
                    return chapter.title.strip()
    for unit in plan.study_units:
        if unit.id != study_unit_id and study_unit_id not in unit.source_section_ids:
            continue
        if unit.summary.strip():
            return unit.summary.strip()
    if fallback:
        return fallback
    return plan.objective


def _resolve_session_document_title(*, document, plan) -> str:
    if document is not None:
        return document.title
    if plan is not None and plan.course_title.strip():
        return plan.course_title.strip()
    return "仅学习目标计划"


def _plan_revision_service(container):
    return PlanRevisionService(
        PlanRevisionRepository(container.database),
        container.harness_proposal_runtime,
        container.capture_model_provider(),
    )


def _stringify_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if (
        isinstance(detail, dict)
        and detail.get("contract_version") == "document-input-error-v1"
        and isinstance(detail.get("message"), str)
    ):
        return detail["message"]
    if detail is not None:
        return str(detail)
    return str(exc)


def _invoke_study_chat(
    container: Container, **request
) -> StudyChatOperationReceiptResponse:
    try:
        receipt = container.study_chat_application().admit(**request)
    except StudyChatApplicationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _study_chat_operation_response(receipt)
