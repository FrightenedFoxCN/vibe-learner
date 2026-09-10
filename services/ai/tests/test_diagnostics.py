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
