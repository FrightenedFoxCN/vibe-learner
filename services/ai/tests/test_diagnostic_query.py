from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import json
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.diagnostic_routes import router
from app.core.diagnostics import DiagnosticStore
from app.models.harness import HarnessWorkflow, HarnessStage
from app.models.diagnostic import DiagnosticEventV1, DiagnosticHarnessReferenceV1
from app.services.diagnostic_index import DiagnosticHarnessIndex


class DiagnosticQueryTests(unittest.TestCase):
    def test_browser_query_schemas_match_current_backend_models(self):
        from app.models.diagnostic import DiagnosticOperationLinkV1
        from app.models.diagnostic_index import DiagnosticHarnessIndexV1
        from app.models.diagnostic_writer import DiagnosticWriterCoverageV1
        root = Path(__file__).parents[3] / "packages/shared/fixtures/diagnostics"
        expected = {name: model.model_json_schema() for name, model in (
            ("event", DiagnosticEventV1), ("index", DiagnosticHarnessIndexV1), ("link", DiagnosticOperationLinkV1), ("writers", DiagnosticWriterCoverageV1))}
        self.assertEqual(json.loads((root / "query-schemas-v1.json").read_text()), expected)
        samples = json.loads((root / "query-pages-v1.json").read_text())
        for event in [samples["events"]["items"][0]["event"], *samples["metrics"]]:
            self.assertEqual(DiagnosticEventV1.model_validate_json(json.dumps(event)).model_dump(mode="json"), event)
        for item in samples["index"]["items"]:
            DiagnosticHarnessIndexV1.model_validate_json(json.dumps(item))
        for item in samples["links"]["items"]:
            DiagnosticOperationLinkV1.model_validate_json(json.dumps(item))

    def test_filters_linked_operations_time_offsets_and_cursor_boundaries(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.sqlite3")
            store.start()
            self.addCleanup(store.close)
            operation = "harness-operation-" + "a" * 32
            base = dict(source="server", request_id="request", timestamp="2026-09-10T08:00:00+08:00")
            for event in [
                DiagnosticEventV1(**base, event_id="started", name="request_started"),
                DiagnosticEventV1(**base, event_id="reference", name="harness_reference", harness=DiagnosticHarnessReferenceV1(operation_id=operation, workflow=HarnessWorkflow("persona"), stage=HarnessStage("persona_generation"))),
                DiagnosticEventV1(**base, event_id="failed", name="request_failed"),
                DiagnosticEventV1(event_id="unrelated", name="request_finished", source="server", request_id="other", timestamp="2026-09-10T00:00:01Z"),
            ]:
                store.enqueue(event)
            store.queue.join()
            app = FastAPI()
            app.state.diagnostics = store
            app.include_router(router)
            with TestClient(app) as client:
                first = client.get("/diagnostics/events", params={"operation_id": operation, "limit": 2}).json()
                self.assertTrue(first["has_more"])
                self.assertEqual([r["event"]["event_id"] for r in first["items"]], ["started", "reference"])
                second = client.get("/diagnostics/events", params={"operation_id": operation, "after": first["next_cursor"], "limit": 2}).json()
                self.assertFalse(second["has_more"])
                self.assertEqual([r["event"]["event_id"] for r in second["items"]], ["failed"])
                for filters in ({"workflow": "persona"}, {"stage": "persona_generation"}, {"since": "2026-09-10T00:00:00Z", "until": "2026-09-10T00:00:01Z"}):
                    self.assertEqual(len(client.get("/diagnostics/events", params=filters).json()["items"]), 3)
                self.assertEqual(len(client.get("/diagnostics/events", params={"severity": "error", "operation_id": operation}).json()["items"]), 1)
                self.assertEqual(client.get("/diagnostics/events", params={"workflow": "study_chat"}).json()["items"], [])
                for filters in ({"since": "2026-09-10"}, {"since": "2026-09-11T00:00:00Z", "until": "2026-09-10T00:00:00Z"}, {"workflow": "invented"}, {"limit": 101}):
                    self.assertEqual(client.get("/diagnostics/events", params=filters).status_code, 422)
                self.assertEqual(store.health()["read_failures"], 0)

    def test_unavailable_and_corrupt_store_do_not_masquerade_as_empty_or_echo_content(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.sqlite3")
            app = FastAPI()
            app.state.diagnostics = store
            app.include_router(router)
            with TestClient(app) as client:
                response = client.get("/diagnostics/events")
                self.assertEqual(response.status_code, 503)
                self.assertFalse(store.path.exists())
                store.start()
                store.emit("lifecycle_started")
                store.queue.join()
                store.close()
                with sqlite3.connect(store.path) as db:
                    db.execute("UPDATE events SET payload=?", ('{"PRIVATE_CONTENT": "PRIVATE_SECRET"}',))
                response = client.get("/diagnostics/events")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("PRIVATE", response.text)
                self.assertEqual(store.read_failures, 2)
                self.assertEqual(store.write_failures, 0)
                operation = "harness-operation-" + "a" * 32
                with sqlite3.connect(store.path) as db:
                    db.execute("INSERT INTO operation_links(operation_id,request_id,payload) VALUES (?,?,?)", (operation, "request", '{"PRIVATE_CONTENT":"PRIVATE_SECRET"}'))
                links = client.get("/diagnostics/operation-links", params={"operation_id": operation})
                self.assertEqual(links.json()["gap"], "diagnostic_store_unavailable")
                self.assertNotIn("PRIVATE", links.text)
            index = DiagnosticHarnessIndex(None, root / "absent-index.sqlite3")
            result = index.query(workflow="persona")
            self.assertEqual(result["coverage"]["freshness"], "unavailable")
            self.assertFalse(index.path.exists())
