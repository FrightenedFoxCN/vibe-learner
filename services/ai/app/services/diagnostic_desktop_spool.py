"""Consume native events only after durable, idempotent diagnostic persistence."""
from datetime import datetime, timezone
from pathlib import Path
import re
import os
import stat
import time
from app.core.diagnostic_quota import DiagnosticDatabaseQuota, DiagnosticQuotaExceeded
import threading

from app.models.diagnostic import DiagnosticEventV1
from app.models.diagnostic_desktop import DesktopSpoolRecordV1, DiagnosticDesktopMetricV1


class DesktopDiagnosticSpool:
    def __init__(self, store, root: Path):
        # Only the shared file-lock primitive is used; no spool database exists.
        self._lock = DiagnosticDatabaseQuota(root / "spool")
        self.store = store
        self.root = root
        self.rejected = 0
        self.failures = 0
        self._stop = threading.Event()
        self._thread = None

    def step(self):
        if not self.root.exists():
            return
        paths = []
        with os.scandir(self.root) as entries:
            for i, entry in enumerate(entries):
                if i >= 1024:
                    self.failures += 1
                    return
                if re.fullmatch(r"desktop-[a-f0-9-]{1,88}\.(json|pending)", entry.name):
                    paths.append(Path(entry.path))
        for path in sorted(paths)[:100]:
            if self._stop.is_set():
                return
            try:
                with self._lock.lock():
                    self._consume(path)
            except DiagnosticQuotaExceeded:
                self.failures += 1
                return

    def _unlink_same(self, path, observed):
        try:
            current = path.lstat()
            if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) != (observed.st_dev, observed.st_ino, observed.st_size, observed.st_mtime_ns):
                self.failures += 1
                return
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            self.failures += 1

    def _consume(self, path):
        observed = None
        try:
            if path.is_symlink():
                return
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(path, flags), "rb") as handle:
                observed = os.fstat(handle.fileno())
                if not stat.S_ISREG(observed.st_mode):
                    return
                current = path.lstat()
                if (current.st_dev, current.st_ino) != (observed.st_dev, observed.st_ino) or stat.S_ISLNK(current.st_mode):
                    self.failures += 1
                    return
                if time.time() - observed.st_mtime > 7 * 86400:
                    self.rejected += 1
                    self._unlink_same(path, observed)
                    return
                raw = handle.read(16385)
            if len(raw) > 16384:
                raise ValueError("desktop_spool_size_limit")
            record = DesktopSpoolRecordV1.model_validate_json(raw)
            if path.stem != record.event_id:
                raise ValueError("desktop_spool_identity_mismatch")
            event = DiagnosticEventV1(
                event_id=record.event_id, source="desktop", name=record.name,
                timestamp=datetime.fromtimestamp(record.unix_time_ms / 1000, timezone.utc).isoformat(),
                duration_ms=float(record.duration_ms) if record.duration_ms is not None else None,
                desktop_metric=DiagnosticDesktopMetricV1(instance_id=record.instance_id, exit_code=record.exit_code,
                    dropped_before=record.dropped_before, write_failures_before=record.write_failures_before),
            )
        except FileNotFoundError:
            return
        except (ValueError, OverflowError):
            self.rejected += 1
            if observed is not None:
                self._unlink_same(path, observed)
            return
        except OSError:
            self.failures += 1
            return
        if self.store.persist_external_event(event):
            self._unlink_same(path, observed)
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
