from __future__ import annotations

from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models.domain import (
    ReusableSceneNodeRecord,
    SceneLayerStateRecord,
    SceneObjectStateRecord,
    SceneProfileRecord,
)


SCENE_TREE_PROPOSAL_SCHEMA_VERSION = "scene-tree-proposal-v1"
SCENE_TREE_PROJECTION_SCHEMA_VERSION = "scene-tree-generated-projection-v1"
SCENE_COMMITTED_SAVE_CONTRACT_VERSION = "scene-committed-save-v1"
SCENE_MAX_DEPTH = 8
SCENE_MAX_LAYER_COUNT = 64
SCENE_MAX_OBJECT_COUNT = 128
SCENE_MAX_TEXT_BUDGET = 60_000


class _StrictSceneModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


ShortSceneText = Annotated[str, Field(min_length=1, max_length=500)]
LongSceneText = Annotated[str, Field(min_length=1, max_length=4000)]
OptionalSceneText = Annotated[str, Field(max_length=1000)]


class SceneObjectProposalV1(_StrictSceneModel):
    name: ShortSceneText
    description: LongSceneText
    interaction: LongSceneText
    tags: list[ShortSceneText] = Field(default_factory=list, max_length=12)
    reuse_hint: OptionalSceneText = ""
    reusable_node_ref: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_tags(self) -> "SceneObjectProposalV1":
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("duplicate_object_tag")
        return self


class SceneLayerProposalV1(_StrictSceneModel):
    title: ShortSceneText
    scope_label: ShortSceneText
    summary: LongSceneText
    atmosphere: LongSceneText
    rules: LongSceneText
    entrance: LongSceneText
    tags: list[ShortSceneText] = Field(default_factory=list, max_length=12)
    reuse_hint: OptionalSceneText = ""
    reusable_node_ref: str | None = Field(default=None, min_length=1, max_length=64)
    objects: list[SceneObjectProposalV1] = Field(default_factory=list, max_length=16)
    children: list["SceneLayerProposalV1"] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_tags(self) -> "SceneLayerProposalV1":
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("duplicate_layer_tag")
        return self


class SceneTreeProposalV1(_StrictSceneModel):
    schema_name: Literal["scene-tree-proposal"]
    schema_version: Literal["scene-tree-proposal-v1"]
    scene_name: ShortSceneText
    scene_summary: LongSceneText
    selected_path: list[int] = Field(min_length=1, max_length=SCENE_MAX_DEPTH)
    scene_layers: list[SceneLayerProposalV1] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def validate_tree(self) -> "SceneTreeProposalV1":
        layer_count, object_count, text_budget = _proposal_tree_metrics(
            self.scene_layers
        )
        if layer_count > SCENE_MAX_LAYER_COUNT:
            raise ValueError("scene_layer_count_exceeded")
        if object_count > SCENE_MAX_OBJECT_COUNT:
            raise ValueError("scene_object_count_exceeded")
        if text_budget + len(self.scene_name) + len(self.scene_summary) > SCENE_MAX_TEXT_BUDGET:
            raise ValueError("scene_text_budget_exceeded")
        _resolve_proposal_path(self.scene_layers, self.selected_path)
        return self


class SceneTreeGeneratedProjectionV1(_StrictSceneModel):
    schema_version: Literal["scene-tree-generated-projection-v1"] = (
        SCENE_TREE_PROJECTION_SCHEMA_VERSION
    )
    scene_name: str
    scene_summary: str
    selected_layer_id: str
    scene_layers: list[SceneLayerStateRecord]

    @model_validator(mode="after")
    def validate_projection(self) -> "SceneTreeGeneratedProjectionV1":
        validate_committed_scene_tree(
            scene_name=self.scene_name,
            scene_summary=self.scene_summary,
            scene_layers=self.scene_layers,
            selected_layer_id=self.selected_layer_id,
            collapsed_layer_ids=[],
        )
        return self


class SceneObjectCommittedInputV1(_StrictSceneModel):
    id: str = Field(min_length=1, max_length=64)
    name: ShortSceneText
    description: LongSceneText
    interaction: LongSceneText
    tags: str = Field(default="", max_length=1000)
    reuse_id: str = Field(min_length=1, max_length=64)
    reuse_hint: str = Field(default="", max_length=1000)


class SceneLayerCommittedInputV1(_StrictSceneModel):
    id: str = Field(min_length=1, max_length=64)
    title: ShortSceneText
    scope_label: ShortSceneText
    summary: LongSceneText
    atmosphere: LongSceneText
    rules: LongSceneText
    entrance: LongSceneText
    tags: str = Field(default="", max_length=1000)
    reuse_id: str = Field(min_length=1, max_length=64)
    reuse_hint: str = Field(default="", max_length=1000)
    objects: list[SceneObjectCommittedInputV1] = Field(
        default_factory=list,
        max_length=16,
    )
    children: list["SceneLayerCommittedInputV1"] = Field(
        default_factory=list,
        max_length=8,
    )


class SceneCommittedSaveV1(_StrictSceneModel):
    contract_version: Literal["scene-committed-save-v1"] = (
        SCENE_COMMITTED_SAVE_CONTRACT_VERSION
    )
    expected_revision: int = Field(ge=0)
    scene_name: ShortSceneText
    scene_summary: LongSceneText
    scene_layers: list[SceneLayerCommittedInputV1] = Field(min_length=1, max_length=8)
    selected_layer_id: str = Field(min_length=1, max_length=64)
    collapsed_layer_ids: list[str] = Field(default_factory=list, max_length=64)

    @model_validator(mode="after")
    def validate_projection(self) -> "SceneCommittedSaveV1":
        validate_committed_scene_tree(
            scene_name=self.scene_name,
            scene_summary=self.scene_summary,
            scene_layers=self.to_domain_layers(),
            selected_layer_id=self.selected_layer_id,
            collapsed_layer_ids=self.collapsed_layer_ids,
        )
        return self

    def to_domain_layers(self) -> list[SceneLayerStateRecord]:
        return [
            SceneLayerStateRecord.model_validate(item.model_dump(mode="json"))
            for item in self.scene_layers
        ]


def decode_scene_tree_proposal(payload: object) -> SceneTreeProposalV1:
    try:
        return SceneTreeProposalV1.model_validate(payload)
    except ValidationError as exc:
        first = exc.errors(include_url=False)[0]
        path = ".".join(str(part) for part in first.get("loc", ())) or "$"
        error_type = str(first.get("type") or "invalid")
        context_error = (first.get("ctx") or {}).get("error")
        reason = str(context_error or error_type).strip().replace(" ", "_")
        raise RuntimeError(
            f"setting_scene_proposal_invalid:{path}:{reason}"
        ) from exc


def project_scene_tree_proposal(
    proposal: SceneTreeProposalV1,
    *,
    allowed_reusable_nodes: dict[str, ReusableSceneNodeRecord] | None = None,
) -> SceneTreeGeneratedProjectionV1:
    reusable_nodes = allowed_reusable_nodes or {}

    def project_object(item: SceneObjectProposalV1) -> SceneObjectStateRecord:
        reusable = _resolve_reusable_node(
            item.reusable_node_ref,
            reusable_nodes,
            expected_type="object",
        )
        return SceneObjectStateRecord(
            id=f"scene-object-{uuid4().hex[:16]}",
            name=item.name,
            description=item.description,
            interaction=item.interaction,
            tags=",".join(item.tags),
            reuse_id=(
                reusable.reuse_id
                if reusable is not None and reusable.reuse_id
                else f"scene-object-reuse-{uuid4().hex[:16]}"
            ),
            reuse_hint=item.reuse_hint or (
                reusable.reuse_hint if reusable is not None else ""
            ),
        )

    def project_layer(item: SceneLayerProposalV1) -> SceneLayerStateRecord:
        reusable = _resolve_reusable_node(
            item.reusable_node_ref,
            reusable_nodes,
            expected_type="layer",
        )
        return SceneLayerStateRecord(
            id=f"scene-layer-{uuid4().hex[:16]}",
            title=item.title,
            scope_label=item.scope_label,
            summary=item.summary,
            atmosphere=item.atmosphere,
            rules=item.rules,
            entrance=item.entrance,
            tags=",".join(item.tags),
            reuse_id=(
                reusable.reuse_id
                if reusable is not None and reusable.reuse_id
                else f"scene-layer-reuse-{uuid4().hex[:16]}"
            ),
            reuse_hint=item.reuse_hint or (
                reusable.reuse_hint if reusable is not None else ""
            ),
            objects=[project_object(obj) for obj in item.objects],
            children=[project_layer(child) for child in item.children],
        )

    layers = [project_layer(layer) for layer in proposal.scene_layers]
    selected = _resolve_committed_path(layers, proposal.selected_path)
    return SceneTreeGeneratedProjectionV1(
        scene_name=proposal.scene_name,
        scene_summary=proposal.scene_summary,
        selected_layer_id=selected.id,
        scene_layers=layers,
    )


def validate_committed_scene_tree(
    *,
    scene_name: str,
    scene_summary: str,
    scene_layers: list[SceneLayerStateRecord],
    selected_layer_id: str,
    collapsed_layer_ids: list[str],
) -> None:
    if not scene_name.strip() or not scene_summary.strip() or not scene_layers:
        raise ValueError("scene_committed_content_required")
    if len(set(collapsed_layer_ids)) != len(collapsed_layer_ids):
        raise ValueError("scene_collapsed_layer_duplicate")
    ids: set[str] = set()
    layer_ids: set[str] = set()
    layer_count = 0
    object_count = 0
    text_budget = len(scene_name) + len(scene_summary)

    def visit(layer: SceneLayerStateRecord, depth: int) -> None:
        nonlocal layer_count, object_count, text_budget
        if depth > SCENE_MAX_DEPTH:
            raise ValueError("scene_depth_exceeded")
        if not layer.id or not layer.reuse_id:
            raise ValueError("scene_layer_identity_required")
        if layer.id in ids:
            raise ValueError("scene_committed_id_duplicate")
        ids.add(layer.id)
        layer_ids.add(layer.id)
        layer_count += 1
        text_budget += sum(
            len(value)
            for value in (
                layer.title,
                layer.scope_label,
                layer.summary,
                layer.atmosphere,
                layer.rules,
                layer.entrance,
                layer.tags,
                layer.reuse_hint,
            )
        )
        if len(layer.objects) > 16 or len(layer.children) > 8:
            raise ValueError("scene_child_budget_exceeded")
        for obj in layer.objects:
            if not obj.id or not obj.reuse_id:
                raise ValueError("scene_object_identity_required")
            if obj.id in ids:
                raise ValueError("scene_committed_id_duplicate")
            ids.add(obj.id)
            object_count += 1
            text_budget += sum(
                len(value)
                for value in (
                    obj.name,
                    obj.description,
                    obj.interaction,
                    obj.tags,
                    obj.reuse_hint,
                )
            )
        for child in layer.children:
            visit(child, depth + 1)

    for root in scene_layers:
        visit(root, 1)
    if layer_count > SCENE_MAX_LAYER_COUNT:
        raise ValueError("scene_layer_count_exceeded")
    if object_count > SCENE_MAX_OBJECT_COUNT:
        raise ValueError("scene_object_count_exceeded")
    if text_budget > SCENE_MAX_TEXT_BUDGET:
        raise ValueError("scene_text_budget_exceeded")
    if selected_layer_id not in layer_ids:
        raise ValueError("scene_selected_layer_missing")
    if any(item not in layer_ids for item in collapsed_layer_ids):
        raise ValueError("scene_collapsed_layer_missing")


def build_scene_profile(
    *,
    scene_name: str,
    scene_summary: str,
    scene_layers: list[SceneLayerStateRecord],
    selected_layer_id: str,
) -> SceneProfileRecord:
    selected, path = _find_committed_layer(scene_layers, selected_layer_id)
    tags = [
        item.strip()
        for item in selected.tags.replace("，", ",").split(",")
        if item.strip()
    ]
    return SceneProfileRecord(
        scene_name=scene_name,
        scene_id=selected.id,
        title=selected.title,
        summary=scene_summary,
        tags=list(dict.fromkeys(tags)),
        selected_path=path,
        focus_object_names=[obj.name for obj in selected.objects[:4]],
        scene_tree=[layer.model_copy(deep=True) for layer in scene_layers],
    )


def _proposal_tree_metrics(
    layers: list[SceneLayerProposalV1],
) -> tuple[int, int, int]:
    layer_count = 0
    object_count = 0
    text_budget = 0

    def visit(layer: SceneLayerProposalV1, depth: int) -> None:
        nonlocal layer_count, object_count, text_budget
        if depth > SCENE_MAX_DEPTH:
            raise ValueError("scene_depth_exceeded")
        layer_count += 1
        object_count += len(layer.objects)
        text_budget += sum(
            len(value)
            for value in (
                layer.title,
                layer.scope_label,
                layer.summary,
                layer.atmosphere,
                layer.rules,
                layer.entrance,
                layer.reuse_hint,
            )
        ) + sum(len(tag) for tag in layer.tags)
        for obj in layer.objects:
            text_budget += sum(
                len(value)
                for value in (
                    obj.name,
                    obj.description,
                    obj.interaction,
                    obj.reuse_hint,
                )
            ) + sum(len(tag) for tag in obj.tags)
        for child in layer.children:
            visit(child, depth + 1)

    for root in layers:
        visit(root, 1)
    return layer_count, object_count, text_budget


def _resolve_proposal_path(
    layers: list[SceneLayerProposalV1],
    path: list[int],
) -> SceneLayerProposalV1:
    current = layers
    selected: SceneLayerProposalV1 | None = None
    for part in path:
        if part < 0 or part >= len(current):
            raise ValueError("scene_selected_path_invalid")
        selected = current[part]
        current = selected.children
    if selected is None:
        raise ValueError("scene_selected_path_required")
    return selected


def _resolve_committed_path(
    layers: list[SceneLayerStateRecord],
    path: list[int],
) -> SceneLayerStateRecord:
    current = layers
    selected: SceneLayerStateRecord | None = None
    for part in path:
        selected = current[part]
        current = selected.children
    if selected is None:
        raise ValueError("scene_selected_path_required")
    return selected


def _find_committed_layer(
    layers: list[SceneLayerStateRecord],
    selected_layer_id: str,
) -> tuple[SceneLayerStateRecord, list[str]]:
    def visit(
        layer: SceneLayerStateRecord,
        path: list[str],
    ) -> tuple[SceneLayerStateRecord, list[str]] | None:
        next_path = [*path, layer.title]
        if layer.id == selected_layer_id:
            return layer, next_path
        for child in layer.children:
            found = visit(child, next_path)
            if found is not None:
                return found
        return None

    for root in layers:
        found = visit(root, [])
        if found is not None:
            return found
    raise ValueError("scene_selected_layer_missing")


def _resolve_reusable_node(
    reference: str | None,
    allowed: dict[str, ReusableSceneNodeRecord],
    *,
    expected_type: Literal["layer", "object"],
) -> ReusableSceneNodeRecord | None:
    if reference is None:
        return None
    node = allowed.get(reference)
    if node is None:
        raise ValueError("scene_reusable_node_ref_not_allowed")
    if node.node_type != expected_type:
        raise ValueError("scene_reusable_node_ref_type_mismatch")
    return node


SceneLayerProposalV1.model_rebuild()
SceneLayerCommittedInputV1.model_rebuild()
