from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Select, select

from app.persistence.database import Database
from app.persistence.models import (
    DocumentDebugRow,
    DocumentRow,
    LearningPlanRow,
    ModelToolConfigRow,
    PersonaCardRow,
    PersonaRow,
    PlanningTraceRow,
    ReusableSceneNodeRow,
    RuntimeSettingsRow,
    SceneLibraryRow,
    SceneSetupRow,
    SessionSceneRow,
    StreamReportRow,
    StudySessionRow,
)
from app.persistence.storage import StorageManager

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class _RepoSpec:
    entity: type[Any]
    key_attr: str
    order_by: tuple[str, ...]
    metadata_builder: Callable[[dict[str, Any]], dict[str, Any]]


def _document_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "original_filename": str(payload.get("original_filename") or ""),
        "stored_path": str(payload.get("stored_path") or ""),
        "status": str(payload.get("status") or ""),
        "ocr_status": str(payload.get("ocr_status") or ""),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _plan_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "document_id": str(payload.get("document_id") or ""),
        "persona_id": str(payload.get("persona_id") or ""),
        "creation_mode": str(payload.get("creation_mode") or "document"),
        "course_title": str(payload.get("course_title") or ""),
        "created_at": str(payload.get("created_at") or ""),
    }


def _session_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "document_id": str(payload.get("document_id") or ""),
        "persona_id": str(payload.get("persona_id") or ""),
        "plan_id": str(payload.get("plan_id") or ""),
        "study_unit_id": str(payload.get("study_unit_id") or payload.get("section_id") or ""),
        "status": str(payload.get("status") or ""),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _document_debug_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "document_id": str(payload.get("document_id") or ""),
        "processed_at": str(payload.get("processed_at") or ""),
        "page_count": int(payload.get("page_count") or 0),
        "extraction_method": str(payload.get("extraction_method") or ""),
    }


def _planning_trace_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    plan_id = payload.get("plan_id")
    return {
        "document_id": str(payload.get("document_id") or ""),
        "plan_id": str(plan_id or ""),
        "model": str(payload.get("model") or ""),
        "created_at": str(payload.get("created_at") or ""),
    }


def _runtime_settings_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "config_id": str(payload.get("config_id") or "default"),
        "updated_at": str(payload.get("updated_at") or ""),
        "plan_provider": str(payload.get("plan_provider") or "mock"),
    }


def _model_tool_config_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "config_id": str(payload.get("config_id") or "default"),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _scene_setup_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "config_id": str(payload.get("config_id") or "default"),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _scene_library_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "scene_id": str(payload.get("scene_id") or ""),
        "scene_name": str(payload.get("scene_name") or ""),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _reusable_scene_node_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "node_id": str(payload.get("node_id") or ""),
        "node_type": str(payload.get("node_type") or ""),
        "title": str(payload.get("title") or ""),
        "source_scene_id": str(payload.get("source_scene_id") or ""),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _session_scene_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "scene_instance_id": str(payload.get("scene_instance_id") or ""),
        "session_id": str(payload.get("session_id") or ""),
        "document_id": str(payload.get("document_id") or ""),
        "persona_id": str(payload.get("persona_id") or ""),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or payload.get("created_at") or ""),
    }


def _persona_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("name") or ""),
        "source": str(payload.get("source") or "user"),
    }


def _persona_card_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "kind": str(payload.get("kind") or "custom"),
        "source": str(payload.get("source") or "manual"),
        "updated_at": str(payload.get("updated_at") or ""),
    }


def _stream_report_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "stream_kind": str(payload.get("stream_kind") or ""),
        "status": str(payload.get("status") or "idle"),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
    }


LIST_SPECS: dict[str, _RepoSpec] = {
    "documents": _RepoSpec(DocumentRow, "id", ("created_at", "id"), _document_metadata),
    "plans": _RepoSpec(LearningPlanRow, "id", ("created_at", "id"), _plan_metadata),
    "sessions": _RepoSpec(StudySessionRow, "id", ("created_at", "id"), _session_metadata),
}

CATEGORY_SPECS: dict[str, _RepoSpec] = {
    "document_debug": _RepoSpec(
        DocumentDebugRow,
        "document_id",
        ("processed_at", "document_id"),
        _document_debug_metadata,
    ),
    "planning_trace": _RepoSpec(
        PlanningTraceRow,
        "document_id",
        ("created_at", "document_id"),
        _planning_trace_metadata,
    ),
    "runtime_settings": _RepoSpec(
        RuntimeSettingsRow,
        "config_id",
        ("updated_at", "config_id"),
        _runtime_settings_metadata,
    ),
    "model_tool_config": _RepoSpec(
        ModelToolConfigRow,
        "config_id",
        ("updated_at", "config_id"),
        _model_tool_config_metadata,
    ),
    "scene_setup": _RepoSpec(
        SceneSetupRow,
        "config_id",
        ("updated_at", "config_id"),
        _scene_setup_metadata,
    ),
    "scene_library": _RepoSpec(
        SceneLibraryRow,
        "scene_id",
        ("updated_at", "scene_id"),
        _scene_library_metadata,
    ),
    "reusable_scene_nodes": _RepoSpec(
        ReusableSceneNodeRow,
        "node_id",
        ("updated_at", "node_id"),
        _reusable_scene_node_metadata,
    ),
    "session_scenes": _RepoSpec(
        SessionSceneRow,
        "scene_instance_id",
        ("updated_at", "scene_instance_id"),
        _session_scene_metadata,
    ),
    "personas": _RepoSpec(PersonaRow, "id", ("name", "id"), _persona_metadata),
    "persona_cards": _RepoSpec(
        PersonaCardRow,
        "id",
        ("updated_at", "id"),
        _persona_card_metadata,
    ),
}

STREAM_CATEGORIES = {"document_process_stream", "learning_plan_stream"}


class LocalJsonStore:
    """Compatibility wrapper that now persists aggregate records through PostgreSQL."""

    def __init__(self, db: Database | Path, storage: StorageManager | None = None) -> None:
        if isinstance(db, Path):
            storage = StorageManager(db)
            db = Database(f"sqlite:///{db / 'vibe_learner.db'}")
            db.create_schema()
        if storage is None:
            raise ValueError("storage_manager_required")
        self._db = db
        self._storage = storage
        self._legacy = LegacyLocalJsonStore(storage.root)
        self.storage = storage
        self.root = storage.root
        self.upload_root = storage.upload_root
        self.chat_attachment_root = storage.chat_attachment_root
        self.runtime_temp_root = storage.runtime_temp_root

    def close(self) -> None:
        self._db.dispose()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def load_list(self, name: str, model: type[T]) -> list[T]:
        spec = LIST_SPECS[name]
        with self._db.session() as session:
            rows = session.scalars(self._ordered_select(spec)).all()
            if rows:
                return [model.model_validate(row.payload or {}) for row in rows]
        legacy_items = self._legacy.load_list(name, model)
        if legacy_items:
            self.save_list(name, legacy_items)
        return legacy_items

    def save_list(self, name: str, items: list[BaseModel]) -> None:
        spec = LIST_SPECS[name]
        serialized = [item.model_dump(mode="json") for item in items]
        incoming_keys = {
            str(spec.metadata_builder(payload)[spec.key_attr])
            for payload in serialized
        }
        with self._db.session() as session:
            existing_rows = {
                str(getattr(row, spec.key_attr)): row
                for row in session.scalars(select(spec.entity)).all()
            }
            for payload in serialized:
                key = str(spec.metadata_builder(payload)[spec.key_attr])
                row = existing_rows.get(key) or spec.entity()
                self._apply_payload(row, payload, spec)
                session.add(row)
            for key, row in existing_rows.items():
                if key not in incoming_keys:
                    session.delete(row)
        self._legacy.save_list(name, items)

    def load_item(self, category: str, item_id: str, model: type[T]) -> T | None:
        if category in STREAM_CATEGORIES:
            item = self._load_stream_item(category, item_id, model)
            if item is not None:
                return item
            legacy_item = self._legacy.load_item(category, item_id, model)
            if legacy_item is not None:
                self.save_item(category, item_id, legacy_item)
            return legacy_item
        spec = CATEGORY_SPECS[category]
        with self._db.session() as session:
            row = session.get(spec.entity, item_id)
            if row is None:
                legacy_item = self._legacy.load_item(category, item_id, model)
                if legacy_item is not None:
                    self.save_item(category, item_id, legacy_item)
                return legacy_item
            return model.model_validate(row.payload or {})

    def save_item(self, category: str, item_id: str, item: BaseModel) -> None:
        payload = item.model_dump(mode="json")
        if category in STREAM_CATEGORIES:
            self._save_stream_item(category, item_id, payload)
            self._legacy.save_item(category, item_id, item)
            return
        spec = CATEGORY_SPECS[category]
        with self._db.session() as session:
            row = session.get(spec.entity, item_id) or spec.entity()
            self._apply_payload(row, payload, spec)
            session.add(row)
        self._legacy.save_item(category, item_id, item)

    def load_category_items(self, category: str, model: type[T]) -> list[T]:
        if category in STREAM_CATEGORIES:
            with self._db.session() as session:
                rows = session.scalars(
                    select(StreamReportRow)
                    .where(StreamReportRow.category == category)
                    .order_by(StreamReportRow.updated_at, StreamReportRow.document_id)
                ).all()
                if rows:
                    return [model.model_validate(row.payload or {}) for row in rows]
            legacy_items = self._legacy.load_category_items(category, model)
            for item in legacy_items:
                self.save_item(category, str(getattr(item, "document_id", "")), item)
            return legacy_items
        spec = CATEGORY_SPECS[category]
        with self._db.session() as session:
            rows = session.scalars(self._ordered_select(spec)).all()
            if rows:
                return [model.model_validate(row.payload or {}) for row in rows]
        legacy_items = self._legacy.load_category_items(category, model)
        for item in legacy_items:
            item_id = str(getattr(item, spec.key_attr, ""))
            if item_id:
                self.save_item(category, item_id, item)
        return legacy_items

    def delete_item(self, category: str, item_id: str) -> None:
        if category in STREAM_CATEGORIES:
            with self._db.session() as session:
                row = session.get(StreamReportRow, self._stream_record_id(category, item_id))
                if row is not None:
                    session.delete(row)
            self._legacy.delete_item(category, item_id)
            return
        spec = CATEGORY_SPECS[category]
        with self._db.session() as session:
            row = session.get(spec.entity, item_id)
            if row is not None:
                session.delete(row)
        self._legacy.delete_item(category, item_id)

    def count_bucket(self, bucket: str) -> int:
        if bucket in LIST_SPECS:
            spec = LIST_SPECS[bucket]
            with self._db.session() as session:
                return len(session.scalars(select(spec.entity)).all())
        if bucket in STREAM_CATEGORIES:
            with self._db.session() as session:
                return len(
                    session.scalars(select(StreamReportRow).where(StreamReportRow.category == bucket)).all()
                )
        spec = CATEGORY_SPECS[bucket]
        with self._db.session() as session:
            return len(session.scalars(select(spec.entity)).all())

    def clear_bucket(self, bucket: str, *, item_id: str | None = None) -> int:
        removed = 0
        if bucket in LIST_SPECS:
            spec = LIST_SPECS[bucket]
            with self._db.session() as session:
                rows = session.scalars(select(spec.entity)).all()
                for row in rows:
                    if item_id is not None and str(getattr(row, spec.key_attr)) != item_id:
                        continue
                    session.delete(row)
                    removed += 1
            self._legacy.clear_bucket(bucket, item_id=item_id)
            return removed
        if bucket in STREAM_CATEGORIES:
            with self._db.session() as session:
                query = select(StreamReportRow).where(StreamReportRow.category == bucket)
                if item_id is not None:
                    query = query.where(StreamReportRow.document_id == item_id)
                rows = session.scalars(query).all()
                for row in rows:
                    session.delete(row)
                    removed += 1
            self._legacy.clear_bucket(bucket, item_id=item_id)
            return removed
        spec = CATEGORY_SPECS[bucket]
        with self._db.session() as session:
            query = select(spec.entity)
            if item_id is not None:
                query = query.where(getattr(spec.entity, spec.key_attr) == item_id)
            rows = session.scalars(query).all()
            for row in rows:
                session.delete(row)
                removed += 1
        self._legacy.clear_bucket(bucket, item_id=item_id)
        return removed

    def _load_stream_item(self, category: str, item_id: str, model: type[T]) -> T | None:
        record_id = self._stream_record_id(category, item_id)
        with self._db.session() as session:
            row = session.get(StreamReportRow, record_id)
            if row is None:
                return None
            return model.model_validate(row.payload or {})

    def _save_stream_item(self, category: str, item_id: str, payload: dict[str, Any]) -> None:
        record_id = self._stream_record_id(category, item_id)
        with self._db.session() as session:
            row = session.get(StreamReportRow, record_id) or StreamReportRow()
            row.record_id = record_id
            row.category = category
            row.document_id = item_id
            row.payload = payload
            for key, value in _stream_report_metadata(payload).items():
                setattr(row, key, value)
            session.add(row)

    def _ordered_select(self, spec: _RepoSpec) -> Select[Any]:
        return select(spec.entity).order_by(
            *(getattr(spec.entity, attr_name) for attr_name in spec.order_by)
        )

    def _apply_payload(self, row: Any, payload: dict[str, Any], spec: _RepoSpec) -> None:
        row.payload = payload
        for key, value in spec.metadata_builder(payload).items():
            setattr(row, key, value)

    @staticmethod
    def _stream_record_id(category: str, item_id: str) -> str:
        return f"{category}:{item_id}"


class LegacyLocalJsonStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.upload_root = self.root / "uploads"
        self.root.mkdir(parents=True, exist_ok=True)
        self.upload_root.mkdir(parents=True, exist_ok=True)

    def load_list(self, name: str, model: type[T]) -> list[T]:
        path = self.root / f"{name}.json"
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [model.model_validate(item) for item in payload]

    def save_list(self, name: str, items: list[BaseModel]) -> None:
        path = self.root / f"{name}.json"
        payload = [item.model_dump(mode="json") for item in items]
        self._write_json(path, payload)

    def load_item(self, category: str, item_id: str, model: type[T]) -> T | None:
        path = self.root / category / f"{item_id}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(payload)

    def save_item(self, category: str, item_id: str, item: BaseModel) -> None:
        category_root = self.root / category
        category_root.mkdir(parents=True, exist_ok=True)
        path = category_root / f"{item_id}.json"
        self._write_json(path, item.model_dump(mode="json"))

    def load_category_items(self, category: str, model: type[T]) -> list[T]:
        category_root = self.root / category
        if not category_root.exists():
            return []
        items: list[T] = []
        for path in sorted(category_root.glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            items.append(model.model_validate(payload))
        return items

    def delete_item(self, category: str, item_id: str) -> None:
        path = self.root / category / f"{item_id}.json"
        if path.exists():
            path.unlink()

    def clear_bucket(self, bucket: str, *, item_id: str | None = None) -> int:
        removed = 0
        if bucket in LIST_SPECS:
            path = self.root / f"{bucket}.json"
            if not path.exists():
                return 0
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                return 0
            if item_id is None:
                removed = len(payload)
                self._write_json(path, [])
                return removed
            spec = LIST_SPECS[bucket]
            filtered = []
            for item in payload:
                key = ""
                if isinstance(item, dict):
                    key = str(spec.metadata_builder(item).get(spec.key_attr, ""))
                if key == item_id:
                    removed += 1
                    continue
                filtered.append(item)
            self._write_json(path, filtered)
            return removed

        category_root = self.root / bucket
        if not category_root.exists():
            return 0
        if item_id is not None:
            path = category_root / f"{item_id}.json"
            if path.exists():
                path.unlink()
                return 1
            return 0
        for path in category_root.glob("*.json"):
            path.unlink()
            removed += 1
        return removed

    def _write_json(self, path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(path)
