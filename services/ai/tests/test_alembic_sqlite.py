from __future__ import annotations

from io import StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.persistence.database import Database


SERVICE_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_HEAD = "20260825_0012"


def _alembic_config(database_url: str) -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _normalize_sql(expression: object) -> str:
    return " ".join(str(expression).lower().split())


def _schema_signature(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names()) - {"alembic_version"}
    signature: dict[str, object] = {}
    for table_name in sorted(table_names):
        columns = tuple(
            sorted(
                (
                    str(column["name"]),
                    str(column["type"]).upper(),
                    bool(column["nullable"]),
                )
                for column in inspector.get_columns(table_name)
            )
        )
        primary_key = tuple(
            inspector.get_pk_constraint(table_name).get("constrained_columns") or ()
        )
        unique_constraints = tuple(
            sorted(
                tuple(constraint.get("column_names") or ())
                for constraint in inspector.get_unique_constraints(table_name)
            )
        )
        foreign_keys = tuple(
            sorted(
                (
                    tuple(foreign_key.get("constrained_columns") or ()),
                    str(foreign_key.get("referred_table") or ""),
                    tuple(foreign_key.get("referred_columns") or ()),
                    str((foreign_key.get("options") or {}).get("ondelete") or "").upper(),
                )
                for foreign_key in inspector.get_foreign_keys(table_name)
            )
        )
        checks = tuple(
            sorted(
                _normalize_sql(constraint.get("sqltext") or "")
                for constraint in inspector.get_check_constraints(table_name)
            )
        )
        indexes = tuple(
            sorted(
                (
                    str(index.get("name") or ""),
                    tuple(index.get("column_names") or ()),
                    bool(index.get("unique")),
                )
                for index in inspector.get_indexes(table_name)
            )
        )
        signature[table_name] = {
            "columns": columns,
            "primary_key": primary_key,
            "unique_constraints": unique_constraints,
            "foreign_keys": foreign_keys,
            "checks": checks,
            "indexes": indexes,
        }
    return signature


class AlembicSqliteTests(unittest.TestCase):
    def test_fresh_sqlite_upgrade_reaches_head_and_matches_runtime_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            migrated_url = f"sqlite:///{Path(temp_dir) / 'migrated.db'}"
            runtime_url = f"sqlite:///{Path(temp_dir) / 'runtime.db'}"

            config = _alembic_config(migrated_url)
            with patch.dict(os.environ, {"DATABASE_URL": migrated_url}):
                command.upgrade(config, "head")

            migrated = Database(migrated_url)
            runtime = Database(runtime_url)
            try:
                runtime.create_schema()
                with migrated.engine.connect() as connection:
                    revision = connection.exec_driver_sql(
                        "SELECT version_num FROM alembic_version"
                    ).scalar_one()
                self.assertEqual(revision, ALEMBIC_HEAD)
                self.assertEqual(
                    _schema_signature(migrated.engine),
                    _schema_signature(runtime.engine),
                )
            finally:
                migrated.dispose()
                runtime.dispose()

    def test_postgresql_offline_ddl_keeps_jsonb_and_named_constraints(self) -> None:
        database_url = "postgresql+psycopg://unused:unused@localhost/unused"
        config = _alembic_config(database_url)
        output = StringIO()
        config.output_buffer = output
        with patch.dict(os.environ, {"DATABASE_URL": database_url}):
            command.upgrade(config, "head", sql=True)

        ddl = output.getvalue()
        documents_ddl = ddl[
            ddl.index("CREATE TABLE documents") : ddl.index("CREATE TABLE learning_plans")
        ]
        self.assertIn("payload JSONB DEFAULT '{}' NOT NULL", documents_ddl)
        self.assertIn("uq_tavern_rooms_creation_key", ddl)
        self.assertIn("ix_tavern_rooms_updated_at_id", ddl)
        self.assertIn("uq_tavern_runs_parent_run_id", ddl)
        self.assertIn("fk_tavern_runs_parent_run_id", ddl)


if __name__ == "__main__":
    unittest.main()
