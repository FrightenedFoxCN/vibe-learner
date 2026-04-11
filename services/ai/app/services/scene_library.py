from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import SceneLibraryRecord
from app.services.local_store import LocalJsonStore


class SceneLibraryService:
    def __init__(self, store: LocalJsonStore) -> None:
        self._store = store

    def list_scenes(self) -> list[SceneLibraryRecord]:
        scenes = self._store.load_category_items("scene_library", SceneLibraryRecord)
        scenes = [self._migrate_scene_summary(scene) for scene in scenes]
        return sorted(scenes, key=lambda item: (item.updated_at, item.created_at), reverse=True)

    def require_scene(self, scene_id: str) -> SceneLibraryRecord:
        scene = self._store.load_item("scene_library", scene_id, SceneLibraryRecord)
        if scene is None:
            raise HTTPException(status_code=404, detail="scene_not_found")
        return self._migrate_scene_summary(scene)

    def upsert_scene(
        self,
        *,
        scene_id: str | None,
        scene_name: str,
        scene_summary: str,
        scene_layers,
        selected_layer_id: str,
        collapsed_layer_ids: list[str],
        scene_profile,
    ) -> SceneLibraryRecord:
        target_scene_id = scene_id or f"scene-{uuid4().hex[:10]}"
        existing = self._store.load_item("scene_library", target_scene_id, SceneLibraryRecord)
        normalized_profile = None
        if scene_profile is not None:
            normalized_profile = scene_profile.model_copy(
                update={
                    "scene_name": scene_name,
                    "summary": scene_summary,
                }
            )
        record = SceneLibraryRecord(
            scene_id=target_scene_id,
            config_id=target_scene_id,
            created_at=existing.created_at if existing is not None else _now_iso(),
            updated_at=_now_iso(),
            scene_name=scene_name,
            scene_summary=scene_summary,
            scene_layers=scene_layers,
            selected_layer_id=selected_layer_id,
            collapsed_layer_ids=collapsed_layer_ids,
            scene_profile=normalized_profile,
        )
        self._store.save_item("scene_library", target_scene_id, record)
        return record

    def delete_scene(self, scene_id: str) -> None:
        if self._store.load_item("scene_library", scene_id, SceneLibraryRecord) is None:
            raise HTTPException(status_code=404, detail="scene_not_found")
        self._store.delete_item("scene_library", scene_id)

    def _migrate_scene_summary(self, scene: SceneLibraryRecord) -> SceneLibraryRecord:
        if scene.scene_summary.strip() or scene.scene_profile is None:
            return scene
        return scene.model_copy(update={"scene_summary": scene.scene_profile.summary})


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()