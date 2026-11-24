from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.core.bootstrap import Container
from app.api.dependencies import get_container
from fastapi import Depends
from app.models.api import (
    ModelToolConfigResponse,
    RuntimeSettingsResponse,
    RuntimeSessionSecretsRequest,
    RuntimeSettingsProbeRequest,
    RuntimeSettingsProbeResponse,
    UpdateModelToolConfigRequest,
    UpdateRuntimeSettingsRequest,
    StorageCleanupRequest,
    StorageCleanupResponse,
    StorageSummaryResponse,
    TokenUsageCallRecord,
    TokenUsageStatsResponse,
    TokenUsageDailyBucket,
)
from app.services.model_provider import OpenAIModelProvider
from app.services.runtime_model_probe import probe_openai_models


from app.api._shared import (
    _into_response,
)
from app.core.coerce import text_at

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/storage/summary", response_model=StorageSummaryResponse)
def get_storage_summary(
    *, container: Container = Depends(get_container)
) -> StorageSummaryResponse:
    return StorageSummaryResponse(
        buckets=container.storage_lifecycle_service.summarize(),
        orphaned_uploads=container.storage_lifecycle_service.list_orphaned_uploads(),
    )


@router.post("/storage/cleanup", response_model=StorageCleanupResponse)
def cleanup_storage(
    payload: StorageCleanupRequest, *, container: Container = Depends(get_container)
) -> StorageCleanupResponse:
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
def get_model_tool_config(
    *, container: Container = Depends(get_container)
) -> ModelToolConfigResponse:
    described = container.model_tool_config_service.describe()
    provider = container.capture_model_provider()

    stage_enabled: dict[str, tuple[bool, str]] = {
        "plan_generation": (True, ""),
        "study_chat": (True, ""),
    }

    for stage in described["stages"]:
        current_stage_name = text_at(stage, "name")
        stage_flag, stage_reason = stage_enabled.get(
            current_stage_name, (False, "当前模型提供器不支持此阶段工具。")
        )
        stage["stage_enabled"] = stage_flag
        stage["stage_disabled_reason"] = stage_reason
        stage["audit_basis"] = [
            f"stage_registry={current_stage_name}",
            f"stage_runtime_gate={'on' if stage_flag else 'off'}",
        ]
        tools = stage.get("tools") or []
        for tool in tools:
            tool_name = text_at(tool, "name")
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
                if current_stage_name == "plan_generation":
                    available = provider.supports_page_image_tools()
                    audit_basis.append(
                        f"plan_multimodal={'on' if available else 'off'}"
                    )
                    if not available:
                        unavailable_reason = "当前计划模型未启用多模态能力。"
                elif current_stage_name == "study_chat":
                    available = provider.supports_chat_page_image_tools()
                    audit_basis.append(
                        f"chat_multimodal={'on' if available else 'off'}"
                    )
                    if not available:
                        unavailable_reason = "当前对话模型未启用多模态能力。"
            elif tool_name == "retrieve_memory_context":
                audit_basis.append("chat_memory_gate=managed_by_model_tools")
            tool["available"] = available
            tool["unavailable_reason"] = unavailable_reason
            tool["effective_enabled"] = bool(tool.get("enabled")) and available
            tool["audit_basis"] = audit_basis

    return _into_response(ModelToolConfigResponse, described)


@router.patch("/model-tools/config", response_model=ModelToolConfigResponse)
def update_model_tool_config(
    payload: UpdateModelToolConfigRequest,
    *,
    container: Container = Depends(get_container),
) -> ModelToolConfigResponse:
    try:
        container.update_model_tool_config(
            [toggle.model_dump(mode="json") for toggle in payload.toggles]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_model_tool_config(container=container)


@router.get("/runtime-settings", response_model=RuntimeSettingsResponse)
def get_runtime_settings(
    *, container: Container = Depends(get_container)
) -> RuntimeSettingsResponse:
    described = container.runtime_settings_service.describe()
    return _into_response(RuntimeSettingsResponse, described)


class _RuntimeSettingsPatchRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as exc:
                # Do not echo API keys or pass non-finite inputs to the JSON encoder.
                raise HTTPException(
                    422,
                    [
                        {name: error[name] for name in ("type", "loc", "msg")}
                        for error in exc.errors()
                    ],
                ) from exc

        return handle


def update_runtime_settings(
    payload: UpdateRuntimeSettingsRequest,
    *,
    container: Container = Depends(get_container),
) -> RuntimeSettingsResponse:
    try:
        updates = payload.model_dump(mode="json", exclude_none=True)
        container.update_runtime_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_runtime_settings(container=container)


router.add_api_route(
    "/runtime-settings",
    update_runtime_settings,
    methods=["PATCH"],
    response_model=RuntimeSettingsResponse,
    route_class_override=_RuntimeSettingsPatchRoute,
)


@router.put("/runtime-settings/session-secrets", response_model=RuntimeSettingsResponse)
def apply_runtime_session_secrets(
    payload: RuntimeSessionSecretsRequest,
    *,
    container: Container = Depends(get_container),
) -> RuntimeSettingsResponse:
    container.apply_runtime_session_secrets(
        payload.model_dump(mode="json", exclude_none=True)
    )
    return get_runtime_settings(container=container)


@router.delete(
    "/runtime-settings/session-secrets", response_model=RuntimeSettingsResponse
)
def clear_runtime_session_secrets(
    *, container: Container = Depends(get_container)
) -> RuntimeSettingsResponse:
    container.clear_runtime_session_secrets()
    return get_runtime_settings(container=container)


@router.post(
    "/runtime-settings/check-openai-models", response_model=RuntimeSettingsProbeResponse
)
def check_openai_models(
    payload: RuntimeSettingsProbeRequest,
    *,
    container: Container = Depends(get_container),
) -> RuntimeSettingsProbeResponse:
    api_key = payload.api_key.strip()
    base_url = payload.base_url.strip().rstrip("/")
    if not api_key:
        raise HTTPException(status_code=400, detail="missing_api_key")
    if not base_url:
        raise HTTPException(status_code=400, detail="missing_base_url")

    timeout_seconds = max(
        5,
        container.runtime_settings_service.effective_settings().openai_timeout_seconds,
    )
    # /models evidence is independent of the representative Chat Completions
    # requests below. The latter are synthetic, not production workflows.
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
            setting_web_search_enabled=False,  # Never issue a live web search here.
            timeout_seconds=timeout_seconds,
        )
        result["feature_readiness"] = probe_provider.probe_feature_readiness(
            payload.features
        )
    return RuntimeSettingsProbeResponse.model_validate(result)


@router.get("/model-usage/stats", response_model=TokenUsageStatsResponse)
def get_model_usage_stats(
    workflow: str = "",
    operation_id: str = "",
    date_from: str = "",
    date_to: str = "",
    *,
    container: Container = Depends(get_container),
) -> TokenUsageStatsResponse:
    records = container.token_usage_service.load_all()
    records = [
        record
        for record in records
        if (not workflow or record.workflow == workflow)
        and (not operation_id or record.operation_id == operation_id)
        and (not date_from or record.created_at[:10] >= date_from)
        and (not date_to or record.created_at[:10] <= date_to)
    ]
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
                operation_id=rec.operation_id,
                workflow=rec.workflow,
                stage=rec.stage,
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
