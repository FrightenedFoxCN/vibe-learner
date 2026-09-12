import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.core.diagnostics import DiagnosticStore
from app.services.diagnostic_desktop_spool import DesktopDiagnosticSpool


class DesktopDiagnosticTests(unittest.TestCase):
    def test_monitor_start_failure_is_best_effort(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            spool = DesktopDiagnosticSpool(DiagnosticStore(root / "events.sqlite3"), root / "spool")
            with patch("threading.Thread.start", side_effect=RuntimeError("unavailable")):
                spool.start()
            spool.close()
            self.assertEqual(spool.failures, 1)

    def test_shared_native_wire_fixture(self):
        from app.models.diagnostic_desktop import DesktopSpoolRecordV1
        fixture = Path(__file__).resolve().parents[3] / "packages/shared/fixtures/diagnostics/desktop-spool-v1.json"
        raw = fixture.read_text()
        record = DesktopSpoolRecordV1.model_validate_json(raw)
        self.assertEqual(record.model_dump(), json.loads(raw))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            store.start()
            store.emit("lifecycle_started")
            store.queue.join()
            try:
                spool = DesktopDiagnosticSpool(store, root / "spool")
                spool.root.mkdir()
                (spool.root / f"{record.event_id}.json").write_text(raw)
                spool.step()
                rows = store.query(0, 100, {"source": "desktop"})
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["event"]["event_id"], record.event_id)
            finally:
                store.close()

    def record(self, root, *, event_id="desktop-abc-123", **extra):
        path = root / f"{event_id}.json"
        root.mkdir(parents=True, exist_ok=True)
        record = {"schema_version": "desktop-diagnostic-v1", "event_id": event_id, "instance_id": "desktop-abc",
                  "name": "sidecar_exited", "unix_time_ms": 1789012800000, "duration_ms": 2, "exit_code": 7,
                  "dropped_before": 3, "write_failures_before": 1, **extra}
        path.write_text(json.dumps(record))
        return path

    def test_offline_persistence_ack_restart_and_duplicate_id(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            spool = DesktopDiagnosticSpool(store, root / "spool")
            path = self.record(spool.root)
            spool.step()  # Event DB not initialized; no acknowledgement or deletion.
            self.assertTrue(path.exists())
            store.start()
            store.emit("lifecycle_started")
            store.queue.join()
            store.close()
            # Native event can commit with no async writer alive.
            spool.step()
            self.assertFalse(path.exists())
            rows = store.query(0, 100, {"source": "desktop"})
            self.assertEqual(len(rows), 1)
            event = rows[0]["event"]
            self.assertEqual(event["event_id"], "desktop-abc-123")
            self.assertEqual(event["desktop_metric"]["exit_code"], 7)
            self.assertEqual(event["desktop_metric"]["dropped_before"], 3)
            # Crash after commit but before unlink leaves the same file for restart.
            path = self.record(spool.root)
            recovered = DesktopDiagnosticSpool(DiagnosticStore(store.path), spool.root)
            recovered.step()
            self.assertFalse(path.exists())
            self.assertEqual(store.query(0, 100, {"source": "desktop"}), rows)
            # Same ID with changed bytes must not be acknowledged as the old event.
            path = self.record(spool.root, exit_code=9)
            recovered.step()
            self.assertTrue(path.exists())
            self.assertEqual(store.query(0, 100, {"source": "desktop"}), rows)

    def test_size_and_schema_rejection_never_persist_input_or_follow_symlinks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            store.start()
            store.emit("lifecycle_started")
            store.queue.join()
            store.close()
            spool = DesktopDiagnosticSpool(store, root / "spool")
            self.record(spool.root, event_id="desktop-a", prompt="PRIVATE_PROMPT")
            self.record(spool.root, event_id="desktop-b").write_text("PRIVATE_BODY" * 2000)
            outside = root / "outside.json"
            outside.write_text("PRIVATE_OUTSIDE")
            (spool.root / "desktop-c.json").symlink_to(outside)
            spool.step()
            self.assertEqual(spool.rejected, 2)
            self.assertEqual(store.query(0, 100, {"source": "desktop"}), [])
            self.assertEqual(outside.read_text(), "PRIVATE_OUTSIDE")
            self.assertNotIn("PRIVATE", json.dumps(store.query(0, 100, {})))

    def test_unlink_failure_does_not_duplicate_on_next_step(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            store.start()
            store.emit("lifecycle_started")
            store.queue.join()
            store.close()
            spool = DesktopDiagnosticSpool(store, root / "spool")
            path = self.record(spool.root)
            with patch.object(Path, "unlink", side_effect=OSError("disk unavailable")):
                spool.step()
            self.assertTrue(path.exists())
            self.assertEqual(spool.failures, 1)
            spool.step()
            self.assertFalse(path.exists())
            self.assertEqual(len(store.query(0, 100, {"source": "desktop"})), 1)

    def test_complete_pending_file_recovers_but_partial_pending_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            store.start(); store.emit("lifecycle_started"); store.queue.join(); store.close()
            spool = DesktopDiagnosticSpool(store, root / "spool")
            complete = self.record(spool.root).rename(spool.root / "desktop-abc-123.pending")
            partial = spool.root / "desktop-b.pending"
            partial.write_bytes(b'{"schema_version":')
            spool.step()
            self.assertFalse(complete.exists(), store._startup_failure)
            self.assertFalse(partial.exists())
            self.assertEqual(spool.rejected, 1)
            self.assertEqual(len(store.query(0, 100, {"source": "desktop"})), 1)

    def test_shared_process_lock_defers_consumption_and_replacement_is_not_unlinked(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            store.start(); store.emit("lifecycle_started"); store.queue.join(); store.close()
            spool = DesktopDiagnosticSpool(store, root / "spool")
            path = self.record(spool.root)
            with spool._lock.lock():
                spool.step()
            self.assertTrue(path.exists())
            original = store.persist_external_event
            def persist_then_replace(event):
                result = original(event)
                path.unlink()
                self.record(spool.root, exit_code=99)
                return result
            with patch.object(store, "persist_external_event", side_effect=persist_then_replace):
                spool.step()
            self.assertTrue(path.exists())
            self.assertEqual(json.loads(path.read_text())["exit_code"], 99)
            self.assertEqual(store.query(0, 100, {"source": "desktop"})[0]["event"]["desktop_metric"]["exit_code"], 7)

    def test_expired_spool_file_is_not_reintroduced_as_newly_ingested_history(self):
        import os
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            spool = DesktopDiagnosticSpool(store, root / "spool")
            path = self.record(spool.root)
            os.utime(path, (1, 1))
            spool.step()
            self.assertFalse(path.exists())
            self.assertEqual(spool.rejected, 1)
            self.assertFalse(store.path.exists())
