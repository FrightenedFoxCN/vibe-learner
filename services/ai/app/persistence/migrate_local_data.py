from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.settings import Settings
from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    LearningPlanRecord,
    ModelToolConfigRecord,
    PersonaCardRecord,
    PersonaProfile,
    PlanGenerationTraceRecord,
    RuntimeSettingsRecord,
    SceneLibraryRecord,
    SceneSetupStateRecord,
    SessionSceneRecord,
    StreamReportRecord,
    StudySessionRecord,
    ReusableSceneNodeRecord,
    TokenUsageRecord,
)
from app.persistence.database import Database
from app.persistence.storage import StorageManager
from app.services.local_store import LegacyLocalJsonStore, LocalJsonStore
from app.services.token_usage import TokenUsageService


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate legacy local JSON data into the primary database.")
    parser.add_argument("--source-root", default="", help="Legacy JSON data root. Defaults to services/ai/data.")
    parser.add_argument("--database-url", default="", help="Target database URL. Defaults to DATABASE_URL.")
    args = parser.parse_args()

    settings = Settings.from_env()
    source_root = Path(args.source_root).expanduser() if args.source_root else Path(__file__).resolve().parents[2] / "data"
    database_url = args.database_url.strip() or settings.database_url
    storage_root = Path(settings.storage_root).expanduser() if settings.storage_root else (
        Path(__file__).resolve().parents[2] / "data"
    )

    legacy = LegacyLocalJsonStore(source_root)
    db = Database(database_url)
    db.create_schema()
    store = LocalJsonStore(db, StorageManager(storage_root))
    token_usage_service = TokenUsageService(db)
    migrate_from_legacy_store(legacy, store, token_usage_service, source_root)
    print(f"migrated legacy data from {source_root} into {database_url}")

def migrate_from_legacy_store(
    legacy: LegacyLocalJsonStore,
    store: LocalJsonStore,
    token_usage_service: TokenUsageService,
    source_root: Path,
) -> None:
    for list_name, model in (
        ("documents", DocumentRecord),
        ("plans", LearningPlanRecord),
        ("sessions", StudySessionRecord),
    ):
        items = legacy.load_list(list_name, model)
        if items:
            store.save_list(list_name, items)

    for category, model in (
        ("document_debug", DocumentDebugRecord),
        ("planning_trace", PlanGenerationTraceRecord),
        ("runtime_settings", RuntimeSettingsRecord),
        ("model_tool_config", ModelToolConfigRecord),
        ("scene_setup", SceneSetupStateRecord),
        ("scene_library", SceneLibraryRecord),
        ("reusable_scene_nodes", ReusableSceneNodeRecord),
        ("session_scenes", SessionSceneRecord),
        ("personas", PersonaProfile),
        ("persona_cards", PersonaCardRecord),
        ("document_process_stream", StreamReportRecord),
        ("learning_plan_stream", StreamReportRecord),
    ):
        for item in legacy.load_category_items(category, model):
            item_id = _item_id_for_category(category, item)
            if item_id:
                store.save_item(category, item_id, item)

    token_usage_path = source_root / "token_usage.jsonl"
    if token_usage_path.exists():
        for raw_line in token_usage_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = TokenUsageRecord.model_validate(json.loads(line))
            except Exception:
                continue
            token_usage_service.record_entry(record)


def _item_id_for_category(category: str, item: object) -> str:
    if category in {"document_debug", "planning_trace", "document_process_stream", "learning_plan_stream"}:
        return str(getattr(item, "document_id", ""))
    if category in {"runtime_settings", "model_tool_config", "scene_setup"}:
        return str(getattr(item, "config_id", "default"))
    if category == "scene_library":
        return str(getattr(item, "scene_id", ""))
    if category == "reusable_scene_nodes":
        return str(getattr(item, "node_id", ""))
    if category == "session_scenes":
        return str(getattr(item, "scene_instance_id", ""))
    return str(getattr(item, "id", ""))


if __name__ == "__main__":
    main()
