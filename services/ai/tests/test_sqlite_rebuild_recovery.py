from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.persistence.database import Database
from app.persistence.models import Base

_STUDY_LEGACY = "study_sessions_legacy_migration"
_RUN_LEGACY = "tavern_runs_legacy_migration"
_STEP_LEGACY = "tavern_run_steps_legacy_migration"


class SQLiteRebuildRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.url = f"sqlite:///{Path(tmp.name) / 'synthetic.db'}"
        self.database = Database(self.url)
        self.addCleanup(lambda: self.database.dispose())

    def _restart(self) -> None:
        self.database.dispose()
        self.database = Database(self.url)
        self.database.create_schema()

    def _query(self, sql: str) -> list[tuple]:
        with self.database.engine.connect() as connection:
            return [tuple(row) for row in connection.exec_driver_sql(sql)]

    @contextmanager
    def _interrupt_after(self, statement_prefix: str):
        def inject(_conn, _cursor, statement, _params, _context, _executemany):
            if statement.strip().startswith(statement_prefix):
                raise RuntimeError("synthetic interruption")

        event.listen(self.database.engine, "after_cursor_execute", inject)
        try:
            with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
                yield
        finally:
            event.remove(self.database.engine, "after_cursor_execute", inject)

    def _study_legacy(self, table: str, row_id: str = "legacy") -> None:
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                f"""
                CREATE TABLE {table} (
                    id TEXT PRIMARY KEY, document_id TEXT NOT NULL DEFAULT '',
                    persona_id TEXT NOT NULL DEFAULT '', plan_id TEXT NOT NULL DEFAULT '',
                    section_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL DEFAULT '',
                    payload JSON NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                f"INSERT INTO {table} (id, section_id, payload) VALUES (?, 'section', ?)",
                (row_id, '{"origin":"legacy"}'),
            )

    def _study_current(self, row_id: str) -> None:
        table = Base.metadata.tables["study_sessions"]
        with self.database.engine.begin() as connection:
            table.create(connection)
            connection.execute(
                table.insert().values(
                    id=row_id,
                    study_unit_id="unit",
                    revision=3,
                    last_turn_sequence=4,
                    payload={"origin": "current"},
                )
            )

    def test_study_rename_and_create_rollback(self) -> None:
        self._study_legacy("study_sessions")
        for statement in (
            f"ALTER TABLE study_sessions RENAME TO {_STUDY_LEGACY}",
            "CREATE TABLE study_sessions (",
            f"DROP TABLE {_STUDY_LEGACY}",
        ):
            with self.subTest(statement=statement), self._interrupt_after(statement):
                self.database.create_schema()
            self.assertEqual(
                self._query("SELECT id, section_id FROM study_sessions"),
                [("legacy", "section")],
            )
            self.assertEqual(
                self._query(
                    f"SELECT name FROM sqlite_master WHERE name='{_STUDY_LEGACY}'"
                ),
                [],
            )
            self.assertEqual(self._query("PRAGMA foreign_keys"), [(1,)])
            self.assertEqual(self._query("PRAGMA legacy_alter_table"), [(0,)])
        self._restart()
        self.assertEqual(
            self._query("SELECT id, study_unit_id FROM study_sessions"),
            [("legacy", "section")],
        )

    def test_study_recovers_rename_only_and_rebinds_foreign_key(self) -> None:
        self._study_legacy("study_sessions")
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE synthetic_child (id TEXT REFERENCES study_sessions(id) ON DELETE CASCADE)"
            )
            connection.exec_driver_sql("INSERT INTO synthetic_child VALUES ('legacy')")
            connection.exec_driver_sql(
                f"ALTER TABLE study_sessions RENAME TO {_STUDY_LEGACY}"
            )
        self.assertEqual(
            self._query(
                """SELECT "table" FROM pragma_foreign_key_list('synthetic_child')"""
            ),
            [(_STUDY_LEGACY,)],
        )
        self._restart()
        self._restart()
        self.assertEqual(self._query("SELECT id FROM study_sessions"), [("legacy",)])
        self.assertEqual(self._query("SELECT id FROM synthetic_child"), [("legacy",)])
        self.assertEqual(
            self._query(
                """SELECT "table" FROM pragma_foreign_key_list('synthetic_child')"""
            ),
            [("study_sessions",)],
        )
        self.assertEqual(self._query("PRAGMA foreign_key_check"), [])

    def test_study_merges_nonoverlapping_sources_and_preserves_revisions(self) -> None:
        self._study_legacy(_STUDY_LEGACY)
        self._study_legacy("study_sessions_legacy", "older")
        self._study_current("current")
        self._restart()
        self._restart()
        self.assertEqual(
            self._query(
                "SELECT id, study_unit_id, revision, last_turn_sequence, "
                "json_extract(payload, '$.origin') FROM study_sessions ORDER BY id"
            ),
            [
                ("current", "unit", 3, 4, "current"),
                ("legacy", "section", 0, 0, "legacy"),
                ("older", "section", 0, 0, "legacy"),
            ],
        )
        self.assertEqual(
            self._query(
                "SELECT name FROM sqlite_master WHERE name LIKE 'study_sessions_legacy%'"
            ),
            [],
        )

    def test_study_conflict_refuses_to_discard_either_row(self) -> None:
        self._study_legacy(_STUDY_LEGACY, "duplicate")
        self._study_current("duplicate")
        with self.assertRaises(IntegrityError):
            self._restart()
        self.assertEqual(
            self._query("SELECT id, study_unit_id, revision FROM study_sessions"),
            [("duplicate", "unit", 3)],
        )
        self.assertEqual(
            self._query(f"SELECT id, section_id FROM {_STUDY_LEGACY}"),
            [("duplicate", "section")],
        )

    def _tavern_legacy(self, *, room_id: str = "room") -> None:
        tables = Base.metadata.tables
        with self.database.engine.begin() as connection:
            tables["tavern_rooms"].create(connection)
            connection.execute(
                tables["tavern_rooms"].insert().values(id="room", title="Synthetic")
            )
            connection.exec_driver_sql(
                """
                CREATE TABLE tavern_runs (
                    id TEXT PRIMARY KEY, room_id TEXT NOT NULL, idempotency_key TEXT NOT NULL,
                    parent_run_id TEXT, status TEXT NOT NULL DEFAULT 'pending',
                    mode TEXT NOT NULL DEFAULT 'direct', input_message_id TEXT NOT NULL DEFAULT '',
                    expected_room_revision INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT NOT NULL DEFAULT '', payload JSON NOT NULL DEFAULT '{}'
                )
                """
            )
            tables["tavern_run_steps"].create(connection)
            connection.exec_driver_sql(
                "INSERT INTO tavern_runs (id, room_id, idempotency_key) VALUES ('old', ?, 'old-key')",
                (room_id,),
            )
            connection.execute(
                tables["tavern_run_steps"]
                .insert()
                .values(
                    run_id="old",
                    step_index=0,
                    persona_id="persona",
                    lease_owner="worker",
                    lease_expires_at="later",
                    claim_count=3,
                )
            )

    def test_tavern_renames_rollback_together_and_failed_fk_check_rolls_back(
        self,
    ) -> None:
        self._tavern_legacy(room_id="missing-room")
        for statement in (
            f"ALTER TABLE tavern_run_steps RENAME TO {_STEP_LEGACY}",
            f"ALTER TABLE tavern_runs RENAME TO {_RUN_LEGACY}",
        ):
            with self.subTest(statement=statement), self._interrupt_after(statement):
                self.database.create_schema()
            self.assertEqual(self._query("SELECT id FROM tavern_runs"), [("old",)])
            self.assertEqual(
                self._query("SELECT run_id FROM tavern_run_steps"), [("old",)]
            )
        with self.assertRaisesRegex(RuntimeError, "sqlite_foreign_key_repair_failed"):
            self._restart()
        self.assertEqual(
            self._query("SELECT room_id FROM tavern_runs"), [("missing-room",)]
        )
        self.assertEqual(
            self._query(
                "SELECT name FROM sqlite_master WHERE name LIKE 'tavern%legacy_migration'"
            ),
            [],
        )
        self.assertEqual(self._query("PRAGMA foreign_keys"), [(1,)])

    def test_tavern_recovers_first_rename_only(self) -> None:
        self._tavern_legacy()
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER TABLE tavern_run_steps RENAME TO {_STEP_LEGACY}"
            )
        self._restart()
        self.assertEqual(self._query("SELECT id FROM tavern_runs"), [("old",)])
        self.assertEqual(
            self._query("SELECT run_id, claim_count FROM tavern_run_steps"),
            [("old", 3)],
        )
        self.assertEqual(self._query("PRAGMA foreign_key_check"), [])

    def test_tavern_merges_residues_with_new_rows_and_rejects_unique_conflicts(
        self,
    ) -> None:
        self._tavern_legacy()
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                f"ALTER TABLE tavern_run_steps RENAME TO {_STEP_LEGACY}"
            )
            connection.exec_driver_sql(
                f"ALTER TABLE tavern_runs RENAME TO {_RUN_LEGACY}"
            )
            for name in (
                "ix_tavern_run_steps_persona_id",
                "ix_tavern_run_steps_status",
            ):
                connection.exec_driver_sql(f"DROP INDEX {name}")
            runs = Base.metadata.tables["tavern_runs"]
            # The current table needs its referenced Harness table for fixture inserts.
            Base.metadata.tables["harness_operation_bindings"].create(connection)
            runs.create(connection)
            connection.execute(
                runs.insert().values(
                    id="new", room_id="room", idempotency_key="old-key"
                )
            )
        with self.assertRaises(IntegrityError):
            self._restart()
        self.assertEqual(self._query("SELECT id FROM tavern_runs"), [("new",)])
        self.assertEqual(self._query(f"SELECT id FROM {_RUN_LEGACY}"), [("old",)])
        self.assertEqual(self._query(f"SELECT run_id FROM {_STEP_LEGACY}"), [("old",)])
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tavern_runs SET idempotency_key='new-key'"
            )
        self._restart()
        self._restart()
        self.assertEqual(
            self._query("SELECT id FROM tavern_runs ORDER BY id"), [("new",), ("old",)]
        )
        self.assertEqual(
            self._query(
                "SELECT run_id, lease_owner, lease_expires_at, claim_count FROM tavern_run_steps"
            ),
            [("old", "worker", "later", 3)],
        )
        self.assertEqual(
            self._query(
                "SELECT name FROM sqlite_master WHERE name LIKE 'tavern%legacy_migration'"
            ),
            [],
        )
        self.assertEqual(self._query("PRAGMA foreign_key_check"), [])
