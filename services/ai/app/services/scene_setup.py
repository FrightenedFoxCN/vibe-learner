from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.models.domain import SceneSetupStateRecord
from app.models.scene import build_scene_profile, validate_committed_scene_tree
from app.services.local_store import LocalJsonStore, LocalStoreRevisionConflict


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
        expected_revision: int,
    ) -> SceneSetupStateRecord:
        self.get_state()
        validate_committed_scene_tree(
            scene_name=scene_name,
            scene_summary=scene_summary,
            scene_layers=scene_layers,
            selected_layer_id=selected_layer_id,
            collapsed_layer_ids=collapsed_layer_ids,
        )
        profile = build_scene_profile(
            scene_name=scene_name,
            scene_summary=scene_summary,
            scene_layers=scene_layers,
            selected_layer_id=selected_layer_id,
        )
        record = SceneSetupStateRecord(
            config_id="default",
            revision=expected_revision + 1,
            updated_at=_now_iso(),
            scene_name=scene_name,
            scene_summary=scene_summary,
            scene_layers=scene_layers,
            selected_layer_id=selected_layer_id,
            collapsed_layer_ids=collapsed_layer_ids,
            scene_profile=profile,
        )
        try:
            return self._store.save_item_cas(
                "scene_setup",
                "default",
                record,
                expected_revision=expected_revision,
                model=SceneSetupStateRecord,
            )
        except LocalStoreRevisionConflict as exc:
            raise HTTPException(status_code=409, detail="scene_revision_conflict") from exc


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
