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
                self.assertTrue(first["attempts"])
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
                restarted.step()
                self.assertTrue(all(item["gap"] is None for item in restarted.query()["items"]))
                broken = DiagnosticHarnessIndex(repo, root)  # directory instead of database
                self.assertEqual(broken.query()["coverage"]["freshness"], "unavailable")
                self.assertEqual(client.get("/health").status_code, 200)
