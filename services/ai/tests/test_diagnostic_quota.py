from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import subprocess
import sys
import unittest

from app.core.diagnostic_quota import DiagnosticDatabaseQuota, DiagnosticQuotaExceeded
from app.core.diagnostic_disk import DiagnosticDiskMaintenance
from app.core.diagnostics import DiagnosticStore


class DiagnosticQuotaTests(unittest.TestCase):
    def test_pinned_reader_stops_admission_below_budget_and_recovers_after_release(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            store = DiagnosticStore(path)
            store.quota.max_bytes = 2 * 1024 * 1024
            store.start()
            self.addCleanup(store.close)
            store.emit("lifecycle_started")
            store.queue.join()
            with sqlite3.connect(path) as reader:
                reader.execute("BEGIN")
                initial = reader.execute("SELECT count(*) FROM events").fetchone()[0]
                for _ in range(150):
                    store.emit("lifecycle_started")
                    store.queue.join()
                    self.assertLessEqual(sum(store.quota.sizes().values()), store.quota.max_bytes)
                self.assertGreater(store.quota.rejected, 0)
                self.assertGreater(store.dropped, 0)
                self.assertEqual(reader.execute("SELECT count(*) FROM events").fetchone()[0], initial)
                reader.rollback()
            with sqlite3.connect(path) as db:
                store.disk_maintenance.maintain(db, force=True)
            before = len(store.query(0, 100, {}, strict=True))
            store.emit("lifecycle_started")
            store.queue.join()
            self.assertEqual(len(store.query(0, 100, {}, strict=True)), before + 1)
            store.close()
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertGreater(db.execute("SELECT observed_dropped FROM diagnostic_writers").fetchone()[0], 0)

    def test_staged_over_budget_transaction_does_not_spill_or_commit(self):
        with TemporaryDirectory() as directory, sqlite3.connect(Path(directory) / "test.db") as db:
            path = Path(directory) / "test.db"
            quota = DiagnosticDatabaseQuota(path, max_bytes=512 * 1024)
            disk = DiagnosticDiskMaintenance()
            disk.configure(db)
            db.execute("PRAGMA journal_mode=WAL")
            with quota.transaction(db):
                db.execute("CREATE TABLE records (value BLOB)")
            before = quota.sizes()["wal"]
            with self.assertRaises((DiagnosticQuotaExceeded, sqlite3.OperationalError)):
                with quota.transaction(db):
                    db.execute("INSERT INTO records VALUES (zeroblob(300000))")
            self.assertFalse(db.in_transaction)
            self.assertEqual(quota.sizes()["wal"], before)
            self.assertEqual(db.execute("SELECT count(*) FROM records").fetchone()[0], 0)
            self.assertLessEqual(sum(quota.sizes().values()), quota.max_bytes)

    def test_process_lock_is_released_after_crash_without_deleting_inode(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "test.db"
            quota = DiagnosticDatabaseQuota(path)
            script = """
import sys,os
from pathlib import Path
from app.core.diagnostic_quota import DiagnosticDatabaseQuota
with DiagnosticDatabaseQuota(Path(sys.argv[1])).lock():
    print('locked',flush=True)
    sys.stdin.read(1)
    os._exit(0)
"""
            process = subprocess.Popen([sys.executable, "-c", script, str(path)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
            try:
                self.assertEqual(process.stdout.readline().strip(), "locked")
                with self.assertRaises(DiagnosticQuotaExceeded):
                    with quota.lock():
                        self.fail("lock must be exclusive")
                process.communicate("x", timeout=5)
                self.assertEqual(process.returncode, 0)
                with quota.lock():
                    self.assertTrue(Path(str(path) + ".quota-lock").exists())
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()

    def test_existing_oversized_file_is_refused_without_truncation(self):
        with TemporaryDirectory() as directory, sqlite3.connect(Path(directory) / "test.db") as db:
            path = Path(directory) / "test.db"
            db.execute("CREATE TABLE records(value BLOB)")
            db.execute("INSERT INTO records VALUES (zeroblob(700000))")
            db.commit()
            db.execute("PRAGMA journal_mode=WAL")
            before = path.stat().st_size
            quota = DiagnosticDatabaseQuota(path, max_bytes=512 * 1024)
            with self.assertRaises(DiagnosticQuotaExceeded):
                with quota.transaction(db):
                    db.execute("DELETE FROM records")
            self.assertEqual(path.stat().st_size, before)
            self.assertEqual(db.execute("SELECT count(*) FROM records").fetchone()[0], 1)

    def test_business_and_canonical_commit_survive_diagnostic_quota_pressure(self):
        from fastapi.testclient import TestClient
        from app.app_factory import create_app
        from app.core.settings import Settings
        from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(settings=Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}", ocr_engine="disabled"))
            with TestClient(app) as client:
                store = app.state.diagnostics
                # Force rejection in the real admitted writer without altering
                # business middleware/provider/runtime ownership.
                original = store.quota.max_bytes
                store.quota.max_bytes = 1
                try:
                    response = client.post("/persona-cards/generate", json={"mode": "keywords", "input_text": "teacher"})
                    self.assertEqual(response.status_code, 200, response.text)
                    store.queue.join()
                    self.assertGreater(store.dropped, 0)
                    self.assertGreater(store.quota.rejected, 0)
                    repository = HarnessRuntimeRepository(app.state.container.database)
                    traces = [repository.get(identity) for identity in repository.list_trace_ids(after="", limit=100)]
                    self.assertTrue(traces)
                    self.assertTrue(all(item.terminal_trace is not None for item in traces))
                finally:
                    store.quota.max_bytes = original
                store.emit("lifecycle_started")
                store.queue.join()
                self.assertEqual(client.get("/health").status_code, 200)

    def test_guarded_incremental_vacuum_preserves_limit_and_records(self):
        with TemporaryDirectory() as directory, sqlite3.connect(Path(directory) / "test.db") as db:
            quota = DiagnosticDatabaseQuota(Path(directory) / "test.db", max_bytes=4 * 1024 * 1024)
            disk = DiagnosticDiskMaintenance(vacuum_pages=4096)
            disk.quota = quota
            disk.configure(db)
            db.execute("PRAGMA journal_mode=WAL")
            with quota.transaction(db):
                db.execute("CREATE TABLE records(id INTEGER PRIMARY KEY,value BLOB)")
                db.executemany("INSERT INTO records(value) VALUES (zeroblob(8192))", [()] * 128)
            disk.maintain(db, force=True)
            with quota.transaction(db):
                db.execute("DELETE FROM records WHERE id>1")
            disk.maintain(db, force=True)
            self.assertEqual(disk.failures, 0)
            self.assertEqual(db.execute("PRAGMA freelist_count").fetchone()[0], 0)
            self.assertLessEqual(sum(quota.sizes().values()), quota.max_bytes)
            self.assertEqual(db.execute("SELECT count(*) FROM records").fetchone()[0], 1)

    def test_non_wal_connection_is_rejected_before_write(self):
        with TemporaryDirectory() as directory, sqlite3.connect(Path(directory) / "test.db") as db:
            quota = DiagnosticDatabaseQuota(Path(directory) / "test.db")
            with self.assertRaisesRegex(DiagnosticQuotaExceeded, "requires_wal"):
                with quota.transaction(db):
                    db.execute("CREATE TABLE should_not_exist(value INTEGER)")
            self.assertFalse(db.in_transaction)
            self.assertEqual(db.execute("SELECT count(*) FROM sqlite_master").fetchone()[0], 0)
