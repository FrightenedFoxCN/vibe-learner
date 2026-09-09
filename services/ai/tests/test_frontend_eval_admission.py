from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.harness_operation import HarnessDomainOperationKind
from app.persistence.database import Database
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.harness_workflow_operation_repository import (
    HarnessWorkflowOperationRepository,
)
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from tests.test_alembic_sqlite import _alembic_config


class FrontendEvalAdmissionTests(unittest.TestCase):
    def test_populated_database_upgrades_preserve_bindings_and_guards(self):
        for migration in ("alembic", "runtime"):
            with self.subTest(migration=migration), TemporaryDirectory() as folder:
                url = f"sqlite:///{Path(folder) / 'db.sqlite'}"
                config = _alembic_config(url)
                with patch.dict(os.environ, {"DATABASE_URL": url}):
                    command.upgrade(config, "20260903_0018")
                db = Database(url)
                old = HarnessWorkflowOperationRepository(db).admit(
                    kind=HarnessDomainOperationKind.PERSONA_GENERATION,
                    request_manifest={"count": 1},
                )
                db.dispose()
                if migration == "alembic":
                    with patch.dict(os.environ, {"DATABASE_URL": url}):
                        command.upgrade(config, "head")
                db = Database(url)
                try:
                    # The second call verifies the compatibility repair is idempotent.
                    db.create_schema()
                    db.create_schema()
                    repo = HarnessWorkflowOperationRepository(db)
                    new = repo.admit(
                        kind=HarnessDomainOperationKind.FRONTEND_DECODE,
                        request_manifest={"case_digest": "a" * 64},
                    )
                    self.assertEqual(new.workflow, HarnessWorkflow.FRONTEND_DECODE)
                    self.assertEqual(
                        new.entry_stage, HarnessStage.FRONTEND_RESPONSE_DECODE
                    )
                    bindings = HarnessOperationBindingRepository(db)
                    self.assertEqual(
                        bindings.resolve_harness_id(
                            harness_operation_id=old.harness_operation_id
                        ),
                        old,
                    )
                    self.assertEqual(
                        bindings.require_domain(
                            domain_operation_kind=HarnessDomainOperationKind.FRONTEND_DECODE,
                            domain_operation_id=new.domain_operation_id,
                        ),
                        new,
                    )
                    for statement, params in [
                        (
                            "UPDATE harness_operation_bindings SET workflow='persona' WHERE harness_operation_id=:id",
                            {"id": new.harness_operation_id},
                        ),
                        (
                            "DELETE FROM harness_operation_bindings WHERE harness_operation_id=:id",
                            {"id": old.harness_operation_id},
                        ),
                        (
                            "UPDATE harness_workflow_operations SET harness_operation_id=NULL WHERE operation_id=:id",
                            {"id": new.domain_operation_id},
                        ),
                    ]:
                        with (
                            self.assertRaises(IntegrityError),
                            db.engine.begin() as conn,
                        ):
                            conn.execute(text(statement), params)
                    with db.engine.connect() as conn:
                        self.assertEqual(
                            conn.exec_driver_sql("PRAGMA foreign_key_check").all(), []
                        )
                finally:
                    db.dispose()
                if migration == "alembic":
                    with (
                        patch.dict(os.environ, {"DATABASE_URL": url}),
                        self.assertRaisesRegex(
                            RuntimeError, "tombstones_prevent_downgrade"
                        ),
                    ):
                        command.downgrade(config, "20260903_0018")

    def test_empty_database_can_downgrade_and_upgrade(self):
        with TemporaryDirectory() as folder:
            url = f"sqlite:///{Path(folder) / 'db.sqlite'}"
            config = _alembic_config(url)
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                command.upgrade(config, "head")
                command.downgrade(config, "20260903_0018")
                command.upgrade(config, "head")
            db = Database(url)
            try:
                HarnessWorkflowOperationRepository(db).admit(
                    kind=HarnessDomainOperationKind.FRONTEND_DECODE,
                    request_manifest={"case": "synthetic"},
                )
            finally:
                db.dispose()


if __name__ == "__main__":
    unittest.main()
