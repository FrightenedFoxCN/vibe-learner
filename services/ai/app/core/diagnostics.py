"""Best-effort bounded diagnostic writer isolated from business transactions."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import queue
import json
import sqlite3
import threading
from uuid import uuid4

from app.models.diagnostic import DiagnosticEventV1

correlation: ContextVar[dict[str, str]] = ContextVar("diagnostic_correlation", default={})


class DiagnosticStore:
    def __init__(self, path: Path, capacity: int = 1000):
        self.path = path
        self.queue: queue.Queue[DiagnosticEventV1] = queue.Queue(maxsize=capacity)
        self.dropped = 0
        self.write_failures = 0
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
        return {"dropped": self.dropped, "write_failures": self.write_failures,
                "queued": self.queue.qsize(),
                "writer_alive": self._thread is not None and self._thread.is_alive()}

    def query(self, after: int, limit: int, filters: dict):
        # Query is read-only, short-lived and never scans business transaction tables.
        allowed = {"request_id", "action_id", "page_view_id", "flow_id", "source"}
        clauses = ["sequence > ?"]
        values = [after]
        for key, value in filters.items():
            if key in allowed and value is not None:
                clauses.append(f"json_extract(payload, '$.{key}') = ?")
                values.append(value)
        try:
            with sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.1) as db:
                rows = db.execute("SELECT sequence,payload FROM events WHERE " +
                                  " AND ".join(clauses) + " ORDER BY sequence LIMIT ?",
                                  [*values, limit]).fetchall()
            return [{"sequence": seq, "event": json.loads(payload)} for seq, payload in rows]
        except (sqlite3.Error, OSError):
            self.write_failures += 1
            return []

    def _run(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path, timeout=0.1) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")
                for field in ("request_id", "action_id", "page_view_id", "flow_id", "source"):
                    db.execute(f"CREATE INDEX IF NOT EXISTS events_{field} ON events(json_extract(payload, '$.{field}'), sequence)")
                while not self._stop.is_set() or not self.queue.empty():
                    try:
                        event = self.queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    try:
                        db.execute("INSERT OR IGNORE INTO events(event_id,payload) VALUES (?,?)", (event.event_id, event.model_dump_json()))
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
