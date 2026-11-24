from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.runtime_settings_validation import repair_legacy_runtime_numbers
from app.core.settings import Settings
from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    LearningPlanRecord,
    ModelToolConfigRecord,
    PersonaCardRecord,
    PersonaProfile,
    PlanGenerationTraceRecord,
    SceneLibraryRecord,
    SceneSetupStateRecord,
    SessionSceneRecord,
    StudySessionRecord,
    ReusableSceneNodeRecord,
    TokenUsageRecord,
)
from app.models.stream import StreamReportRecord
from app.persistence.database import Database
from app.persistence.document_repository import DocumentRepository, document_from_row
from app.persistence.models import DocumentDebugRow, DocumentRow, StudySessionRow
from app.persistence.runtime_settings_repository import RuntimeSettingsRepository
from app.persistence.storage import StorageManager
from app.persistence.study_session_repository import StudySessionRepository
from app.services.local_store import LegacyLocalJsonStore, LocalJsonStore
from app.services.token_usage import TokenUsageService

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy local JSON data into the primary database."
    )
    parser.add_argument(
        "--source-root",
        default="",
        help="Legacy JSON data root. Defaults to services/ai/data.",
    )
    parser.add_argument(
        "--database-url",
        default="",
        help="Target database URL. Defaults to DATABASE_URL.",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    source_root = (
        Path(args.source_root).expanduser()
        if args.source_root
        else Path(__file__).resolve().parents[2] / "data"
    )
    database_url = args.database_url.strip() or settings.database_url
    storage_root = (
        Path(settings.storage_root).expanduser()
        if settings.storage_root
        else (Path(__file__).resolve().parents[2] / "data")
    )

    legacy = LegacyLocalJsonStore(source_root)
    db = Database(database_url)
    db.create_schema()
    store = LocalJsonStore(db, StorageManager(storage_root))
    token_usage_service = TokenUsageService(db)
    migrate_from_legacy_store(legacy, store, token_usage_service, source_root)
    print(f"migrated legacy data from {source_root} into {database_url}")


def migrate_desktop_legacy_aggregates(
    legacy: LegacyLocalJsonStore, database: Database
) -> None:
    """Preserve empty-table upgrades for existing desktop JSON installations."""
    if (legacy.root / "documents.json").is_file():
        with database.session() as session:
            documents_empty = session.scalar(select(DocumentRow.id).limit(1)) is None
            missing_debug = set(
                session.scalars(
                    select(DocumentRow.id)
                    .outerjoin(
                        DocumentDebugRow, DocumentDebugRow.document_id == DocumentRow.id
                    )
                    .where(
                        DocumentRow.status == "processed",
                        DocumentDebugRow.document_id.is_(None),
                    )
                )
            )
        if documents_empty or missing_debug:
            documents = legacy.load_list("documents", DocumentRecord)
            if documents_empty:
                DocumentRepository(database).import_legacy(documents)
            for document in documents:
                if document.debug_ready and (
                    documents_empty or document.id in missing_debug
                ):
                    _import_paired_document_debug(legacy, database, document)
    if (legacy.root / "sessions.json").is_file():
        with database.session() as session:
            sessions_empty = session.scalar(select(StudySessionRow.id).limit(1)) is None
        if sessions_empty:
            StudySessionRepository(database).import_legacy(
                legacy.load_list("sessions", StudySessionRecord)
            )


def _import_paired_document_debug(
    legacy: LegacyLocalJsonStore, database: Database, document: DocumentRecord
) -> None:
    """Import a missing debug projection only against the same document snapshot."""
    try:
        debug = legacy.load_item("document_debug", document.id, DocumentDebugRecord)
        if debug is None:
            return
        if not (
            debug.document_id == document.id
            and document.status == "processed"
            and datetime.fromisoformat(document.created_at)
            <= datetime.fromisoformat(debug.processed_at)
            <= datetime.fromisoformat(document.updated_at)
            and debug.page_count == document.page_count
            and len(debug.chunks) == document.chunk_count
            and debug.ocr_status == document.ocr_status
            and debug.study_units == document.study_units
            and all(chunk.document_id == document.id for chunk in debug.chunks)
        ):
            logger.warning(
                "legacy.document_debug.projection_mismatch id=%s", document.id
            )
            return
    except (OSError, ValueError, TypeError):
        logger.warning("legacy.document_debug.unreadable id=%s", document.id)
        return
    try:
        with database.session() as session, session.begin_nested():
            # The database savepoint hook opens a real SQLite transaction
            # before this read. PostgreSQL also locks the parent row.
            row = session.get(DocumentRow, document.id, with_for_update=True)
            if row is None or document_from_row(row) != document:
                logger.warning(
                    "legacy.document_debug.document_changed id=%s", document.id
                )
                return
            if session.get(DocumentDebugRow, document.id) is None:
                session.add(
                    DocumentDebugRow(
                        document_id=document.id,
                        processed_at=debug.processed_at,
                        page_count=debug.page_count,
                        extraction_method=debug.extraction_method,
                        payload=debug.model_dump(mode="json"),
                    )
                )
    except IntegrityError:
        # A competing writer that filled the same projection wins. Do not upsert.
        with database.session() as session:
            if session.get(DocumentDebugRow, document.id) is None:
                raise
    except OperationalError as exc:
        if (
            database.engine.dialect.name != "sqlite"
            or "locked" not in str(exc.orig).lower()
        ):
            raise
        logger.warning("legacy.document_debug.concurrent_write id=%s", document.id)


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

    def import_runtime_settings(current):
        if current is not None:
            return None
        runtime_payload = legacy.load_runtime_settings_payload()
        if runtime_payload is None:
            return None
        return repair_legacy_runtime_numbers(runtime_payload)

    RuntimeSettingsRepository(store.database).initialize(import_runtime_settings)

    for category, model in (
        ("document_debug", DocumentDebugRecord),
        ("planning_trace", PlanGenerationTraceRecord),
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
    if category in {
        "document_debug",
        "planning_trace",
        "document_process_stream",
        "learning_plan_stream",
    }:
        return str(getattr(item, "document_id", ""))
    if category in {"model_tool_config", "scene_setup"}:
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
