from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.app_factory import create_app
from app.core.settings import Settings
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.diagnostic_index import DiagnosticHarnessIndex


class DiagnosticIndexTests(unittest.TestCase):
    def test_projection_preserves_nullable_revisions_and_sequence_without_digest(self):
        from datetime import datetime, timezone
        from types import SimpleNamespace
        from app.models.harness import HarnessResourceRefV3, HarnessCommittedResourceRefV3
        from app.services.diagnostic_index import project_execution
        ref = HarnessResourceRefV3.model_validate_json('{"resource_type":"study_session","resource_id":"session","revision":null}')
        committed = HarnessCommittedResourceRefV3.model_validate_json(json.dumps(dict(
            resource_type="study_session", resource_id="session", expected_revision=4,
            committed_revision=5, first_sequence=9, last_sequence=9, payload_digest="a" * 64)))
        now = datetime.now(timezone.utc)
        execution = SimpleNamespace(trace_id="trace", parent_trace_id=None, harness_operation_id=None,
            workflow=SimpleNamespace(value="study"), stage=SimpleNamespace(value="study_chat"),
            state=SimpleNamespace(value="terminal"), updated_at=now, attempt_records=[],
            context=SimpleNamespace(subject_refs=[ref], component_versions=[]),
            terminal_trace=SimpleNamespace(status=SimpleNamespace(value="passed"), duration_ms=1,
                started_at=now, completed_at=now, commit_evidence=SimpleNamespace(
                    status=SimpleNamespace(value="committed"), attempted_resource_refs=[ref], committed_resources=[committed])))
        projected = project_execution(execution)
        # This adapter test does not assert a domain commit; its input resources are typed.
        resources = projected["resources"]
        self.assertIsNone(resources["context_subjects"][0]["revision"])
        self.assertIsNone(resources["attempted_outputs"][0]["revision"])
        self.assertEqual(resources["committed_outputs"][0], dict(resource_type="study_session",
            resource_id="session", expected_revision=4, committed_revision=5, first_sequence=9, last_sequence=9))
        execution.terminal_trace = None
        projected = project_execution(execution)
        self.assertEqual(projected["resources"]["committed_outputs"], [])
        self.assertEqual(projected["resources"]["attempted_outputs"], [])
        self.assertEqual(projected["gap"], "terminal_trace_not_available")

    def test_restart_deduplication_late_rows_fault_isolation_and_content_exclusion(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(settings=Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}", ocr_engine="disabled"))
            with TestClient(app) as client:
                app.state.diagnostic_index.close()
                response = client.post("/persona-cards/generate", json={"mode": "keywords", "input_text": "SECRET_INDEX_INPUT"},
                                       headers={"X-Debug-Flow-Id": "flow", "X-Debug-Action-Id": "generation"})
                self.assertEqual(response.status_code, 200, response.text)
                store = app.state.diagnostics
                store.queue.join()
                repo = HarnessRuntimeRepository(app.state.container.database)
                index = DiagnosticHarnessIndex(repo, root / "index.sqlite3")
                self.assertEqual(index.step(1), 1)
                first = index.query()["items"][0]
                self.assertEqual(first["gap"], None)
                self.assertEqual(index.query(workflow=first["workflow"], stage=first["stage"])["items"], [first])
                self.assertEqual(index.query(workflow="not_the_workflow")["items"], [])
                self.assertFalse(index.query()["has_more"])
                self.assertTrue(first["attempts"])
                self.assertIsNone(first["resources_gap"])
                execution = repo.get(first["trace_id"])
                self.assertEqual(first["resources"]["context_subjects"], [item.model_dump(mode="json") for item in execution.context.subject_refs])
                self.assertEqual(first["resources"]["committed_outputs"], [item.model_dump(mode="json", exclude={"payload_digest"}) for item in execution.terminal_trace.commit_evidence.committed_resources])
                self.assertNotIn("payload_digest", json.dumps(first["resources"]))
                # Old projections are explicitly incomplete until a canonical sweep backfills them.
                with sqlite3.connect(index.path) as db:
                    db.execute("UPDATE projections SET payload=json_remove(payload,'$.resources','$.resources_gap')")
                legacy = index.query()["items"][0]
                self.assertIsNone(legacy["resources"])
                self.assertEqual(legacy["resources_gap"], "not_backfilled")
                index.step(1)
                index.step(1)
                self.assertEqual(index.query()["items"], [first])
                self.assertEqual(first["usage_gap"], "not_recorded_in_canonical_trace")
                self.assertIsNone(first["model"])
                self.assertNotIn("SECRET_INDEX_INPUT", json.dumps(first))
                links = store.operation_links(first["operation_id"])
                self.assertEqual(len(links["items"]), 1)  # admission + terminal + attempts deduplicate
                self.assertEqual(links["items"][0]["flow_id"], "flow")
                # Event-list retention does not erase the separately persisted correlation link.
                from app.core.diagnostics import DiagnosticStore
                with sqlite3.connect(store.path) as db:
                    db.execute("DELETE FROM events")
                self.assertEqual(DiagnosticStore(store.path).operation_links(first["operation_id"]), links)
                linked = client.get("/diagnostics/operation-links", params={"operation_id": first["operation_id"]})
                self.assertEqual(linked.json()["items"], links["items"])

                # The cursor is durable, and replaying the same sweep never duplicates a trace.
                restarted = DiagnosticHarnessIndex(repo, index.path)
                self.assertEqual(restarted.step(1), 0)
                restarted.step(1)
                self.assertEqual(restarted.query()["items"], [first])
                with app.state.container.database.engine.connect() as db:
                    before = db.execute(text("SELECT terminal_trace_digest FROM harness_runtime_executions ORDER BY trace_id")).all()
                # An unavailable source becomes an explicit gap, and can recover in a later sweep.
                restarted.step(1)
                with patch.object(repo, "get", side_effect=RuntimeError("PRIVATE_FAILURE")):
                    restarted.step(1)
                self.assertEqual(restarted.query()["items"][0]["gap"], "source_invalid_or_unavailable")
                restarted.step(1)
                restarted.step(1)
                self.assertEqual(restarted.query()["items"], [first])
                with app.state.container.database.engine.connect() as db:
                    after = db.execute(text("SELECT terminal_trace_digest FROM harness_runtime_executions ORDER BY trace_id")).all()
                self.assertEqual(before, after)
                # A new commit behind the persisted cursor is found by the next sweep.
                with sqlite3.connect(index.path) as db:
                    db.execute("UPDATE checkpoint SET cursor='zzzz' WHERE name='runtime'")
                response = client.post("/persona-cards/generate", json={"mode": "keywords", "input_text": "second"})
                self.assertEqual(response.status_code, 200)
                restarted.step()
                restarted.step()
                self.assertEqual(len(restarted.query()["items"]), 2)
                self.assertEqual(len(restarted.query(operation_id=first["operation_id"])["items"]), 1)
                app.state.diagnostic_index = restarted
                response = client.get("/diagnostics/harness-index", params={"operation_id": first["operation_id"]})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(len(response.json()["items"]), 1)
                self.assertTrue(response.json()["coverage"]["canonical_read_back_required"])

                # A completed sweep missing an earlier source cannot keep claiming its old status.
                with patch.object(repo, "list_trace_ids", return_value=()):
                    restarted.step()
                vanished = restarted.query()["items"]
                self.assertTrue(all(item["gap"] == "source_removed" and item["commit_status"] is None for item in vanished))
                self.assertTrue(all(item["resources"] is None and item["resources_gap"] == "source_removed" for item in vanished))
                restarted.step()
                self.assertTrue(all(item["gap"] is None for item in restarted.query()["items"]))
                broken = DiagnosticHarnessIndex(repo, root)  # directory instead of database
                self.assertEqual(broken.query()["coverage"]["freshness"], "unavailable")
                self.assertEqual(client.get("/health").status_code, 200)
