"""Best-effort SQLite reclamation, strictly outside diagnostic/domain commits.

This reduces reclaimable space; it is not a hard aggregate disk quota. Readers
can pin WAL frames. Busy/failed work is retried by a later maintenance cycle.
"""
import time
from contextlib import nullcontext


class DiagnosticDiskMaintenance:
    def __init__(self, *, interval_seconds=60, budget_seconds=0.25, vacuum_pages=256):
        if interval_seconds < 0 or budget_seconds <= 0 or vacuum_pages < 1:
            raise ValueError("diagnostic_disk_budget_invalid")
        self.interval_seconds = interval_seconds
        self.budget_seconds = budget_seconds
        self.vacuum_pages = vacuum_pages
        self.last_run = None
        self.failures = 0
        self.busy = 0
        self.completed = 0
        self.legacy_migrations = 0

    def configure(self, db):
        # Before table creation this activates incremental vacuum immediately.
        # Legacy files need the separately bounded VACUUM migration below.
        try:
            db.execute("PRAGMA auto_vacuum=INCREMENTAL")
            db.execute("PRAGMA wal_autocheckpoint=256")
            db.execute("PRAGMA journal_size_limit=1048576")
        except Exception:
            self.failures += 1

    def maintain(self, db, *, force=False):
        # Never commit or roll back another owner's active transaction.
        if db.in_transaction:
            return
        now = time.monotonic()
        if not force and self.last_run is not None and now - self.last_run < self.interval_seconds:
            return
        self.last_run = now
        previous_timeout = None
        try:
            quota = getattr(self, "quota", None)
            with quota.lock() if quota is not None else nullcontext():
                previous_timeout = db.execute("PRAGMA busy_timeout").fetchone()[0]
                db.execute("PRAGMA busy_timeout=0")
                deadline = now + self.budget_seconds
                db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 100)
                # Checkpoint first can release pressure without adding WAL.
                if quota is not None:
                    db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                    db.execute("PRAGMA cache_spill=OFF")
                    quota.reserve(db, migration=db.execute("PRAGMA auto_vacuum").fetchone()[0] != 2)
                if db.execute("PRAGMA auto_vacuum").fetchone()[0] != 2:
                    db.execute("PRAGMA auto_vacuum=INCREMENTAL")
                    db.execute("VACUUM")
                    self.legacy_migrations += 1
                # Drain the cursor: incremental vacuum can emit one result per page.
                if quota is not None:
                    # One transaction prevents a multi-step incremental vacuum
                    # from appending repeated metadata frames per freed page.
                    db.execute("BEGIN IMMEDIATE")
                    initial_pages = db.execute("PRAGMA page_count").fetchone()[0]
                    try:
                        db.execute(f"PRAGMA incremental_vacuum({self.vacuum_pages})").fetchall()
                        quota.reserve(db, initial_pages=initial_pages)
                        db.commit()
                    except Exception:
                        db.rollback()
                        raise
                else:
                    db.execute(f"PRAGMA incremental_vacuum({self.vacuum_pages})").fetchall()
                # TRUNCATE is nonblocking with busy_timeout=0. A reader can defer it
                # without being cancelled or changing any committed record.
                result = db.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
                if result and result[0]:
                    self.busy += 1
                else:
                    self.completed += 1
        except Exception:
            self.failures += 1
        finally:
            try:
                db.set_progress_handler(None, 0)
                if previous_timeout is not None:
                    db.execute(f"PRAGMA busy_timeout={previous_timeout}")
            except Exception:
                self.failures += 1
