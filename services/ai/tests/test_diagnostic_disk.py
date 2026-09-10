from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import unittest
from unittest.mock import patch

from app.core.diagnostic_disk import DiagnosticDiskMaintenance
from app.core.diagnostics import DiagnosticStore


class DiagnosticDiskTests(unittest.TestCase):
    def test_new_database_reclaims_freelist_and_wal_after_delete(self):
        with TemporaryDirectory() as directory, sqlite3.connect(Path(directory) / "records.db") as db:
            policy = DiagnosticDiskMaintenance(interval_seconds=0, vacuum_pages=4096)
            policy.configure(db)
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE payloads (id INTEGER PRIMARY KEY, payload BLOB)")
            db.executemany("INSERT INTO payloads(payload) VALUES (zeroblob(8192))", [()] * 128)
            db.commit()
            path = Path(directory) / "records.db"
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            before = path.stat().st_size
            db.execute("DELETE FROM payloads WHERE id>1")
            db.commit()
            self.assertGreater(db.execute("PRAGMA freelist_count").fetchone()[0], 0)
            policy.maintain(db, force=True)
            self.assertEqual(policy.failures, 0)
            self.assertEqual(db.execute("PRAGMA freelist_count").fetchone()[0], 0)
            self.assertLess(path.stat().st_size, before // 4)
            self.assertEqual(Path(str(path) + "-wal").stat().st_size, 0)
            self.assertEqual(db.execute("SELECT count(*) FROM payloads").fetchone()[0], 1)

    def test_reader_defers_checkpoint_then_later_cycle_recovers(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "records.db"
            with sqlite3.connect(path) as db, sqlite3.connect(path) as reader:
                policy = DiagnosticDiskMaintenance(interval_seconds=0)
                policy.configure(db)
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE sample(value INTEGER)")
                db.execute("INSERT INTO sample VALUES (1)")
                db.commit()
                reader.execute("BEGIN")
                self.assertEqual(reader.execute("SELECT value FROM sample").fetchone()[0], 1)
                db.execute("UPDATE sample SET value=2")
                db.commit()
                policy.maintain(db, force=True)
                self.assertEqual(policy.busy, 1)
                self.assertEqual(policy.failures, 0)
                self.assertEqual(reader.execute("SELECT value FROM sample").fetchone()[0], 1)
                reader.rollback()
                policy.maintain(db, force=True)
                self.assertEqual(policy.completed, 1)
                self.assertEqual(Path(str(path) + "-wal").stat().st_size, 0)
                self.assertEqual(reader.execute("SELECT value FROM sample").fetchone()[0], 2)

    def test_legacy_migration_preserves_records_and_resumes_after_interruption(self):
        with TemporaryDirectory() as directory, sqlite3.connect(Path(directory) / "legacy.db") as db:
            db.execute("CREATE TABLE sample(value BLOB)")
            db.executemany("INSERT INTO sample VALUES (zeroblob(8192))", [()] * 128)
            db.commit()
            policy = DiagnosticDiskMaintenance(interval_seconds=0, budget_seconds=0.000001)
            policy.configure(db)
            self.assertEqual(db.execute("PRAGMA auto_vacuum").fetchone()[0], 0)
            policy.maintain(db, force=True)
            self.assertGreater(policy.failures, 0)
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute("SELECT count(*) FROM sample").fetchone()[0], 128)
            policy.budget_seconds = 1
            policy.maintain(db, force=True)
            self.assertEqual(db.execute("PRAGMA auto_vacuum").fetchone()[0], 2)
            self.assertEqual(policy.legacy_migrations, 1)
            self.assertEqual(db.execute("SELECT count(*) FROM sample").fetchone()[0], 128)
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_active_transaction_is_never_committed_by_maintenance(self):
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE TABLE sample(value INTEGER)")
            db.execute("INSERT INTO sample VALUES (1)")
            policy = DiagnosticDiskMaintenance()
            policy.maintain(db, force=True)
            self.assertTrue(db.in_transaction)
            self.assertIsNone(policy.last_run)
            db.rollback()
            self.assertEqual(db.execute("SELECT count(*) FROM sample").fetchone()[0], 0)

    def test_maintenance_sql_failure_cannot_relabel_written_event(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            original = store.disk_maintenance.maintain
            class BrokenMaintenanceConnection:
                in_transaction = False
                def execute(self, *args):
                    raise sqlite3.OperationalError("PRIVATE_DISK_FAILURE")
                def set_progress_handler(self, *args):
                    pass
            with patch.object(store.disk_maintenance, "maintain", side_effect=lambda db, **kwargs: original(BrokenMaintenanceConnection(), force=True)):
                store.start()
                store.emit("lifecycle_started")
                store.queue.join()
                store.close()
            self.assertGreater(store.disk_maintenance.failures, 0)
            self.assertEqual(store.write_failures, 0)
            self.assertEqual(store.dropped, 0)
            self.assertEqual(len(store.query(0, 100, {}, strict=True)), 1)
            with sqlite3.connect(store.path) as db:
                self.assertEqual(db.execute("PRAGMA auto_vacuum").fetchone()[0], 2)

    def test_application_domain_commit_survives_maintenance_failures(self):
        from fastapi.testclient import TestClient
        from app.app_factory import create_app
        from app.core.settings import Settings
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(settings=Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}", ocr_engine="disabled"))
            original = DiagnosticDiskMaintenance.maintain
            class BrokenConnection:
                in_transaction = False
                def execute(self, *args):
                    raise sqlite3.OperationalError("PRIVATE_MAINTENANCE_FAILURE")
                def set_progress_handler(self, *args):
                    pass
            with patch.object(DiagnosticDiskMaintenance, "maintain", lambda policy, db, **kwargs: original(policy, BrokenConnection(), force=True)):
                with TestClient(app) as client:
                    response = client.post("/persona-cards/generate", json={"mode": "keywords", "input_text": "teacher"})
                    self.assertEqual(response.status_code, 200, response.text)
                    app.state.diagnostics.queue.join()
                    self.assertGreater(app.state.diagnostics.disk_maintenance.failures, 0)
                    self.assertEqual(app.state.diagnostics.write_failures, 0)
                    from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
                    repository = HarnessRuntimeRepository(app.state.container.database)
                    traces = [repository.get(identity) for identity in repository.list_trace_ids(after="", limit=100)]
                    self.assertTrue(traces)
                    self.assertTrue(all(item.terminal_trace is not None for item in traces))
                    self.assertEqual(client.get("/health").status_code, 200)
