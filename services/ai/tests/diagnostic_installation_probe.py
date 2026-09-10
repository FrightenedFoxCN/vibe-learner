"""Provider-free cross-runtime probe; requires the compiled Rust library test binary.

Exercises real diagnostic writers and the native spool in a disposable directory.
Missing-source index rows are honest synthetic storage load, not Harness adoption
or domain-commit evidence. Observed samples do not prove an atomic peak.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
import threading
import time

from app.core.diagnostics import DiagnosticStore
from app.services.diagnostic_desktop_spool import DesktopDiagnosticSpool
from app.services.diagnostic_directory_storage import observe_diagnostic_directory
from app.services.diagnostic_index import DiagnosticHarnessIndex


class RemovedSource:
    active = False

    def list_trace_ids(self, *, after, limit):
        return [f"probe-{i:06d}" for i in range(3000) if f"probe-{i:06d}" > after][:limit] if self.active else []

    def get(self, trace_id):
        return None


def seed_freelist(path, megabytes):
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA auto_vacuum=NONE")
        db.execute("VACUUM")
        db.execute("CREATE TABLE probe_padding(value BLOB)")
        db.execute("INSERT INTO probe_padding VALUES (zeroblob(?))", (megabytes * 1024 * 1024,))
        db.execute("DROP TABLE probe_padding"); db.commit()
        db.execute("PRAGMA journal_mode=WAL")


def run(native_binary):
    with TemporaryDirectory() as directory:
        root = Path(directory)
        diagnostics = root / "diagnostics"; diagnostics.mkdir()
        event_path, index_path = diagnostics / "events.sqlite3", diagnostics / "harness-index.sqlite3"
        initial = DiagnosticStore(event_path)
        initial.start(); initial.emit("lifecycle_started"); initial.queue.join(); initial.close()
        source = RemovedSource()
        index = DiagnosticHarnessIndex(source, index_path); index.step()
        seed_freelist(event_path, 60); seed_freelist(index_path, 28)
        spool_root = diagnostics / "desktop-spool"; spool_root.mkdir()
        for i in range(256):
            event_id = f"desktop-{i:016x}"
            record = dict(schema_version="desktop-diagnostic-v1", event_id=event_id, instance_id="desktop-probe",
                          name="desktop_started", unix_time_ms=int(time.time() * 1000), duration_ms=None,
                          exit_code=None, dropped_before=0, write_failures_before=0)
            raw = json.dumps(record).encode()
            (spool_root / f"{event_id}.json").write_bytes(raw + b" " * (16384 - len(raw)))
        store = DiagnosticStore(event_path)
        spool = DesktopDiagnosticSpool(store, spool_root)
        stop = threading.Event(); failures = []; index_completed = 0; index_refused = 0
        samples = []
        sample_elapsed_ms = []
        process = None
        workers = []
        started = time.monotonic()
        def observe():
            snapshot = observe_diagnostic_directory(store, index)
            samples.append(snapshot)
            sample_elapsed_ms.append((time.monotonic() - started) * 1000)
            return snapshot
        with closing(sqlite3.connect(event_path)) as event_reader, closing(sqlite3.connect(index_path)) as index_reader:
            for db, table in ((event_reader, "events"), (index_reader, "projections")):
                db.execute("BEGIN"); db.execute(f"SELECT count(*) FROM {table}").fetchone()
            source.active = True
            store.start()
            def events():
                try:
                    for _ in range(1000):
                        if stop.is_set():
                            return
                        store.emit("lifecycle_started")
                        while store.queue.unfinished_tasks and not stop.wait(0.001):
                            pass
                except Exception:
                    failures.append("event_worker")
            def projections():
                nonlocal index_completed, index_refused
                try:
                    for _ in range(160):
                        if stop.is_set():
                            return
                        try:
                            index.step(100); index_completed += 1
                        except Exception:
                            index_refused += 1
                except Exception:
                    failures.append("index_worker")
            def consume():
                try:
                    while not stop.is_set():
                        spool.step(); stop.wait(0.005)
                except Exception:
                    failures.append("spool_worker")
            try:
                observe()
                environment = dict(os.environ, DIAGNOSTIC_INSTALLATION_TEST_ROOT=str(root))
                process = subprocess.Popen([str(native_binary), "--exact", "diagnostics::tests::installation_spool_child_process"],
                                           env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                workers = [threading.Thread(target=fn) for fn in (events, projections, consume)]
                for worker in workers:
                    worker.start()
                while time.monotonic() - started < 45:
                    observe()
                    if process.poll() is not None and not any(worker.is_alive() for worker in workers[:2]):
                        break
                    time.sleep(0.01)
                assert process.poll() == 0, "native_process_failed_or_timed_out"
                assert not any(worker.is_alive() for worker in workers[:2]), "python_workers_timed_out"
            finally:
                stop.set()
                if process is not None:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)
                for worker in workers:
                    worker.join(5)
                event_reader.rollback(); index_reader.rollback()
                store.close()
        assert not failures and not any(worker.is_alive() for worker in workers), "worker_failure"
        # Readers released: ordinary maintenance/recovery can now reclaim pages.
        store.oversize_recovery.interval_seconds = 0
        with closing(sqlite3.connect(event_path)) as db:
            store.disk_maintenance.maintain(db, force=True)
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        index.oversize_recovery.interval_seconds = 0
        index.step(100)
        with closing(sqlite3.connect(index_path)) as db:
            assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        spool.step()
        final = observe()
        assert store.quota.rejected > 0 and index.quota.rejected > 0, "quota_pressure_not_exercised"
        assert all(sample["total_bytes"] <= 200 * 1024 * 1024 for sample in samples), "observed_installation_overage"
        assert final["status"] == "observed", "final_inventory_incomplete"
        assert sum(store.quota.sizes().values()) <= store.quota.max_bytes
        assert sum(index.quota.sizes().values()) <= index.quota.max_bytes
        source_root = Path(__file__).parents[1]
        repo_root = source_root.parents[1]
        sources = [source_root / "app/core/diagnostic_quota.py", source_root / "app/core/diagnostic_recovery.py",
                   source_root / "app/core/diagnostics.py", source_root / "app/services/diagnostic_index.py",
                   source_root / "app/services/diagnostic_desktop_spool.py", source_root / "app/services/diagnostic_directory_storage.py",
                   Path(__file__), repo_root / "apps/desktop/src-tauri/src/diagnostics.rs"]
        fields = ["total_bytes", "database_bytes", "spool_bytes", "other_bytes", "scanned_entries", "skipped_entries", "status", "gaps"]
        with native_binary.open("rb") as binary:
            native_sha256 = hashlib.file_digest(binary, "sha256").hexdigest()
        return dict(native_test_binary_sha256=native_sha256, schema_version="diagnostic-installation-probe-v1", observed_at=datetime.now(timezone.utc).isoformat(),
                    platform=platform.platform(), sqlite_version=sqlite3.sqlite_version,
                    source_sha256={str(path.relative_to(repo_root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
                    event_limit_bytes=store.quota.max_bytes, index_limit_bytes=index.quota.max_bytes,
                    native_event_limit_bytes=4 * 1024 * 1024, installation_reference_bytes=200 * 1024 * 1024,
                    event_quota_refusals=store.quota.rejected, index_quota_refusals=index.quota.rejected,
                    event_dropped=store.dropped, index_steps_completed=index_completed, index_steps_refused=index_refused,
                    desktop_consumer_failures=spool.failures, native_events_attempted=1200,
                    peak_observed_file_lengths=max(sample["total_bytes"] for sample in samples),
                    final=final, sample_columns=["elapsed_ms", *fields],
                    samples=[[elapsed, *[sample[field] for field in fields]] for elapsed, sample in zip(sample_elapsed_ms, samples)], elapsed_ms=(time.monotonic()-started)*1000,
                    atomic_peak_claim=False, installation_disk_limit_certified=False,
                    workload="pinned_60_and_28_MiB_legacy_freelists_with_native_spool_and_missing_source_index_rows")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-test-binary", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.native_test_binary), indent=2))
