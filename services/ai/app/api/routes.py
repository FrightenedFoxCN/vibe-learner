import json
from datetime import datetime, timezone
from pathlib import Path
import queue
import threading
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.core.logging import get_logger
from app.core.bootstrap import container
from app.models.api import (
    BatchCreatePersonaCardsRequest,
    CreatePersonaCardRequest,
    CreateReusableSceneNodeRequest,
    CreatePersonaRequest,
    CreateStudySessionRequest,
    DocumentDebugResponse,
    DocumentListResponse,
    DocumentPlanningContextResponse,
    DocumentPlanningTraceResponse,
    DocumentResponse,
    DocumentStudyUnitUpdateResponse,
    StreamReportResponse,
    DocumentStatusResponse,
    ExerciseGenerateRequest,
    ExerciseGenerateResponse,
    LearningPlanCreateRequest,
    LearningPlanListResponse,
    LearningPlanResponse,
    LearningPlanUpdateRequest,
    ModelToolConfigResponse,
    RuntimeSettingsResponse,
    RuntimeSettingsProbeRequest,
    RuntimeSettingsProbeResponse,
    ReusableSceneNodeListResponse,
    ReusableSceneNodeResponse,
    SceneLibraryListResponse,
    SceneLibraryResponse,
    SceneTreeGenerateRequest,
    SceneTreeGenerateResponse,
    SceneSetupResponse,
    StudyUnitTitleUpdateRequest,
    UpdateModelToolConfigRequest,
    UpdateSceneSetupRequest,
    UpsertSceneLibraryRequest,
    UpdateRuntimeSettingsRequest,
    PersonaAssetsResponse,
    PersonaCardGenerateRequest,
    PersonaCardGenerateResponse,
    PersonaCardListResponse,
    PersonaCardResponse,
    PersonaSlotAssistRequest,
    PersonaSlotAssistResponse,
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
    TokenUsageStatsResponse,
    TokenUsageDailyBucket,
)
from app.models.domain import PersonaCardRecord, PlanGenerationTraceRecord, SceneLayerStateRecord
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)
from app.services.plan_prompt import build_learning_plan_context
from app.services.plan_tool_runtime import get_learning_plan_tool_specs
from app.services.runtime_model_probe import probe_openai_models
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


def _map_persona_card_generation_error(exc: RuntimeError) -> HTTPException:
    detail = str(exc)
    if detail == "setting_keyword_generation_requires_openai":
        return HTTPException(status_code=400, detail="keyword_generation_requires_openai")
    return _map_setting_generation_error(exc)


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/model-tools/config", response_model=ModelToolConfigResponse)
def get_model_tool_config() -> ModelToolConfigResponse:
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
def update_model_tool_config(payload: UpdateModelToolConfigRequest) -> ModelToolConfigResponse:
    try:
        container.model_tool_config_service.update(
            [toggle.model_dump(mode="json") for toggle in payload.toggles]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_model_tool_config()


@router.get("/runtime-settings", response_model=RuntimeSettingsResponse)
def get_runtime_settings() -> RuntimeSettingsResponse:
    described = container.runtime_settings_service.describe()
    return _into_response(RuntimeSettingsResponse, described)


@router.patch("/runtime-settings", response_model=RuntimeSettingsResponse)
def update_runtime_settings(payload: UpdateRuntimeSettingsRequest) -> RuntimeSettingsResponse:
    try:
        updates = payload.model_dump(mode="json", exclude_none=True)
        container.update_runtime_settings(updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return get_runtime_settings()


@router.get("/scene-setup", response_model=SceneSetupResponse)
def get_scene_setup() -> SceneSetupResponse:
    record = container.scene_setup_service.get_state()
    return _into_response(SceneSetupResponse, record)


@router.put("/scene-setup", response_model=SceneSetupResponse)
def update_scene_setup(payload: UpdateSceneSetupRequest) -> SceneSetupResponse:
    record = container.scene_setup_service.upsert_state(
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.scene_layers,
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        scene_profile=payload.scene_profile,
    )
    return _into_response(SceneSetupResponse, record)


@router.get("/scene-library", response_model=SceneLibraryListResponse)
def list_scene_library() -> SceneLibraryListResponse:
    items = container.scene_library_service.list_scenes()
    return SceneLibraryListResponse(items=[_into_response(SceneLibraryResponse, item) for item in items])


@router.get("/scene-library/{scene_id}", response_model=SceneLibraryResponse)
def get_scene_library_item(scene_id: str) -> SceneLibraryResponse:
    record = container.scene_library_service.require_scene(scene_id)
    return _into_response(SceneLibraryResponse, record)


@router.post("/scene-library", response_model=SceneLibraryResponse)
def create_scene_library_item(payload: UpsertSceneLibraryRequest) -> SceneLibraryResponse:
    record = container.scene_library_service.upsert_scene(
        scene_id=None,
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.scene_layers,
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        scene_profile=payload.scene_profile,
    )
    return _into_response(SceneLibraryResponse, record)


@router.put("/scene-library/{scene_id}", response_model=SceneLibraryResponse)
def update_scene_library_item(scene_id: str, payload: UpsertSceneLibraryRequest) -> SceneLibraryResponse:
    record = container.scene_library_service.upsert_scene(
        scene_id=scene_id,
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.scene_layers,
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        scene_profile=payload.scene_profile,
    )
    return _into_response(SceneLibraryResponse, record)


@router.delete("/scene-library/{scene_id}")
def delete_scene_library_item(scene_id: str) -> dict[str, str]:
    container.scene_library_service.delete_scene(scene_id)
    return {"deleted_scene_id": scene_id}


@router.get("/reusable-scene-nodes", response_model=ReusableSceneNodeListResponse)
def list_reusable_scene_nodes() -> ReusableSceneNodeListResponse:
    items = container.reusable_scene_node_library_service.list_nodes()
    return ReusableSceneNodeListResponse(
        items=[_into_response(ReusableSceneNodeResponse, item) for item in items]
    )


@router.post("/reusable-scene-nodes", response_model=ReusableSceneNodeResponse)
def create_reusable_scene_node(payload: CreateReusableSceneNodeRequest) -> ReusableSceneNodeResponse:
    record = container.reusable_scene_node_library_service.create_node(payload)
    return _into_response(ReusableSceneNodeResponse, record)


@router.delete("/reusable-scene-nodes/{node_id}")
def delete_reusable_scene_node(node_id: str) -> dict[str, str]:
    container.reusable_scene_node_library_service.delete_node(node_id)
    return {"deleted_reusable_scene_node_id": node_id}


@router.post("/scene-setup/generate", response_model=SceneTreeGenerateResponse)
def generate_scene_tree(payload: SceneTreeGenerateRequest) -> SceneTreeGenerateResponse:
    try:
        if payload.mode == "keywords":
            result = container.model_provider.generate_scene_tree_from_keywords(
                keywords=payload.input_text,
                layer_count=payload.layer_count,
            )
        elif payload.mode == "long_text":
            result = container.model_provider.generate_scene_tree_from_text(
                text=payload.input_text,
                layer_count=payload.layer_count,
            )
        else:
            raise HTTPException(status_code=400, detail="invalid_scene_tree_generation_mode")
    except RuntimeError as exc:
        raise _map_setting_generation_error(exc) from exc

    return SceneTreeGenerateResponse(
        mode=payload.mode,
        used_model=str(result.get("used_model") or ""),
        used_web_search=bool(result.get("used_web_search")),
        scene_name=str(result.get("scene_name") or ""),
        scene_summary=str(result.get("scene_summary") or ""),
        selected_layer_id=str(result.get("selected_layer_id") or ""),
        scene_layers=[
            SceneLayerStateRecord.model_validate(item)
            for item in (result.get("scene_layers") or [])
        ],
    )


@router.post("/runtime-settings/check-openai-models", response_model=RuntimeSettingsProbeResponse)
def check_openai_models(payload: RuntimeSettingsProbeRequest) -> RuntimeSettingsProbeResponse:
    api_key = payload.api_key.strip()
    base_url = payload.base_url.strip().rstrip("/")
    if not api_key:
        raise HTTPException(status_code=400, detail="missing_api_key")
    if not base_url:
        raise HTTPException(status_code=400, detail="missing_base_url")

    timeout_seconds = max(5, container.runtime_settings_service.effective_settings().openai_timeout_seconds)
    return RuntimeSettingsProbeResponse.model_validate(
        probe_openai_models(
            api_key=api_key,
            base_url=base_url,
            timeout_seconds=timeout_seconds,
        )
    )


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


@router.patch(
    "/documents/{document_id}/study-units/{study_unit_id}",
    response_model=DocumentStudyUnitUpdateResponse,
)
def update_study_unit_title(
    document_id: str,
    study_unit_id: str,
    payload: StudyUnitTitleUpdateRequest,
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


@router.get("/persona-cards", response_model=PersonaCardListResponse)
def list_persona_cards() -> PersonaCardListResponse:
    items = container.persona_card_library_service.list_cards()
    return PersonaCardListResponse(
        items=[_into_response(PersonaCardResponse, item) for item in items]
    )


@router.post("/persona-cards", response_model=PersonaCardResponse)
def create_persona_card(payload: CreatePersonaCardRequest) -> PersonaCardResponse:
    record = container.persona_card_library_service.create_card(payload)
    return _into_response(PersonaCardResponse, record)


@router.post("/persona-cards/batch", response_model=PersonaCardListResponse)
def create_persona_cards_batch(payload: BatchCreatePersonaCardsRequest) -> PersonaCardListResponse:
    items = container.persona_card_library_service.create_many(payload.items)
    return PersonaCardListResponse(
        items=[_into_response(PersonaCardResponse, item) for item in items]
    )


@router.delete("/persona-cards/{card_id}")
def delete_persona_card(card_id: str) -> dict[str, str]:
    container.persona_card_library_service.delete_card(card_id)
    return {"deleted_persona_card_id": card_id}


@router.post("/persona-cards/generate", response_model=PersonaCardGenerateResponse)
def generate_persona_cards(payload: PersonaCardGenerateRequest) -> PersonaCardGenerateResponse:
    try:
        if payload.mode == "keywords":
            result = container.model_provider.generate_persona_cards_from_keywords(
                keywords=payload.input_text,
                count=payload.count,
            )
            source = "generated_keywords"
        elif payload.mode == "long_text":
            result = container.model_provider.generate_persona_cards_from_text(
                text=payload.input_text,
                count=payload.count,
            )
            source = "generated_text"
        else:
            raise HTTPException(status_code=400, detail="invalid_persona_card_generation_mode")
    except RuntimeError as exc:
        raise _map_persona_card_generation_error(exc) from exc

    cards = [
        PersonaCardRecord(
            id=f"generated-{uuid4().hex[:10]}",
            title=str(item.get("title") or ""),
            kind=str(item.get("kind") or "custom"),
            label=str(item.get("label") or item.get("kind") or "自定义"),
            content=str(item.get("content") or ""),
            tags=[str(tag) for tag in (item.get("tags") or []) if str(tag).strip()],
            search_keywords=payload.input_text.strip() if payload.mode == "keywords" else "自定义",
            source=source,
            source_note=str(item.get("source_note") or ""),
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        for item in result.get("cards") or []
    ]
    return PersonaCardGenerateResponse(
        mode=payload.mode,
        used_model=str(result.get("used_model") or ""),
        used_web_search=bool(result.get("used_web_search")),
        summary=str(result.get("summary") or ""),
        relationship=str(result.get("relationship") or ""),
        learner_address=str(result.get("learner_address") or ""),
        items=[_into_response(PersonaCardResponse, item) for item in cards],
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


@router.post("/personas/assist-slot", response_model=PersonaSlotAssistResponse)
def assist_persona_slot(payload: PersonaSlotAssistRequest) -> PersonaSlotAssistResponse:
    try:
        result = container.model_provider.assist_persona_slot(
            name=payload.name,
            summary=payload.summary,
            slot=payload.slot,
            rewrite_strength=payload.rewrite_strength,
        )
    except RuntimeError as exc:
        http_error = _map_setting_generation_error(exc)
        logger.warning(
            "persona.assist_slot.model_failed detail=%s internal_error_code=%s fallback=local",
            http_error.detail,
            str(exc),
        )
        result = {
            "slot": container.persona_engine.assist_slot(
                name=payload.name,
                summary=payload.summary,
                slot=payload.slot,
                rewrite_strength=payload.rewrite_strength,
            ).model_dump()
        }
    return PersonaSlotAssistResponse(**result)


@router.post("/study-sessions/{session_id}/chat", response_model=StudyChatExchangeResponse)
def study_chat(session_id: str, payload: StudyChatRequest) -> StudyChatExchangeResponse:
    session = _ensure_session_scene_binding(container.study_session_service.require_session(session_id))
    memory_sessions = container.study_session_service.list_sessions(
        document_id=session.document_id,
        persona_id=session.persona_id,
    )
    persona = container.persona_engine.require_persona(session.persona_id)
    document = container.document_service.require_document(session.document_id)
    debug_report = None
    try:
        debug_report = container.document_service.require_debug_report(session.document_id)
    except HTTPException:
        debug_report = None

    scene_tool_runtime = (
        container.session_scene_service.build_tool_runtime(session.scene_instance_id)
        if session.scene_instance_id
        else None
    )
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
            memory_sessions=memory_sessions,
            active_scene_summary=_scene_profile_summary(session),
            active_scene_context=scene_tool_runtime.scene_context() if scene_tool_runtime else "",
            scene_tool_runtime=scene_tool_runtime,
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
    verdict = "回答正确" if payload.is_correct else "回答不正确"
    feedback_text = (
        verdict
        if payload.is_correct
        else (
            f"{verdict}，正确答案是 {payload.answer_key}"
            if payload.answer_key
            else f"{verdict}，参考答案：{' / '.join(payload.accepted_answers) or '未提供'}"
        )
    )
    session = container.study_session_service.append_attempt_turn(
        session_id=session_id,
        prompt=payload.prompt,
        submitted_answer=answer,
        is_correct=payload.is_correct,
        feedback_text=feedback_text,
    )
    return _into_response(StudySessionResponse, session)


@router.patch("/study-sessions/{session_id}", response_model=StudySessionResponse)
def update_study_session(
    session_id: str, payload: UpdateStudySessionRequest
) -> StudySessionResponse:
    if payload.section_id is None and "scene_profile" not in payload.model_fields_set:
        raise HTTPException(status_code=400, detail="update_payload_empty")

    current_session = _ensure_session_scene_binding(
        container.study_session_service.require_session(session_id)
    )
    next_section_id = payload.section_id or current_session.section_id
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
    document = container.document_service.require_document(current_session.document_id)
    next_section_title = _resolve_section_title(document=document, section_id=next_section_id)
    session_system_prompt = build_study_session_system_prompt(
        persona_name=persona.name,
        persona_relationship=persona.relationship,
        persona_learner_address=persona.learner_address,
        persona_system_prompt=persona.system_prompt,
        document_title=document.title,
        section_id=next_section_id,
        section_title=next_section_title,
        theme_hint=current_session.theme_hint,
        scene_profile=next_scene_profile,
    )

    session = container.study_session_service.update_session(
        session_id=session_id,
        section_id=payload.section_id,
        scene_instance_id=next_scene_instance_id if has_scene_profile else None,
        scene_profile=next_scene_profile,
        has_scene_profile=has_scene_profile,
        section_title=next_section_title,
        session_system_prompt=session_system_prompt,
    )
    return _into_response(StudySessionResponse, session)


@router.post("/study-sessions", response_model=StudySessionResponse)
def create_study_session(payload: CreateStudySessionRequest) -> StudySessionResponse:
    session_id = f"session-{uuid4().hex[:10]}"
    logger.info(
        "study_sessions.create document_id=%s persona_id=%s section_id=%s scene_id=%s",
        payload.document_id,
        payload.persona_id,
        payload.section_id,
        payload.scene_profile.scene_id if payload.scene_profile else "",
    )
    persona = container.persona_engine.require_persona(payload.persona_id)
    document = container.document_service.require_document(payload.document_id)
    section_title = payload.section_title.strip() or _resolve_section_title(
        document=document,
        section_id=payload.section_id,
    )
    theme_hint = payload.theme_hint.strip()
    bound_scene = container.session_scene_service.clone_scene_for_session(
        session_id=session_id,
        document_id=payload.document_id,
        persona_id=payload.persona_id,
        scene_profile=payload.scene_profile,
    )
    session_scene_profile = bound_scene.scene_profile if bound_scene else None
    session_system_prompt = build_study_session_system_prompt(
        persona_name=persona.name,
        persona_relationship=persona.relationship,
        persona_learner_address=persona.learner_address,
        persona_system_prompt=persona.system_prompt,
        document_title=document.title,
        section_id=payload.section_id,
        section_title=section_title,
        theme_hint=theme_hint,
        scene_profile=session_scene_profile,
    )
    session = container.study_session_service.create_session(
        session_id=session_id,
        document_id=payload.document_id,
        persona_id=payload.persona_id,
        scene_instance_id=bound_scene.scene_instance_id if bound_scene else "",
        scene_profile=session_scene_profile,
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


def _scene_profile_summary(session) -> str:
    if not session.scene_profile:
        return ""
    return session.scene_profile.summary.strip()


def _ensure_session_scene_binding(session):
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


@router.patch("/learning-plans/{plan_id}", response_model=LearningPlanResponse)
def update_learning_plan(
    plan_id: str,
    payload: LearningPlanUpdateRequest,
) -> LearningPlanResponse:
    plan = container.plan_service.update_plan(
        plan_id=plan_id,
        course_title=payload.course_title,
        study_chapters=payload.study_chapters,
    )
    return _into_response(LearningPlanResponse, plan)


@router.delete("/learning-plans/{plan_id}")
def delete_learning_plan(plan_id: str) -> dict[str, str]:
    container.plan_service.delete_plan(plan_id)
    return {"deleted_plan_id": plan_id}


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


@router.get("/model-usage/stats", response_model=TokenUsageStatsResponse)
def get_model_usage_stats() -> TokenUsageStatsResponse:
    records = container.token_usage_service.load_all()
    buckets_map: dict[tuple[str, str, str], TokenUsageDailyBucket] = {}
    total_prompt = 0
    total_completion = 0
    total_all = 0
    for rec in records:
        date_str = rec.created_at[:10]
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
    return TokenUsageStatsResponse(
        buckets=buckets,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_all,
    )


def _stringify_error(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if detail is not None:
        return str(detail)
    return str(exc)
