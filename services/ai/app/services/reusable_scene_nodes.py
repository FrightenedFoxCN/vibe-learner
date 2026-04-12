from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models.api import CreateReusableSceneNodeRequest
from app.models.domain import ReusableSceneNodeRecord
from app.services.local_store import LocalJsonStore


class ReusableSceneNodeLibraryService:
    def __init__(self, store: LocalJsonStore) -> None:
        self._store = store

    def list_nodes(self) -> list[ReusableSceneNodeRecord]:
        items = self._store.load_category_items("reusable_scene_nodes", ReusableSceneNodeRecord)
        return sorted(items, key=lambda item: (item.updated_at, item.created_at), reverse=True)

    def require_node(self, node_id: str) -> ReusableSceneNodeRecord:
        item = self._store.load_item("reusable_scene_nodes", node_id, ReusableSceneNodeRecord)
        if item is None:
            raise HTTPException(status_code=404, detail="reusable_scene_node_not_found")
        return item

    def create_node(self, payload: CreateReusableSceneNodeRequest) -> ReusableSceneNodeRecord:
        if payload.node_type not in {"layer", "object"}:
            raise HTTPException(status_code=400, detail="invalid_reusable_scene_node_type")
        if payload.node_type == "layer" and payload.layer_node is None:
            raise HTTPException(status_code=400, detail="missing_reusable_layer_node")
        if payload.node_type == "object" and payload.object_node is None:
            raise HTTPException(status_code=400, detail="missing_reusable_object_node")

        node_id = f"scene-node-{uuid4().hex[:10]}"
        record = ReusableSceneNodeRecord(
            node_id=node_id,
            node_type=payload.node_type,
            title=payload.title.strip(),
            summary=payload.summary.strip(),
            tags=[tag.strip() for tag in payload.tags if tag.strip()],
            reuse_id=payload.reuse_id.strip(),
            reuse_hint=payload.reuse_hint.strip(),
            source_scene_id=payload.source_scene_id.strip(),
            source_scene_name=payload.source_scene_name.strip(),
            layer_node=payload.layer_node,
            object_node=payload.object_node,
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        self._store.save_item("reusable_scene_nodes", node_id, record)
        return record

    def delete_node(self, node_id: str) -> None:
        self.require_node(node_id)
        self._store.delete_item("reusable_scene_nodes", node_id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
