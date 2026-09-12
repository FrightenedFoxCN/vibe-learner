from datetime import datetime, timezone, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import sqlite3
import subprocess
import sys
import unittest

from app.core.diagnostic_record_retention import DiagnosticRecordRetention
from app.core.diagnostics import DiagnosticStore
from app.services.diagnostic_index import DiagnosticHarnessIndex


class DiagnosticRecordRetentionTests(unittest.TestCase):
    def test_legacy_migration_utf8_budget_and_atomic_cleanup_counts(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE operation_links (operation_id TEXT, request_id TEXT, payload TEXT)")
            db.execute("INSERT INTO operation_links VALUES ('op','a','汉字')")
            policy = DiagnosticRecordRetention("operation_links", max_rows=2, max_payload_bytes=12)
            policy.initialize(db)
            db.commit()
            before = policy.coverage(db)
            self.assertEqual(before["legacy_timestamp_rows"], 1)
            self.assertEqual(before["retained_payload_bytes"], 6)
            for i in range(3):
                db.execute("INSERT INTO operation_links(operation_id,request_id,payload) VALUES ('op',?,'汉字')", (str(i),))
                policy.prune(db)
            coverage = policy.coverage(db)
            self.assertEqual((coverage["retained_rows"], coverage["retained_payload_bytes"], coverage["removed_rows"]), (2, 12, 2))
            db.rollback()
            self.assertEqual(policy.coverage(db), before)
            policy.initialize(db)
            self.assertEqual(policy.coverage(db), before)
            db.execute("UPDATE operation_links SET retained_at=1")
            # Updating a payload does not renew an existing request's age.
            db.execute("UPDATE operation_links SET payload='更新'")
            policy.prune(db)
            self.assertEqual(policy.coverage(db)["retained_rows"], 0)
            self.assertEqual(policy.coverage(db)["removed_rows"], 1)

    def test_store_prunes_links_in_event_transaction_and_persists_counts(self):
        from app.models.diagnostic import DiagnosticEventV1, DiagnosticHarnessReferenceV1
        from app.models.harness import HarnessWorkflow, HarnessStage
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            store.link_retention = DiagnosticRecordRetention("operation_links", max_rows=2)
            store.start()
            self.addCleanup(store.close)
            for i in range(5):
                store.enqueue(DiagnosticEventV1(event_id=f"event-{i}", request_id=f"request-{i}", source="server", name="harness_reference", timestamp="2099-01-01T00:00:00Z", harness=DiagnosticHarnessReferenceV1(operation_id="harness-operation-" + "a" * 32, workflow=HarnessWorkflow("persona"), stage=HarnessStage("persona_generation"))))
            store.queue.join()
            store.close()
            self.assertEqual(store.write_failures, 0)
            with sqlite3.connect(store.path) as db:
                self.assertEqual(store.link_retention.coverage(db)["removed_rows"], 3)
                self.assertEqual([r[0] for r in db.execute("SELECT request_id FROM operation_links ORDER BY request_id")], ["request-3", "request-4"])
            self.assertEqual(len(store.query(0, 100, {}, strict=True)), 5)
            restarted = DiagnosticStore(store.path)
            restarted.start()
            restarted.emit("lifecycle_started")
            restarted.queue.join()
            restarted.close()
            with sqlite3.connect(store.path) as db:
                self.assertEqual(restarted.link_retention.coverage(db)["removed_rows"], 3)

    def test_index_source_age_excludes_old_rows_across_sweeps_and_latest_rows_fit_cap(self):
        now = datetime.now(timezone.utc)
        projections = {f"trace-{i}": dict(trace_id=f"trace-{i}", source_updated_at=(now - timedelta(days=8) if i == 0 else now - timedelta(seconds=10-i)).isoformat(), gap="terminal_trace_not_available") for i in range(5)}
        repository = SimpleNamespace(list_trace_ids=lambda after, limit: [key for key in sorted(projections) if key > after][:limit], get=lambda identity: projections[identity])
        with TemporaryDirectory() as directory:
            index = DiagnosticHarnessIndex(repository, Path(directory) / "index.db", retention=DiagnosticRecordRetention("projections", max_rows=2))
            with patch("app.services.diagnostic_index.project_execution", side_effect=lambda value: value):
                for _ in range(3):
                    index.step()
                    self.assertEqual([row["trace_id"] for row in index.query()["items"]], ["trace-3", "trace-4"])
                # Real canonical update can bring a previously old trace back.
                projections["trace-0"]["source_updated_at"] = now.isoformat()
                index.step()
                self.assertEqual([row["trace_id"] for row in index.query()["items"]], ["trace-0", "trace-4"])
            self.assertEqual(len(projections), 5)
            with index._connect() as db:
                self.assertEqual(index.retention.coverage(db)["retained_rows"], 2)
                self.assertGreater(index.retention.coverage(db)["removed_rows"], 0)

    def test_unchanged_future_source_does_not_refresh_retained_row_each_sweep(self):
        projection = dict(trace_id="trace", source_updated_at="2099-01-01T00:00:00Z", gap="terminal_trace_not_available")
        repository = SimpleNamespace(list_trace_ids=lambda after, limit: ["trace"], get=lambda identity: projection)
        with TemporaryDirectory() as directory:
            index = DiagnosticHarnessIndex(repository, Path(directory) / "index.db")
            with patch("app.services.diagnostic_index.project_execution", return_value=projection):
                index.step()
                with index._connect() as db:
                    db.execute("UPDATE projections SET retained_at=CAST(strftime('%s','now') AS INTEGER)-20")
                    expected = db.execute("SELECT retained_at FROM projections").fetchone()[0]
                    db.commit()
                index.step()
                with index._connect() as db:
                    self.assertEqual(db.execute("SELECT retained_at FROM projections").fetchone()[0], expected)

    def test_real_process_loss_rolls_back_prune_and_counter_together(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "records.db"
            policy = DiagnosticRecordRetention("operation_links")
            with sqlite3.connect(path) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE operation_links (operation_id TEXT,request_id TEXT,payload TEXT)")
                policy.initialize(db)
                db.execute("INSERT INTO operation_links(operation_id,request_id,payload) VALUES ('op','request','{}')")
                db.commit()
            script = """
import sqlite3,sys,os
from app.core.diagnostic_record_retention import DiagnosticRecordRetention
with sqlite3.connect(sys.argv[1]) as db:
    db.execute('UPDATE operation_links SET retained_at=1')
    DiagnosticRecordRetention('operation_links').prune(db)
    if sys.argv[2]=='commit': db.commit()
    os._exit(0)
"""
            for mode, expected in (("rollback", (1, 0)), ("commit", (0, 1))):
                subprocess.run([sys.executable, "-c", script, str(path), mode], check=True, timeout=10)
                with sqlite3.connect(path) as db:
                    result = policy.coverage(db)
                    self.assertEqual((result["retained_rows"], result["removed_rows"]), expected)
