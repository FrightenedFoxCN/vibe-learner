from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.core.diagnostics import DiagnosticStore
from app.core.settings import Settings
from app.models.diagnostic import DiagnosticEventV1


class DiagnosticFailureIsolationTests(unittest.TestCase):
    def test_all_diagnostic_thread_start_failures_preserve_business_start_commit_and_close(self):
        original = threading.Thread.start
        failed = []
        def start(thread):
            if thread.name in {"diagnostic-writer", "diagnostic-harness-index", "desktop-diagnostic-spool"}:
                failed.append(thread.name)
                raise RuntimeError("PRIVATE_THREAD_FAILURE")
            return original(thread)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}", ocr_engine="disabled")
            app = create_app(settings=settings)
            with patch.object(threading.Thread, "start", start), TestClient(app) as client:
                container = app.state.container
                self.assertEqual(client.get("/health").status_code, 200)
                changed = client.patch("/runtime-settings", json={"openai_chat_model": "durable-without-diagnostics"})
                self.assertEqual(changed.status_code, 200)
                generated = client.post("/persona-cards/generate", json={"mode": "keywords", "input_text": "PRIVATE_INPUT"})
                self.assertEqual(generated.status_code, 200, generated.text)
                from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
                canonical = HarnessRuntimeRepository(container.database)
                traces = [canonical.get(trace_id) for trace_id in canonical.list_trace_ids(limit=100)]
                self.assertTrue(any(trace.terminal_trace is not None for trace in traces))
                self.assertEqual(client.get("/runtime-settings").json()["openai_chat_model"], "durable-without-diagnostics")
                self.assertFalse(app.state.diagnostics.health()["writer_alive"])
                self.assertEqual(app.state.diagnostics.health()["queued"], 0)
                self.assertGreater(app.state.diagnostics.health()["dropped"], 0)
                response = client.get("/diagnostics/events")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("PRIVATE", response.text)
            self.assertTrue(container._closed)
            self.assertEqual(set(failed), {"diagnostic-writer", "diagnostic-harness-index", "desktop-diagnostic-spool"})
            with TestClient(create_app(settings=settings)) as restarted:
                self.assertEqual(restarted.get("/runtime-settings").json()["openai_chat_model"], "durable-without-diagnostics")

    def test_dead_writer_discards_queue_and_rejects_late_admission_without_hanging(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory), capacity=4)  # Opening a directory as SQLite must fail.
            event = DiagnosticEventV1(event_id="queued", name="request_started", source="server", timestamp="2026-09-10T00:00:00Z")
            self.assertTrue(store.enqueue(event))
            store.start()
            store._thread.join(timeout=2)
            self.assertFalse(store._thread.is_alive())
            self.assertFalse(store.enqueue(event))
            self.assertEqual(store.queue.unfinished_tasks, 0)
            self.assertEqual(store.health()["queued"], 0)
            self.assertEqual(store.dropped, 2)
            store.close()
            self.assertFalse(store.enqueue(event))

    def test_persistent_schema_failure_has_bounded_retries_and_releases_queue_waiters(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            event = DiagnosticEventV1(event_id="queued", name="request_started", source="server", timestamp="2026-09-10T00:00:00Z")
            self.assertTrue(store.enqueue(event))
            with (
                patch("app.core.diagnostics.DIAGNOSTIC_STARTUP_RETRY_SECONDS", 0.001),
                patch.object(store, "_initialize_schema", side_effect=OSError("test_schema_unavailable")),
            ):
                store.start()
                store._thread.join(timeout=2)
            self.assertFalse(store._thread.is_alive())
            self.assertEqual(store.write_failures, 5)
            self.assertEqual(store._startup_failure, "OSError: test_schema_unavailable")
            self.assertEqual(store.queue.unfinished_tasks, 0)
            self.assertEqual(store.dropped, 1)
            self.assertFalse(store.enqueue(event))
            store.close()

    def test_repeated_start_has_one_writer_and_close_fences_producers(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            store.start()
            original = store._thread
            store.start()
            self.assertIs(store._thread, original)
            store.emit("lifecycle_started")
            store.queue.join()
            store.close()
            store.start()
            self.assertIs(store._thread, original)
            self.assertFalse(original.is_alive())
            event = DiagnosticEventV1(event_id="late", name="request_started", source="server", timestamp="2026-09-10T00:00:00Z")
            self.assertFalse(store.enqueue(event))
            self.assertEqual(store.queue.unfinished_tasks, 0)


    def test_failed_diagnostic_transaction_rolls_back_and_next_event_can_persist(self):
        from app.core.diagnostic_retention import DiagnosticEventRetention
        class FailOnce(DiagnosticEventRetention):
            calls = 0
            def prune(self, db):
                self.calls += 1
                if self.calls == 2:  # initialize succeeds; the first event transaction fails.
                    raise OSError("PRIVATE_DISK_FAILURE")
                super().prune(db)
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db", retention=FailOnce())
            store.start()
            for identity in ("failed", "persisted"):
                store.enqueue(DiagnosticEventV1(event_id=identity, name="request_finished", source="server", timestamp="2026-09-10T00:00:00Z"))
            store.queue.join()
            store.close()
            rows, coverage = store.query(0, 100, {}, strict=True, with_coverage=True)
            self.assertEqual([row["event"]["event_id"] for row in rows], ["persisted"])
            self.assertEqual(coverage["retained_events"], 1)
            self.assertEqual(store.write_failures, 1)
            self.assertEqual(store.dropped, 1)
