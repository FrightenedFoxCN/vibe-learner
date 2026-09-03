from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest

from app.models.domain import ModelRecoveryRecord
from app.models.harness import (
    HarnessAttemptPhase,
    HarnessAttemptRecord,
    HarnessAttemptStatus,
    HarnessStage,
    HarnessWorkflow,
)
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.models.harness_recovery_migration import (
    HarnessRecoveryMigrationError,
    migrate_legacy_recovery,
)
from app.services.harness_recovery_migration import (
    is_legacy_recovery_read_only,
    migrate_legacy_recoveries,
)


class HarnessRecoveryMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.binding = HarnessOperationBindingV1(
            harness_operation_id="harness-operation-" + "a" * 32,
            domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
            domain_operation_id="run-1",
            workflow=HarnessWorkflow.TAVERN,
            entry_stage=HarnessStage.TAVERN_ACTOR_REPLY,
            admitted_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
        attempt = HarnessAttemptRecord(
            attempt_id="harness-attempt-" + "b" * 32,
            attempt_index=1,
            phase=HarnessAttemptPhase.REPAIR,
            status=HarnessAttemptStatus.PASSED,
            error_code="",
            duration_ms=4,
        )
        self.trace = SimpleNamespace(
            trace_id="harness-trace-" + "c" * 32,
            operation_id=self.binding.harness_operation_id,
            workflow=self.binding.workflow,
            stage=self.binding.entry_stage,
            attempt_records=[attempt],
        )
        self.recovery = ModelRecoveryRecord(
            recovery_id="recovery-1",
            category="semantic_retry",
            reason="invalid_actor_reply",
            strategy="retry_strict_actor_reply",
            created_at="2026-09-01T00:00:00+00:00",
        )

    def test_admitted_mapping_references_existing_attempt(self) -> None:
        evidence = migrate_legacy_recovery(
            recovery=self.recovery,
            operation_binding=self.binding,
            trace=self.trace,
        )
        self.assertEqual(evidence.operation_id, self.binding.harness_operation_id)
        self.assertEqual(evidence.attempt_id, self.trace.attempt_records[0].attempt_id)
        self.assertEqual(evidence.check.code, "legacy_semantic_retry")

    def test_legacy_unbound_is_rejected(self) -> None:
        with self.assertRaisesRegex(HarnessRecoveryMigrationError, "legacy_unbound"):
            migrate_legacy_recovery(
                recovery=self.recovery, operation_binding=None, trace=self.trace
            )

    def test_unknown_mapping_is_rejected(self) -> None:
        unknown = self.recovery.model_copy(update={"strategy": "invented_strategy"})
        with self.assertRaisesRegex(HarnessRecoveryMigrationError, "mapping_unknown"):
            migrate_legacy_recovery(
                recovery=unknown, operation_binding=self.binding, trace=self.trace
            )

    def test_missing_historical_attempt_is_rejected(self) -> None:
        trace = SimpleNamespace(**{**vars(self.trace), "attempt_records": []})
        with self.assertRaisesRegex(HarnessRecoveryMigrationError, "attempt_missing"):
            migrate_legacy_recovery(
                recovery=self.recovery, operation_binding=self.binding, trace=trace
            )

    def test_duplicate_recovery_ids_are_rejected(self) -> None:
        with self.assertRaisesRegex(HarnessRecoveryMigrationError, "duplicate_mapping"):
            migrate_legacy_recoveries(
                recoveries=[self.recovery, self.recovery],
                operation_binding=self.binding,
                trace=self.trace,
                write_cutoff=datetime(2026, 9, 2, tzinfo=UTC),
            )

    def test_write_cutoff_keeps_new_records_read_only(self) -> None:
        self.assertTrue(
            is_legacy_recovery_read_only(
                self.recovery, write_cutoff=datetime(2026, 8, 31, tzinfo=UTC)
            )
        )
        with self.assertRaisesRegex(HarnessRecoveryMigrationError, "write_cutoff"):
            migrate_legacy_recoveries(
                recoveries=[self.recovery],
                operation_binding=self.binding,
                trace=self.trace,
                write_cutoff=datetime(2026, 8, 31, tzinfo=UTC),
            )

    def test_naive_cutoff_is_rejected(self) -> None:
        with self.assertRaisesRegex(HarnessRecoveryMigrationError, "cutoff_must_be_utc"):
            migrate_legacy_recoveries(
                recoveries=[],
                operation_binding=self.binding,
                trace=self.trace,
                write_cutoff=datetime(2026, 9, 2),
            )


if __name__ == "__main__":
    unittest.main()
