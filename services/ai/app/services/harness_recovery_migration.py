"""Read-only legacy recovery migration boundary (HRN-RECOVERY-MIG-001)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.models.domain import ModelRecoveryRecord
from app.models.harness import HarnessTraceV3
from app.models.harness_operation import HarnessOperationBindingV1
from app.models.harness_recovery_migration import (
    HarnessRecoveryMigrationError,
    HarnessRecoveryMigrationEvidenceV1,
    migrate_legacy_recovery,
)


def migrate_legacy_recoveries(
    *,
    recoveries: list[ModelRecoveryRecord] | tuple[ModelRecoveryRecord, ...],
    operation_binding: HarnessOperationBindingV1 | None,
    trace: HarnessTraceV3 | None,
    write_cutoff: datetime,
) -> tuple[HarnessRecoveryMigrationEvidenceV1, ...]:
    """Translate historical records without modifying the source trace.

    The cutoff is a hard write boundary: records created on/after it stay in
    the legacy read-only projection.  A recovery ID can be emitted once per
    batch, which prevents metric double counting on replayed migration jobs.
    """
    if write_cutoff.tzinfo is None or write_cutoff.utcoffset() != datetime.now(UTC).utcoffset():
        raise HarnessRecoveryMigrationError("harness_recovery_cutoff_must_be_utc")
    if operation_binding is None or trace is None:
        raise HarnessRecoveryMigrationError("harness_recovery_legacy_unbound")
    seen: set[str] = set()
    output: list[HarnessRecoveryMigrationEvidenceV1] = []
    for recovery in recoveries:
        if recovery.recovery_id in seen:
            raise HarnessRecoveryMigrationError("harness_recovery_duplicate_mapping")
        seen.add(recovery.recovery_id)
        try:
            created = datetime.fromisoformat(recovery.created_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HarnessRecoveryMigrationError("harness_recovery_timestamp_invalid") from exc
        if created.tzinfo is None or created.utcoffset() != datetime.now(UTC).utcoffset():
            raise HarnessRecoveryMigrationError("harness_recovery_timestamp_must_be_utc")
        if created >= write_cutoff:
            raise HarnessRecoveryMigrationError("harness_recovery_after_write_cutoff")
        output.append(migrate_legacy_recovery(recovery=recovery, operation_binding=operation_binding, trace=trace))
    return tuple(output)


def is_legacy_recovery_read_only(
    recovery: ModelRecoveryRecord, *, write_cutoff: datetime
) -> bool:
    """Return whether a legacy row is retained without migration writes."""
    if write_cutoff.tzinfo is None or write_cutoff.utcoffset() != timedelta(0):
        raise HarnessRecoveryMigrationError("harness_recovery_cutoff_must_be_utc")
    try:
        created = datetime.fromisoformat(recovery.created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HarnessRecoveryMigrationError("harness_recovery_timestamp_invalid") from exc
    if created.tzinfo is None or created.utcoffset() != timedelta(0):
        raise HarnessRecoveryMigrationError("harness_recovery_timestamp_must_be_utc")
    return created >= write_cutoff
