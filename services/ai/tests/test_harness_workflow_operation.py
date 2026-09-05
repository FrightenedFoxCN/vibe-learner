from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models.harness_operation import HarnessDomainOperationKind
from app.persistence.database import Database
from app.persistence.harness_operation_repository import HarnessOperationBindingRepository
from app.persistence.harness_workflow_operation_repository import (
    HarnessWorkflowOperationRepository,
)
from app.persistence.models import HarnessWorkflowOperationRow


class HarnessWorkflowOperationRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(
            f"sqlite:///{Path(self.temp.name) / 'workflow-operations.db'}"
        )
        self.database.create_schema()
        self.repository = HarnessWorkflowOperationRepository(self.database)

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def test_admission_persists_domain_row_and_immutable_binding_atomically(self) -> None:
        binding = self.repository.admit(
            kind=HarnessDomainOperationKind.PERSONA_GENERATION,
            request_manifest={"mode": "keywords", "count": 3},
            operation_id="persona-generation-op-fixture",
        )
        resolved = HarnessOperationBindingRepository(self.database).require_domain(
            domain_operation_kind=HarnessDomainOperationKind.PERSONA_GENERATION,
            domain_operation_id="persona-generation-op-fixture",
        )
        self.assertEqual(resolved, binding)
        with self.database.session() as session:
            row = session.get(
                HarnessWorkflowOperationRow, "persona-generation-op-fixture"
            )
            assert row is not None
            self.assertEqual(row.status, "running")
            self.assertEqual(row.harness_operation_id, binding.harness_operation_id)
            self.assertEqual(len(row.request_digest), 64)

        self.repository.terminalize(binding=binding, success=True)
        with self.database.session() as session:
            row = session.get(
                HarnessWorkflowOperationRow, "persona-generation-op-fixture"
            )
            assert row is not None
            self.assertEqual(row.status, "completed")
            self.assertTrue(row.completed_at)

    def test_generic_row_binding_is_immutable_and_route_checked(self) -> None:
        binding = self.repository.admit(
            kind=HarnessDomainOperationKind.SCENE_GENERATION,
            request_manifest={"mode": "long_text", "layer_count": 2},
            operation_id="scene-generation-op-fixture",
        )
        with self.assertRaisesRegex(IntegrityError, "rebinding_forbidden"):
            with self.database.session() as session:
                session.execute(
                    update(HarnessWorkflowOperationRow)
                    .where(
                        HarnessWorkflowOperationRow.operation_id
                        == "scene-generation-op-fixture"
                    )
                    .values(harness_operation_id=None)
                )
        self.assertEqual(binding.domain_operation_kind.value, "scene_generation")

    def test_unsupported_domain_kind_fails_before_write(self) -> None:
        with self.assertRaisesRegex(ValueError, "kind_unsupported"):
            self.repository.admit(
                kind=HarnessDomainOperationKind.STUDY_CHAT,
                request_manifest={"kind": "invalid"},
            )

    def test_recover_abandoned_operation_fails_closed(self) -> None:
        binding = self.repository.admit(
            kind=HarnessDomainOperationKind.PERSONA_GENERATION,
            request_manifest={"mode": "keywords"},
            operation_id="persona-generation-op-abandoned",
        )
        self.assertEqual(self.repository.recover_abandoned_operations(), 1)
        with self.database.session() as session:
            row = session.get(
                HarnessWorkflowOperationRow, "persona-generation-op-abandoned"
            )
            assert row is not None
            self.assertEqual(row.status, "failed")
            self.assertEqual(row.error_code, "harness_workflow_operation_abandoned")
            self.assertTrue(row.completed_at)


if __name__ == "__main__":
    unittest.main()
