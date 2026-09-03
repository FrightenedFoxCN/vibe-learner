"""Versioned, fail-closed migration evidence for legacy model recoveries.

Legacy ``ModelRecoveryRecord`` values are useful for compatibility projections,
but they do not contain Harness identity or lifecycle timestamps.  This module
only translates them when an already admitted operation and an already stored
v3 trace provide those facts.  It deliberately never manufactures a trace,
attempt, or commit claim.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.domain import ModelRecoveryRecord
from app.models.harness import (
    HarnessAttemptPhase,
    HarnessAttemptRecord,
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessTraceV3,
)
from app.models.harness_operation import HarnessOperationBindingV1


HARNESS_RECOVERY_MIGRATION_SCHEMA_VERSION = "harness-recovery-migration-v1"


class HarnessLegacyRecoveryMappingV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal["HarnessLegacyRecoveryMappingV1"] = (
        "HarnessLegacyRecoveryMappingV1"
    )
    schema_version: Literal["harness-recovery-migration-v1"] = (
        HARNESS_RECOVERY_MIGRATION_SCHEMA_VERSION
    )
    category: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=1, max_length=160)
    strategy: str = Field(min_length=1, max_length=320)
    phase: HarnessAttemptPhase
    check_name: str = Field(min_length=1, max_length=160)
    check_code: str = Field(min_length=1, max_length=160)


# This is intentionally a closed registry.  Adding a new legacy value requires
# review and a fixture; unknown values must remain in the compatibility view.
HARNESS_LEGACY_RECOVERY_MAPPINGS: tuple[HarnessLegacyRecoveryMappingV1, ...] = (
    HarnessLegacyRecoveryMappingV1(category="schema_retry", reason="*", strategy="retry_strict_actor_reply", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_schema_retry"),
    HarnessLegacyRecoveryMappingV1(category="schema_retry", reason="*", strategy="retry_without_tools", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_schema_retry"),
    HarnessLegacyRecoveryMappingV1(category="semantic_retry", reason="*", strategy="retry_strict_actor_reply", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_semantic_retry"),
    HarnessLegacyRecoveryMappingV1(category="semantic_retry", reason="*", strategy="retry_without_tools", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_semantic_retry"),
    HarnessLegacyRecoveryMappingV1(category="transport_retry", reason="*", strategy="retry_without_tools", phase=HarnessAttemptPhase.GENERATE, check_name="legacy_recovery", check_code="legacy_transport_retry"),
    HarnessLegacyRecoveryMappingV1(category="transport_compatibility", reason="*", strategy="retry_json_object", phase=HarnessAttemptPhase.GENERATE, check_name="legacy_recovery", check_code="legacy_transport_compatibility"),
    HarnessLegacyRecoveryMappingV1(category="transport_retry", reason="*", strategy="retry_same_payload", phase=HarnessAttemptPhase.GENERATE, check_name="legacy_recovery", check_code="legacy_transport_retry"),
    HarnessLegacyRecoveryMappingV1(category="feature_fallback", reason="*", strategy="disable_web_search", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_feature_fallback"),
    HarnessLegacyRecoveryMappingV1(category="schema_retry", reason="*", strategy="strict_contract_repair", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_schema_retry"),
    HarnessLegacyRecoveryMappingV1(category="semantic_retry", reason="*", strategy="retry_structured_json", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_semantic_retry"),
    HarnessLegacyRecoveryMappingV1(category="semantic_retry", reason="*", strategy="retry_structured_response", phase=HarnessAttemptPhase.REPAIR, check_name="legacy_recovery", check_code="legacy_semantic_retry"),
)


class HarnessRecoveryMigrationEvidenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal["HarnessRecoveryMigrationEvidenceV1"] = "HarnessRecoveryMigrationEvidenceV1"
    schema_version: Literal["harness-recovery-migration-v1"] = HARNESS_RECOVERY_MIGRATION_SCHEMA_VERSION
    recovery_id: str = Field(min_length=1, max_length=160)
    trace_id: str = Field(min_length=1, max_length=160)
    operation_id: str = Field(min_length=1, max_length=160)
    attempt_id: str = Field(min_length=1, max_length=160)
    attempt_index: int = Field(ge=1)
    attempt: HarnessAttemptRecord
    check: HarnessCheckV2
    mapping_code: str = Field(min_length=1, max_length=160)


class HarnessRecoveryMigrationError(ValueError):
    pass


def migrate_legacy_recovery(
    *,
    recovery: ModelRecoveryRecord,
    operation_binding: HarnessOperationBindingV1 | None,
    trace: HarnessTraceV3 | None,
) -> HarnessRecoveryMigrationEvidenceV1:
    """Map one legacy record to an existing v3 attempt and a typed check.

    ``operation_binding`` and ``trace`` are mandatory in practice.  ``None``
    is accepted only to provide a typed, deterministic error for read-only
    retention jobs handling legacy-unbound rows.
    """
    if operation_binding is None:
        raise HarnessRecoveryMigrationError("harness_recovery_legacy_unbound")
    if trace is None:
        raise HarnessRecoveryMigrationError("harness_recovery_trace_not_found")
    if trace.operation_id != operation_binding.harness_operation_id:
        raise HarnessRecoveryMigrationError("harness_recovery_operation_binding_mismatch")
    if trace.stage != operation_binding.entry_stage or trace.workflow != operation_binding.workflow:
        raise HarnessRecoveryMigrationError("harness_recovery_stage_binding_mismatch")

    matches = [m for m in HARNESS_LEGACY_RECOVERY_MAPPINGS if m.category == recovery.category and m.strategy == recovery.strategy and (m.reason == "*" or m.reason == recovery.reason)]
    if not matches:
        raise HarnessRecoveryMigrationError("harness_recovery_mapping_unknown")
    if len(matches) != 1:
        raise HarnessRecoveryMigrationError("harness_recovery_mapping_ambiguous")
    mapping = matches[0]
    candidates = [a for a in trace.attempt_records if a.phase == mapping.phase and ((mapping.phase == HarnessAttemptPhase.REPAIR) or a.status.value == "failed")]
    if not candidates:
        raise HarnessRecoveryMigrationError("harness_recovery_historical_attempt_missing")
    attempt = candidates[-1]
    check = HarnessCheckV2(name=mapping.check_name, status=HarnessCheckStatus.WARNING, code=mapping.check_code, message=f"legacy recovery {recovery.recovery_id} mapped to existing attempt {attempt.attempt_id}")
    return HarnessRecoveryMigrationEvidenceV1(recovery_id=recovery.recovery_id, trace_id=trace.trace_id, operation_id=trace.operation_id, attempt_id=attempt.attempt_id, attempt_index=attempt.attempt_index, attempt=attempt, check=check, mapping_code=mapping.check_code)
