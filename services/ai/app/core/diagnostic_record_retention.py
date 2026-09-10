"""Bound disposable links/projections; never prune canonical Harness records."""
from datetime import datetime

from app.models.diagnostic_retention import DiagnosticRecordRetentionV1


class DiagnosticRecordRetention:
    def __init__(self, table, *, max_rows=None, max_payload_bytes=None, max_age_seconds=7 * 86400):
        if table not in {"operation_links", "projections"}:
            raise ValueError("diagnostic_retention_table_invalid")
        self.table = table
        self.max_rows = max_rows if max_rows is not None else 10000 if table == "operation_links" else 5000
        self.max_payload_bytes = max_payload_bytes if max_payload_bytes is not None else (4 if table == "operation_links" else 32) * 1024 * 1024
        self.max_age_seconds = max_age_seconds
        if min(self.max_rows, self.max_payload_bytes, self.max_age_seconds) < 1:
            raise ValueError("diagnostic_retention_limit_invalid")

    def initialize(self, db):
        table = self.table  # fixed reviewed table names only
        if "retained_at" not in {row[1] for row in db.execute(f"PRAGMA table_info({table})")}:
            db.execute(f"ALTER TABLE {table} ADD COLUMN retained_at INTEGER NOT NULL DEFAULT 0")
        legacy = db.execute(f"SELECT count(*) FROM {table} WHERE retained_at=0").fetchone()[0]
        db.execute(f"UPDATE {table} SET retained_at=unixepoch('now') WHERE retained_at=0")
        db.execute(f"CREATE INDEX IF NOT EXISTS {table}_retention_age ON {table}(retained_at)")
        db.execute("CREATE TABLE IF NOT EXISTS diagnostic_record_retention (table_name TEXT PRIMARY KEY, retained_rows INTEGER NOT NULL, retained_payload_bytes INTEGER NOT NULL, removed_rows INTEGER NOT NULL, legacy_timestamp_rows INTEGER NOT NULL)")
        inserted = db.execute(f"INSERT OR IGNORE INTO diagnostic_record_retention SELECT ?,count(*),coalesce(sum(length(cast(payload AS BLOB))),0),0,? FROM {table}", (table, legacy)).rowcount
        if not inserted and legacy:
            db.execute("UPDATE diagnostic_record_retention SET legacy_timestamp_rows=legacy_timestamp_rows+? WHERE table_name=?", (legacy, table))
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_retention_insert AFTER INSERT ON {table} BEGIN
            UPDATE {table} SET retained_at=unixepoch('now') WHERE rowid=NEW.rowid AND retained_at=0;
            UPDATE diagnostic_record_retention SET retained_rows=retained_rows+1,
                retained_payload_bytes=retained_payload_bytes+length(cast(NEW.payload AS BLOB)) WHERE table_name='{table}';
        END""")
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_retention_update AFTER UPDATE OF payload ON {table} BEGIN
            UPDATE diagnostic_record_retention SET retained_payload_bytes=retained_payload_bytes
                +length(cast(NEW.payload AS BLOB))-length(cast(OLD.payload AS BLOB)) WHERE table_name='{table}';
        END""")
        db.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_retention_delete AFTER DELETE ON {table} BEGIN
            UPDATE diagnostic_record_retention SET retained_rows=retained_rows-1,
                retained_payload_bytes=retained_payload_bytes-length(cast(OLD.payload AS BLOB)),
                removed_rows=removed_rows+1 WHERE table_name='{table}';
        END""")
        self.prune(db)

    def prune(self, db):
        table = self.table
        db.execute(f"DELETE FROM {table} WHERE retained_at < unixepoch('now')-?", (self.max_age_seconds,))
        count, size = db.execute("SELECT retained_rows,retained_payload_bytes FROM diagnostic_record_retention WHERE table_name=?", (table,)).fetchone()
        if count > self.max_rows:
            db.execute(f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} ORDER BY retained_at,rowid LIMIT ?)", (count - self.max_rows,))
        if size > self.max_payload_bytes:
            db.execute(f"""DELETE FROM {table} WHERE rowid IN (
                SELECT identity FROM (SELECT rowid AS identity,sum(length(cast(payload AS BLOB))) OVER (ORDER BY retained_at DESC,rowid DESC) AS bytes FROM {table}) WHERE bytes > ?
            )""", (self.max_payload_bytes,))

    def source_time(self, db, timestamp):
        """Canonical update time prevents old traces resurrecting each sweep.

        Missing/invalid source time uses bounded local observation age. Future
        timestamps clamp to the first DB observation time for unchanged records.
        """
        now = db.execute("SELECT unixepoch('now')").fetchone()[0]
        try:
            value = datetime.fromisoformat(timestamp)
            if value.utcoffset() is None:
                raise ValueError("timezone_missing")
            return min(now, max(1, int(value.timestamp())))
        except (TypeError, ValueError, OverflowError):
            return None

    def coverage(self, db):
        row = db.execute("SELECT retained_rows,retained_payload_bytes,removed_rows,legacy_timestamp_rows FROM diagnostic_record_retention WHERE table_name=?", (self.table,)).fetchone()
        if row is None:
            raise ValueError("diagnostic_retention_unavailable")
        return DiagnosticRecordRetentionV1(table=self.table, retained_rows=row[0], retained_payload_bytes=row[1],
            removed_rows=row[2], legacy_timestamp_rows=row[3], max_rows=self.max_rows,
            max_payload_bytes=self.max_payload_bytes, max_age_seconds=self.max_age_seconds,
            source_age_exclusions_possible=self.table == "projections",
            age_basis="first_local_observation" if self.table == "operation_links" else "canonical_update_or_first_local_observation").model_dump(mode="json")
