from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.clock import utc_now_iso
from app.models.domain import RuntimeSettingsRecord
from app.persistence.database import Database
from app.persistence.models import RuntimeSettingsRow

Payload = dict[str, Any]
_CONFIG_ID = "default"


class RuntimeSettingsRepository:
    """A single authoritative DB row, including its monotonically increasing revision."""

    def __init__(self, database: Database) -> None:
        self._database = database

    def read(self) -> RuntimeSettingsRecord:
        with self._database.session() as session:
            row = session.get(RuntimeSettingsRow, _CONFIG_ID)
            if row is None:
                raise RuntimeError("runtime_settings_not_initialized")
            return RuntimeSettingsRecord.model_validate(row.payload)

    def initialize(self, build: Callable[[Payload | None], Payload | None]) -> None:
        self._mutate(build, return_existing=False)

    def patch(self, updates: Payload) -> RuntimeSettingsRecord:
        def merge(current: Payload | None) -> Payload | None:
            if current is None:
                raise RuntimeError("runtime_settings_not_initialized")
            record = RuntimeSettingsRecord.model_validate(current)
            next_payload = record.model_dump() | updates
            return None if next_payload == current else next_payload

        record = self._mutate(merge)
        if record is None:
            raise RuntimeError("runtime_settings_not_initialized")
        return record

    def _mutate(
        self,
        build: Callable[[Payload | None], Payload | None],
        *,
        return_existing: bool = True,
    ) -> RuntimeSettingsRecord | None:
        dialect = self._database.engine.dialect.name
        with self._database.session() as session:
            if dialect == "sqlite":
                # Acquire the database writer lock *before* selecting. SQLite's
                # SELECT has no FOR UPDATE; a structured no-op UPDATE keeps the
                # lock in the managed transaction even if the singleton is absent.
                session.execute(
                    update(RuntimeSettingsRow)
                    .where(RuntimeSettingsRow.config_id == _CONFIG_ID)
                    .values(updated_at=RuntimeSettingsRow.updated_at)
                )
            row = session.get(RuntimeSettingsRow, _CONFIG_ID, with_for_update=True)
            if row is not None:
                return self._update_locked(row, build, return_existing=return_existing)

            payload = build(None)
            if payload is None:
                return None
            record = self._commit_candidate(payload, revision=1)
            if dialect == "postgresql":
                receipt = session.execute(
                    pg_insert(RuntimeSettingsRow)
                    .values(**self._row_values(record))
                    .on_conflict_do_nothing(
                        index_elements=[RuntimeSettingsRow.config_id]
                    )
                )
                if receipt.rowcount == 0:
                    # A concurrent initializer inserted before us. At READ
                    # COMMITTED this new statement sees and locks the winner.
                    row = session.get(
                        RuntimeSettingsRow, _CONFIG_ID, with_for_update=True
                    )
                    if row is None:
                        raise RuntimeError("runtime_settings_initialization_conflict")
                    return self._update_locked(
                        row, build, return_existing=return_existing
                    )
            else:
                session.add(RuntimeSettingsRow(**self._row_values(record)))
            return record

    def _update_locked(
        self,
        row: RuntimeSettingsRow,
        build: Callable[[Payload | None], Payload | None],
        *,
        return_existing: bool,
    ) -> RuntimeSettingsRecord | None:
        current = row.payload
        if not isinstance(current, dict):
            raise ValueError("invalid_runtime_settings_record")
        payload = build(current)
        if payload is None:
            return (
                RuntimeSettingsRecord.model_validate(current)
                if return_existing
                else None
            )
        revision = (
            RuntimeSettingsRecord.model_validate(current).revision
            if "revision" in current
            else 0
        )
        record = self._commit_candidate(payload, revision=revision + 1)
        row.updated_at = record.updated_at
        row.plan_provider = record.plan_provider
        row.payload = record.model_dump(mode="json")
        return record

    @staticmethod
    def _commit_candidate(payload: Payload, *, revision: int) -> RuntimeSettingsRecord:
        return RuntimeSettingsRecord.model_validate(
            payload | {"revision": revision, "updated_at": utc_now_iso()}
        )

    @staticmethod
    def _row_values(record: RuntimeSettingsRecord) -> Payload:
        return {
            "config_id": record.config_id,
            "updated_at": record.updated_at,
            "plan_provider": record.plan_provider,
            "payload": record.model_dump(mode="json"),
        }
