from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.diagnostics import reference_persona, reference_scene
from app.core.bootstrap import Container
from app.api.dependencies import get_container
from fastapi import Depends
from app.models.api import (
    BatchCreatePersonaCardsRequest,
    CreatePersonaCardRequest,
    CreateReusableSceneNodeRequest,
    CreatePersonaRequest,
    ReusableSceneNodeListResponse,
    ReusableSceneNodeResponse,
    SceneLibraryListResponse,
    SceneLibraryResponse,
    SceneTreeGenerateRequest,
    SceneTreeGenerateResponse,
    SceneSetupResponse,
    UpdateSceneSetupRequest,
    UpsertSceneLibraryRequest,
    PersonaAssetsResponse,
    PersonaCardGenerateRequest,
    PersonaCardGenerateResponse,
    PersonaCardListResponse,
    PersonaCardResponse,
    PersonaSlotAssistRequest,
    PersonaSlotAssistResponse,
    PersonaSettingAssistRequest,
    PersonaSettingAssistResponse,
    PersonaListResponse,
    PersonaResponse,
    UpdatePersonaRequest,
)
from app.models.domain import PersonaCardRecord, PersonaSlot
from app.services.model_recovery import (
    record_model_recovery,
    reset_model_recovery_state,
)
from app.models.persona_generation import (
    PersonaGenerationInputManifest,
    PersonaGenerationProposalV1,
)
from app.models.scene_generation import (
    SceneGenerationInputManifest,
    SceneGenerationProposalV1,
)
from app.models.scene import SceneTreeProposalV1, project_scene_tree_proposal


from app.api._shared import (
    logger,
    _into_response,
    _into_response_with_model_recoveries,
    _map_setting_generation_error,
    _map_persona_card_generation_error,
)

router = APIRouter()


@router.get("/scene-setup", response_model=SceneSetupResponse)
def get_scene_setup(
    *, container: Container = Depends(get_container)
) -> SceneSetupResponse:
    record = container.scene_setup_service.get_state()
    return _into_response(SceneSetupResponse, record)


@router.put("/scene-setup", response_model=SceneSetupResponse)
def update_scene_setup(
    payload: UpdateSceneSetupRequest, *, container: Container = Depends(get_container)
) -> SceneSetupResponse:
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
def list_scene_library(
    *, container: Container = Depends(get_container)
) -> SceneLibraryListResponse:
    items = container.scene_library_service.list_scenes()
    return SceneLibraryListResponse(
        items=[_into_response(SceneLibraryResponse, item) for item in items]
    )


@router.get("/scene-library/{scene_id}", response_model=SceneLibraryResponse)
def get_scene_library_item(
    scene_id: str, *, container: Container = Depends(get_container)
) -> SceneLibraryResponse:
    record = container.scene_library_service.require_scene(scene_id)
    return _into_response(SceneLibraryResponse, record)


@router.post("/scene-library", response_model=SceneLibraryResponse)
def create_scene_library_item(
    payload: UpsertSceneLibraryRequest, *, container: Container = Depends(get_container)
) -> SceneLibraryResponse:
    record = container.scene_library_service.upsert_scene(
        scene_id=None,
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.to_domain_layers(),
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        expected_revision=payload.expected_revision,
    )
    reference_scene(record)
    return _into_response(SceneLibraryResponse, record)


@router.put("/scene-library/{scene_id}", response_model=SceneLibraryResponse)
def update_scene_library_item(
    scene_id: str,
    payload: UpsertSceneLibraryRequest,
    *,
    container: Container = Depends(get_container),
) -> SceneLibraryResponse:
    record = container.scene_library_service.upsert_scene(
        scene_id=scene_id,
        scene_name=payload.scene_name,
        scene_summary=payload.scene_summary,
        scene_layers=payload.to_domain_layers(),
        selected_layer_id=payload.selected_layer_id,
        collapsed_layer_ids=payload.collapsed_layer_ids,
        expected_revision=payload.expected_revision,
    )
    reference_scene(record)
    return _into_response(SceneLibraryResponse, record)


@router.delete("/scene-library/{scene_id}")
def delete_scene_library_item(
    scene_id: str, *, container: Container = Depends(get_container)
) -> dict[str, str]:
    container.scene_library_service.delete_scene(scene_id)
    return {"deleted_scene_id": scene_id}


@router.get("/reusable-scene-nodes", response_model=ReusableSceneNodeListResponse)
def list_reusable_scene_nodes(
    *, container: Container = Depends(get_container)
) -> ReusableSceneNodeListResponse:
    items = container.reusable_scene_node_library_service.list_nodes()
    return ReusableSceneNodeListResponse(
        items=[_into_response(ReusableSceneNodeResponse, item) for item in items]
    )


@router.post("/reusable-scene-nodes", response_model=ReusableSceneNodeResponse)
def create_reusable_scene_node(
    payload: CreateReusableSceneNodeRequest,
    *,
    container: Container = Depends(get_container),
) -> ReusableSceneNodeResponse:
    record = container.reusable_scene_node_library_service.create_node(payload)
    return _into_response(ReusableSceneNodeResponse, record)


@router.delete("/reusable-scene-nodes/{node_id}")
def delete_reusable_scene_node(
    node_id: str, *, container: Container = Depends(get_container)
) -> dict[str, str]:
    container.reusable_scene_node_library_service.delete_node(node_id)
    return {"deleted_reusable_scene_node_id": node_id}


@router.post("/scene-setup/generate", response_model=SceneTreeGenerateResponse)
def generate_scene_tree(
    payload: SceneTreeGenerateRequest, *, container: Container = Depends(get_container)
) -> SceneTreeGenerateResponse:
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

    return _into_response_with_model_recoveries(
        SceneTreeGenerateResponse,
        SceneTreeGenerateResponse(
            mode=payload.mode,
            used_model=generated.used_model,
            used_web_search=generated.used_web_search,
            scene_name=projection.scene_name,
            scene_summary=projection.scene_summary,
            selected_layer_id=projection.selected_layer_id,
            scene_layers=projection.scene_layers,
            harness_trace=harness_trace,
        ),
    )


@router.get("/personas", response_model=PersonaListResponse)
def list_personas(
    *, container: Container = Depends(get_container)
) -> PersonaListResponse:
    personas = container.persona_engine.list_personas()
    return PersonaListResponse(
        items=[_into_response(PersonaResponse, persona) for persona in personas]
    )


@router.post("/personas", response_model=PersonaResponse)
def create_persona(
    payload: CreatePersonaRequest, *, container: Container = Depends(get_container)
) -> PersonaResponse:
    persona = container.persona_engine.create_persona(payload)
    reference_persona(persona)
    return _into_response(PersonaResponse, persona)


@router.patch("/personas/{persona_id}", response_model=PersonaResponse)
def update_persona(
    persona_id: str,
    payload: UpdatePersonaRequest,
    *,
    container: Container = Depends(get_container),
) -> PersonaResponse:
    persona = container.persona_engine.update_persona(persona_id, payload)
    reference_persona(persona)
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
def get_persona_assets(
    persona_id: str, *, container: Container = Depends(get_container)
) -> PersonaAssetsResponse:
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
def list_persona_cards(
    *, container: Container = Depends(get_container)
) -> PersonaCardListResponse:
    items = container.persona_card_library_service.list_cards()
    return PersonaCardListResponse(
        items=[_into_response(PersonaCardResponse, item) for item in items]
    )


@router.post("/persona-cards", response_model=PersonaCardResponse)
def create_persona_card(
    payload: CreatePersonaCardRequest, *, container: Container = Depends(get_container)
) -> PersonaCardResponse:
    record = container.persona_card_library_service.create_card(payload)
    return _into_response(PersonaCardResponse, record)


@router.post("/persona-cards/batch", response_model=PersonaCardListResponse)
def create_persona_cards_batch(
    payload: BatchCreatePersonaCardsRequest,
    *,
    container: Container = Depends(get_container),
) -> PersonaCardListResponse:
    items = container.persona_card_library_service.create_many(payload.items)
    return PersonaCardListResponse(
        items=[_into_response(PersonaCardResponse, item) for item in items]
    )


@router.delete("/persona-cards/{card_id}")
def delete_persona_card(
    card_id: str, *, container: Container = Depends(get_container)
) -> dict[str, str]:
    container.persona_card_library_service.delete_card(card_id)
    return {"deleted_persona_card_id": card_id}


@router.post("/persona-cards/generate", response_model=PersonaCardGenerateResponse)
def generate_persona_cards(
    payload: PersonaCardGenerateRequest,
    *,
    container: Container = Depends(get_container),
) -> PersonaCardGenerateResponse:
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
        source = (
            "generated_keywords" if payload.mode == "keywords" else "generated_text"
        )
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
            search_keywords=payload.input_text.strip()
            if payload.mode == "keywords"
            else "自定义",
            source=source,
            source_note=item.source_note,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        for item in generated.cards
    ]
    return _into_response_with_model_recoveries(
        PersonaCardGenerateResponse,
        PersonaCardGenerateResponse(
            mode=payload.mode,
            used_model=generated.used_model,
            used_web_search=generated.used_web_search,
            summary=generated.summary,
            relationship=generated.relationship,
            learner_address=generated.learner_address,
            items=[_into_response(PersonaCardResponse, item) for item in cards],
            harness_trace=harness_trace,
        ),
    )


@router.post("/personas/assist-setting", response_model=PersonaSettingAssistResponse)
def assist_persona_setting(
    payload: PersonaSettingAssistRequest,
    *,
    container: Container = Depends(get_container),
) -> PersonaSettingAssistResponse:
    reset_model_recovery_state()
    try:

        def generate_setting(
            protected: dict[str, object],
        ) -> PersonaGenerationProposalV1:
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
                used_model = str(
                    getattr(container.model_provider, "setting_model", "mock")
                )
            except RuntimeError as exc:
                logger.warning(
                    "persona.assist_setting.model_failed internal_error_code=%s fallback=local",
                    str(exc),
                )
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
                result["slots"] = [
                    item.model_dump(mode="json") for item in protected_slots
                ]
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
                input_char_count=len(payload.name)
                + len(payload.summary)
                + sum(len(item.content) for item in payload.slots),
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
def assist_persona_slot(
    payload: PersonaSlotAssistRequest, *, container: Container = Depends(get_container)
) -> PersonaSlotAssistResponse:
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
                used_model = str(
                    getattr(container.model_provider, "setting_model", "mock")
                )
            except RuntimeError as exc:
                logger.warning(
                    "persona.assist_slot.model_failed internal_error_code=%s fallback=local",
                    str(exc),
                )
                reset_model_recovery_state()
                record_model_recovery(
                    category="persona_slot_assist",
                    reason="setting_model_unavailable_or_invalid",
                    strategy="local_fallback",
                    note="模型润色未完成，已使用本地规则；请检查结果后再保存。",
                )
                result = {
                    "slot": container.persona_engine.assist_slot(
                        name=str(protected["name"]),
                        summary=str(protected["summary"]),
                        slot=protected_slot,
                        rewrite_strength=float(protected["rewrite_strength"]),
                    ).model_dump(mode="json")
                }
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
                input_char_count=len(payload.name)
                + len(payload.summary)
                + len(payload.slot.content),
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
