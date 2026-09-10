"""Conservative per-database admission for cooperating diagnostic writers.

This is not an installation-wide certification: the desktop spool and existing
oversized/externally modified files require separate coverage. SQLite cache spill
is disabled so failed admission can roll back before writing new WAL frames.
"""
from contextlib import contextmanager
from pathlib import Path
import math
import os


class DiagnosticQuotaExceeded(RuntimeError):
    pass


class DiagnosticDatabaseQuota:
    def __init__(self, path: Path, *, max_bytes=128 * 1024 * 1024):
        if max_bytes < 256 * 1024:
            raise ValueError("diagnostic_quota_invalid_limit")
        self.path = path
        self.max_bytes = max_bytes
        self.rejected = 0
        self.unavailable = 0

    @contextmanager
    def lock(self):
        # Retain the stable lock inode; unlinking it would break mutual exclusion.
        descriptor = None
        acquired = False
        try:
            descriptor = os.open(str(self.path) + ".quota-lock", os.O_CREAT | os.O_RDWR, 0o600)
            if os.name == "nt":
                import msvcrt
                if os.fstat(descriptor).st_size == 0:
                    os.write(descriptor, b"0")
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, ImportError):
            self.unavailable += 1
            if descriptor is not None:
                os.close(descriptor)
            raise DiagnosticQuotaExceeded("diagnostic_quota_unavailable") from None
        try:
            yield
        finally:
            if acquired:
                try:
                    if os.name == "nt":
                        os.lseek(descriptor, 0, os.SEEK_SET)
                        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    self.unavailable += 1
                finally:
                    try:
                        os.close(descriptor)
                    except OSError:
                        self.unavailable += 1

    def sizes(self):
        result = {}
        for name, suffix in (("database", ""), ("wal", "-wal"), ("shm", "-shm"), ("journal", "-journal"), ("lock", ".quota-lock")):
            path = Path(str(self.path) + suffix)
            try:
                result[name] = path.stat().st_size
            except FileNotFoundError:
                result[name] = 0
        return result

    def reserve(self, db, *, initial_pages=0, migration=False):
        sizes = self.sizes()
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        pages = max(initial_pages, db.execute("PRAGMA page_count").fetchone()[0])
        logical = pages * page_size
        # Worst-case commit rewrites every logical page once, with cache spill
        # disabled. Reserve database growth if an autocheckpoint materializes it.
        wal = sizes["wal"] + 32 + pages * (page_size + 24)
        shm = max(sizes["shm"], math.ceil((wal // (page_size + 24) + 4096) / 4096) * 32768)
        projected = max(sizes["database"], logical) + wal + shm + sizes["journal"] + max(sizes["lock"], 1)
        if migration:
            projected += 2 * logical  # SQLite VACUUM temporary database/rebuild allowance.
        if projected > self.max_bytes:
            self.rejected += 1
            raise DiagnosticQuotaExceeded("diagnostic_quota_exceeded")
        return projected

    @contextmanager
    def transaction(self, db):
        if db.in_transaction:
            raise RuntimeError("diagnostic_quota_transaction_owned")
        with self.lock():
            if db.execute("PRAGMA journal_mode").fetchone()[0].lower() != "wal":
                raise DiagnosticQuotaExceeded("diagnostic_quota_requires_wal")
            db.execute("PRAGMA cache_spill=OFF")
            if db.execute("PRAGMA cache_spill").fetchone()[0] != 0:
                raise DiagnosticQuotaExceeded("diagnostic_quota_spill_enabled")
            # Cap in-memory dirty staging too. SQLite will not lower below an
            # existing larger file; such legacy files are not certified in-budget.
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            db.execute(f"PRAGMA max_page_count={max(1, self.max_bytes // (2 * page_size))}")
            db.execute("BEGIN IMMEDIATE")
            initial_pages = db.execute("PRAGMA page_count").fetchone()[0]
            try:
                self.reserve(db, initial_pages=initial_pages)
                yield
                self.reserve(db, initial_pages=initial_pages)
                db.commit()
            except Exception:
                db.rollback()
                raise
