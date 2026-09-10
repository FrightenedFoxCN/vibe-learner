from app.services.study_chat_context import _resolve_session_document
from app.services.study_chat_errors import StudyChatApplicationError, map_chat_generation_error
import json
from datetime import datetime, timezone
from pathlib import Path
import queue
import threading
from contextvars import copy_context
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.bootstrap import Container
from app.api.dependencies import get_container
from fastapi import Depends
from app.models.api import BatchCreatePersonaCardsRequest, CreatePersonaCardRequest, CreateReusableSceneNodeRequest, CreatePersonaRequest, CreateStudySessionRequest, DocumentDebugResponse, DocumentListResponse, DocumentPlanningContextResponse, DocumentPlanningTraceResponse, DocumentResponse, DocumentProcessResponse, DocumentStudyUnitUpdateResponse, StreamReportResponse, DocumentStatusResponse, ExerciseGenerateRequest, ExerciseGenerateResponse, LearningPlanCreateRequest, LearningPlanListResponse, LearningPlanOperationResponse, LearningPlanProgressUpdateRequest, LearningPlanResponse, LearningPlanCreateResponse, LearningPlanUpdateRequest, ModelToolConfigResponse, PlanningQuestionAnswerRequest, RuntimeSettingsResponse, RuntimeSessionSecretsRequest, RuntimeSettingsProbeRequest, RuntimeSettingsProbeResponse, ReusableSceneNodeListResponse, ReusableSceneNodeResponse, SceneLibraryListResponse, SceneLibraryResponse, SceneTreeGenerateRequest, SceneTreeGenerateResponse, SceneSetupResponse, StudyUnitTitleUpdateRequest, UpdateModelToolConfigRequest, UpdateSceneSetupRequest, UpsertSceneLibraryRequest, UpdateRuntimeSettingsRequest, PersonaAssetsResponse, PersonaCardGenerateRequest, PersonaCardGenerateResponse, PersonaCardListResponse, PersonaCardResponse, PersonaSlotAssistRequest, PersonaSlotAssistResponse, ProcessDocumentRequest, PersonaSettingAssistRequest, PersonaSettingAssistResponse, PersonaListResponse, PersonaResponse, StudyChatRequest, StudyChatExchangeResponse, StudyChatOperationReceiptResponse, StudySessionPlanConfirmationDecisionRequest, StudySessionPlanConfirmationDecisionResponse, StudyQuestionAttemptRequest, StudyQuestionAttemptResponse, StorageCleanupRequest, StorageCleanupResponse, StorageSummaryResponse, StudySessionListResponse, StudySessionResponse, UpdatePersonaRequest, UpdateStudySessionRequest, SubmissionGradeRequest, SubmissionGradeResponse, TokenUsageCallRecord, TokenUsageStatsResponse, TokenUsageDailyBucket
from app.models.domain import PersonaCardRecord, PersonaSlot, PlanGenerationTraceRecord
from app.models.harness import HarnessStage, canonical_harness_digest
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.stream import (
    DOCUMENT_STREAM_PROJECTION_CONTRACT,
    LEARNING_PLAN_STREAM_PROJECTION_CONTRACT,
    StreamSubjectRefV1,
    StreamTerminalEvidenceV1,
)
from app.persistence.study_chat_operation_repository import StudyChatOperationNotFound
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.model_recovery import consume_model_recovery_state, record_model_recovery, reset_model_recovery_state
from app.services.model_provider import OpenAIModelProvider
from app.services.study_chat_attachments import read_study_chat_attachment_inputs
from app.services.study_chat_attachments import render_pdf_page_png_bytes
from app.services.stream_interrupts import StreamInterruptedError
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)
from app.services.plan_prompt import build_learning_plan_context
from app.services.plan_tool_runtime import get_learning_plan_tool_specs
from app.services.runtime_model_probe import probe_openai_models
from app.services.study_session_prompt import build_study_session_system_prompt
from app.models.persona_generation import (
    PersonaGenerationInputManifest,
    PersonaGenerationProposalV1,
)
from app.models.scene_generation import (
    SceneGenerationInputManifest,
    SceneGenerationProposalV1,
)
from app.models.scene import SceneTreeProposalV1, project_scene_tree_proposal

router = APIRouter()
logger = get_logger("vibe_learner.routes")


def _into_response(response_model: type[BaseModel], value: BaseModel | dict) -> BaseModel:
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
        if item.stage == stage and item.trace_slot == 0 and item.terminal_trace is not None
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
    if detail == "setting_model_invalid_json":
        return HTTPException(status_code=502, detail="setting_model_invalid_json")
    if detail == "setting_model_invalid_payload":
        return HTTPException(status_code=502, detail="setting_model_invalid_payload")
    if detail == "setting_persona_card_count_mismatch":
        return HTTPException(status_code=502, detail="setting_persona_card_count_mismatch")
    if detail.startswith("setting_scene_proposal_invalid:"):
        return HTTPException(status_code=502, detail="setting_model_invalid_payload")
    return HTTPException(status_code=500, detail="setting_generation_failed")


def _map_persona_card_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "setting_keyword_generation_requires_openai":
        return HTTPException(status_code=400, detail="keyword_generation_requires_openai")
    return _map_setting_generation_error(exc)


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/storage/summary", response_model=StorageSummaryResponse)
def get_storage_summary(*, container: Container = Depends(get_container)) -> StorageSummaryResponse:
    return StorageSummaryResponse(
        buckets=container.storage_lifecycle_service.summarize(),
        orphaned_uploads=container.storage_lifecycle_service.list_orphaned_uploads(),
    )


@router.post("/storage/cleanup", response_model=StorageCleanupResponse)
def cleanup_storage(payload: StorageCleanupRequest, *, container: Container = Depends(get_container)) -> StorageCleanupResponse:
    try:
        items = container.storage_lifecycle_service.cleanup(
            buckets=payload.buckets,
            document_id=payload.document_id,
            session_id=payload.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageCleanupResponse(items=items)


@router.get("/model-tools/config", response_model=ModelToolConfigResponse)
def get_model_tool_config(*, container: Container = Depends(get_container)) -> ModelToolConfigResponse:
    described = container.model_tool_config_service.describe()
    provider = container.model_provider

    stage_enabled: dict[str, tuple[bool, str]] = {
        "plan_generation": (True, ""),
        "study_chat": (True, ""),
    }

    for stage in described["stages"]:
        current_stage_name = str(stage.get("name") or "")
        stage_flag, stage_reason = stage_enabled.get(current_stage_name, (False, "当前模型提供器不支持此阶段工具。"))
        stage["stage_enabled"] = stage_flag
        stage["stage_disabled_reason"] = stage_reason
        stage["audit_basis"] = [
            f"stage_registry={current_stage_name}",
            f"stage_runtime_gate={'on' if stage_flag else 'off'}",
        ]
        tools = stage.get("tools") or []
        for tool in tools:
            tool_name = str(tool.get("name") or "")
            available = True
            unavailable_reason = ""
            audit_basis = [
                f"manual_toggle={'on' if bool(tool.get('enabled')) else 'off'}",
                f"stage_gate={'on' if stage_flag else 'off'}",
            ]
            if not stage_flag:
                available = False
                unavailable_reason = stage_reason
            elif tool_name == "read_page_range_images":
                if current_stage_name == "plan_generation" and not provider.supports_page_image_tools():
                    available = False
                    unavailable_reason = "当前计划模型未启用多模态能力。"
                    audit_basis.append("plan_multimodal=off")
                else:
                    audit_basis.append("plan_multimodal=on")
                if current_stage_name == "study_chat" and not provider.supports_chat_page_image_tools():
                    available = False
                    unavailable_reason = "当前对话模型未启用多模态能力。"
                    audit_basis.append("chat_multimodal=off")
                elif current_stage_name == "study_chat":
                    audit_basis.append("chat_multimodal=on")
            elif tool_name == "retrieve_memory_context":
                audit_basis.append("chat_memory_gate=managed_by_model_tools")
            tool["available"] = available
            tool["unavailable_reason"] = unavailable_reason
            tool["effective_enabled"] = bool(tool.get("enabled")) and available
            tool["audit_basis"] = audit_basis

    return _into_response(ModelToolConfigResponse, described)


@router.patch("/model-tools/config", response_model=ModelToolConfigResponse)
def update_model_tool_config(payload: UpdateModelToolConfigRequest, *, container: Container = Depends(get_container)) -> ModelToolConfigResponse:
    try:
        container.model_tool_config_service.update(
            [toggle.model_dump(mode="json") for toggle in payload.toggles]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_model_tool_config(container=container)


@router.get("/runtime-settings", response_model=RuntimeSettingsResponse)
def get_runtime_settings(*, container: Container = Depends(get_container)) -> RuntimeSettingsResponse:
    described = container.runtime_settings_service.describe()
    return _into_response(RuntimeSettingsResponse, described)


@router.patch("/runtime-settings", response_model=RuntimeSettingsResponse)
def update_runtime_settings(payload: UpdateRuntimeSettingsRequest, *, container: Container = Depends(get_container)) -> RuntimeSettingsResponse:
    try:
        updates = payload.model_dump(mode="json", exclude_none=True)
        container.update_runtime_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_runtime_settings(container=container)


@router.put("/runtime-settings/session-secrets", response_model=RuntimeSettingsResponse)
def apply_runtime_session_secrets(payload: RuntimeSessionSecretsRequest, *, container: Container = Depends(get_container)) -> RuntimeSettingsResponse:
    container.apply_runtime_session_secrets(
        payload.model_dump(mode="json", exclude_none=True)
    )
    return get_runtime_settings(container=container)


@router.delete("/runtime-settings/session-secrets", response_model=RuntimeSettingsResponse)
def clear_runtime_session_secrets(*, container: Container = Depends(get_container)) -> RuntimeSettingsResponse:
    container.clear_runtime_session_secrets()
    return get_runtime_settings(container=container)


@router.get("/scene-setup", response_model=SceneSetupResponse)
def get_scene_setup(*, container: Container = Depends(get_container)) -> SceneSetupResponse:
    record = container.scene_setup_service.get_state()
    return _into_response(SceneSetupResponse, record)


@router.put("/scene-setup", response_model=SceneSetupResponse)
def update_scene_setup(payload: UpdateSceneSetupRequest, *, container: Container = Depends(get_container)) -> SceneSetupResponse:
    record = container.scene_setup_service.upsert_state(
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.to_domain_layers(),
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        expected_revision=payload.expected_revision,
    )
    return _into_response(SceneSetupResponse, record)


@router.get("/scene-library", response_model=SceneLibraryListResponse)
def list_scene_library(*, container: Container = Depends(get_container)) -> SceneLibraryListResponse:
    items = container.scene_library_service.list_scenes()
    return SceneLibraryListResponse(items=[_into_response(SceneLibraryResponse, item) for item in items])


@router.get("/scene-library/{scene_id}", response_model=SceneLibraryResponse)
def get_scene_library_item(scene_id: str, *, container: Container = Depends(get_container)) -> SceneLibraryResponse:
    record = container.scene_library_service.require_scene(scene_id)
    return _into_response(SceneLibraryResponse, record)


@router.post("/scene-library", response_model=SceneLibraryResponse)
def create_scene_library_item(payload: UpsertSceneLibraryRequest, *, container: Container = Depends(get_container)) -> SceneLibraryResponse:
    record = container.scene_library_service.upsert_scene(
        scene_id=None,
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.to_domain_layers(),
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        expected_revision=payload.expected_revision,
    )
    return _into_response(SceneLibraryResponse, record)


@router.put("/scene-library/{scene_id}", response_model=SceneLibraryResponse)
def update_scene_library_item(scene_id: str, payload: UpsertSceneLibraryRequest, *, container: Container = Depends(get_container)) -> SceneLibraryResponse:
    record = container.scene_library_service.upsert_scene(
        scene_id=scene_id,
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.to_domain_layers(),
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        expected_revision=payload.expected_revision,
    )
    return _into_response(SceneLibraryResponse, record)


@router.delete("/scene-library/{scene_id}")
def delete_scene_library_item(scene_id: str, *, container: Container = Depends(get_container)) -> dict[str, str]:
    container.scene_library_service.delete_scene(scene_id)
    return {"deleted_scene_id": scene_id}


@router.get("/reusable-scene-nodes", response_model=ReusableSceneNodeListResponse)
def list_reusable_scene_nodes(*, container: Container = Depends(get_container)) -> ReusableSceneNodeListResponse:
    items = container.reusable_scene_node_library_service.list_nodes()
    return ReusableSceneNodeListResponse(
        items=[_into_response(ReusableSceneNodeResponse, item) for item in items]
    )


@router.post("/reusable-scene-nodes", response_model=ReusableSceneNodeResponse)
def create_reusable_scene_node(payload: CreateReusableSceneNodeRequest, *, container: Container = Depends(get_container)) -> ReusableSceneNodeResponse:
    record = container.reusable_scene_node_library_service.create_node(payload)
    return _into_response(ReusableSceneNodeResponse, record)


@router.delete("/reusable-scene-nodes/{node_id}")
def delete_reusable_scene_node(node_id: str, *, container: Container = Depends(get_container)) -> dict[str, str]:
    container.reusable_scene_node_library_service.delete_node(node_id)
    return {"deleted_reusable_scene_node_id": node_id}


@router.post("/scene-setup/generate", response_model=SceneTreeGenerateResponse)
def generate_scene_tree(payload: SceneTreeGenerateRequest, *, container: Container = Depends(get_container)) -> SceneTreeGenerateResponse:
    reset_model_recovery_state()
    try:
        def generate_scene(protected: dict[str, object]) -> SceneGenerationProposalV1:
            mode = str(protected["mode"])
            input_text = str(protected["input_text"])
            layer_count = protected.get("layer_count")
            if mode == "keywords":
                result = container.model_provider.generate_scene_tree_from_keywords(
                    keywords=input_text,
                    layer_count=layer_count if isinstance(layer_count, int) else None,
                )
            else:
                result = container.model_provider.generate_scene_tree_from_text(
                    text=input_text,
                    layer_count=layer_count if isinstance(layer_count, int) else None,
                )
            return SceneGenerationProposalV1(
                used_model=str(result.get("used_model") or ""),
                used_web_search=bool(result.get("used_web_search")),
                proposal=SceneTreeProposalV1.model_validate(result.get("proposal")),
            )

        generated, harness_trace = container.harness_proposal_runtime.run_scene(
            manifest=SceneGenerationInputManifest(
                mode=payload.mode,
                requested_layer_count=payload.layer_count or 0,
                input_char_count=len(payload.input_text),
            ),
            protected_input=payload.model_dump(mode="json", exclude_none=False),
            generate=generate_scene,
        )
        projection = project_scene_tree_proposal(generated.proposal)
    except RuntimeError as exc:
        raise _map_setting_generation_error(exc) from exc

    return _into_response_with_model_recoveries(SceneTreeGenerateResponse, SceneTreeGenerateResponse(
        mode=payload.mode,
        used_model=generated.used_model,
        used_web_search=generated.used_web_search,
        scene_name=projection.scene_name,
        scene_summary=projection.scene_summary,
        selected_layer_id=projection.selected_layer_id,
        scene_layers=projection.scene_layers,
        harness_trace=harness_trace,
    ))


@router.post("/runtime-settings/check-openai-models", response_model=RuntimeSettingsProbeResponse)
def check_openai_models(payload: RuntimeSettingsProbeRequest, *, container: Container = Depends(get_container)) -> RuntimeSettingsProbeResponse:
    api_key = payload.api_key.strip()
    base_url = payload.base_url.strip().rstrip("/")
    if not api_key:
        raise HTTPException(status_code=400, detail="missing_api_key")
    if not base_url:
        raise HTTPException(status_code=400, detail="missing_base_url")

    timeout_seconds = max(5, container.runtime_settings_service.effective_settings().openai_timeout_seconds)
    result = probe_openai_models(
        api_key=api_key,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
    )
    if payload.features:
        probe_provider = OpenAIModelProvider(
            api_key=api_key,
            base_url=base_url,
            plan_model=payload.model,
            setting_model=payload.model,
            chat_model=payload.model,
            setting_web_search_enabled=False,
            timeout_seconds=timeout_seconds,
        )
        result["feature_readiness"] = probe_provider.probe_feature_readiness(
            payload.features
        )
    return RuntimeSettingsProbeResponse.model_validate(result)


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(*, container: Container = Depends(get_container)) -> DocumentListResponse:
    return DocumentListResponse(
        items=[
            _into_response(DocumentResponse, document)
            for document in container.document_service.list_documents()
        ]
    )


@router.post("/documents", response_model=DocumentResponse)
def create_document(file: UploadFile = File(...), *, container: Container = Depends(get_container)) -> DocumentResponse:
    logger.info(
        "documents.create filename=%s content_type=%s",
        file.filename,
        file.content_type,
    )
    document = container.document_service.create_document(file)
    return _into_response(DocumentResponse, document)


@router.post("/documents/{document_id}/process", response_model=DocumentProcessResponse)
def process_document(
    document_id: str, payload: ProcessDocumentRequest | None = None
, *, container: Container = Depends(get_container)) -> DocumentProcessResponse:
    domain_operation_id = ""

    def remember_operation(operation_id: str) -> None:
        nonlocal domain_operation_id
        domain_operation_id = operation_id

    recorder = StreamReportRecorder(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
        subject=_document_stream_subject(document_id),
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
            operation_admitted_callback=remember_operation,
        )
    except Exception as exc:
        recorder.emit(
            "stream_error",
            {
                "document_id": document_id,
                "error": _stringify_error(exc),
            },
            terminal_evidence=_stream_failure_evidence(
                operation_id=domain_operation_id,
                domain="document_process",
                container=container,
            ),
        )
        raise
    harness_trace = _require_domain_harness_trace(
        domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
        domain_operation_id=domain_operation_id,
        stage=HarnessStage.DOCUMENT_PARSE,
        container=container,
    )
    document_commit_projection = document.model_dump(mode="json")
    document_projection = {
        **document_commit_projection,
        "harness_trace": harness_trace.model_dump(mode="json", exclude_none=False),
    }
    recorder.emit(
        "stream_completed",
        {
            "document_id": document.id,
            "status": document.status,
        },
        terminal_evidence=_document_stream_committed_evidence(
            operation_id=domain_operation_id,
            document_payload=document_projection,
            container=container,
        ),
        committed_projection=document_projection,
    )
    return DocumentProcessResponse.model_validate(document_projection)


@router.patch(
    "/documents/{document_id}/study-units/{study_unit_id}",
    response_model=DocumentStudyUnitUpdateResponse,
)
def update_study_unit_title(
    document_id: str,
    study_unit_id: str,
    payload: StudyUnitTitleUpdateRequest,
    *,
    container: Container = Depends(get_container),
) -> DocumentStudyUnitUpdateResponse:
    document = container.document_service.update_study_unit_title(
        document_id=document_id,
        study_unit_id=study_unit_id,
        title=payload.title,
    )
    plans = container.plan_service.update_study_unit_title(
        document_id=document_id,
        study_unit_id=study_unit_id,
        title=payload.title,
    )
    return DocumentStudyUnitUpdateResponse(
        document=_into_response(DocumentResponse, document),
        plans=[_into_response(LearningPlanResponse, plan) for plan in plans],
    )


@router.post("/documents/{document_id}/process/stream")
def process_document_stream(
    document_id: str, payload: ProcessDocumentRequest | None = None
, *, container: Container = Depends(get_container)) -> StreamingResponse:
    force_ocr = payload.force_ocr if payload else False
    event_queue: queue.Queue[dict[str, object] | None] = queue.Queue()
    interrupt_handle = container.stream_interrupt_registry.create(
        stream_kind="document_process",
        target_id=document_id,
    )
    recorder = StreamReportRecorder(
        store=container.store,
        category=DOCUMENT_PROCESS_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="document_process",
        subject=_document_stream_subject(document_id),
        operation_id=interrupt_handle.stream_id,
    )
    domain_operation_id = ""

    def remember_operation(operation_id: str) -> None:
        nonlocal domain_operation_id
        domain_operation_id = operation_id

    def report(stage: str, event_payload: dict[str, object]) -> None:
        interrupt_handle.raise_if_cancelled()
        event = recorder.emit(stage, event_payload)
        event_queue.put(event.model_dump(mode="json"))

    def emit_cancelled() -> None:
        event = recorder.emit(
            "stream_cancelled",
            {
                "document_id": document_id,
                "detail": "stream_interrupted",
            },
            terminal_evidence=_stream_failure_evidence(
                operation_id=domain_operation_id,
                domain="document_process",
                container=container,
            ),
        )
        event_queue.put(event.model_dump(mode="json"))

    def run() -> None:
        try:
            document = container.document_service.process_document(
                document_id,
                force_ocr=force_ocr,
                progress_callback=report,
                interrupt_check=interrupt_handle.raise_if_cancelled,
                operation_admitted_callback=remember_operation,
            )
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                harness_trace = _require_domain_harness_trace(
                    domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                    domain_operation_id=domain_operation_id,
                    stage=HarnessStage.DOCUMENT_PARSE,
                    container=container,
                )
                document_commit_projection = document.model_dump(mode="json")
                document_projection = {
                    **document_commit_projection,
                    "harness_trace": harness_trace.model_dump(mode="json", exclude_none=False),
                }
                event = recorder.emit(
                    "stream_completed",
                    {
                        "document_id": document.id,
                        "status": document.status,
                    },
                    terminal_evidence=_document_stream_committed_evidence(
                        operation_id=domain_operation_id,
                        document_payload=document_projection,
                        container=container,
                    ),
                    committed_projection=document_projection,
                )
                event_queue.put(event.model_dump(mode="json"))
        except StreamInterruptedError:
            interrupt_handle.claim_terminal()
            emit_cancelled()
        except Exception as exc:
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                event = recorder.emit(
                    "stream_error",
                    {
                        "document_id": document_id,
                        "error": _stringify_error(exc),
                    },
                    terminal_evidence=_stream_failure_evidence(
                        operation_id=domain_operation_id,
                        domain="document_process",
                        container=container,
                    ),
                )
                event_queue.put(event.model_dump(mode="json"))
        finally:
            interrupt_handle.mark_completed()
            event_queue.put(None)

    threading.Thread(target=copy_context().run, args=(run,), daemon=True).start()

    def generate():
        while True:
            item = event_queue.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
def get_document_status(document_id: str, *, container: Container = Depends(get_container)) -> DocumentStatusResponse:
    document = container.document_service.require_document(document_id)
    return _into_response(DocumentStatusResponse, document)


@router.get("/documents/{document_id}/file")
def get_document_file(document_id: str, *, container: Container = Depends(get_container)) -> FileResponse:
    document = container.document_service.require_document(document_id)
    path = Path(document.stored_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="document_file_not_found")
    return FileResponse(
        path=path,
        media_type="application/pdf",
        headers={"Content-Disposition": "inline"},
    )


@router.get("/documents/{document_id}/pages/{page_number}/image")
def get_document_page_image(document_id: str, page_number: int, *, container: Container = Depends(get_container)) -> Response:
    document = container.document_service.require_document(document_id)
    path = Path(document.stored_path)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="document_file_not_found")
    image_bytes = render_pdf_page_png_bytes(
        pdf_path=str(path),
        page_number=page_number,
    )
    return Response(content=image_bytes, media_type="image/png")


@router.get("/documents/{document_id}/debug", response_model=DocumentDebugResponse)
def get_document_debug(document_id: str, *, container: Container = Depends(get_container)) -> DocumentDebugResponse:
    report = container.document_service.require_debug_report(document_id)
    return _into_response(DocumentDebugResponse, report)


@router.get("/documents/{document_id}/process-events", response_model=StreamReportResponse)
def get_document_process_events(document_id: str, *, container: Container = Depends(get_container)) -> StreamReportResponse:
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
def get_document_planning_context(document_id: str, *, container: Container = Depends(get_container)) -> DocumentPlanningContextResponse:
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
def get_document_planning_trace(document_id: str, *, container: Container = Depends(get_container)) -> DocumentPlanningTraceResponse:
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
def get_document_plan_events(document_id: str, *, container: Container = Depends(get_container)) -> StreamReportResponse:
    report = StreamReportRecorder.load(
        store=container.store,
        category=LEARNING_PLAN_STREAM_CATEGORY,
        document_id=document_id,
        stream_kind="learning_plan",
    )
    return _into_response(StreamReportResponse, report)


@router.get("/personas", response_model=PersonaListResponse)
def list_personas(*, container: Container = Depends(get_container)) -> PersonaListResponse:
    personas = container.persona_engine.list_personas()
    return PersonaListResponse(
        items=[_into_response(PersonaResponse, persona) for persona in personas]
    )


@router.post("/personas", response_model=PersonaResponse)
def create_persona(payload: CreatePersonaRequest, *, container: Container = Depends(get_container)) -> PersonaResponse:
    persona = container.persona_engine.create_persona(payload)
    return _into_response(PersonaResponse, persona)


@router.patch("/personas/{persona_id}", response_model=PersonaResponse)
def update_persona(persona_id: str, payload: UpdatePersonaRequest, *, container: Container = Depends(get_container)) -> PersonaResponse:
    persona = container.persona_engine.update_persona(persona_id, payload)
    return _into_response(PersonaResponse, persona)


@router.delete("/personas/{persona_id}")
def delete_persona(
    persona_id: str,
    expected_revision: int = Query(ge=0),
    *,
    container: Container = Depends(get_container),
) -> dict[str, str]:
    container.persona_engine.delete_persona(
        persona_id,
        expected_revision=expected_revision,
    )
    return {"deleted_persona_id": persona_id}


@router.get("/personas/{persona_id}/assets", response_model=PersonaAssetsResponse)
def get_persona_assets(persona_id: str, *, container: Container = Depends(get_container)) -> PersonaAssetsResponse:
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


@router.get("/persona-cards", response_model=PersonaCardListResponse)
def list_persona_cards(*, container: Container = Depends(get_container)) -> PersonaCardListResponse:
    items = container.persona_card_library_service.list_cards()
    return PersonaCardListResponse(
        items=[_into_response(PersonaCardResponse, item) for item in items]
    )


@router.post("/persona-cards", response_model=PersonaCardResponse)
def create_persona_card(payload: CreatePersonaCardRequest, *, container: Container = Depends(get_container)) -> PersonaCardResponse:
    record = container.persona_card_library_service.create_card(payload)
    return _into_response(PersonaCardResponse, record)


@router.post("/persona-cards/batch", response_model=PersonaCardListResponse)
def create_persona_cards_batch(payload: BatchCreatePersonaCardsRequest, *, container: Container = Depends(get_container)) -> PersonaCardListResponse:
    items = container.persona_card_library_service.create_many(payload.items)
    return PersonaCardListResponse(
        items=[_into_response(PersonaCardResponse, item) for item in items]
    )


@router.delete("/persona-cards/{card_id}")
def delete_persona_card(card_id: str, *, container: Container = Depends(get_container)) -> dict[str, str]:
    container.persona_card_library_service.delete_card(card_id)
    return {"deleted_persona_card_id": card_id}


@router.post("/persona-cards/generate", response_model=PersonaCardGenerateResponse)
def generate_persona_cards(payload: PersonaCardGenerateRequest, *, container: Container = Depends(get_container)) -> PersonaCardGenerateResponse:
    reset_model_recovery_state()
    try:
        def generate_cards(protected: dict[str, object]) -> PersonaGenerationProposalV1:
            mode = str(protected["mode"])
            input_text = str(protected["input_text"])
            count = protected.get("count")
            if mode == "keywords":
                result = container.model_provider.generate_persona_cards_from_keywords(
                    keywords=input_text,
                    count=count if isinstance(count, int) else None,
                )
            elif mode == "long_text":
                result = container.model_provider.generate_persona_cards_from_text(
                    text=input_text,
                    count=count if isinstance(count, int) else None,
                )
            else:
                raise RuntimeError("invalid_persona_card_generation_mode")
            raw_cards = result.get("cards")
            if not isinstance(raw_cards, list):
                raise RuntimeError("setting_model_invalid_payload")
            try:
                return PersonaGenerationProposalV1.model_validate(
                    {
                        "request_kind": "card_batch",
                        "used_model": result.get("used_model", ""),
                        "used_web_search": result.get("used_web_search", False),
                        "summary": result.get("summary", ""),
                        "relationship": result.get("relationship", ""),
                        "learner_address": result.get("learner_address", ""),
                        "cards": raw_cards,
                    },
                    strict=True,
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError("setting_model_invalid_payload") from exc

        generated, harness_trace = container.harness_proposal_runtime.run_persona(
            manifest=PersonaGenerationInputManifest(
                request_kind="card_batch",
                mode=payload.mode,
                requested_count=payload.count or 0,
                input_char_count=len(payload.input_text),
            ),
            protected_input=payload.model_dump(mode="json", exclude_none=False),
            generate=generate_cards,
        )
        source = "generated_keywords" if payload.mode == "keywords" else "generated_text"
    except RuntimeError as exc:
        raise _map_persona_card_generation_error(exc) from exc

    cards = [
        PersonaCardRecord(
            id=f"generated-{uuid4().hex[:10]}",
            title=item.title,
            kind=item.kind,
            label=item.label,
            content=item.content,
            tags=list(item.tags),
            search_keywords=payload.input_text.strip() if payload.mode == "keywords" else "自定义",
            source=source,
            source_note=item.source_note,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        for item in generated.cards
    ]
    return _into_response_with_model_recoveries(PersonaCardGenerateResponse, PersonaCardGenerateResponse(
        mode=payload.mode,
        used_model=generated.used_model,
        used_web_search=generated.used_web_search,
        summary=generated.summary,
        relationship=generated.relationship,
        learner_address=generated.learner_address,
        items=[_into_response(PersonaCardResponse, item) for item in cards],
        harness_trace=harness_trace,
    ))


@router.post("/personas/assist-setting", response_model=PersonaSettingAssistResponse)
def assist_persona_setting(payload: PersonaSettingAssistRequest, *, container: Container = Depends(get_container)) -> PersonaSettingAssistResponse:
    reset_model_recovery_state()
    try:
        def generate_setting(protected: dict[str, object]) -> PersonaGenerationProposalV1:
            recovery_strategy = "none"
            protected_slots = [
                PersonaSlot.model_validate(item) for item in protected["slots"]
            ]
            try:
                result = container.model_provider.assist_persona_setting(
                    name=str(protected["name"]),
                    summary=str(protected["summary"]),
                    slots=protected_slots,
                    rewrite_strength=float(protected["rewrite_strength"]),
                )
                used_model = str(getattr(container.model_provider, "setting_model", "mock"))
            except RuntimeError as exc:
                logger.warning("persona.assist_setting.model_failed internal_error_code=%s fallback=local", str(exc))
                reset_model_recovery_state()
                record_model_recovery(
                    category="persona_setting_assist",
                    reason="setting_model_unavailable_or_invalid",
                    strategy="local_fallback",
                    note="模型润色未完成，已使用本地规则；请检查结果后再保存。",
                )
                result = container.persona_engine.assist_setting(
                    name=str(protected["name"]),
                    summary=str(protected["summary"]),
                    slots=protected_slots,
                )
                # A failed model call must not merge away biography slots or
                # replace locked/user-authored content with canned prose.
                result["slots"] = [item.model_dump(mode="json") for item in protected_slots]
                recovery_strategy = "local_fallback"
                used_model = "local"
            raw_slots = result.get("slots")
            system_prompt = result.get("system_prompt_suggestion")
            if not isinstance(raw_slots, list) or not isinstance(system_prompt, str):
                raise RuntimeError("setting_model_invalid_payload")
            try:
                return PersonaGenerationProposalV1.model_validate(
                    {
                        "request_kind": "setting_assist",
                        "used_model": used_model,
                        "slots": [
                            item.model_dump(mode="python")
                            if isinstance(item, BaseModel)
                            else item
                            for item in raw_slots
                        ],
                        "system_prompt_suggestion": system_prompt,
                        "recovery_strategy": recovery_strategy,
                    },
                    strict=True,
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError("setting_model_invalid_payload") from exc

        generated, harness_trace = container.harness_proposal_runtime.run_persona(
            manifest=PersonaGenerationInputManifest(
                request_kind="setting_assist",
                mode="assist",
                requested_count=len(payload.slots),
                input_char_count=len(payload.name) + len(payload.summary) + sum(len(item.content) for item in payload.slots),
            ),
            protected_input=payload.model_dump(mode="json", exclude_none=False),
            generate=generate_setting,
        )
    except RuntimeError as exc:
        raise _map_setting_generation_error(exc) from exc
    return _into_response_with_model_recoveries(
        PersonaSettingAssistResponse,
        PersonaSettingAssistResponse(
            slots=[item.model_dump(mode="json") for item in generated.slots],
            system_prompt_suggestion=generated.system_prompt_suggestion,
            harness_trace=harness_trace,
        ),
    )


@router.post("/personas/assist-slot", response_model=PersonaSlotAssistResponse)
def assist_persona_slot(payload: PersonaSlotAssistRequest, *, container: Container = Depends(get_container)) -> PersonaSlotAssistResponse:
    reset_model_recovery_state()
    try:
        def generate_slot(protected: dict[str, object]) -> PersonaGenerationProposalV1:
            recovery_strategy = "none"
            protected_slot = PersonaSlot.model_validate(protected["slot"])
            try:
                result = container.model_provider.assist_persona_slot(
                    name=str(protected["name"]),
                    summary=str(protected["summary"]),
                    slot=protected_slot,
                    rewrite_strength=float(protected["rewrite_strength"]),
                )
                used_model = str(getattr(container.model_provider, "setting_model", "mock"))
            except RuntimeError as exc:
                logger.warning("persona.assist_slot.model_failed internal_error_code=%s fallback=local", str(exc))
                reset_model_recovery_state()
                record_model_recovery(
                    category="persona_slot_assist",
                    reason="setting_model_unavailable_or_invalid",
                    strategy="local_fallback",
                    note="模型润色未完成，已使用本地规则；请检查结果后再保存。",
                )
                result = {"slot": container.persona_engine.assist_slot(
                    name=str(protected["name"]),
                    summary=str(protected["summary"]),
                    slot=protected_slot,
                    rewrite_strength=float(protected["rewrite_strength"]),
                ).model_dump(mode="json")}
                recovery_strategy = "local_fallback"
                used_model = "local"
            raw_slot = result.get("slot")
            if isinstance(raw_slot, BaseModel):
                raw_slot = raw_slot.model_dump(mode="python")
            if not isinstance(raw_slot, dict):
                raise RuntimeError("setting_model_invalid_payload")
            try:
                return PersonaGenerationProposalV1.model_validate(
                    {
                        "request_kind": "slot_assist",
                        "used_model": used_model,
                        "slot": raw_slot,
                        "recovery_strategy": recovery_strategy,
                    },
                    strict=True,
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError("setting_model_invalid_payload") from exc

        generated, harness_trace = container.harness_proposal_runtime.run_persona(
            manifest=PersonaGenerationInputManifest(
                request_kind="slot_assist",
                mode="assist",
                requested_count=1,
                input_char_count=len(payload.name) + len(payload.summary) + len(payload.slot.content),
            ),
            protected_input=payload.model_dump(mode="json", exclude_none=False),
            generate=generate_slot,
        )
    except RuntimeError as exc:
        raise _map_setting_generation_error(exc) from exc
    assert generated.slot is not None
    return _into_response_with_model_recoveries(
        PersonaSlotAssistResponse,
        PersonaSlotAssistResponse(
            slot=generated.slot.model_dump(mode="json"),
            harness_trace=harness_trace,
        ),
    )


@router.get("/study-sessions/{session_id}/attachments/{attachment_id}/file")
def get_study_session_attachment_file(session_id: str, attachment_id: str, *, container: Container = Depends(get_container)) -> FileResponse:
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


@router.get("/study-sessions/{session_id}/attachments/{attachment_id}/pages/{page_number}/image")
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
    if attachment.kind != "pdf" or not attachment.stored_path or not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="session_attachment_file_not_found")
    image_bytes = render_pdf_page_png_bytes(
        pdf_path=str(path),
        page_number=page_number,
    )
    return Response(content=image_bytes, media_type="image/png")


@router.post("/study-sessions/{session_id}/chat", response_model=StudyChatOperationReceiptResponse)
def study_chat(session_id: str, payload: StudyChatRequest, *, container: Container = Depends(get_container)) -> StudyChatOperationReceiptResponse:
    return _invoke_study_chat(
        container,
        session_id=session_id,
        client_request_id=payload.client_request_id,
        expected_session_revision=payload.expected_session_revision,
        message=payload.message,
        message_kind=payload.message_kind,
        follow_up_id=payload.follow_up_id,
        hidden_message_prefix=payload.hidden_message_prefix,
    )


@router.post("/study-sessions/{session_id}/chat-with-attachments", response_model=StudyChatOperationReceiptResponse)
def study_chat_with_attachments(
    session_id: str,
    client_request_id: str = Form(...),
    expected_session_revision: int = Form(...),
    message: str = Form(...),
    message_kind: str = Form("learner"),
    follow_up_id: str = Form(""),
    hidden_message_prefix: str = Form(""),
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
            session_id=session_id, client_request_id=client_request_id,
        )
    except StudyChatOperationNotFound as exc:
        raise HTTPException(status_code=404, detail="study_chat_operation_not_found") from exc
    return _study_chat_operation_response(receipt)


def _study_chat_operation_response(receipt) -> StudyChatOperationReceiptResponse:
    payload = receipt.model_dump(mode="json")
    if receipt.result is not None:
        payload["result"] = StudyChatExchangeResponse.model_validate(
            receipt.result
        ).model_dump(mode="json")
    return StudyChatOperationReceiptResponse.model_validate(payload)


@router.post("/study-sessions/{session_id}/follow-ups/cancel", response_model=StudySessionResponse)
def cancel_study_session_follow_ups(session_id: str, *, container: Container = Depends(get_container)) -> StudySessionResponse:
    session = container.study_session_service.cancel_pending_follow_ups(session_id=session_id)
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
    session, confirmation = container.study_session_service.resolve_plan_confirmation(
        session_id=session_id,
        confirmation_id=confirmation_id,
        decision=decision,
        note=payload.note,
    )
    updated_plan = None
    if decision == "approve":
        action_type = confirmation.action_type.strip()
        if action_type == "update_plan_progress":
            updated_plan = container.plan_service.update_progress(
                plan_id=confirmation.plan_id,
                schedule_ids=[
                    str(item).strip()
                    for item in (confirmation.payload.get("schedule_ids") or [])
                    if str(item).strip()
                ],
                status=str(confirmation.payload.get("status") or ""),
                note=str(confirmation.payload.get("note") or payload.note or ""),
                actor="user",
                source="chat_confirmation",
            )
        elif action_type == "update_plan":
            updated_plan = container.plan_service.update_plan(
                plan_id=confirmation.plan_id,
                course_title=(
                    str(confirmation.payload.get("course_title") or "").strip()
                    or None
                ),
            )
        else:
            raise HTTPException(status_code=400, detail="unsupported_confirmation_action")
    refreshed_session = container.study_session_service.require_session(session_id)
    return StudySessionPlanConfirmationDecisionResponse(
        session=_into_response(StudySessionResponse, refreshed_session),
        plan=_into_response(LearningPlanResponse, updated_plan) if updated_plan is not None else None,
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
def get_study_session(session_id: str, *, container: Container = Depends(get_container)) -> StudySessionResponse:
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
    return StudyQuestionAttemptResponse.model_validate(result.model_dump(mode="json"))


@router.patch("/study-sessions/{session_id}", response_model=StudySessionResponse)
def update_study_session(
    session_id: str, payload: UpdateStudySessionRequest
, *, container: Container = Depends(get_container)) -> StudySessionResponse:
    if payload.study_unit_id is None and "scene_profile" not in payload.model_fields_set:
        raise HTTPException(status_code=400, detail="update_payload_empty")

    current_session = _ensure_session_scene_binding(
        container.study_session_service.require_session(session_id)
    , container=container)
    next_study_unit_id = payload.study_unit_id or current_session.study_unit_id
    has_scene_profile = "scene_profile" in payload.model_fields_set
    next_scene_instance_id = current_session.scene_instance_id
    next_scene_profile = current_session.scene_profile
    if has_scene_profile:
        bound_scene = container.session_scene_service.clone_scene_for_session(
            session_id=session_id,
            document_id=current_session.document_id,
            persona_id=current_session.persona_id,
            scene_profile=payload.scene_profile,
        )
        next_scene_instance_id = bound_scene.scene_instance_id if bound_scene else ""
        next_scene_profile = bound_scene.scene_profile if bound_scene else None

    persona = container.persona_engine.require_persona(current_session.persona_id)
    active_plan = None
    if current_session.plan_id:
        try:
            active_plan = container.plan_service.require_plan(current_session.plan_id)
        except HTTPException:
            active_plan = None
    document = _resolve_session_document(current_session.document_id, active_plan, document_service=container.document_service)
    next_study_unit_title = _resolve_study_unit_title(
        document=document,
        plan=active_plan,
        study_unit_id=next_study_unit_id,
    )
    next_theme_hint = _resolve_study_unit_theme_hint(
        plan=active_plan,
        study_unit_id=next_study_unit_id,
        fallback=current_session.theme_hint,
    )
    session_system_prompt = build_study_session_system_prompt(
        persona_name=persona.name,
        persona_relationship=persona.relationship,
        persona_learner_address=persona.learner_address,
        document_title=_resolve_session_document_title(document=document, plan=active_plan),
        study_unit_id=next_study_unit_id,
        study_unit_title=next_study_unit_title,
        theme_hint=next_theme_hint,
        scene_profile=next_scene_profile,
    )

    session = container.study_session_service.update_session(
        session_id=session_id,
        study_unit_id=payload.study_unit_id,
        scene_instance_id=next_scene_instance_id if has_scene_profile else None,
        scene_profile=next_scene_profile,
        has_scene_profile=has_scene_profile,
        study_unit_title=next_study_unit_title,
        theme_hint=next_theme_hint,
        session_system_prompt=session_system_prompt,
    )
    return _into_response(StudySessionResponse, session)


@router.post("/study-sessions", response_model=StudySessionResponse)
def create_study_session(payload: CreateStudySessionRequest, *, container: Container = Depends(get_container)) -> StudySessionResponse:
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
        if plan.document_id and payload.document_id and plan.document_id != payload.document_id:
            raise HTTPException(status_code=400, detail="plan_session_binding_mismatch")
        if not resolved_document_id and plan.document_id:
            resolved_document_id = plan.document_id
    document = _resolve_session_document(resolved_document_id, plan, document_service=container.document_service)
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
    bound_scene = container.session_scene_service.clone_scene_for_session(
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
        scene_instance_id=bound_scene.scene_instance_id if bound_scene else "",
        scene_profile=session_scene_profile,
        study_unit_id=payload.study_unit_id,
        study_unit_title=study_unit_title,
        theme_hint=theme_hint,
        session_system_prompt=session_system_prompt,
    )
    return _into_response(StudySessionResponse, session)


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


def _resolve_study_unit_theme_hint(*, plan, study_unit_id: str, fallback: str = "") -> str:
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


def _ensure_session_scene_binding(session, *, container: Container):
    if session.scene_instance_id or session.scene_profile is None:
        return session
    bound_scene = container.session_scene_service.clone_scene_for_session(
        session_id=session.id,
        document_id=session.document_id,
        persona_id=session.persona_id,
        scene_profile=session.scene_profile,
    )
    if bound_scene is None:
        return session
    return container.study_session_service.update_session(
        session_id=session.id,
        scene_instance_id=bound_scene.scene_instance_id,
        scene_profile=bound_scene.scene_profile,
        has_scene_profile=True,
    )


@router.post("/learning-plans", response_model=LearningPlanCreateResponse)
def create_learning_plan(payload: LearningPlanCreateRequest, *, container: Container = Depends(get_container)) -> LearningPlanCreateResponse:
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
    document = None
    debug_report = None
    if payload.document_id:
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
            "creation_mode": "document" if payload.document_id else "goal_only",
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
def list_learning_plans(*, container: Container = Depends(get_container)) -> LearningPlanListResponse:
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
    document = None
    debug_report = None
    if payload.document_id:
        document = container.document_service.require_document(payload.document_id)
        debug_report = (
            container.document_service.require_debug_report(payload.document_id)
            if document.debug_ready
            else None
        )
    event_queue: queue.Queue[dict[str, object] | None] = queue.Queue()
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
    domain_operation_id = ""

    def remember_operation(operation_id: str) -> None:
        nonlocal domain_operation_id
        domain_operation_id = operation_id

    def report(stage: str, event_payload: dict[str, object]) -> None:
        interrupt_handle.raise_if_cancelled()
        event = recorder.emit(stage, event_payload)
        event_queue.put(event.model_dump(mode="json"))

    def emit_cancelled() -> None:
        event = recorder.emit(
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
        event_queue.put(event.model_dump(mode="json"))

    def run() -> None:
        reset_model_recovery_state()
        try:
            report(
                "learning_plan_started",
                {
                    "document_id": payload.document_id,
                    "persona_id": payload.persona_id,
                    "creation_mode": "document" if payload.document_id else "goal_only",
                },
            )
            plan = container.plan_service.create_plan(
                goal=payload,
                document=document,
                persona_name=persona.name,
                persona=persona,
                debug_report=debug_report,
                progress_callback=report,
                interrupt_check=interrupt_handle.raise_if_cancelled,
                operation_admitted_callback=remember_operation,
            )
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                harness_trace = _require_domain_harness_trace(
                    domain_operation_kind=HarnessDomainOperationKind.LEARNING_PLAN_GENERATION,
                    domain_operation_id=domain_operation_id,
                    stage=HarnessStage.PLAN_GENERATION,
                    container=container,
                )
                plan_commit_projection = plan.model_dump(mode="json")
                plan_projection = {
                    **plan_commit_projection,
                    "harness_trace": harness_trace.model_dump(mode="json", exclude_none=False),
                }
                event = recorder.emit(
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
                event_queue.put(event.model_dump(mode="json"))
        except StreamInterruptedError:
            interrupt_handle.claim_terminal()
            emit_cancelled()
        except RuntimeError as exc:
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                http_error = _map_plan_generation_error(exc)
                event = recorder.emit(
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
                event_queue.put(event.model_dump(mode="json"))
        except Exception as exc:
            if interrupt_handle.claim_terminal():
                emit_cancelled()
            else:
                event = recorder.emit(
                    "stream_error",
                    {
                        "document_id": payload.document_id,
                        "detail": str(exc),
                    },
                    terminal_evidence=_stream_failure_evidence(
                        operation_id=domain_operation_id,
                        domain="learning_plan",
                        container=container,
                    ),
                )
                event_queue.put(event.model_dump(mode="json"))
        finally:
            interrupt_handle.mark_completed()
            event_queue.put(None)

    threading.Thread(target=copy_context().run, args=(run,), daemon=True).start()

    def generate():
        while True:
            item = event_queue.get()
            if item is None:
                break
            yield json.dumps(item, ensure_ascii=False) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson")


@router.post("/stream-runs/{stream_id}/cancel")
def cancel_stream_run(stream_id: str, *, container: Container = Depends(get_container)) -> dict[str, object]:
    handle = container.stream_interrupt_registry.cancel(stream_id=stream_id)
    return {
        "stream_id": handle.stream_id,
        "stream_kind": handle.stream_kind,
        "target_id": handle.target_id,
        "cancelled": handle.cancelled(),
        "cancelled_at": handle.cancelled_at,
    }


@router.get("/learning-plans/{plan_id}", response_model=LearningPlanResponse)
def get_learning_plan(plan_id: str, *, container: Container = Depends(get_container)) -> LearningPlanResponse:
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
        schedule_ids=payload.schedule_ids,
        status=payload.status,
        note=payload.note,
        actor="user",
        source="ui",
    )
    return _into_response(LearningPlanResponse, plan)


@router.patch("/learning-plans/{plan_id}/planning-questions/{question_id}", response_model=LearningPlanResponse)
def answer_learning_plan_question(
    plan_id: str,
    question_id: str,
    payload: PlanningQuestionAnswerRequest,
    *,
    container: Container = Depends(get_container),
) -> LearningPlanResponse:
    plan = container.plan_service.answer_planning_question(
        plan_id=plan_id,
        question_id=question_id,
        answer=payload.answer,
    )
    return _into_response(LearningPlanResponse, plan)


@router.delete("/learning-plans/{plan_id}")
def delete_learning_plan(plan_id: str, *, container: Container = Depends(get_container)) -> dict[str, str]:
    container.plan_service.delete_plan(plan_id)
    return {"deleted_plan_id": plan_id}


@router.post("/exercises/generate", response_model=ExerciseGenerateResponse)
def generate_exercise(payload: ExerciseGenerateRequest, *, container: Container = Depends(get_container)) -> ExerciseGenerateResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.pedagogy_orchestrator.generate_exercise(
        persona=persona,
        section_id=payload.section_id,
        topic=payload.topic,
    )
    return _into_response(ExerciseGenerateResponse, response)


@router.post("/submissions/grade", response_model=SubmissionGradeResponse)
def grade_submission(payload: SubmissionGradeRequest, *, container: Container = Depends(get_container)) -> SubmissionGradeResponse:
    persona = container.persona_engine.require_persona(payload.persona_id)
    response = container.pedagogy_orchestrator.grade_submission(
        persona=persona,
        exercise_id=payload.exercise_id,
        answer=payload.answer,
    )
    return _into_response(SubmissionGradeResponse, response)


@router.get("/model-usage/stats", response_model=TokenUsageStatsResponse)
def get_model_usage_stats(*, container: Container = Depends(get_container)) -> TokenUsageStatsResponse:
    records = container.token_usage_service.load_all()
    buckets_map: dict[tuple[str, str, str], TokenUsageDailyBucket] = {}
    call_records: list[TokenUsageCallRecord] = []
    total_prompt = 0
    total_completion = 0
    total_all = 0
    for rec in records:
        date_str = rec.created_at[:10]
        call_records.append(
            TokenUsageCallRecord(
                id=rec.id,
                created_at=rec.created_at,
                feature=rec.feature,
                model=rec.model,
                prompt_tokens=rec.prompt_tokens,
                completion_tokens=rec.completion_tokens,
                total_tokens=rec.total_tokens,
            )
        )
        key = (date_str, rec.feature, rec.model)
        if key not in buckets_map:
            buckets_map[key] = TokenUsageDailyBucket(
                date=date_str,
                feature=rec.feature,
                model=rec.model,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
            )
        bucket = buckets_map[key]
        buckets_map[key] = TokenUsageDailyBucket(
            date=bucket.date,
            feature=bucket.feature,
            model=bucket.model,
            prompt_tokens=bucket.prompt_tokens + rec.prompt_tokens,
            completion_tokens=bucket.completion_tokens + rec.completion_tokens,
            total_tokens=bucket.total_tokens + rec.total_tokens,
        )
        total_prompt += rec.prompt_tokens
        total_completion += rec.completion_tokens
        total_all += rec.total_tokens
    buckets = sorted(buckets_map.values(), key=lambda b: (b.date, b.feature, b.model))
    call_records.sort(key=lambda item: item.created_at, reverse=True)
    return TokenUsageStatsResponse(
        buckets=buckets,
        records=call_records,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_all,
    )


def _stringify_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail is not None:
        return str(detail)
    return str(exc)


def _invoke_study_chat(container: Container, **request) -> StudyChatOperationReceiptResponse:
    try:
        receipt = container.study_chat_application().admit(**request)
    except StudyChatApplicationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return _study_chat_operation_response(receipt)
