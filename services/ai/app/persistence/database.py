from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import Base


class Database:
    def __init__(self, url: str) -> None:
        engine_kwargs: dict[str, object] = {
            "future": True,
            "pool_pre_ping": True,
        }
        if url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        self.url = url
        self.engine: Engine = create_engine(url, **engine_kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

    def create_schema(self) -> None:
        self._migrate_sqlite_schema()
        Base.metadata.create_all(self.engine)
        if self.url.startswith("sqlite"):
            with self.engine.begin() as connection:
                self._ensure_sqlite_study_session_indexes(connection)
                self._ensure_sqlite_tavern_room_indexes(connection)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _migrate_sqlite_schema(self) -> None:
        if not self.url.startswith("sqlite"):
            return

        self._repair_sqlite_tavern_run_foreign_key()
        with self.engine.begin() as connection:
            table_names = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

            if "tavern_rooms" in table_names:
                tavern_columns = self._sqlite_column_names(connection, "tavern_rooms")
                if "creation_key" not in tavern_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_rooms ADD COLUMN creation_key VARCHAR(80)"
                    )
                if "creation_input_digest" not in tavern_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_rooms ADD COLUMN "
                        "creation_input_digest VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                connection.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_tavern_rooms_creation_key "
                    "ON tavern_rooms (creation_key) WHERE creation_key IS NOT NULL"
                )

            if "tavern_run_steps" in table_names:
                step_columns = self._sqlite_column_names(connection, "tavern_run_steps")
                if "lease_owner" not in step_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_run_steps ADD COLUMN "
                        "lease_owner VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                if "lease_expires_at" not in step_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_run_steps ADD COLUMN "
                        "lease_expires_at VARCHAR(64) NOT NULL DEFAULT ''"
                    )
                if "claim_count" not in step_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE tavern_run_steps ADD COLUMN "
                        "claim_count INTEGER NOT NULL DEFAULT 0"
                    )

            if "learning_plan_operations" in table_names:
                plan_operation_columns = self._sqlite_column_names(
                    connection,
                    "learning_plan_operations",
                )
                if "base_debug_digest" not in plan_operation_columns:
                    connection.exec_driver_sql(
                        "ALTER TABLE learning_plan_operations ADD COLUMN "
                        "base_debug_digest VARCHAR(64) NOT NULL DEFAULT ''"
                    )

            for scene_table in ("scene_setup_states", "scene_library_entries"):
                if scene_table not in table_names:
                    continue
                scene_columns = self._sqlite_column_names(connection, scene_table)
                if "revision" not in scene_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {scene_table} ADD COLUMN "
                        "revision INTEGER NOT NULL DEFAULT 0"
                    )

            # Recover partially applied migrations that left a duplicate legacy table behind.
            if "study_sessions_legacy" in table_names and "study_sessions" not in table_names:
                connection.exec_driver_sql("ALTER TABLE study_sessions_legacy RENAME TO study_sessions")
                table_names.remove("study_sessions_legacy")
                table_names.add("study_sessions")

            if "study_sessions_legacy" in table_names and "study_sessions" in table_names:
                current_columns = self._sqlite_column_names(connection, "study_sessions")
                legacy_columns = self._sqlite_column_names(connection, "study_sessions_legacy")
                if "study_unit_id" in current_columns and "section_id" in legacy_columns:
                    connection.exec_driver_sql(
                        """
                        INSERT OR IGNORE INTO study_sessions (
                            id,
                            document_id,
                            persona_id,
                            plan_id,
                            study_unit_id,
                            status,
                            created_at,
                            updated_at,
                            payload
                        )
                        SELECT
                            id,
                            document_id,
                            persona_id,
                            plan_id,
                            section_id,
                            status,
                            created_at,
                            updated_at,
                            payload
                        FROM study_sessions_legacy
                        """
                    )
                    connection.exec_driver_sql("DROP TABLE study_sessions_legacy")
                    table_names.remove("study_sessions_legacy")

            if "study_sessions" not in table_names:
                return

            columns = self._sqlite_column_names(connection, "study_sessions")
            if "study_unit_id" not in columns and "section_id" in columns:
                self._rebuild_legacy_study_sessions_table(connection, source_table="study_sessions")
                columns = self._sqlite_column_names(connection, "study_sessions")
            if "revision" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE study_sessions ADD COLUMN "
                    "revision INTEGER NOT NULL DEFAULT 0"
                )
            if "last_turn_sequence" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE study_sessions ADD COLUMN "
                    "last_turn_sequence INTEGER NOT NULL DEFAULT 0"
                )

    def _repair_sqlite_tavern_run_foreign_key(self) -> None:
        with self.engine.connect() as connection:
            table_names = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            if "tavern_runs" not in table_names:
                return
            columns = self._sqlite_column_names(connection, "tavern_runs")
            foreign_keys = connection.exec_driver_sql(
                "PRAGMA foreign_key_list(tavern_runs)"
            ).all()
            has_parent_foreign_key = any(
                str(row[2]) == "tavern_runs"
                and str(row[3]) == "parent_run_id"
                and str(row[4]) == "id"
                for row in foreign_keys
            )
            if "parent_run_id" in columns and has_parent_foreign_key:
                return

            connection.commit()
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                with connection.begin():
                    self._rebuild_legacy_tavern_runs_table(
                        connection,
                        has_parent_column="parent_run_id" in columns,
                        has_step_table="tavern_run_steps" in table_names,
                    )
            finally:
                if connection.in_transaction():
                    connection.rollback()
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
                connection.commit()

            violations = connection.exec_driver_sql("PRAGMA foreign_key_check").all()
            if violations:
                raise RuntimeError("sqlite_foreign_key_repair_failed")

    @staticmethod
    def _drop_tavern_run_indexes(connection) -> None:
        for index_name in (
            "ix_tavern_runs_room_id",
            "ix_tavern_runs_status",
            "uq_tavern_runs_parent_run_id",
        ):
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

    @staticmethod
    def _drop_tavern_run_step_indexes(connection) -> None:
        for index_name in (
            "ix_tavern_run_steps_persona_id",
            "ix_tavern_run_steps_status",
        ):
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

    def _rebuild_legacy_tavern_runs_table(
        self,
        connection,
        *,
        has_parent_column: bool,
        has_step_table: bool,
    ) -> None:
        legacy_runs = "tavern_runs_legacy_migration"
        legacy_steps = "tavern_run_steps_legacy_migration"
        if has_step_table:
            connection.exec_driver_sql(
                f"ALTER TABLE tavern_run_steps RENAME TO {legacy_steps}"
            )
            self._drop_tavern_run_step_indexes(connection)
        connection.exec_driver_sql(f"ALTER TABLE tavern_runs RENAME TO {legacy_runs}")
        self._drop_tavern_run_indexes(connection)
        Base.metadata.tables["tavern_runs"].create(connection, checkfirst=True)

        parent_expression = (
            f"CASE WHEN source.parent_run_id IS NULL OR EXISTS ("
            f"SELECT 1 FROM {legacy_runs} AS parent WHERE parent.id = source.parent_run_id"
            ") THEN source.parent_run_id ELSE NULL END"
            if has_parent_column
            else "NULL"
        )
        connection.exec_driver_sql(
            f"""
            INSERT INTO tavern_runs (
                id,
                room_id,
                idempotency_key,
                parent_run_id,
                status,
                mode,
                input_message_id,
                expected_room_revision,
                error_code,
                created_at,
                completed_at,
                payload
            )
            SELECT
                source.id,
                source.room_id,
                source.idempotency_key,
                {parent_expression},
                source.status,
                source.mode,
                source.input_message_id,
                source.expected_room_revision,
                source.error_code,
                source.created_at,
                source.completed_at,
                source.payload
            FROM {legacy_runs} AS source
            """
        )

        if has_step_table:
            Base.metadata.tables["tavern_run_steps"].create(connection, checkfirst=True)
            connection.exec_driver_sql(
                f"""
                INSERT INTO tavern_run_steps (
                    run_id,
                    step_index,
                    persona_id,
                    participant_prompt_hash,
                    status,
                    message_id,
                    reply_to_message_id,
                    error_code,
                    started_at,
                    completed_at,
                    lease_owner,
                    lease_expires_at,
                    claim_count,
                    payload
                )
                SELECT
                    run_id,
                    step_index,
                    persona_id,
                    participant_prompt_hash,
                    status,
                    message_id,
                    reply_to_message_id,
                    error_code,
                    started_at,
                    completed_at,
                    '',
                    '',
                    0,
                    payload
                FROM {legacy_steps}
                """
            )
            connection.exec_driver_sql(f"DROP TABLE {legacy_steps}")
        connection.exec_driver_sql(f"DROP TABLE {legacy_runs}")

    @staticmethod
    def _sqlite_column_names(connection, table_name: str) -> set[str]:
        return {
            str(row[1])
            for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})")
        }

    @staticmethod
    def _drop_study_session_indexes(connection) -> None:
        for index_name in (
            "ix_study_sessions_document_id",
            "ix_study_sessions_persona_id",
            "ix_study_sessions_plan_id",
        ):
            connection.exec_driver_sql(f"DROP INDEX IF EXISTS {index_name}")

    @staticmethod
    def _ensure_sqlite_study_session_indexes(connection) -> None:
        table = Base.metadata.tables.get("study_sessions")
        if table is None:
            return
        for index in table.indexes:
            index.create(connection, checkfirst=True)

    @staticmethod
    def _ensure_sqlite_tavern_room_indexes(connection) -> None:
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_tavern_rooms_updated_at_id "
            "ON tavern_rooms (updated_at DESC, id DESC)"
        )

    def _rebuild_legacy_study_sessions_table(self, connection, *, source_table: str) -> None:
        legacy_table = "study_sessions_legacy_migration"
        connection.exec_driver_sql(f"DROP TABLE IF EXISTS {legacy_table}")
        connection.exec_driver_sql(f"ALTER TABLE {source_table} RENAME TO {legacy_table}")
        self._drop_study_session_indexes(connection)
        Base.metadata.tables["study_sessions"].create(connection, checkfirst=True)
        connection.exec_driver_sql(
            f"""
            INSERT INTO study_sessions (
                id,
                document_id,
                persona_id,
                plan_id,
                study_unit_id,
                status,
                revision,
                last_turn_sequence,
                created_at,
                updated_at,
                payload
            )
            SELECT
                id,
                document_id,
                persona_id,
                plan_id,
                section_id,
                status,
                0,
                0,
                created_at,
                updated_at,
                payload
            FROM {legacy_table}
            """
        )
        connection.exec_driver_sql(f"DROP TABLE {legacy_table}")


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()
