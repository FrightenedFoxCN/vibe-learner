from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import sqlite3
import unittest

from app.core.diagnostic_recovery import DiagnosticOversizeRecovery
from app.core.diagnostics import DiagnosticStore
from app.models.diagnostic import DiagnosticEventV1
from app.services.diagnostic_index import DiagnosticHarnessIndex


class DiagnosticRecoveryTests(unittest.TestCase):
    def test_schema_quota_contention_retries_and_drains_accepted_event(self):
        from threading import Event
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.sqlite3")
            original = store._initialize_schema
            ready = Event()
            calls = 0

            def initialize(db):
                nonlocal calls
                calls += 1
                if calls == 1:
                    # A separate descriptor holds the actual admission lock after
                    # configure succeeds, reproducing the native startup window.
                    with store.quota.lock():
                        return original(db)
                original(db)
                ready.set()

            with patch.object(store, "_initialize_schema", side_effect=initialize):
                store.emit("lifecycle_started")
                store.start()
                try:
                    self.assertTrue(ready.wait(4))
                finally:
                    store.close()
            self.assertGreaterEqual(calls, 2)
            self.assertGreaterEqual(store.write_failures, 1)
            self.assertEqual(store.dropped, 0)
            self.assertEqual(len(store.query(0, 100, {})), 1)

    def test_close_during_schema_refusal_stops_retry_and_accounts_queue(self):
        from threading import Event
        from app.core.diagnostic_quota import DiagnosticQuotaExceeded
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.sqlite3")
            refused = Event()

            def initialize(db):
                refused.set()
                raise DiagnosticQuotaExceeded("diagnostic_quota_unavailable")

            with patch.object(store, "_initialize_schema", side_effect=initialize):
                store.emit("lifecycle_started")
                store.start()
                self.assertTrue(refused.wait(2))
                store.close()
            self.assertFalse(store.health()["writer_alive"])
            self.assertEqual(store.queue.unfinished_tasks, 0)
            self.assertEqual(store.dropped, 1)

    def seed_events(self, path, count=200):
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE NOT NULL,payload TEXT NOT NULL)")
            db.execute("CREATE TABLE operation_links(operation_id TEXT,request_id TEXT,payload TEXT NOT NULL,PRIMARY KEY(operation_id,request_id))")
            for i in range(count):
                event = DiagnosticEventV1(event_id=f"legacy-{i}", source="server", name="lifecycle_started", timestamp="2026-09-10T00:00:00Z")
                db.execute("INSERT INTO events(event_id,payload) VALUES (?,?)", (event.event_id, event.model_dump_json()))
            # Free pages reproduce a pre-vacuum legacy file without unreviewed
            # event content. They must be reclaimed without losing the suffix.
            db.execute("CREATE TABLE padding(value BLOB)")
            db.execute("INSERT INTO padding VALUES (zeroblob(2000000))")
            db.execute("DROP TABLE padding")
            db.commit()

    def test_real_event_writer_recovers_legacy_file_and_preserves_loss_evidence(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            self.seed_events(path)
            store = DiagnosticStore(path)
            store.retention.max_rows = 64
            store.quota.max_bytes = 1024 * 1024
            store.start(); self.addCleanup(store.close)
            store.emit("lifecycle_started"); store.queue.join(); store.close()
            self.assertEqual(store.oversize_recovery.completed, 1)
            from app.services.diagnostic_storage import observe_diagnostic_storage
            observation = observe_diagnostic_storage(store, None).databases[0].recovery
            self.assertEqual((observation.attempts, observation.completed), (1, 1))
            self.assertTrue(observation.temporary_overage_possible)
            self.assertEqual(store.write_failures, 0)
            self.assertLess(sum(store.quota.sizes().values()), store.quota.max_bytes)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("PRAGMA auto_vacuum").fetchone()[0], 2)
                self.assertEqual(db.execute("SELECT removed_events,removed_through_sequence FROM event_retention").fetchone(), (137, 137))
                self.assertEqual(db.execute("SELECT event_id FROM events ORDER BY sequence LIMIT 1").fetchone()[0], "legacy-137")
                self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 64)
            resumed = DiagnosticStore(path); resumed.quota.max_bytes = store.quota.max_bytes
            resumed.start(); resumed.emit("lifecycle_started"); resumed.queue.join(); resumed.close()
            self.assertEqual(resumed.oversize_recovery.attempts, 0)

    def test_real_index_recovers_without_changing_source_repository(self):
        class Source:
            calls = 0
            def list_trace_ids(self, **kwargs):
                self.calls += 1
                return []
        with TemporaryDirectory() as directory:
            path = Path(directory) / "index.db"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE projections(trace_id TEXT PRIMARY KEY,operation_id TEXT,workflow TEXT,stage TEXT,payload TEXT NOT NULL)")
                db.executemany("INSERT INTO projections(trace_id,payload) VALUES (?,?)", [(f"trace-{i:04d}", '{"gap":"source_removed"}') for i in range(200)])
                db.execute("CREATE TABLE padding(value BLOB)")
                db.execute("INSERT INTO padding VALUES (zeroblob(2000000))")
                db.execute("DROP TABLE padding"); db.commit()
            source = Source(); index = DiagnosticHarnessIndex(source, path)
            index.retention.max_rows = 64
            index.quota.max_bytes = 1024 * 1024
            self.assertEqual(index.step(), 0)
            self.assertEqual(source.calls, 1)
            self.assertEqual(index.oversize_recovery.completed, 1)
            with sqlite3.connect(path) as db:
                self.assertEqual(db.execute("SELECT removed_rows FROM diagnostic_record_retention").fetchone()[0], 136)
                self.assertEqual(db.execute("SELECT count(*) FROM projections").fetchone()[0], 64)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_pinned_reader_defers_then_same_connection_can_recover(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"; self.seed_events(path)
            store = DiagnosticStore(path); store.retention.max_rows = 64; store.quota.max_bytes = 1024 * 1024
            recovery = store.oversize_recovery; recovery.interval_seconds = 0
            with sqlite3.connect(path) as db, sqlite3.connect(path) as reader:
                db.execute("PRAGMA journal_mode=WAL")
                reader.execute("BEGIN"); reader.execute("SELECT count(*) FROM events").fetchone()
                db.execute("UPDATE events SET event_id=event_id WHERE sequence=1"); db.commit()
                self.assertFalse(recovery.recover(db))
                self.assertEqual(recovery.deferred, 1)
                self.assertEqual(reader.execute("SELECT count(*) FROM events").fetchone()[0], 200)
                reader.rollback()
                self.assertTrue(recovery.recover(db))
                self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 64)

    def test_space_refusal_deadline_and_owned_transaction_leave_database_valid(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"; self.seed_events(path)
            store = DiagnosticStore(path); store.retention.max_rows = 64; store.quota.max_bytes = 1024 * 1024
            recovery = store.oversize_recovery; recovery.interval_seconds = 0
            with sqlite3.connect(path) as db:
                with patch("app.core.diagnostic_recovery.shutil.disk_usage", return_value=type("Disk", (), {"free": 0})()):
                    self.assertFalse(recovery.recover(db))
                self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 200)
                recovery.budget_seconds = 0.000001
                self.assertFalse(recovery.recover(db))
                self.assertFalse(db.in_transaction)
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                db.execute("BEGIN IMMEDIATE")
                attempts = recovery.attempts
                self.assertFalse(recovery.recover(db))
                self.assertTrue(db.in_transaction)
                self.assertEqual(recovery.attempts, attempts)
                db.rollback(); recovery.budget_seconds = 5
                self.assertTrue(recovery.recover(db))

    def test_workspace_envelope_refuses_before_pruning(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"; self.seed_events(path)
            store = DiagnosticStore(path); store.retention.max_rows = 64; store.quota.max_bytes = 1024 * 1024
            recovery = DiagnosticOversizeRecovery(store.quota, lambda db: self.fail("must not prune"), workspace_bytes=1024)
            with sqlite3.connect(path) as db:
                self.assertFalse(recovery.recover(db))
                self.assertEqual(recovery.deferred, 1)
                self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 200)

    def test_process_crashes_around_retention_commit_and_during_vacuum_resume_once(self):
        import subprocess
        import sys
        script = '''
import os, sqlite3, sys
from pathlib import Path
from app.core.diagnostics import DiagnosticStore
path, phase = Path(sys.argv[1]), sys.argv[2]
store = DiagnosticStore(path)
store.retention.max_rows = 64
store.quota.max_bytes = 1024 * 1024
class CrashConnection(sqlite3.Connection):
    vacuum_active = False
    def set_progress_handler(self, callback, count):
        if callback is None:
            return super().set_progress_handler(None, count)
        def progress():
            if phase == "during_vacuum" and self.vacuum_active:
                os._exit(17)
            return callback()
        return super().set_progress_handler(progress, count)
    def execute(self, sql, *args):
        if sql == "VACUUM":
            if phase == "after_commit":
                os._exit(17)
            self.vacuum_active = True
        value = super().execute(sql, *args)
        self.vacuum_active = False
        return value
def prune(db):
    store._prune_for_recovery(db)
    if phase == "before_commit":
        os._exit(17)
store.oversize_recovery.prune = prune
with sqlite3.connect(path, factory=CrashConnection) as db:
    store.oversize_recovery.recover(db)
raise SystemExit(99)
'''
        for phase in ("before_commit", "after_commit", "during_vacuum"):
            with self.subTest(phase=phase), TemporaryDirectory() as directory:
                path = Path(directory) / "events.db"; self.seed_events(path)
                result = subprocess.run([sys.executable, "-c", script, str(path), phase], timeout=10, capture_output=True)
                self.assertEqual(result.returncode, 17, result.stderr.decode())
                store = DiagnosticStore(path); store.retention.max_rows = 64; store.quota.max_bytes = 1024 * 1024
                with sqlite3.connect(path) as db:
                    self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                    self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 200 if phase == "before_commit" else 64)
                    self.assertTrue(store.oversize_recovery.recover(db))
                    self.assertEqual(db.execute("SELECT removed_events,removed_through_sequence FROM event_retention").fetchone(), (136, 136))
                    self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 64)

    def test_running_writer_retries_after_startup_reader_releases(self):
        import time
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"; self.seed_events(path)
            with sqlite3.connect(path) as db, sqlite3.connect(path) as reader:
                db.execute("PRAGMA journal_mode=WAL")
                reader.execute("BEGIN"); reader.execute("SELECT count(*) FROM events").fetchone()
                db.execute("UPDATE events SET event_id=event_id WHERE sequence=1"); db.commit()
                store = DiagnosticStore(path); store.retention.max_rows = 64; store.quota.max_bytes = 1024 * 1024
                store.oversize_recovery.interval_seconds = 0
                self.addCleanup(store.close); store.start(); store.emit("lifecycle_started")
                deadline = time.monotonic() + 3
                while not store.oversize_recovery.deferred and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertGreater(store.oversize_recovery.deferred, 0)
                self.assertTrue(store._thread.is_alive())
                reader.rollback()
                deadline = time.monotonic() + 4
                while store.queue.unfinished_tasks and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(store.queue.unfinished_tasks, 0)
                self.assertEqual(store.oversize_recovery.completed, 1)
                store.close()


    def test_normal_admission_after_checkpoint_never_shortens_retention(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE sample(value INTEGER)")
                db.execute("INSERT INTO sample VALUES(1)"); db.commit()
                db.execute("PRAGMA journal_mode=WAL")
                store = DiagnosticStore(path)
                recovery = DiagnosticOversizeRecovery(store.quota, lambda db: self.fail("no pruning when ordinary admission fits"))
                self.assertTrue(recovery.recover(db))
                self.assertEqual(db.execute("SELECT value FROM sample").fetchone()[0], 1)

    def test_close_during_initialization_drains_accepted_events(self):
        import threading
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            entered, release = threading.Event(), threading.Event()
            configure = store._configure_database
            def paused(db):
                entered.set()
                if not release.wait(2):
                    raise RuntimeError("test_initialization_timeout")
                configure(db)
            with patch.object(store, "_configure_database", side_effect=paused):
                store.emit("lifecycle_started"); store.start()
                self.assertTrue(entered.wait(1))
                closer = threading.Thread(target=store.close)
                closer.start()
                try:
                    self.assertTrue(store._stop.wait(1))
                finally:
                    release.set(); closer.join(3)
                self.assertFalse(closer.is_alive())
                self.assertEqual(store.dropped, 0)
                self.assertEqual(store.queue.unfinished_tasks, 0)
                self.assertEqual(len(store.query(0, 100, {}, strict=True)), 1)

    def test_freelist_compaction_preserves_all_in_policy_events(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"; self.seed_events(path)
            store = DiagnosticStore(path); store.quota.max_bytes = 1024 * 1024
            with sqlite3.connect(path) as db:
                self.assertTrue(store.oversize_recovery.recover(db))
                self.assertEqual(db.execute("SELECT retained_events,removed_events FROM event_retention").fetchone(), (200, 0))
                self.assertLess(sum(store.quota.sizes().values()), store.quota.max_bytes)

    def test_pressure_suffix_is_only_used_when_compacted_records_still_block_admission(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"; self.seed_events(path, count=2000)
            store = DiagnosticStore(path); store.quota.max_bytes = 1024 * 1024
            with sqlite3.connect(path) as db:
                self.assertTrue(store.oversize_recovery.recover(db))
                self.assertEqual(db.execute("SELECT retained_events,removed_events FROM event_retention").fetchone(), (64, 1936))
                self.assertEqual(db.execute("SELECT event_id FROM events ORDER BY sequence LIMIT 1").fetchone()[0], "legacy-1936")
                self.assertLess(sum(store.quota.sizes().values()), store.quota.max_bytes)

    def test_same_directory_recoveries_share_one_workspace_without_blocking_normal_writes(self):
        import threading
        from app.core.diagnostic_quota import DiagnosticDatabaseQuota
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first_path, second_path = root / "events.db", root / "index.db"
            self.seed_events(first_path); self.seed_events(second_path)
            first = DiagnosticStore(first_path); first.quota.max_bytes = 1024 * 1024
            second = DiagnosticStore(second_path); second.quota.max_bytes = 1024 * 1024
            second.oversize_recovery.interval_seconds = 0
            entered, release = threading.Event(), threading.Event()
            result = []
            prune = first.oversize_recovery.prune
            def hold(db):
                entered.set()
                if not release.wait(3):
                    raise RuntimeError("test_recovery_timeout")
                prune(db)
            first.oversize_recovery.prune = hold
            def run():
                with sqlite3.connect(first_path) as db:
                    result.append(first.oversize_recovery.recover(db))
            worker = threading.Thread(target=run); worker.start()
            try:
                self.assertTrue(entered.wait(1))
                with sqlite3.connect(second_path) as db:
                    self.assertFalse(second.oversize_recovery.recover(db))
                    self.assertEqual(second.oversize_recovery.deferred, 1)
                    self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 200)
                normal_path = root / "normal.db"
                with sqlite3.connect(normal_path) as db:
                    db.execute("PRAGMA journal_mode=WAL")
                    with DiagnosticDatabaseQuota(normal_path).transaction(db):
                        db.execute("CREATE TABLE normal(value INTEGER)")
                    self.assertEqual(db.execute("SELECT count(*) FROM normal").fetchone()[0], 0)
            finally:
                release.set(); worker.join(5)
            self.assertEqual(result, [True])
            self.assertFalse(worker.is_alive())
            with sqlite3.connect(second_path) as db:
                self.assertTrue(second.oversize_recovery.recover(db))
            self.assertTrue((root / "recovery.quota-lock").exists())

    def test_writer_close_releases_sqlite_handle_without_waiting_for_garbage_collection(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            connect = sqlite3.connect
            retained_handles = []
            def track(*args, **kwargs):
                db = connect(*args, **kwargs)
                retained_handles.append(db)
                return db
            with patch("app.core.diagnostics.sqlite3.connect", side_effect=track):
                store = DiagnosticStore(path)
                store.start(); store.emit("lifecycle_started"); store.queue.join(); store.close()
            self.assertTrue(retained_handles)
            with connect(path) as db:
                self.assertEqual(db.execute("PRAGMA journal_mode=DELETE").fetchone()[0], "delete")
                self.assertEqual(db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
