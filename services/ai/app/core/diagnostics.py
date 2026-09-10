"""Best-effort bounded diagnostic writer isolated from business transactions."""
from __future__ import annotations

from contextvars import ContextVar
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path
import queue
import json
import sqlite3
import threading
from uuid import uuid4

from app.models.diagnostic import DiagnosticEventV1, DiagnosticHarnessReferenceV1, DiagnosticResourceReferenceV1

correlation: ContextVar[dict[str, str]] = ContextVar("diagnostic_correlation", default={})

active_span: ContextVar[str | None] = ContextVar("active_diagnostic_span", default=None)

active_harness: ContextVar[DiagnosticHarnessReferenceV1 | None] = ContextVar("active_diagnostic_harness", default=None)


def diagnostic_runtime_scope(function):
    @wraps(function)
    def scoped(*args, **kwargs):
        token = active_harness.set(None)
        try:
            return function(*args, **kwargs)
        finally:
            active_harness.reset(token)
    return scoped


def set_diagnostic_execution(execution):
    try:
        active_harness.set(DiagnosticHarnessReferenceV1(
            operation_id=execution.harness_operation_id, workflow=execution.workflow,
            stage=execution.stage, trace_id=execution.trace_id,
        ))
    except Exception:
        pass


active_store: ContextVar["DiagnosticStore | None"] = ContextVar("active_diagnostic_store", default=None)


def reference_harness(binding, trace=None):
    """Called only with admitted server bindings and canonical runtime traces."""
    try:
        store = active_store.get()
        if store is None:
            return
        if trace is not None and trace.operation_id != binding.harness_operation_id:
            return
        store.emit("harness_reference", harness=DiagnosticHarnessReferenceV1(
            operation_id=binding.harness_operation_id,
            workflow=trace.workflow if trace is not None else binding.workflow,
            stage=trace.stage if trace is not None else binding.entry_stage,
            trace_id=trace.trace_id if trace is not None else None,
        ))
        if trace is not None:
            for attempt in trace.attempt_records:
                store.emit("harness_reference", duration_ms=float(attempt.duration_ms), harness=DiagnosticHarnessReferenceV1(
                    operation_id=trace.operation_id, workflow=trace.workflow, stage=trace.stage,
                    trace_id=trace.trace_id, attempt_id=attempt.attempt_id,
                    attempt_index=attempt.attempt_index, phase=attempt.phase, attempt_status=attempt.status,
                ))
    except Exception:
        # No diagnostic validation/storage failure may change the domain outcome.
        if active_store.get() is not None:
            active_store.get().dropped += 1


def reference_persona(persona):
    """Identity/revision from the saved domain record, without any persona content."""
    store = active_store.get()
    if store is None:
        return
    try:
        store.emit("resource_reference", resource=DiagnosticResourceReferenceV1(
            resource_type="persona", resource_id=persona.id, revision=persona.revision,
        ))
    except Exception:
        store.dropped += 1



class DiagnosticQueryUnavailable(RuntimeError):
    pass


class DiagnosticStore:
    def __init__(self, path: Path, capacity: int = 1000):
        self.path = path
        self.queue: queue.Queue[DiagnosticEventV1] = queue.Queue(maxsize=capacity)
        self.dropped = 0
        self.write_failures = 0
        self.read_failures = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="diagnostic-writer")
        self._thread.start()

    def emit(self, name: str, **fields):
        try:
            event = DiagnosticEventV1(
                event_id=uuid4().hex, source="server", name=name,
                timestamp=datetime.now(timezone.utc).isoformat(),
                **{**correlation.get(), **fields},
            )
            self.enqueue(event)
        except Exception:
            self.dropped += 1

    def enqueue(self, event: DiagnosticEventV1) -> bool:
        try:
            self.queue.put_nowait(event)
            return True
        except queue.Full:
            self.dropped += 1
            return False

    def health(self):
        return {"dropped": self.dropped, "write_failures": self.write_failures, "read_failures": self.read_failures,
                "queued": self.queue.qsize(),
                "writer_alive": self._thread is not None and self._thread.is_alive()}

    def query(self, after: int, limit: int, filters: dict, *, strict=False):
        # All predicates target this diagnostic database, never domain transactions.
        from contextlib import closing
        if not 0 <= after or not 1 <= limit <= 101:
            raise ValueError("diagnostic_query_bounds")
        paths = {key: key for key in ("request_id", "action_id", "page_view_id", "flow_id", "source", "page_path", "severity")}
        paths.update(resource_id="resource.resource_id", resource_type="resource.resource_type")
        clauses = ["e.sequence > ?"]
        values = [after]
        for key, path in paths.items():
            if filters.get(key) is not None:
                clauses.append(f"json_extract(e.payload, '$.{path}') = ?")
                values.append(filters[key])
        for key in ("operation_id", "workflow", "stage"):
            if filters.get(key) is None:
                continue
            # Canonical references and durable request links cover transport/provider/tool events.
            clauses.append(f"(json_extract(e.payload, '$.harness.{key}') = ? OR EXISTS (SELECT 1 FROM operation_links l WHERE "
                           + ("l.operation_id = ?" if key == "operation_id" else f"json_extract(l.payload, '$.{key}') = ?")
                           + " AND l.request_id=json_extract(e.payload, '$.request_id')))")
            values.extend([filters[key], filters[key]])
        for key, operator in (("since", ">="), ("until", "<")):
            if filters.get(key) is not None:
                clauses.append(f"julianday(json_extract(e.payload, '$.timestamp')) {operator} julianday(?)")
                values.append(filters[key])
        try:
            with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.1)) as db:
                rows = db.execute("SELECT e.sequence,e.payload FROM events e WHERE " +
                                  " AND ".join(clauses) + " ORDER BY e.sequence LIMIT ?",
                                  [*values, limit]).fetchall()
            # Revalidate stored bytes before returning anything to a global viewer/exporter.
            return [{"sequence": seq, "event": DiagnosticEventV1.model_validate_json(payload).model_dump(mode="json")} for seq, payload in rows]
        except (sqlite3.Error, OSError, ValueError):
            self.read_failures += 1
            if strict:
                raise DiagnosticQueryUnavailable("diagnostic_query_unavailable") from None
            return []

    def persist_external_event(self, event: DiagnosticEventV1) -> bool:
        """Desktop spool acknowledgement means committed diagnostic bytes, never queue acceptance."""
        from contextlib import closing
        try:
            payload = event.model_dump_json()
            with closing(sqlite3.connect(self.path, timeout=0.1)) as db:
                with db:
                    existing = db.execute("SELECT payload FROM events WHERE event_id=?", (event.event_id,)).fetchone()
                    if existing is not None:
                        return DiagnosticEventV1.model_validate_json(existing[0]) == event
                    db.execute("INSERT INTO events(event_id,payload) VALUES (?,?)", (event.event_id, payload))
                    db.execute("DELETE FROM events WHERE sequence <= (SELECT COALESCE(MAX(sequence),0)-10000 FROM events)")
            return True
        except Exception:
            self.write_failures += 1
            return False

    def operation_links(self, operation_id: str, after: str = "", limit: int = 100):
        if not 1 <= limit <= 100:
            raise ValueError("diagnostic_link_page_limit")
        try:
            from contextlib import closing
            with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.1)) as db:
                rows = db.execute("SELECT payload FROM operation_links WHERE operation_id=? AND request_id>? ORDER BY request_id LIMIT ?", (operation_id, after, limit)).fetchall()
            from app.models.diagnostic import DiagnosticOperationLinkV1
            items = [DiagnosticOperationLinkV1.model_validate_json(row[0]).model_dump(mode="json", exclude_unset=True) for row in rows]
            if any(item["operation_id"] != operation_id or item["request_id"] <= after for item in items):
                raise ValueError("diagnostic_link_identity_mismatch")
            return {"items": items, "next_cursor": items[-1]["request_id"] if items else after,
                    "gap": None if items else "no_correlation_recorded_or_retained"}
        except (sqlite3.Error, OSError, ValueError):
            self.read_failures += 1
            return {"items": [], "next_cursor": after, "gap": "diagnostic_store_unavailable"}

    def _run(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path, timeout=0.1) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")
                db.execute("CREATE TABLE IF NOT EXISTS operation_links (operation_id TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(operation_id,request_id))")
                db.execute("CREATE INDEX IF NOT EXISTS operation_links_request ON operation_links(request_id,operation_id)")
                for field in ("request_id", "action_id", "page_view_id", "flow_id", "source"):
                    db.execute(f"CREATE INDEX IF NOT EXISTS events_{field} ON events(json_extract(payload, '$.{field}'), sequence)")
                while not self._stop.is_set() or not self.queue.empty():
                    try:
                        event = self.queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    try:
                        db.execute("INSERT OR IGNORE INTO events(event_id,payload) VALUES (?,?)", (event.event_id, event.model_dump_json()))
                        if event.source == "server" and event.harness is not None and event.request_id is not None:
                            link = {"operation_id": event.harness.operation_id, "request_id": event.request_id,
                                    "client_instance_id": event.client_instance_id, "page_view_id": event.page_view_id,
                                    "flow_id": event.flow_id, "action_id": event.action_id,
                                    "workflow": event.harness.workflow, "stage": event.harness.stage}
                            db.execute("INSERT INTO operation_links VALUES (?,?,?) ON CONFLICT(operation_id,request_id) DO UPDATE SET payload=excluded.payload",
                                       (event.harness.operation_id, event.request_id, json.dumps(link, sort_keys=True)))
                        # Initial hard bound. Time/byte retention and export follow in OBS-AUDIT.
                        db.execute("DELETE FROM events WHERE sequence <= (SELECT COALESCE(MAX(sequence),0)-10000 FROM events)")
                        db.commit()
                    except Exception:
                        self.write_failures += 1
                    finally:
                        self.queue.task_done()
        except Exception:
            self.write_failures += 1

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
