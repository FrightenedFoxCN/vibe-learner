import asyncio
import json
import logging
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from pydantic import ValidationError

from app.api.diagnostic_middleware import DiagnosticMiddleware
from app.core.diagnostics import DiagnosticStore, correlation
from app.models.diagnostic import DiagnosticEventV1


class DiagnosticTests(unittest.TestCase):
    def test_python_formatter_drops_unreviewed_content(self):
        from app.core.logging import DiagnosticJsonFormatter
        record = logging.LogRecord("provider", logging.ERROR, "", 0,
                                   "secret %s", ("api-key-and-prompt",), None)
        text = DiagnosticJsonFormatter().format(record)
        self.assertNotIn("secret", text)
        self.assertNotIn("api-key", text)
        self.assertEqual(json.loads(text)["event"], "log")

    def test_shared_classification_fixture_and_untrusted_types(self):
        from app.models.diagnostic import classify_diagnostic
        fixture = Path(__file__).parents[3] / "packages/shared/fixtures/diagnostics/event-classification-v1.json"
        for case in json.loads(fixture.read_text()):
            self.assertEqual(classify_diagnostic(case["name"], case["status_code"]), case["classification"])
        base = dict(event_id="event", source="browser", name="request_finished", timestamp="2026-09-10")
        for patch in ({"status_code": "secret"}, {"name": []}, {"category": "harness"}, {"status_code": 503, "outcome": "completed"}):
            with self.assertRaises(ValidationError):
                DiagnosticEventV1.model_validate({**base, **patch})

    def test_storage_default_matches_business_root_and_expands_home(self):
        from app.core.settings import Settings
        expected = Path(__file__).parents[1] / "data"
        self.assertEqual(Settings().resolved_storage_root, expected)
        self.assertEqual(Settings(storage_root="~/diagnostic-test").resolved_storage_root, Path.home() / "diagnostic-test")

    def test_cancel_and_explicit_thread_context_preserve_request_identity(self):
        from contextvars import copy_context
        from concurrent.futures import ThreadPoolExecutor
        from app.core.diagnostics import active_store
        async def scenario():
            store = Mock()
            observed = []
            store.emit.side_effect = lambda name, **fields: observed.append((name, dict(correlation.get())))
            scope = {"type": "http", "path": "/stream", "method": "POST", "headers": [(b"x-debug-action-id", b"cancel_action")],
                     "app": SimpleNamespace(state=SimpleNamespace(diagnostics=store))}
            async def app(scope, receive, send):
                with ThreadPoolExecutor(1) as worker:
                    def inspect():
                        return correlation.get(), active_store.get()
                    context, sink = worker.submit(copy_context().run, inspect).result()
                self.assertEqual(context["action_id"], "cancel_action")
                self.assertIs(sink, store)
                raise asyncio.CancelledError()
            async def receive(): return {"type": "http.disconnect"}
            async def send(message): pass
            with self.assertRaises(asyncio.CancelledError):
                await DiagnosticMiddleware(app)(scope, receive, send)
            self.assertEqual(observed[-1][0], "request_cancelled")
            self.assertEqual(observed[0][1], observed[-1][1])
            self.assertEqual(correlation.get(), {})
            self.assertIsNone(active_store.get())
        asyncio.run(scenario())

    def test_closed_contract_rejects_content_and_nonfinite_metrics(self):
        safe = dict(event_id="event", source="browser", name="request_started", timestamp="2026-09-10")
        for extra in ({"prompt": "secret"}, {"duration_ms": float("nan")}, {"route": "/settings?key=secret"}, {"request_id": "Bearer secret"}):
            with self.assertRaises(ValidationError):
                DiagnosticEventV1(**safe, **extra)

    def test_queue_is_bounded_and_disk_failure_is_isolated(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory), capacity=1)  # directory is not a DB file
            store.emit("request_started")
            store.emit("request_started")
            self.assertEqual(store.dropped, 1)
            store.start()
            store.close()
            self.assertEqual(store.write_failures, 1)

    def test_writer_survives_restart_and_records_safe_context(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            for _ in range(2):
                store = DiagnosticStore(path)
                store.start()
                token = correlation.set({"request_id": "real_request"})
                store.emit("request_finished", status_code=200, duration_ms=1.0)
                correlation.reset(token)
                store.close()
            with sqlite3.connect(path) as db:
                rows = db.execute("SELECT payload FROM events ORDER BY sequence").fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(json.loads(rows[0][0])["request_id"], "real_request")

    def test_ingest_deduplicates_and_filters_without_recursive_collection(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.api.diagnostic_routes import router
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            store.start()
            self.addCleanup(store.close)
            app = FastAPI()
            app.state.diagnostics = store
            app.add_middleware(DiagnosticMiddleware)
            app.include_router(router)
            event = DiagnosticEventV1(event_id="browser_event", source="browser",
                                      name="request_started", timestamp="2026-09-10",
                                      action_id="persona_save").model_dump()
            with TestClient(app) as client:
                for _ in range(2):
                    self.assertEqual(client.post("/diagnostics/events", json={"events": [event]}).status_code, 200)
                store.queue.join()
                result = client.get("/diagnostics/events?action_id=persona_save").json()
                self.assertEqual(len(result["items"]), 1)
                cursor = result["next_cursor"]
                self.assertEqual(client.get(f"/diagnostics/events?after={cursor}").json()["items"], [])
                self.assertEqual(client.get("/diagnostics/events?action_id=other").json()["items"], [])
                bad = client.post("/diagnostics/events", json={"events": [{**event, "prompt": "secret_material"}]})
                self.assertEqual(bad.status_code, 422)
                self.assertNotIn("secret_material", bad.text)
                self.assertEqual(client.post("/diagnostics/events", json={"events": [{**event, "source": "server"}]}).status_code, 422)
                self.assertEqual(len(client.get("/diagnostics/events").json()["items"]), 1)

    def test_persona_generation_references_real_runtime_identity(self):
        from fastapi.testclient import TestClient
        from app.app_factory import create_app
        from app.core.settings import Settings
        from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
        from tests.test_persona_lifecycle import create_request
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(settings=Settings(database_url=f"sqlite:///{root / 'domain.db'}",
                                               storage_root=str(root / "data"), ocr_engine="disabled"))
            with TestClient(app) as client:
                headers = {"X-Debug-Flow-Id": "persona_flow", "X-Debug-Action-Id": "generate"}
                generated = client.post("/persona-cards/generate", json={"mode": "keywords", "input_text": "PRIVATE_PROMPT"}, headers=headers)
                self.assertEqual(generated.status_code, 200, generated.text)
                store = app.state.diagnostics
                store.queue.join()
                events = store.query(0, 100, {"action_id": "generate"})
                refs = [row["event"]["harness"] for row in events if row["event"]["name"] == "harness_reference"]
                self.assertGreater(len(refs), 2)
                self.assertIsNone(refs[0]["trace_id"])
                self.assertEqual(refs[0]["operation_id"], refs[1]["operation_id"])
                canonical = HarnessRuntimeRepository(app.state.container.database).list_operation_traces(refs[0]["operation_id"])
                self.assertIn(refs[1]["trace_id"], [item.terminal_trace.trace_id for item in canonical if item.terminal_trace])
                attempts = [ref for ref in refs if ref["attempt_id"] is not None]
                canonical_attempts = [attempt for item in canonical if item.terminal_trace for attempt in item.terminal_trace.attempt_records]
                self.assertEqual({ref["attempt_id"] for ref in attempts}, {attempt.attempt_id for attempt in canonical_attempts})
                for ref in attempts:
                    attempt = next(attempt for attempt in canonical_attempts if attempt.attempt_id == ref["attempt_id"])
                    self.assertEqual((ref["attempt_index"], ref["phase"], ref["attempt_status"]), (attempt.attempt_index, attempt.phase.value, attempt.status.value))
                self.assertNotIn("PRIVATE_PROMPT", json.dumps(events))
                forged = {**events[0]["event"], "source": "browser", "harness": refs[1]}
                self.assertEqual(client.post("/diagnostics/events", json={"events": [forged]}).status_code, 422)
                saved = client.post("/personas", json=create_request().model_dump(mode="json"),
                                    headers={**headers, "X-Debug-Action-Id": "save"})
                self.assertEqual(saved.status_code, 200, saved.text)
                reloaded = client.get("/personas", headers={**headers, "X-Debug-Action-Id": "reload"})
                self.assertIn(saved.json()["id"], [item["id"] for item in reloaded.json()["items"]])
                replayed_read = client.get("/personas", headers={**headers, "X-Debug-Action-Id": "reload"})
                self.assertNotEqual(reloaded.headers["X-Request-ID"], replayed_read.headers["X-Request-ID"])
                self.assertEqual(len({generated.headers["X-Request-ID"], saved.headers["X-Request-ID"], reloaded.headers["X-Request-ID"]}), 3)
                store.queue.join()
                flow = store.query(0, 100, {"flow_id": "persona_flow"})
                self.assertEqual({row["event"]["action_id"] for row in flow}, {"generate", "save", "reload"})
                resource = next(row["event"]["resource"] for row in flow if row["event"]["name"] == "resource_reference")
                self.assertEqual(resource, {"resource_type": "persona", "resource_id": saved.json()["id"], "revision": saved.json()["revision"]})

    def test_asgi_records_body_completion_and_resets_context(self):
        async def scenario(failure=False):
            events = []
            store = Mock()
            store.emit.side_effect = lambda name, **fields: events.append((name, {**correlation.get(), **fields}))
            scope = {"type": "http", "path": "/personas/private-title", "method": "GET", "app": SimpleNamespace(state=SimpleNamespace(diagnostics=store)), "headers": [(b"x-debug-action-id", b"action"), (b"x-request-id", b"forged")]}
            async def app(scope, receive, send):
                scope["route"] = SimpleNamespace(path="/personas/{persona_id}")
                await send({"type": "http.response.start", "status": 200})
                await send({"type": "http.response.body", "body": b"first", "more_body": True})
                self.assertNotIn("request_finished", [name for name, _ in events])
                if failure:
                    raise RuntimeError("secret provider content")
                await send({"type": "http.response.body", "body": b"last"})
            async def send(message):
                pass
            async def receive():
                return {"type": "http.disconnect"}
            try:
                await DiagnosticMiddleware(app)(scope, receive, send)
            except RuntimeError:
                self.assertTrue(failure)
            self.assertEqual(correlation.get(), {})
            self.assertEqual(events[-1][0], "request_failed" if failure else "request_finished")
            self.assertEqual(events[-1][1]["action_id"], "action")
            self.assertNotEqual(events[-1][1]["request_id"], "forged")
            self.assertNotIn("private-title", json.dumps(events))
            self.assertNotIn("secret provider", json.dumps(events))
        asyncio.run(scenario())
        asyncio.run(scenario(True))
