from __future__ import annotations

from tests.support.migrations import alembic_config
from io import StringIO
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from app.persistence.database import Database
from app.persistence.document_repository import DocumentRepository
from tests.support.planning_operations import planning_document


ALEMBIC_HEAD = "20261029_0025"


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
                    str(
                        (foreign_key.get("options") or {}).get("ondelete") or ""
                    ).upper(),
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
    def test_unit_revision_upgrade_preserves_admissions_and_guards(self) -> None:
        from app.models.harness_operation import HarnessDomainOperationKind
        from app.persistence.harness_operation_repository import (
            HarnessOperationBindingRepository,
        )
        from app.persistence.harness_workflow_operation_repository import (
            HarnessWorkflowOperationRepository,
        )
        from sqlalchemy.exc import DatabaseError

        for mode in ("alembic", "runtime"):
            with self.subTest(mode=mode), TemporaryDirectory() as folder:
                url = f"sqlite:///{Path(folder) / 'populated.db'}"
                config = alembic_config(url)
                with patch.dict(os.environ, {"DATABASE_URL": url}):
                    command.upgrade(config, "20261029_0023")
                database = Database(url)
                binding = HarnessWorkflowOperationRepository(database).admit(
                    kind=HarnessDomainOperationKind.FRONTEND_DECODE,
                    request_manifest={"fixture": "migration"},
                )
                if mode == "alembic":
                    with patch.dict(os.environ, {"DATABASE_URL": url}):
                        command.upgrade(config, "head")
                else:
                    database.create_schema()
                restored = HarnessOperationBindingRepository(database).require_domain(
                    domain_operation_kind=binding.domain_operation_kind,
                    domain_operation_id=binding.domain_operation_id,
                )
                self.assertEqual(restored, binding)
                with database.engine.connect() as connection:
                    self.assertEqual(
                        connection.exec_driver_sql("PRAGMA foreign_key_check").all(), []
                    )
                    self.assertIn(
                        "study_unit_revision",
                        next(
                            item["sqltext"]
                            for item in inspect(connection).get_check_constraints(
                                "harness_operation_bindings"
                            )
                            if item["name"] == "ck_harness_operation_binding_route"
                        ),
                    )
                with (
                    self.assertRaises(DatabaseError),
                    database.engine.begin() as connection,
                ):
                    connection.execute(
                        text(
                            "UPDATE harness_operation_bindings SET domain_operation_id='tampered'"
                        )
                    )
                database.dispose()

    def test_document_revision_upgrade_preserves_legacy_payload_and_digest(
        self,
    ) -> None:
        payload = planning_document().model_dump(mode="json")
        self.assertNotIn("revision", payload)
        for migration in ("alembic", "runtime"):
            with self.subTest(migration=migration), TemporaryDirectory() as temp_dir:
                url = f"sqlite:///{Path(temp_dir) / 'legacy.db'}"
                config = alembic_config(url)
                with patch.dict(os.environ, {"DATABASE_URL": url}):
                    command.upgrade(config, "20260914_0022")
                engine = create_engine(url)
                with engine.begin() as connection:
                    connection.execute(
                        text(
                            "INSERT INTO documents (id, payload) VALUES (:id, :payload)"
                        ),
                        {"id": payload["id"], "payload": json.dumps(payload)},
                    )
                engine.dispose()
                if migration == "alembic":
                    with patch.dict(os.environ, {"DATABASE_URL": url}):
                        command.upgrade(config, "head")
                database = Database(url)
                try:
                    database.create_schema()
                    document = DocumentRepository(database).get(payload["id"])
                    self.assertEqual(document.revision, 0)
                    self.assertEqual(document.model_dump(mode="json"), payload)
                    with database.engine.connect() as connection:
                        stored = connection.execute(
                            text("SELECT payload FROM documents")
                        ).scalar_one()
                    self.assertEqual(json.loads(stored), payload)
                finally:
                    database.dispose()

    def test_fresh_sqlite_upgrade_reaches_head_and_matches_runtime_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            migrated_url = f"sqlite:///{Path(temp_dir) / 'migrated.db'}"
            runtime_url = f"sqlite:///{Path(temp_dir) / 'runtime.db'}"

            config = alembic_config(migrated_url)
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
        config = alembic_config(database_url)
        output = StringIO()
        config.output_buffer = output
        with patch.dict(os.environ, {"DATABASE_URL": database_url}):
            command.upgrade(config, "head", sql=True)

        ddl = output.getvalue()
        documents_ddl = ddl[
            ddl.index("CREATE TABLE documents") : ddl.index(
                "CREATE TABLE learning_plans"
            )
        ]
        self.assertIn("payload JSONB DEFAULT '{}' NOT NULL", documents_ddl)
        self.assertIn("uq_tavern_rooms_creation_key", ddl)
        self.assertIn("ix_tavern_rooms_updated_at_id", ddl)
        self.assertIn("uq_tavern_runs_parent_run_id", ddl)
        self.assertIn("fk_tavern_runs_parent_run_id", ddl)
        self.assertIn("CREATE TABLE harness_operation_bindings", ddl)
        self.assertIn("uq_harness_operation_binding_domain_identity", ddl)
        self.assertIn("fk_harness_operation_binding_parent", ddl)
        self.assertIn("ck_harness_operation_binding_route", ddl)
        self.assertIn("CREATE TABLE harness_artifacts", ddl)
        self.assertIn("CREATE TABLE harness_artifact_grants", ddl)
        self.assertIn("CREATE TABLE harness_effect_batches", ddl)
        self.assertIn("CREATE TABLE harness_effect_journal", ddl)
        self.assertIn("CREATE TABLE harness_runtime_executions", ddl)
        self.assertIn("CREATE TABLE harness_workflow_operations", ddl)
        self.assertIn("uq_harness_runtime_operation_stage_slot", ddl)
        self.assertIn("ck_harness_runtime_state_shape", ddl)
        self.assertIn("validate_harness_runtime_update", ddl)
        self.assertIn("reject_harness_runtime_delete", ddl)


if __name__ == "__main__":
    unittest.main()
