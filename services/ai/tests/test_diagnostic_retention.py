import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from app.core.diagnostics import DiagnosticStore
from app.core.diagnostic_retention import DiagnosticEventRetention
from app.models.diagnostic import DiagnosticEventV1


class DiagnosticRetentionTests(unittest.TestCase):
    def legacy(self, path, count=3):
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)")
            for i in range(count):
                event = DiagnosticEventV1(event_id=f"event_{i}", source="server", name="request_finished", timestamp="2099-01-01T00:00:00Z")
                db.execute("INSERT INTO events(event_id,payload) VALUES (?,?)", (event.event_id, event.model_dump_json()))

    def test_legacy_migration_row_retention_restart_and_transactional_loss_counters(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            self.legacy(path)
            policy = DiagnosticEventRetention(max_rows=2)
            with sqlite3.connect(path) as db:
                policy.initialize(db)
                db.commit()
                first = policy.coverage(db, 0)
                self.assertEqual(first["legacy_timestamp_rows"], 3)
                self.assertEqual(first["retained_events"], 2)
                self.assertEqual(first["removed_events"], 1)
                self.assertEqual(first["removed_through_sequence"], 1)
                self.assertTrue(first["cursor_gap"])
                self.assertFalse(policy.coverage(db, 1)["cursor_gap"])
                # Counter and deletions roll back together on failed maintenance.
                db.execute("UPDATE events SET ingested_at=1")
                policy.prune(db)
                self.assertEqual(policy.coverage(db, 0)["retained_events"], 0)
                db.rollback()
                self.assertEqual(policy.coverage(db, 0), first)
            with sqlite3.connect(path) as db:
                policy.initialize(db)
                self.assertEqual(policy.coverage(db, 0), first)

    def test_source_clock_cannot_extend_retention_and_utf8_byte_budget_is_exact(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            self.legacy(path, 0)
            policy = DiagnosticEventRetention(max_payload_bytes=8)
            with sqlite3.connect(path) as db:
                policy.initialize(db)
                # Retention operates on byte accounting without exposing contents.
                for i in range(3):
                    db.execute("INSERT INTO events(event_id,payload) VALUES (?,?)", (str(i), "汉字"))
                    policy.prune(db)
                coverage = policy.coverage(db, 0)
                self.assertEqual(coverage["retained_events"], 1)
                self.assertEqual(coverage["retained_payload_bytes"], 6)
                self.assertEqual(coverage["removed_events"], 2)
                db.execute("UPDATE events SET ingested_at=unixepoch('now')-604801")
                policy.prune(db)
                self.assertEqual(policy.coverage(db, 0)["retained_events"], 0)
                self.assertEqual(policy.coverage(db, 0)["removed_events"], 3)

    def test_async_and_native_writes_share_limits_and_query_coverage_snapshot(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            store = DiagnosticStore(path, retention=DiagnosticEventRetention(max_rows=2))
            store.start()
            for i in range(3):
                store.enqueue(DiagnosticEventV1(event_id=f"event_{i}", source="server", name="request_finished", timestamp="2099-01-01T00:00:00Z"))
            store.queue.join()
            store.close()
            self.assertTrue(store.persist_external_event(DiagnosticEventV1(event_id="native", source="desktop", name="desktop_started", timestamp="1999-01-01T00:00:00Z")))
            rows, coverage = store.query(0, 100, {}, strict=True, with_coverage=True)
            self.assertEqual([row["event"]["event_id"] for row in rows], ["event_2", "native"])
            self.assertEqual(coverage["removed_events"], 2)
            self.assertTrue(coverage["cursor_gap"])
            self.assertEqual(coverage["retained_events"], len(rows))
            with sqlite3.connect(path) as db:
                measured = db.execute("SELECT sum(length(cast(payload AS BLOB))) FROM events").fetchone()[0]
            self.assertEqual(coverage["retained_payload_bytes"], measured)

    def test_process_exit_before_and_after_commit_preserves_matching_loss_evidence(self):
        import subprocess
        import sys
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            self.legacy(path)
            with sqlite3.connect(path) as db:
                DiagnosticEventRetention().initialize(db)
                db.commit()
            script = """
import os, sqlite3, sys
from app.core.diagnostic_retention import DiagnosticEventRetention
connection = sqlite3.connect(sys.argv[1])
DiagnosticEventRetention(max_rows=1).prune(connection)
if sys.argv[2] == 'commit': connection.commit()
os._exit(9)
"""
            for mode, expected_rows, expected_removed in (("rollback", 3, 0), ("commit", 1, 2)):
                result = subprocess.run([sys.executable, "-c", script, str(path), mode], check=False, capture_output=True)
                self.assertEqual(result.returncode, 9)
                with sqlite3.connect(path) as db:
                    coverage = DiagnosticEventRetention().coverage(db, 0)
                    self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], expected_rows)
                    self.assertEqual(coverage["retained_events"], expected_rows)
                    self.assertEqual(coverage["removed_events"], expected_removed)


    def test_restart_recovers_interrupted_add_column_migration_without_expiring_legacy_rows(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            self.legacy(path)
            with sqlite3.connect(path) as db:
                # A prior process died after SQLite committed the schema change.
                db.execute("ALTER TABLE events ADD COLUMN ingested_at INTEGER NOT NULL DEFAULT 0")
            with sqlite3.connect(path) as db:
                policy = DiagnosticEventRetention()
                policy.initialize(db)
                coverage = policy.coverage(db, 0)
                self.assertEqual(coverage["retained_events"], 3)
                self.assertEqual(coverage["removed_events"], 0)
                self.assertEqual(coverage["legacy_timestamp_rows"], 3)
