"""Bounded in-place recovery of disposable diagnostic databases.

Normal admission remains unchanged. Legacy recovery may temporarily exceed its
steady-state quota, but only within an independently checked workspace envelope.
Retention counters commit with deletion; SQLite owns crash atomicity throughout.
No rename/unlink/replacement of an open database or canonical source is used.
"""
import shutil
import time

from app.core.diagnostic_quota import DiagnosticDatabaseQuota, DiagnosticQuotaExceeded


class DiagnosticOversizeRecovery:
    def __init__(self, quota, prune, *, pressure_prune=None, interval_seconds=60, budget_seconds=5,
                 workspace_bytes=512 * 1024 * 1024):
        self.quota = quota
        # One transient recovery workspace per diagnostic directory. Use the
        # stable process-lock inode; normal per-database admission stays separate.
        self.installation_lock = DiagnosticDatabaseQuota(quota.path.parent / "recovery")
        self.prune = prune
        self.pressure_prune = pressure_prune
        self.interval_seconds = interval_seconds
        self.budget_seconds = budget_seconds
        self.workspace_bytes = workspace_bytes
        self.last_run = None
        self.attempts = 0
        self.completed = 0
        self.deferred = 0
        self.failures = 0

    def recover(self, db):
        if db.in_transaction:
            return False
        now = time.monotonic()
        if self.last_run is not None and now - self.last_run < self.interval_seconds:
            return False
        self.last_run = now
        self.attempts += 1
        previous_timeout = None
        previous_pages = None
        previous_temp_store = None
        try:
            with self.installation_lock.lock(), self.quota.lock():
                previous_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
                db.execute("PRAGMA busy_timeout=0")
                db.set_progress_handler(lambda: int(time.monotonic() - now >= self.budget_seconds), 100)
                # Checkpoint/reuse first. Never vacuum against a pinned reader.
                if db.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal":
                    if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                        raise DiagnosticQuotaExceeded("diagnostic_recovery_reader_busy")
                try:
                    self.quota.reserve(db)
                    # A released WAL reader may be the entire problem. Do not
                    # shorten retention merely to fund an optional migration.
                    self.completed += 1
                    return True
                except DiagnosticQuotaExceeded:
                    pass
                baseline = sum(self.quota.sizes().values())
                ceiling = baseline + self.workspace_bytes
                # Reserve the full fixed workspace on the source filesystem;
                # free space is a live observation, not protection from outsiders.
                if shutil.disk_usage(self.quota.path.parent).free < self.workspace_bytes:
                    raise DiagnosticQuotaExceeded("diagnostic_recovery_space_unavailable")
                self.quota.reserve(db, migration=True, limit_bytes=ceiling)
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA cache_spill=OFF")
                previous_temp_store = db.execute("PRAGMA temp_store").fetchone()[0]
                db.execute("PRAGMA temp_store=MEMORY")
                previous_pages = db.execute("PRAGMA max_page_count").fetchone()[0]
                page_size = db.execute("PRAGMA page_size").fetchone()[0]
                pages = db.execute("PRAGMA page_count").fetchone()[0]
                # Bound dirty in-memory staging and schema migration growth too.
                db.execute(f"PRAGMA max_page_count={pages + self.workspace_bytes // (8 * page_size)}")
                # First compact the normal retained set. Physical-pressure
                # eviction is a second pass only if actual ordinary admission
                # still fails after compaction; freelist bloat loses no records.
                for prune in (self.prune, self.pressure_prune):
                    if prune is None:
                        break
                    pages = db.execute("PRAGMA page_count").fetchone()[0]
                    db.execute("BEGIN IMMEDIATE")
                    try:
                        prune(db)
                        self.quota.reserve(db, initial_pages=pages, migration=True, limit_bytes=ceiling)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                    if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                        raise DiagnosticQuotaExceeded("diagnostic_recovery_reader_busy")
                    self.quota.reserve(db, migration=True, limit_bytes=ceiling)
                    db.execute("PRAGMA auto_vacuum=INCREMENTAL")
                    db.execute("VACUUM")
                    if db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()[0]:
                        raise DiagnosticQuotaExceeded("diagnostic_recovery_reader_busy")
                    try:
                        # Completion requires ordinary admission, not just a
                        # smaller file or a successful VACUUM statement.
                        self.quota.reserve(db)
                        self.completed += 1
                        return True
                    except DiagnosticQuotaExceeded:
                        continue
                raise DiagnosticQuotaExceeded("diagnostic_recovery_admission_unavailable")
        except DiagnosticQuotaExceeded:
            self.deferred += 1
        except Exception:
            self.failures += 1
        finally:
            try:
                db.set_progress_handler(None, 0)
                if db.in_transaction:
                    db.rollback()
                if previous_pages is not None:
                    db.execute(f"PRAGMA max_page_count={previous_pages}")
                if previous_temp_store is not None:
                    db.execute(f"PRAGMA temp_store={previous_temp_store}")
                if previous_timeout is not None:
                    db.execute(f"PRAGMA busy_timeout={previous_timeout}")
            except Exception:
                self.failures += 1
        return False
