"""Consume native events only after durable, idempotent diagnostic persistence."""
from datetime import datetime, timezone
from pathlib import Path
import re
import threading

from app.models.diagnostic import DiagnosticEventV1
from app.models.diagnostic_desktop import DesktopSpoolRecordV1, DiagnosticDesktopMetricV1


class DesktopDiagnosticSpool:
    def __init__(self, store, root: Path):
        self.store = store
        self.root = root
        self.rejected = 0
        self.failures = 0
        self._stop = threading.Event()
        self._thread = None

    def step(self):
        if not self.root.exists():
            return
        for path in sorted(self.root.glob("desktop-*.json"))[:100]:
            if self._stop.is_set():
                return
            if not re.fullmatch(r"desktop-[a-f0-9-]{1,88}\.json", path.name) or path.is_symlink():
                continue
            try:
                with path.open("rb") as handle:
                    raw = handle.read(16385)
                if len(raw) > 16384:
                    raise ValueError("desktop_spool_size_limit")
                record = DesktopSpoolRecordV1.model_validate_json(raw)
                if path.name != f"{record.event_id}.json":
                    raise ValueError("desktop_spool_identity_mismatch")
                event = DiagnosticEventV1(
                    event_id=record.event_id, source="desktop", name=record.name,
                    timestamp=datetime.fromtimestamp(record.unix_time_ms / 1000, timezone.utc).isoformat(),
                    duration_ms=float(record.duration_ms) if record.duration_ms is not None else None,
                    desktop_metric=DiagnosticDesktopMetricV1(instance_id=record.instance_id, exit_code=record.exit_code,
                        dropped_before=record.dropped_before, write_failures_before=record.write_failures_before),
                )
            except FileNotFoundError:
                continue  # Native ring retention can race the read.
            except (ValueError, OverflowError):
                self.rejected += 1
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    self.failures += 1
                continue
            except OSError:
                self.failures += 1
                continue
            if self.store.persist_external_event(event):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    self.failures += 1  # Restart retries same identity; no duplicate persistence.
            else:
                self.failures += 1

    def start(self):
        if self._thread is not None or self._stop.is_set():
            return
        def run():
            while not self._stop.is_set():
                try:
                    self.step()
                except Exception:
                    self.failures += 1
                self._stop.wait(1)
        try:
            self._thread = threading.Thread(target=run, daemon=True, name="desktop-diagnostic-spool")
            self._thread.start()
        except RuntimeError:
            self.failures += 1
            self._thread = None

    def close(self):
        self._stop.set()
        if self._thread is not None:
            try:
                self._thread.join(timeout=2)
            except RuntimeError:
                self.failures += 1
