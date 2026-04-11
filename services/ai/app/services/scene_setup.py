from __future__ import annotations

from datetime import datetime, timezone

from app.models.domain import SceneSetupStateRecord
from app.services.local_store import LocalJsonStore


class SceneSetupService:
    def __init__(self, store: LocalJsonStore) -> None:
        self._store = store

    def get_state(self) -> SceneSetupStateRecord:
        existing = self._store.load_item("scene_setup", "default", SceneSetupStateRecord)
        if existing is not None:
            if not existing.scene_summary.strip() and existing.scene_profile is not None:
                return existing.model_copy(update={"scene_summary": existing.scene_profile.summary})
            return existing
        return SceneSetupStateRecord(updated_at=_now_iso())

    def upsert_state(
        self,
        *,
        scene_name: str,
        scene_summary: str,
        scene_layers,
        selected_layer_id: str,
        collapsed_layer_ids: list[str],
        scene_profile,
    ) -> SceneSetupStateRecord:
        normalized_profile = None
        if scene_profile is not None:
            normalized_profile = scene_profile.model_copy(
                update={
                    "scene_name": scene_name,
                    "summary": scene_summary,
                }
            )
        record = SceneSetupStateRecord(
            config_id="default",
            updated_at=_now_iso(),
            scene_name=scene_name,
            scene_summary=scene_summary,
            scene_layers=scene_layers,
            selected_layer_id=selected_layer_id,
            collapsed_layer_ids=collapsed_layer_ids,
            scene_profile=normalized_profile,
        )
        self._store.save_item("scene_setup", "default", record)
        return record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
