"""Bounded durable writer observations, never a claim of complete collection."""
from contextlib import closing
import sqlite3


class DiagnosticWriterCoverage:
    def __init__(self, path, epoch_id, *, max_epochs=256):
        if max_epochs < 1:
            raise ValueError("diagnostic_writer_epoch_limit")
        self.path = path
        self.epoch_id = epoch_id
        self.max_epochs = max_epochs

    def initialize(self, db):
        db.execute("""CREATE TABLE IF NOT EXISTS diagnostic_writers (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT, epoch_id TEXT NOT NULL UNIQUE,
            started_at INTEGER NOT NULL, observed_at INTEGER NOT NULL, closed_at INTEGER,
            observed_dropped INTEGER NOT NULL, observed_write_failures INTEGER NOT NULL,
            observed_read_failures INTEGER NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS diagnostic_writer_totals (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1), retired_epochs INTEGER NOT NULL,
            retired_unclosed INTEGER NOT NULL, observed_dropped INTEGER NOT NULL,
            observed_write_failures INTEGER NOT NULL, observed_read_failures INTEGER NOT NULL)""")
        db.execute("INSERT OR IGNORE INTO diagnostic_writer_totals VALUES (1,0,0,0,0,0)")
        db.execute("INSERT OR IGNORE INTO diagnostic_writers(epoch_id,started_at,observed_at,closed_at,observed_dropped,observed_write_failures,observed_read_failures) VALUES (?,unixepoch('now'),unixepoch('now'),NULL,0,0,0)", (self.epoch_id,))
        overflow = db.execute("SELECT count(*) FROM diagnostic_writers").fetchone()[0] - self.max_epochs
        if overflow > 0:
            retired = db.execute("SELECT sequence,closed_at,observed_dropped,observed_write_failures,observed_read_failures FROM diagnostic_writers ORDER BY sequence LIMIT ?", (overflow,)).fetchall()
            db.execute("UPDATE diagnostic_writer_totals SET retired_epochs=retired_epochs+?,retired_unclosed=retired_unclosed+?,observed_dropped=observed_dropped+?,observed_write_failures=observed_write_failures+?,observed_read_failures=observed_read_failures+? WHERE singleton=1",
                       (len(retired), sum(row[1] is None for row in retired), sum(row[2] for row in retired), sum(row[3] for row in retired), sum(row[4] for row in retired)))
            db.execute("DELETE FROM diagnostic_writers WHERE sequence<=?", (retired[-1][0],))

    def observe(self, db, *, dropped, write_failures, read_failures, closed=False):
        # Counters are lower bounds observed at this checkpoint, not final global
        # totals. Events rejected after closure and pre-checkpoint process loss
        # cannot be reconstructed from a diagnostic database.
        db.execute("""UPDATE diagnostic_writers SET observed_at=unixepoch('now'),
            closed_at=CASE WHEN ? THEN unixepoch('now') ELSE closed_at END,
            observed_dropped=max(observed_dropped,?),
            observed_write_failures=max(observed_write_failures,?),
            observed_read_failures=max(observed_read_failures,?) WHERE epoch_id=?""",
                   (closed, dropped, write_failures, read_failures, self.epoch_id))

    def query(self, after=0, limit=100):
        if after < 0 or not 1 <= limit <= 100:
            raise ValueError("diagnostic_writer_query_bounds")
        with closing(sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=0.1)) as db:
            db.row_factory = sqlite3.Row
            db.execute("BEGIN")
            rows = db.execute("SELECT * FROM diagnostic_writers WHERE sequence>? ORDER BY sequence LIMIT ?", (after, limit + 1)).fetchall()
            total = dict(db.execute("SELECT * FROM diagnostic_writer_totals WHERE singleton=1").fetchone())
            aggregate = db.execute("SELECT count(*) AS retained_epochs,coalesce(sum(closed_at IS NULL),0) AS unclosed_epochs,coalesce(sum(observed_dropped),0) AS observed_dropped,coalesce(sum(observed_write_failures),0) AS observed_write_failures,coalesce(sum(observed_read_failures),0) AS observed_read_failures FROM diagnostic_writers").fetchone()
        total.pop("singleton")
        for key in ("observed_dropped", "observed_write_failures", "observed_read_failures"):
            total[key] += aggregate[key]
        total.update(retained_epochs=aggregate["retained_epochs"], unclosed_epochs=aggregate["unclosed_epochs"])
        items = [dict(row) for row in rows[:limit]]
        from app.models.diagnostic_writer import DiagnosticWriterCoverageV1
        return DiagnosticWriterCoverageV1(schema_version="diagnostic-writer-coverage-v1", items=items, next_cursor=items[-1]["sequence"] if items else after,
                    has_more=len(rows) > limit, totals=total, counts_are_lower_bounds=True,
                    unpersisted_queue_gap=True, startup_before_epoch_gap=True,
                    unclosed_meaning="active_or_interrupted", complete_collection_claim=False).model_dump(mode="json")
