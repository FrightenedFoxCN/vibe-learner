"""Event retention uses database ingestion time, never untrusted source timestamps.

Deletion counters share the deleting transaction. They describe diagnostic
coverage only and never prune authoritative domain/Harness records.
"""
import sqlite3


class DiagnosticEventRetention:
    def __init__(self, *, max_rows=10_000, max_payload_bytes=64 * 1024 * 1024, max_age_seconds=7 * 86400):
        if min(max_rows, max_payload_bytes, max_age_seconds) < 1:
            raise ValueError("diagnostic_retention_invalid_limit")
        self.max_rows = max_rows
        self.max_payload_bytes = max_payload_bytes
        self.max_age_seconds = max_age_seconds

    def initialize(self, db: sqlite3.Connection):
        # Legacy source time cannot prove when the event was ingested. Retain it
        # from this migration and persist the extent of that timestamp gap.
        columns = {row[1] for row in db.execute("PRAGMA table_info(events)")}
        if "ingested_at" not in columns:
            db.execute("ALTER TABLE events ADD COLUMN ingested_at INTEGER NOT NULL DEFAULT 0")
        legacy = db.execute("SELECT count(*) FROM events WHERE ingested_at=0").fetchone()[0]
        db.execute("UPDATE events SET ingested_at=unixepoch('now') WHERE ingested_at=0")
        db.execute("CREATE INDEX IF NOT EXISTS events_ingested_at ON events(ingested_at,sequence)")
        db.execute("CREATE TABLE IF NOT EXISTS event_retention (singleton INTEGER PRIMARY KEY CHECK(singleton=1), retained_events INTEGER NOT NULL, retained_payload_bytes INTEGER NOT NULL, removed_events INTEGER NOT NULL, removed_through_sequence INTEGER NOT NULL, legacy_timestamp_rows INTEGER NOT NULL)")
        inserted = db.execute("INSERT OR IGNORE INTO event_retention SELECT 1,count(*),coalesce(sum(length(cast(payload AS BLOB))),0),0,0,? FROM events", (legacy,)).rowcount
        if not inserted and legacy:
            db.execute("UPDATE event_retention SET legacy_timestamp_rows=legacy_timestamp_rows+? WHERE singleton=1", (legacy,))
        db.execute("""CREATE TRIGGER IF NOT EXISTS diagnostic_event_insert AFTER INSERT ON events BEGIN
            UPDATE events SET ingested_at=unixepoch('now') WHERE sequence=NEW.sequence AND ingested_at=0;
            UPDATE event_retention SET retained_events=retained_events+1,
                retained_payload_bytes=retained_payload_bytes+length(cast(NEW.payload AS BLOB)) WHERE singleton=1;
        END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS diagnostic_event_delete AFTER DELETE ON events BEGIN
            UPDATE event_retention SET retained_events=retained_events-1,
                retained_payload_bytes=retained_payload_bytes-length(cast(OLD.payload AS BLOB)),
                removed_events=removed_events+1,
                removed_through_sequence=max(removed_through_sequence,OLD.sequence) WHERE singleton=1;
        END""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS diagnostic_event_payload_update AFTER UPDATE OF payload ON events BEGIN
            UPDATE event_retention SET retained_payload_bytes=retained_payload_bytes
                +length(cast(NEW.payload AS BLOB))-length(cast(OLD.payload AS BLOB)) WHERE singleton=1;
        END""")
        self.prune(db)

    def prune(self, db: sqlite3.Connection):
        db.execute("DELETE FROM events WHERE ingested_at < unixepoch('now')-?", (self.max_age_seconds,))
        count, size = db.execute("SELECT retained_events,retained_payload_bytes FROM event_retention WHERE singleton=1").fetchone()
        if count > self.max_rows:
            db.execute("DELETE FROM events WHERE sequence IN (SELECT sequence FROM events ORDER BY sequence LIMIT ?)", (count - self.max_rows,))
        if size > self.max_payload_bytes:
            # Keep the newest suffix fitting the payload budget, including the
            # honest empty suffix when a single event exceeds that budget.
            db.execute("""DELETE FROM events WHERE sequence <= (
                SELECT max(sequence) FROM (
                    SELECT sequence,sum(length(cast(payload AS BLOB))) OVER (ORDER BY sequence DESC) AS bytes FROM events
                ) WHERE bytes > ?
            )""", (self.max_payload_bytes,))

    def coverage(self, db: sqlite3.Connection, after: int):
        row = db.execute("SELECT retained_events,retained_payload_bytes,removed_events,removed_through_sequence,legacy_timestamp_rows FROM event_retention WHERE singleton=1").fetchone()
        if row is None:
            raise ValueError("diagnostic_retention_unavailable")
        return dict(schema_version="diagnostic-event-retention-v1", retained_events=row[0], retained_payload_bytes=row[1],
                    removed_events=row[2], removed_through_sequence=row[3], legacy_timestamp_rows=row[4],
                    cursor_gap=after < row[3], max_age_seconds=self.max_age_seconds,
                    max_rows=self.max_rows, max_payload_bytes=self.max_payload_bytes,
                    storage_scope="event_payloads", disk_size_limit_certified=False)
