from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
import json
from typing import Generic, Literal, TypeVar

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


class HarnessStatus(StrEnum):
    PASSED = "passed"
    REPAIRED = "repaired"
    FAILED = "failed"
    SKIPPED = "skipped"


class HarnessCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class HarnessCheckRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: HarnessCheckStatus
    code: str = ""
    message: str = ""


class HarnessTraceRecord(BaseModel):
    """Legacy v1 validation summary kept for existing Tavern records."""

    model_config = ConfigDict(extra="forbid")

    version: str
    workflow: str
    stage: str
    status: HarnessStatus
    schema_name: str
    input_digest: str = ""
    context_digest: str = ""
    checks: list[HarnessCheckRecord] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=1, le=3)
    recovery_strategy: str = "none"
    duration_ms: int = Field(default=0, ge=0)

    @field_validator("version")
    @classmethod
    def reject_reserved_schema_version_prefix(cls, value: str) -> str:
        if value.startswith("harness-trace-"):
            raise ValueError("harness_trace_schema_version_discriminator_required")
        return value


# Existing persisted Tavern payloads have no discriminator. Keep their exact model
# and ambiguous ``version`` semantics intact instead of fabricating v2 evidence.
HarnessTraceV1 = HarnessTraceRecord


HARNESS_TRACE_SCHEMA_V2 = "harness-trace-v2"


class HarnessWorkflow(StrEnum):
    DOCUMENT_PARSE = "document_parse"
    OCR = "ocr"
    STUDY_UNIT_CLEANUP = "study_unit_cleanup"
    PLANNING = "planning"
    PERSONA = "persona"
    SCENE = "scene"
    STUDY_CHAT = "study_chat"
    TAVERN = "tavern"
    FRONTEND_DECODE = "frontend_decode"


class HarnessDigestAlgorithm(StrEnum):
    SHA256 = "sha256"


class HarnessAttemptPhase(StrEnum):
    GENERATE = "generate"
    DECODE = "decode"
    VALIDATE = "validate"
    REPAIR = "repair"
    COMMIT = "commit"
    ROLLBACK = "rollback"


class HarnessAttemptStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class HarnessCommitStatus(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    NOT_COMMITTED = "not_committed"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class HarnessDigestScope(StrEnum):
    COMMITTED_PROJECTION = "committed_projection"
    COMMITTED_BATCH = "committed_batch"


class HarnessV2Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HarnessContractRef(HarnessV2Model):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=160)


class HarnessResourceRef(HarnessV2Model):
    resource_type: str = Field(min_length=1, max_length=96)
    resource_id: str = Field(min_length=1, max_length=160)
    revision: int | None = Field(default=None, ge=0)


class HarnessSnapshotRef(HarnessV2Model):
    artifact_type: str = Field(min_length=1, max_length=96)
    artifact_id: str = Field(min_length=1, max_length=160)
    schema_version: str = Field(min_length=1, max_length=160)
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] = HarnessDigestAlgorithm.SHA256
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class HarnessContextEnvelope(HarnessV2Model):
    schema_name: str = Field(min_length=1, max_length=160)
    schema_version: str = Field(min_length=1, max_length=160)
    workflow: HarnessWorkflow
    operation_id: str = Field(min_length=1, max_length=160)
    subject_refs: list[HarnessResourceRef] = Field(default_factory=list, max_length=64)
    component_versions: list[HarnessContractRef] = Field(
        default_factory=list,
        max_length=64,
    )
    snapshot_refs: list[HarnessSnapshotRef] = Field(default_factory=list, max_length=64)
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] = HarnessDigestAlgorithm.SHA256
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_version: str | None = Field(default=None, min_length=1, max_length=160)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_canonical_references(self) -> "HarnessContextEnvelope":
        subject_identities = [
            (item.resource_type, item.resource_id) for item in self.subject_refs
        ]
        if len(subject_identities) != len(set(subject_identities)):
            raise ValueError("harness_context_subject_ref_duplicate")
        if subject_identities != sorted(subject_identities):
            raise ValueError("harness_context_subject_refs_not_sorted")

        component_names = [item.name for item in self.component_versions]
        if len(component_names) != len(set(component_names)):
            raise ValueError("harness_context_component_version_duplicate")
        if component_names != sorted(component_names):
            raise ValueError("harness_context_component_versions_not_sorted")

        snapshot_identities = [
            (item.artifact_type, item.artifact_id) for item in self.snapshot_refs
        ]
        if len(snapshot_identities) != len(set(snapshot_identities)):
            raise ValueError("harness_context_snapshot_ref_duplicate")
        if snapshot_identities != sorted(snapshot_identities):
            raise ValueError("harness_context_snapshot_refs_not_sorted")
        return self


class HarnessCheckV2(HarnessV2Model):
    name: str = Field(min_length=1, max_length=160)
    status: HarnessCheckStatus
    code: str = Field(max_length=160)
    message: str = Field(max_length=2000)


class HarnessAttemptRecord(HarnessV2Model):
    attempt_id: str = Field(min_length=1, max_length=160)
    attempt_index: int = Field(ge=1)
    phase: HarnessAttemptPhase
    status: HarnessAttemptStatus
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    error_code: str = Field(max_length=160)
    duration_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_error_code(self) -> "HarnessAttemptRecord":
        if self.status == HarnessAttemptStatus.FAILED and not self.error_code:
            raise ValueError("harness_failed_attempt_error_code_required")
        if self.status != HarnessAttemptStatus.FAILED and self.error_code:
            raise ValueError("harness_nonfailed_attempt_error_code_forbidden")
        return self


class HarnessCommittedResourceRef(HarnessV2Model):
    resource_type: str = Field(min_length=1, max_length=96)
    resource_id: str = Field(min_length=1, max_length=160)
    expected_revision: int | None = Field(default=None, ge=0)
    committed_revision: int | None = Field(default=None, ge=0)
    first_sequence: int | None = Field(default=None, ge=1)
    last_sequence: int | None = Field(default=None, ge=1)
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_committed_resource(self) -> "HarnessCommittedResourceRef":
        if (self.first_sequence is None) != (self.last_sequence is None):
            raise ValueError("harness_commit_sequence_range_incomplete")
        if (
            self.first_sequence is not None
            and self.last_sequence is not None
            and self.first_sequence > self.last_sequence
        ):
            raise ValueError("harness_commit_sequence_range_invalid")
        if (
            self.expected_revision is not None
            and self.committed_revision is not None
            and self.committed_revision < self.expected_revision
        ):
            raise ValueError("harness_commit_revision_regressed")
        return self


class HarnessCommitEvidence(HarnessV2Model):
    status: HarnessCommitStatus
    effect_batch_id: str | None = Field(default=None, min_length=1, max_length=160)
    payload_contract: HarnessContractRef | None = None
    digest_algorithm: Literal[HarnessDigestAlgorithm.SHA256] | None = None
    digest_scope: HarnessDigestScope | None = None
    attempted_resource_refs: list[HarnessResourceRef] = Field(
        default_factory=list,
        max_length=64,
    )
    committed_resources: list[HarnessCommittedResourceRef] = Field(
        default_factory=list,
        max_length=64,
    )
    payload_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    committed_at: AwareDatetime | None = None
    rollback_reason_code: str = Field(max_length=160)
    rolled_back_at: AwareDatetime | None = None

    @field_validator("committed_at", "rolled_back_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("harness_effect_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_commit_shape(self) -> "HarnessCommitEvidence":
        attempted_identities = [
            (item.resource_type, item.resource_id)
            for item in self.attempted_resource_refs
        ]
        if len(attempted_identities) != len(set(attempted_identities)):
            raise ValueError("harness_attempted_resource_ref_duplicate")
        if attempted_identities != sorted(attempted_identities):
            raise ValueError("harness_attempted_resource_refs_not_sorted")

        committed_identities = [
            (item.resource_type, item.resource_id)
            for item in self.committed_resources
        ]
        if len(committed_identities) != len(set(committed_identities)):
            raise ValueError("harness_committed_resource_ref_duplicate")
        if committed_identities != sorted(committed_identities):
            raise ValueError("harness_committed_resource_refs_not_sorted")

        if (
            self.digest_scope == HarnessDigestScope.COMMITTED_PROJECTION
            and len(self.attempted_resource_refs) != 1
        ):
            raise ValueError("harness_projection_digest_requires_single_resource")

        if self.status == HarnessCommitStatus.NOT_APPLICABLE:
            if (
                self.effect_batch_id is not None
                or self.payload_contract is not None
                or self.digest_algorithm is not None
                or self.digest_scope is not None
                or self.attempted_resource_refs
                or self.committed_resources
                or self.payload_digest is not None
                or self.committed_at is not None
                or self.rollback_reason_code
                or self.rolled_back_at is not None
            ):
                raise ValueError("harness_not_applicable_evidence_not_empty")
        elif self.status == HarnessCommitStatus.NOT_COMMITTED:
            if self.committed_resources or self.payload_digest is not None or self.committed_at:
                raise ValueError("harness_not_committed_contains_committed_state")
            if self.rollback_reason_code or self.rolled_back_at is not None:
                raise ValueError("harness_not_committed_contains_rollback_state")
            attempted_metadata = (
                self.effect_batch_id,
                self.payload_contract,
                self.digest_algorithm,
                self.digest_scope,
            )
            if self.attempted_resource_refs:
                if any(value is None for value in attempted_metadata):
                    raise ValueError("harness_not_committed_attempt_metadata_incomplete")
            elif any(value is not None for value in attempted_metadata):
                raise ValueError("harness_not_committed_attempt_resources_missing")
        elif self.status == HarnessCommitStatus.COMMITTED:
            if (
                self.effect_batch_id is None
                or self.payload_contract is None
                or self.digest_algorithm is None
                or self.digest_scope is None
                or not self.attempted_resource_refs
                or not self.committed_resources
                or self.payload_digest is None
                or self.committed_at is None
            ):
                raise ValueError("harness_committed_evidence_incomplete")
            if attempted_identities != committed_identities:
                raise ValueError("harness_commit_resource_set_mismatch")
            for attempted, committed in zip(
                self.attempted_resource_refs,
                self.committed_resources,
                strict=True,
            ):
                if attempted.revision != committed.expected_revision:
                    raise ValueError("harness_commit_expected_revision_mismatch")
            if (
                self.digest_scope == HarnessDigestScope.COMMITTED_PROJECTION
                and self.payload_digest != self.committed_resources[0].payload_digest
            ):
                raise ValueError("harness_projection_digest_mismatch")
            if (
                self.digest_scope == HarnessDigestScope.COMMITTED_BATCH
                and self.payload_digest
                != canonical_harness_commit_digest(
                    payload_contract=self.payload_contract,
                    committed_resources=self.committed_resources,
                    digest_scope=self.digest_scope,
                )
            ):
                raise ValueError("harness_batch_manifest_digest_mismatch")
            if self.rollback_reason_code or self.rolled_back_at is not None:
                raise ValueError("harness_committed_contains_rollback_state")
        elif self.status == HarnessCommitStatus.ROLLED_BACK:
            if (
                self.effect_batch_id is None
                or self.payload_contract is None
                or self.digest_algorithm is None
                or self.digest_scope is None
                or not self.attempted_resource_refs
                or not self.rollback_reason_code
                or self.rolled_back_at is None
            ):
                raise ValueError("harness_rollback_evidence_incomplete")
            if self.committed_resources or self.payload_digest is not None or self.committed_at:
                raise ValueError("harness_rolled_back_contains_committed_state")
        return self


class HarnessTraceV2(HarnessV2Model):
    trace_schema_version: Literal["harness-trace-v2"]
    trace_id: str = Field(min_length=1, max_length=160)
    operation_id: str = Field(min_length=1, max_length=160)
    parent_trace_id: str | None = Field(default=None, min_length=1, max_length=160)
    workflow: HarnessWorkflow
    stage: str = Field(min_length=1, max_length=160)
    status: HarnessStatus
    contract: HarnessContractRef
    context: HarnessContextEnvelope
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    checks: list[HarnessCheckV2] = Field(default_factory=list, max_length=256)
    attempt_records: list[HarnessAttemptRecord] = Field(min_length=1, max_length=128)
    recovery_strategy: str = Field(min_length=1, max_length=320)
    error_code: str = Field(max_length=160)
    duration_ms: int = Field(ge=0)
    commit_evidence: HarnessCommitEvidence
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("harness_trace_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_trace_shape(self) -> "HarnessTraceV2":
        if self.parent_trace_id == self.trace_id:
            raise ValueError("harness_parent_trace_self_reference")
        if self.context.operation_id != self.operation_id:
            raise ValueError("harness_context_operation_mismatch")
        if self.context.workflow != self.workflow:
            raise ValueError("harness_context_workflow_mismatch")

        attempt_ids = [item.attempt_id for item in self.attempt_records]
        if len(attempt_ids) != len(set(attempt_ids)):
            raise ValueError("harness_attempt_id_duplicate")
        attempt_indexes = [item.attempt_index for item in self.attempt_records]
        if attempt_indexes != list(range(1, len(attempt_indexes) + 1)):
            raise ValueError("harness_attempt_indexes_not_contiguous")

        if self.completed_at < self.started_at:
            raise ValueError("harness_trace_time_range_invalid")
        if any(item.duration_ms > self.duration_ms for item in self.attempt_records):
            raise ValueError("harness_attempt_duration_exceeds_trace")

        failed_attempts = [
            item for item in self.attempt_records if item.status == HarnessAttemptStatus.FAILED
        ]
        failed_checks = [
            item for item in self.checks if item.status == HarnessCheckStatus.FAILED
        ]
        warning_checks = [
            item for item in self.checks if item.status == HarnessCheckStatus.WARNING
        ]
        repair_attempts = [
            item
            for item in self.attempt_records
            if item.phase == HarnessAttemptPhase.REPAIR
            and item.status == HarnessAttemptStatus.PASSED
        ]
        commit_attempts = [
            item for item in self.attempt_records if item.phase == HarnessAttemptPhase.COMMIT
        ]
        rollback_attempts = [
            item for item in self.attempt_records if item.phase == HarnessAttemptPhase.ROLLBACK
        ]

        if self.status == HarnessStatus.PASSED:
            if self.output_digest is None:
                raise ValueError("harness_success_output_digest_required")
            if failed_attempts or failed_checks or warning_checks:
                raise ValueError("harness_passed_trace_contains_failure_or_warning")
            if self.recovery_strategy != "none" or repair_attempts:
                raise ValueError("harness_passed_trace_contains_recovery")
        elif self.status == HarnessStatus.REPAIRED:
            if self.output_digest is None:
                raise ValueError("harness_success_output_digest_required")
            if self.recovery_strategy == "none" or not repair_attempts:
                raise ValueError("harness_repaired_trace_strategy_required")
            if not failed_attempts and not warning_checks:
                raise ValueError("harness_repaired_trace_recovery_trigger_missing")
            if failed_checks:
                raise ValueError("harness_repaired_trace_contains_failed_check")
        elif self.status == HarnessStatus.FAILED:
            if not self.error_code:
                raise ValueError("harness_failed_trace_error_code_required")
            if not failed_attempts and not failed_checks:
                raise ValueError("harness_failed_trace_failure_evidence_missing")
            if self.commit_evidence.status == HarnessCommitStatus.COMMITTED:
                raise ValueError("harness_failed_trace_cannot_be_committed")
        elif self.status == HarnessStatus.SKIPPED:
            if self.output_digest is not None or self.error_code:
                raise ValueError("harness_skipped_trace_contains_output_or_error")
            if self.recovery_strategy != "none" or failed_attempts or failed_checks:
                raise ValueError("harness_skipped_trace_contains_execution")
            if any(
                item.status != HarnessAttemptStatus.SKIPPED
                for item in self.attempt_records
            ):
                raise ValueError("harness_skipped_trace_attempt_not_skipped")
            if self.commit_evidence.status != HarnessCommitStatus.NOT_APPLICABLE:
                raise ValueError("harness_skipped_trace_commit_not_applicable_required")

        if self.status != HarnessStatus.FAILED and self.error_code:
            raise ValueError("harness_nonfailed_trace_error_code_forbidden")

        output_attempts = [
            item
            for item in self.attempt_records
            if item.phase
            in {
                HarnessAttemptPhase.GENERATE,
                HarnessAttemptPhase.DECODE,
                HarnessAttemptPhase.VALIDATE,
                HarnessAttemptPhase.REPAIR,
            }
        ]
        if self.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}:
            if not output_attempts:
                raise ValueError("harness_success_output_attempt_missing")
            terminal_output_attempt = output_attempts[-1]
            if (
                terminal_output_attempt.phase != HarnessAttemptPhase.VALIDATE
                or terminal_output_attempt.status != HarnessAttemptStatus.PASSED
            ):
                raise ValueError("harness_terminal_output_attempt_not_passed")
            if terminal_output_attempt.output_digest != self.output_digest:
                raise ValueError("harness_output_attempt_digest_mismatch")
            if self.status == HarnessStatus.REPAIRED:
                last_repair_index = repair_attempts[-1].attempt_index
                if last_repair_index >= terminal_output_attempt.attempt_index:
                    raise ValueError("harness_repaired_trace_validation_after_repair_required")

        if self.commit_evidence.status == HarnessCommitStatus.COMMITTED:
            if self.status not in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}:
                raise ValueError("harness_committed_trace_status_invalid")
            if not commit_attempts or commit_attempts[-1] != self.attempt_records[-1]:
                raise ValueError("harness_commit_attempt_not_terminal")
            successful_commit = commit_attempts[-1]
            if successful_commit.status != HarnessAttemptStatus.PASSED:
                raise ValueError("harness_committed_trace_attempt_missing")
            if successful_commit.output_digest != self.commit_evidence.payload_digest:
                raise ValueError("harness_commit_attempt_digest_mismatch")
        elif self.commit_evidence.status in {
            HarnessCommitStatus.NOT_APPLICABLE,
            HarnessCommitStatus.NOT_COMMITTED,
        }:
            if any(item.status == HarnessAttemptStatus.PASSED for item in commit_attempts):
                raise ValueError("harness_uncommitted_trace_has_passed_commit")
            if rollback_attempts:
                raise ValueError("harness_uncommitted_trace_has_rollback")
            if self.commit_evidence.status == HarnessCommitStatus.NOT_APPLICABLE:
                if commit_attempts:
                    raise ValueError("harness_not_applicable_trace_has_commit_attempt")
            elif self.commit_evidence.attempted_resource_refs:
                if not commit_attempts or commit_attempts[-1].status != HarnessAttemptStatus.FAILED:
                    raise ValueError("harness_not_committed_failed_attempt_missing")
            elif commit_attempts:
                raise ValueError("harness_not_committed_attempt_evidence_missing")
        elif self.commit_evidence.status == HarnessCommitStatus.ROLLED_BACK:
            if self.status != HarnessStatus.FAILED:
                raise ValueError("harness_rolled_back_trace_status_invalid")
            if (
                not commit_attempts
                or commit_attempts[-1].status != HarnessAttemptStatus.FAILED
                or any(
                    item.status == HarnessAttemptStatus.PASSED
                    for item in commit_attempts
                )
            ):
                raise ValueError("harness_rollback_failed_commit_missing")
            if not rollback_attempts or rollback_attempts[-1] != self.attempt_records[-1]:
                raise ValueError("harness_rollback_attempt_not_terminal")
            if rollback_attempts[-1].status != HarnessAttemptStatus.PASSED:
                raise ValueError("harness_rollback_success_missing")
            if commit_attempts[-1] != self.attempt_records[-2]:
                raise ValueError("harness_rollback_failed_commit_not_adjacent")

        for timestamp in (
            self.commit_evidence.committed_at,
            self.commit_evidence.rolled_back_at,
        ):
            if timestamp is not None and not (self.started_at <= timestamp <= self.completed_at):
                raise ValueError("harness_effect_timestamp_outside_trace")
        return self


ProposalT = TypeVar("ProposalT", bound=HarnessV2Model)


class HarnessProposalEnvelope(HarnessV2Model, Generic[ProposalT]):
    """Metadata wrapper; each workflow must supply a strict domain proposal DTO."""

    operation_id: str = Field(min_length=1, max_length=160)
    contract: HarnessContractRef
    context_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    proposal: ProposalT

    @model_validator(mode="after")
    def validate_payload_digest(self) -> "HarnessProposalEnvelope[ProposalT]":
        generic_metadata = getattr(
            self.__class__,
            "__pydantic_generic_metadata__",
            {},
        )
        if not generic_metadata.get("args"):
            raise ValueError("harness_proposal_type_parameter_required")
        if not isinstance(self.proposal, BaseModel):
            raise ValueError("harness_proposal_pydantic_model_required")
        if self.proposal.model_config.get("extra") != "forbid":
            raise ValueError("harness_proposal_extra_forbid_required")
        if canonical_harness_digest(self.proposal) != self.payload_digest:
            raise ValueError("harness_proposal_payload_digest_mismatch")
        return self


HarnessTraceWire = HarnessTraceRecord | HarnessTraceV2
_HARNESS_TRACE_WIRE_ADAPTER = TypeAdapter(HarnessTraceWire)


def validate_harness_trace(payload: object) -> HarnessTraceWire:
    """Strictly decode legacy v1 or known v2; unknown v2 versions are rejected."""

    return _HARNESS_TRACE_WIRE_ADAPTER.validate_python(payload)


def canonical_harness_digest(payload: object) -> str:
    """SHA-256 over UTF-8 canonical JSON, preserving explicit null values."""

    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", exclude_none=False)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_harness_commit_digest(
    *,
    payload_contract: HarnessContractRef,
    committed_resources: list[HarnessCommittedResourceRef],
    digest_scope: HarnessDigestScope,
) -> str:
    """Digest one projection directly or a canonical ordered resource manifest."""

    if digest_scope == HarnessDigestScope.COMMITTED_PROJECTION:
        if len(committed_resources) != 1:
            raise ValueError("harness_projection_digest_requires_single_resource")
        return committed_resources[0].payload_digest
    return canonical_harness_digest(
        {
            "payload_contract": payload_contract.model_dump(
                mode="json",
                exclude_none=False,
            ),
            "resources": [
                item.model_dump(mode="json", exclude_none=False)
                for item in committed_resources
            ],
        }
    )
