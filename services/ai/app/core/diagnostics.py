"""Best-effort bounded diagnostic writer isolated from business transactions."""
from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import queue
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
            self.queue.put_nowait(event)
        except Exception:
            self.dropped += 1

    def _run(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path, timeout=0.1) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")
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
