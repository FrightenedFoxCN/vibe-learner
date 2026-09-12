"""Restartable, content-free projection of canonical Harness executions.

The cursor performs bounded repeated primary-key sweeps. It deliberately does not
use updated_at as a commit watermark: concurrent commits can arrive out of order.
Only this disposable diagnostic database is written, never the domain database.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
import time

from app.models.diagnostic_index import DiagnosticHarnessIndexV1
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository


RESOURCE_ROLES = ("context_subjects", "attempted_outputs", "committed_outputs")


def diagnostic_index_resource_predicate(resource_id=None, resource_type=None, resource_role=None):
    """Match type and identity on one canonical reference, never across arrays."""
    if resource_role is not None and resource_role not in RESOURCE_ROLES:
        raise ValueError("diagnostic_index_resource_role_invalid")
    if all(value is None for value in (resource_id, resource_type, resource_role)):
        return "1", []
    clauses, params = [], []
    for role in (resource_role,) if resource_role else RESOURCE_ROLES:
        matches = []
        for field, value in (("resource_id", resource_id), ("resource_type", resource_type)):
            if value is not None:
                matches.append(f"json_extract(r.value, '$.{field}')=?")
                params.append(value)
        clauses.append(f"EXISTS (SELECT 1 FROM json_each(payload, '$.resources.{role}') r" +
                       (" WHERE " + " AND ".join(matches) if matches else "") + ")")
    return "(json_extract(payload, '$.resources_gap') IS NULL AND json_type(payload, '$.resources')='object' AND (" + " OR ".join(clauses) + "))", params


class DiagnosticHarnessIndex:
    def __init__(self, repository: HarnessRuntimeRepository, path: Path, *, retention=None):
        from app.core.diagnostic_record_retention import DiagnosticRecordRetention
        self.retention = retention or DiagnosticRecordRetention("projections")
        from app.core.diagnostic_disk import DiagnosticDiskMaintenance
        self.disk_maintenance = DiagnosticDiskMaintenance()
        self.repository = repository
        self.path = path
        from app.core.diagnostic_quota import DiagnosticDatabaseQuota
        self.quota = DiagnosticDatabaseQuota(path, max_bytes=64 * 1024 * 1024)
        self.disk_maintenance.quota = self.quota
        from app.core.diagnostic_recovery import DiagnosticOversizeRecovery
        self.oversize_recovery = DiagnosticOversizeRecovery(self.quota, self._prune_for_recovery, pressure_prune=self._prune_for_pressure)
        self.disk_maintenance.oversize_recovery = self.oversize_recovery
        self.failures = 0
        self._stop = threading.Event()
        self._thread = None

    def _prune_for_recovery(self, db):
        self.retention.initialize(db)

    def _prune_for_pressure(self, db):
        from app.core.diagnostic_record_retention import DiagnosticRecordRetention
        DiagnosticRecordRetention("projections", max_rows=min(self.retention.max_rows, max(1, self.quota.max_bytes // 16384)),
            max_payload_bytes=min(self.retention.max_payload_bytes, max(1, self.quota.max_bytes // 8)),
            max_age_seconds=self.retention.max_age_seconds).initialize(db)

    @contextmanager
    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path, timeout=0.1)
        try:
            from app.core.diagnostic_quota import DiagnosticQuotaExceeded
            try:
                with self.quota.lock():
                    self.quota.reserve(db)
                    self.disk_maintenance.configure(db)
                    db.execute("PRAGMA journal_mode=WAL")
            except DiagnosticQuotaExceeded:
                if not self.oversize_recovery.recover(db):
                    raise
                with self.quota.lock():
                    self.quota.reserve(db)
                    self.disk_maintenance.configure(db)
                    db.execute("PRAGMA journal_mode=WAL")
            with self.quota.transaction(db):
                db.execute("CREATE TABLE IF NOT EXISTS projections (trace_id TEXT PRIMARY KEY, operation_id TEXT, workflow TEXT, stage TEXT, payload TEXT NOT NULL)")
                if "last_seen_sweep" not in {row[1] for row in db.execute("PRAGMA table_info(projections)")}:
                    db.execute("ALTER TABLE projections ADD COLUMN last_seen_sweep INTEGER NOT NULL DEFAULT -1")
                db.execute("CREATE INDEX IF NOT EXISTS projections_operation ON projections(operation_id,trace_id)")
                db.execute("CREATE TABLE IF NOT EXISTS checkpoint (name TEXT PRIMARY KEY, cursor TEXT NOT NULL, sweeps INTEGER NOT NULL)")
                db.execute("INSERT OR IGNORE INTO checkpoint VALUES ('runtime','',0)")
                self.retention.initialize(db)
            self.disk_maintenance.maintain(db)
            yield db
        except Exception:
            db.rollback()
            self.disk_maintenance.maintain(db, force=True)
            raise
        finally:
            db.close()

    def step(self, limit=25):
        if not 1 <= limit <= 100:
            raise ValueError("diagnostic_index_page_limit")
        with self._connect() as db:
            cursor, sweep = db.execute("SELECT cursor,sweeps FROM checkpoint WHERE name='runtime'").fetchone()
            ids = self.repository.list_trace_ids(after=cursor, limit=limit)
            projections = []
            for trace_id in ids:
                if self._stop.is_set():
                    return 0  # No checkpoint advance for an interrupted page.
                try:
                    execution = self.repository.get(trace_id)
                    if execution is None:
                        projection = {"schema_version": "diagnostic-harness-index-v1", "trace_id": trace_id, "gap": "source_removed", "resources_gap": "source_removed"}
                    else:
                        projection = project_execution(execution)
                except Exception:
                    self.failures += 1
                    projection = {"schema_version": "diagnostic-harness-index-v1", "trace_id": trace_id, "gap": "source_invalid_or_unavailable", "resources_gap": "source_invalid_or_unavailable"}
                projections.append(projection)
            with self.quota.transaction(db):
                for value in projections:
                    value = DiagnosticHarnessIndexV1.model_validate(value).model_dump(mode="json")
                    retained_at = self.retention.source_time(db, value.get("source_updated_at"))
                    if retained_at is not None and db.execute("SELECT ? < CAST(strftime('%s','now') AS INTEGER)-?", (retained_at, self.retention.max_age_seconds)).fetchone()[0]:
                        db.execute("DELETE FROM projections WHERE trace_id=?", (value["trace_id"],))
                        continue
                    db.execute("INSERT INTO projections(trace_id,operation_id,workflow,stage,payload,last_seen_sweep,retained_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(trace_id) DO UPDATE SET operation_id=excluded.operation_id,workflow=excluded.workflow,stage=excluded.stage,payload=excluded.payload,last_seen_sweep=excluded.last_seen_sweep,retained_at=CASE WHEN ? IS NOT NULL AND projections.payload != excluded.payload THEN excluded.retained_at ELSE projections.retained_at END WHERE projections.payload != excluded.payload OR projections.last_seen_sweep != excluded.last_seen_sweep",
                               (value["trace_id"], value.get("operation_id"), value.get("workflow"), value.get("stage"), json.dumps(value, sort_keys=True), sweep, retained_at or 0, retained_at))
                exhausted = len(ids) < limit
                if exhausted:
                    db.execute("UPDATE projections SET payload=json_set(payload,'$.gap','source_removed','$.state',NULL,'$.status',NULL,'$.commit_status',NULL,'$.resources',NULL,'$.resources_gap','source_removed') WHERE last_seen_sweep < ?", (sweep,))
                self.retention.prune(db)
                db.execute("UPDATE checkpoint SET cursor=?, sweeps=sweeps+? WHERE name='runtime'", ("" if exhausted else ids[-1], int(exhausted)))
            self.disk_maintenance.maintain(db)
            return len(ids)

    def query(self, after="", limit=100, operation_id=None, workflow=None, stage=None, resource_id=None, resource_type=None, resource_role=None):
        if not 1 <= limit <= 100:
            raise ValueError("diagnostic_index_page_limit")
        resource_predicate, resource_params = diagnostic_index_resource_predicate(resource_id, resource_type, resource_role)
        try:
            from contextlib import closing
            with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.1)) as db:
                deadline = time.monotonic() + 5
                db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
                db.execute("BEGIN")
                rows = db.execute("SELECT payload FROM projections WHERE trace_id > ? AND (? IS NULL OR operation_id=?) AND (? IS NULL OR workflow=?) AND (? IS NULL OR stage=?) AND " + resource_predicate + " ORDER BY trace_id LIMIT ?",
                                  [after, operation_id, operation_id, workflow, workflow, stage, stage, *resource_params, limit + 1]).fetchall()
                cursor, sweeps = db.execute("SELECT cursor,sweeps FROM checkpoint WHERE name='runtime'").fetchone()
            items = [DiagnosticHarnessIndexV1.model_validate_json(row[0]).model_dump(mode="json") for row in rows[:limit]]
            return {"items": items, "has_more": len(rows) > limit, "next_cursor": items[-1]["trace_id"] if items else after,
                    "coverage": {"cursor": cursor, "completed_sweeps": sweeps, "failures": self.failures,
                                 "freshness": "eventual", "canonical_read_back_required": True}}
        except (sqlite3.Error, OSError, ValueError):
            self.failures += 1
            return {"items": [], "has_more": False, "next_cursor": after, "coverage": {"failures": self.failures, "freshness": "unavailable", "canonical_read_back_required": True}}

    def start(self):
        if self._thread is not None or self._stop.is_set():
            return
        def run():
            while not self._stop.is_set():
                count = 0
                try:
                    count = self.step()
                except Exception:
                    self.failures += 1
                self._stop.wait(0.1 if count == 25 else 2)
        try:
            self._thread = threading.Thread(target=run, daemon=True, name="diagnostic-harness-index")
            self._thread.start()
        except RuntimeError:
            self.failures += 1
            self._thread = None

    def close(self):
        self._stop.set()
        if self._thread is not None:
            try:
                self._thread.join(timeout=6)
            except RuntimeError:
                self.failures += 1


def project_execution(execution):
    trace = execution.terminal_trace
    return {
        "schema_version": "diagnostic-harness-index-v1",
        "trace_id": execution.trace_id,
        "parent_trace_id": execution.parent_trace_id,
        "operation_id": execution.harness_operation_id,
        "workflow": execution.workflow.value,
        "stage": execution.stage.value,
        "state": execution.state.value,
        "status": trace.status.value if trace else None,
        "commit_status": trace.commit_evidence.status.value if trace else None,
        "duration_ms": trace.duration_ms if trace else None,
        "started_at": trace.started_at.isoformat() if trace else None,
        "completed_at": trace.completed_at.isoformat() if trace else None,
        "source_updated_at": execution.updated_at.isoformat(),
        "gap": None if trace else "terminal_trace_not_available",
        "resources": {
            "context_subjects": [item.model_dump(mode="json") for item in execution.context.subject_refs],
            "attempted_outputs": [item.model_dump(mode="json") for item in trace.commit_evidence.attempted_resource_refs] if trace else [],
            "committed_outputs": [item.model_dump(mode="json", exclude={"payload_digest"}) for item in trace.commit_evidence.committed_resources] if trace else [],
            "scope": "historical_canonical_projection_requires_read_back",
        },
        "resources_gap": None,
        "components": [{"name": item.name, "version": item.version} for item in execution.context.component_versions],
        "attempts": [{"attempt_id": item.attempt_id, "attempt_index": item.attempt_index,
                      "phase": item.phase.value, "status": item.status.value, "duration_ms": item.duration_ms}
                     for item in execution.attempt_records],
        # Trace contexts do not bind provider usage/configuration. Do not guess from timing or model defaults.
        "provider": None, "model": None, "tokens": None, "cost": None,
        "usage_gap": "not_recorded_in_canonical_trace",
        "correlation_gap": "resolve_request_links_separately",
    }
