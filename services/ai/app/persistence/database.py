from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
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

        with self.engine.begin() as connection:
            table_names = {
                str(row[0])
                for row in connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }

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
            FROM {legacy_table}
            """
        )
        connection.exec_driver_sql(f"DROP TABLE {legacy_table}")
