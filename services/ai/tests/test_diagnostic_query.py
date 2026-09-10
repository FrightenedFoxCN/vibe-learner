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
    def test_canonical_resource_filters_match_one_reference_role_and_page(self):
        from app.models.diagnostic_index import DiagnosticHarnessIndexV1
        with TemporaryDirectory() as directory:
            index = DiagnosticHarnessIndex(None, Path(directory) / "index.db")
            def projection(trace_id, subjects=(), attempted=(), committed=(), gap=None):
                return DiagnosticHarnessIndexV1.model_validate(dict(trace_id=trace_id,
                    resources=dict(context_subjects=list(subjects), attempted_outputs=list(attempted), committed_outputs=list(committed)),
                    resources_gap=gap)).model_dump_json()
            def ref(kind, identity):
                return dict(resource_type=kind, resource_id=identity, revision=None)
            with index._connect() as db:
                with index.quota.transaction(db):
                    for trace_id, payload in [
                        ("a", projection("a", [ref("document", "same"), ref("scene", "other")])),
                        ("b", projection("b", attempted=[ref("document", "same")])),
                        ("c", projection("c", committed=[dict(resource_type="learning_plan", resource_id="same")])),
                        ("d", projection("d", [ref("document", "same")], gap="not_backfilled")),
                        ("e", DiagnosticHarnessIndexV1(trace_id="e").model_dump_json()),
                    ]:
                        db.execute("INSERT INTO projections(trace_id,payload) VALUES (?,?)", (trace_id, payload))
            app = FastAPI(); app.include_router(router); app.state.diagnostic_index = index
            with TestClient(app) as client:
                path = "/diagnostics/harness-index"
                def read(**params):
                    result = client.get(path, params=params)
                    self.assertEqual(result.status_code, 200, result.text)
                    return result.json()
                first = read(resource_type="document", resource_id="same", limit=1)
                self.assertEqual([item["trace_id"] for item in first["items"]], ["a"])
                self.assertTrue(first["has_more"])
                second = read(resource_type="document", resource_id="same", limit=1, after=first["next_cursor"])
                self.assertEqual([item["trace_id"] for item in second["items"]], ["b"])
                self.assertFalse(second["has_more"])
                self.assertEqual(read(resource_type="document", resource_id="other")["items"], [])
                self.assertEqual(read(resource_type="scene", resource_id="same")["items"], [])
                self.assertEqual([item["trace_id"] for item in read(resource_role="attempted_outputs")["items"]], ["b"])
                self.assertEqual([item["trace_id"] for item in read(resource_id="same", resource_role="committed_outputs")["items"]], ["c"])
                self.assertEqual(read(resource_type="document", resource_role="committed_outputs")["items"], [])
                self.assertEqual(client.get(path, params={"resource_type": "invented"}).status_code, 422)
                self.assertEqual(client.get(path, params={"resource_role": "private"}).status_code, 422)
                self.assertEqual(client.get(path, params={"resource_id": "' OR 1=1"}).status_code, 422)

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
