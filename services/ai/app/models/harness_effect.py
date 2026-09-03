from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
from types import MappingProxyType
from typing import Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.harness import (
    HarnessContractRef,
    HarnessResourceType,
    canonical_harness_digest,
    require_versioned_harness_contract,
)
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN


HARNESS_PREPARED_EFFECT_SCHEMA_VERSION = "harness-prepared-effect-v1"
HARNESS_PREPARED_EFFECT_BATCH_SCHEMA_VERSION = "harness-prepared-effect-batch-v1"
HARNESS_EFFECT_JOURNAL_ENTRY_SCHEMA_VERSION = "harness-effect-journal-entry-v1"
HARNESS_EFFECT_TERMINAL_EVIDENCE_SCHEMA_VERSION = "harness-effect-terminal-evidence-v1"

EffectProposalT = TypeVar("EffectProposalT", bound=BaseModel)


class HarnessEffectBoundaryKind(StrEnum):
    PURE_READ = "pure_read"
    DATABASE_WRITE = "database_write"
    FILE_WRITE = "file_write"
    EXTERNAL_CALL = "external_call"


class HarnessEffectTerminalOutcome(StrEnum):
    NOT_COMMITTED = "not_committed"
    COMMITTED = "committed"
    UNCERTAIN = "uncertain"


class HarnessEffectJournalState(StrEnum):
    PREPARED = "prepared"
    CLAIMED = "claimed"
    TERMINAL = "terminal"


class HarnessEffectCompensationOutcome(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INCOMPLETE = "incomplete"


class HarnessEffectReadBackOutcome(StrEnum):
    NOT_ATTEMPTED = "not_attempted"
    VERIFIED = "verified"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class HarnessEffectPreparePolicy(StrEnum):
    VALIDATE_AND_ASSIGN_IDENTITY = "validate_and_assign_identity"


class HarnessEffectCommitPolicy(StrEnum):
    DATABASE_TRANSACTION = "database_transaction"
    STAGING_OUTBOX = "staging_outbox"
    EXTERNAL_IDEMPOTENCY_OR_READ_BACK = "external_idempotency_or_read_back"


class HarnessEffectCompensationPolicy(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    CLEANUP = "cleanup"
    DOMAIN_COMPENSATION = "domain_compensation"


class HarnessEffectReadBackPolicy(StrEnum):
    EXACT_PROJECTION = "exact_projection"
    PROVIDER_LOOKUP = "provider_lookup"
    UNSUPPORTED = "unsupported"


class HarnessEffectModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HarnessEffectAdapterRefV1(HarnessEffectModel):
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=160)
    boundary_kind: HarnessEffectBoundaryKind
    prepare_policy: HarnessEffectPreparePolicy
    commit_policy: HarnessEffectCommitPolicy
    compensation_policy: HarnessEffectCompensationPolicy
    read_back_policy: HarnessEffectReadBackPolicy


HARNESS_EFFECT_ADAPTER_POLICIES = MappingProxyType(
    {
        "study_affinity_delta": HarnessEffectAdapterRefV1(
            name="study_affinity_delta",
            version="study-affinity-delta-v1",
            boundary_kind=HarnessEffectBoundaryKind.DATABASE_WRITE,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.DATABASE_TRANSACTION,
            compensation_policy=HarnessEffectCompensationPolicy.NOT_APPLICABLE,
            read_back_policy=HarnessEffectReadBackPolicy.EXACT_PROJECTION,
        ),
        "study_attachment_stage": HarnessEffectAdapterRefV1(
            name="study_attachment_stage",
            version="study-attachment-stage-v1",
            boundary_kind=HarnessEffectBoundaryKind.FILE_WRITE,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.STAGING_OUTBOX,
            compensation_policy=HarnessEffectCompensationPolicy.CLEANUP,
            read_back_policy=HarnessEffectReadBackPolicy.EXACT_PROJECTION,
        ),
        "study_memory_upsert": HarnessEffectAdapterRefV1(
            name="study_memory_upsert",
            version="study-memory-upsert-v1",
            boundary_kind=HarnessEffectBoundaryKind.DATABASE_WRITE,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.DATABASE_TRANSACTION,
            compensation_policy=HarnessEffectCompensationPolicy.NOT_APPLICABLE,
            read_back_policy=HarnessEffectReadBackPolicy.EXACT_PROJECTION,
        ),
        "study_follow_up_mutation": HarnessEffectAdapterRefV1(
            name="study_follow_up_mutation",
            version="study-follow-up-mutation-v1",
            boundary_kind=HarnessEffectBoundaryKind.DATABASE_WRITE,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.DATABASE_TRANSACTION,
            compensation_policy=HarnessEffectCompensationPolicy.NOT_APPLICABLE,
            read_back_policy=HarnessEffectReadBackPolicy.EXACT_PROJECTION,
        ),
        "study_projection_mutation": HarnessEffectAdapterRefV1(
            name="study_projection_mutation",
            version="study-projection-mutation-v1",
            boundary_kind=HarnessEffectBoundaryKind.DATABASE_WRITE,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.DATABASE_TRANSACTION,
            compensation_policy=HarnessEffectCompensationPolicy.NOT_APPLICABLE,
            read_back_policy=HarnessEffectReadBackPolicy.EXACT_PROJECTION,
        ),
        "study_provider_execution": HarnessEffectAdapterRefV1(
            name="study_provider_execution",
            version="study-provider-execution-v1",
            boundary_kind=HarnessEffectBoundaryKind.EXTERNAL_CALL,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.EXTERNAL_IDEMPOTENCY_OR_READ_BACK,
            compensation_policy=HarnessEffectCompensationPolicy.NOT_APPLICABLE,
            read_back_policy=HarnessEffectReadBackPolicy.UNSUPPORTED,
        ),
        "study_scene_replace": HarnessEffectAdapterRefV1(
            name="study_scene_replace",
            version="study-scene-replace-v1",
            boundary_kind=HarnessEffectBoundaryKind.DATABASE_WRITE,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.DATABASE_TRANSACTION,
            compensation_policy=HarnessEffectCompensationPolicy.NOT_APPLICABLE,
            read_back_policy=HarnessEffectReadBackPolicy.EXACT_PROJECTION,
        ),
        "study_plan_confirmation_create": HarnessEffectAdapterRefV1(
            name="study_plan_confirmation_create",
            version="study-plan-confirmation-create-v1",
            boundary_kind=HarnessEffectBoundaryKind.DATABASE_WRITE,
            prepare_policy=HarnessEffectPreparePolicy.VALIDATE_AND_ASSIGN_IDENTITY,
            commit_policy=HarnessEffectCommitPolicy.DATABASE_TRANSACTION,
            compensation_policy=HarnessEffectCompensationPolicy.NOT_APPLICABLE,
            read_back_policy=HarnessEffectReadBackPolicy.EXACT_PROJECTION,
        )
    }
)


def harness_effect_adapter_policy_registry_snapshot() -> dict[str, object]:
    return {
        "schema_name": "HarnessEffectAdapterPolicyRegistry",
        "schema_version": "harness-effect-adapter-policy-registry-v1",
        "adapters": [
            adapter.model_dump(mode="json")
            for _, adapter in sorted(HARNESS_EFFECT_ADAPTER_POLICIES.items())
        ],
    }


class HarnessEffectTargetRefV1(HarnessEffectModel):
    resource_type: HarnessResourceType
    resource_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")


class HarnessProviderEffectIdentityV1(HarnessEffectModel):
    """Provider correlation without claiming provider idempotency or read-back."""

    provider_name: str = Field(min_length=1, max_length=160)
    request_id: str = Field(min_length=1, max_length=160)
    provider_effect_id: str = Field(default="", max_length=240)
    idempotency_key: str = Field(default="", max_length=240)
    request_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    idempotency_supported: bool
    read_back_supported: bool


def harness_effect_batch_id(harness_operation_id: str) -> str:
    token = hashlib.sha256(harness_operation_id.encode("utf-8")).hexdigest()[:32]
    return f"harness-effect-batch-{token}"


def harness_effect_id(harness_operation_id: str, slot: int) -> str:
    if slot < 0 or slot > 127:
        raise ValueError("harness_effect_slot_out_of_bounds")
    token = hashlib.sha256(
        f"{harness_operation_id}:{slot}".encode("utf-8")
    ).hexdigest()[:32]
    return f"harness-effect-{token}"


class HarnessEffectJournalEntryV1(HarnessEffectModel):
    schema_name: Literal["HarnessEffectJournalEntryV1"] = "HarnessEffectJournalEntryV1"
    schema_version: Literal[HARNESS_EFFECT_JOURNAL_ENTRY_SCHEMA_VERSION] = (
        HARNESS_EFFECT_JOURNAL_ENTRY_SCHEMA_VERSION
    )
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    effect_batch_id: str = Field(pattern=r"^harness-effect-batch-[0-9a-f]{32}$")
    effect_id: str = Field(pattern=r"^harness-effect-[0-9a-f]{32}$")
    slot: int = Field(ge=0, le=127)
    adapter: HarnessEffectAdapterRefV1
    proposal_contract: HarnessContractRef
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_refs: tuple[HarnessEffectTargetRefV1, ...] = Field(min_length=1, max_length=8)
    state: HarnessEffectJournalState
    claim_owner: str = Field(default="", max_length=160)
    claim_count: int = Field(default=0, ge=0, le=3)
    lease_expires_at: AwareDatetime | None = None
    commit_started_at: AwareDatetime | None = None
    read_back_started_at: AwareDatetime | None = None
    compensation_started_at: AwareDatetime | None = None
    provider_effect_identity: HarnessProviderEffectIdentityV1 | None = None
    prepared_at: AwareDatetime
    updated_at: AwareDatetime
    terminal_evidence: "HarnessEffectTerminalEvidenceV1 | None" = None

    @field_validator(
        "lease_expires_at",
        "commit_started_at",
        "read_back_started_at",
        "compensation_started_at",
        "prepared_at",
        "updated_at",
    )
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("harness_effect_journal_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_entry(self) -> "HarnessEffectJournalEntryV1":
        _validate_effect_identity(
            harness_operation_id=self.harness_operation_id,
            effect_batch_id=self.effect_batch_id,
            effect_id=self.effect_id,
            slot=self.slot,
            adapter=self.adapter,
            proposal_contract=self.proposal_contract,
            target_refs=self.target_refs,
        )
        if self.updated_at < self.prepared_at:
            raise ValueError("harness_effect_journal_timestamp_order_invalid")
        if self.state == HarnessEffectJournalState.PREPARED:
            if self.claim_owner or self.claim_count or self.lease_expires_at is not None:
                raise ValueError("harness_effect_prepared_claim_state_forbidden")
        elif self.state == HarnessEffectJournalState.CLAIMED:
            if not self.claim_owner or self.claim_count < 1 or self.lease_expires_at is None:
                raise ValueError("harness_effect_claim_incomplete")
        elif self.state == HarnessEffectJournalState.TERMINAL:
            if self.terminal_evidence is None:
                raise ValueError("harness_effect_terminal_evidence_required")
        if self.state != HarnessEffectJournalState.TERMINAL and self.terminal_evidence is not None:
            raise ValueError("harness_effect_terminal_evidence_premature")
        if self.provider_effect_identity is not None and (
            self.adapter.boundary_kind != HarnessEffectBoundaryKind.EXTERNAL_CALL
        ):
            raise ValueError("harness_effect_provider_identity_boundary_mismatch")
        return self


class HarnessEffectTerminalEvidenceV1(HarnessEffectModel):
    """Strict, content-free terminal evidence for exactly one journal slot."""

    schema_name: Literal["HarnessEffectTerminalEvidenceV1"] = (
        "HarnessEffectTerminalEvidenceV1"
    )
    schema_version: Literal[HARNESS_EFFECT_TERMINAL_EVIDENCE_SCHEMA_VERSION] = (
        HARNESS_EFFECT_TERMINAL_EVIDENCE_SCHEMA_VERSION
    )
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    effect_batch_id: str = Field(pattern=r"^harness-effect-batch-[0-9a-f]{32}$")
    effect_id: str = Field(pattern=r"^harness-effect-[0-9a-f]{32}$")
    slot: int = Field(ge=0, le=127)
    adapter: HarnessEffectAdapterRefV1
    proposal_contract: HarnessContractRef
    proposal_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_refs: tuple[HarnessEffectTargetRefV1, ...] = Field(min_length=1, max_length=8)
    outcome: HarnessEffectTerminalOutcome
    provider_effect_identity: HarnessProviderEffectIdentityV1 | None = None
    read_back_outcome: HarnessEffectReadBackOutcome
    committed_projection_contract: HarnessContractRef | None = None
    committed_projection_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    compensation_outcome: HarnessEffectCompensationOutcome = (
        HarnessEffectCompensationOutcome.NOT_APPLICABLE
    )
    compensation_contract: HarnessContractRef | None = None
    compensation_evidence_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    prepared_at: AwareDatetime
    commit_started_at: AwareDatetime | None = None
    read_back_started_at: AwareDatetime | None = None
    compensation_started_at: AwareDatetime | None = None
    read_back_at: AwareDatetime | None = None
    compensated_at: AwareDatetime | None = None
    terminal_at: AwareDatetime
    failure_code: str = Field(default="", max_length=160)

    @field_validator(
        "prepared_at",
        "commit_started_at",
        "read_back_started_at",
        "compensation_started_at",
        "read_back_at",
        "compensated_at",
        "terminal_at",
    )
    @classmethod
    def require_utc_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("harness_effect_evidence_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_terminal_evidence(self) -> "HarnessEffectTerminalEvidenceV1":
        _validate_effect_identity(
            harness_operation_id=self.harness_operation_id,
            effect_batch_id=self.effect_batch_id,
            effect_id=self.effect_id,
            slot=self.slot,
            adapter=self.adapter,
            proposal_contract=self.proposal_contract,
            target_refs=self.target_refs,
        )
        if self.terminal_at < self.prepared_at or (
            self.commit_started_at is not None
            and self.commit_started_at < self.prepared_at
        ):
            raise ValueError("harness_effect_evidence_timestamp_order_invalid")
        for timestamp in (
            self.commit_started_at,
            self.read_back_started_at,
            self.compensation_started_at,
            self.read_back_at,
            self.compensated_at,
        ):
            if timestamp is not None and timestamp > self.terminal_at:
                raise ValueError("harness_effect_evidence_timestamp_order_invalid")
        if (
            self.read_back_started_at is not None
            and self.read_back_at is not None
            and self.read_back_started_at > self.read_back_at
        ) or (
            self.compensation_started_at is not None
            and self.compensated_at is not None
            and self.compensation_started_at > self.compensated_at
        ):
            raise ValueError("harness_effect_evidence_timestamp_order_invalid")
        projection_fields = (
            self.committed_projection_contract,
            self.committed_projection_digest,
        )
        compensation_fields = (
            self.compensation_contract,
            self.compensation_evidence_digest,
            self.compensated_at,
        )
        if self.read_back_outcome == HarnessEffectReadBackOutcome.VERIFIED:
            if any(
                value is None
                for value in (
                    *projection_fields,
                    self.read_back_started_at,
                    self.read_back_at,
                )
            ):
                raise ValueError("harness_effect_read_back_evidence_incomplete")
        elif any(value is not None for value in projection_fields):
            raise ValueError("harness_effect_projection_without_verified_read_back")
        if self.read_back_outcome in {
            HarnessEffectReadBackOutcome.FAILED,
            HarnessEffectReadBackOutcome.VERIFIED,
        } and (
            self.read_back_started_at is None or self.read_back_at is None
        ):
            raise ValueError("harness_effect_read_back_timestamp_required")
        if self.read_back_outcome in {
            HarnessEffectReadBackOutcome.NOT_ATTEMPTED,
            HarnessEffectReadBackOutcome.UNSUPPORTED,
        } and (
            self.read_back_started_at is not None or self.read_back_at is not None
        ):
            raise ValueError("harness_effect_read_back_timestamp_forbidden")
        if self.compensation_outcome == HarnessEffectCompensationOutcome.NOT_APPLICABLE:
            if any(
                value is not None
                for value in (*compensation_fields, self.compensation_started_at)
            ):
                raise ValueError("harness_effect_compensation_evidence_forbidden")
        elif self.compensation_outcome == HarnessEffectCompensationOutcome.INCOMPLETE:
            if self.compensation_started_at is None or any(
                value is not None for value in compensation_fields
            ):
                raise ValueError("harness_effect_compensation_incomplete_invalid")
        elif any(
            value is None
            for value in (*compensation_fields, self.compensation_started_at)
        ):
            raise ValueError("harness_effect_compensation_evidence_incomplete")
        if self.provider_effect_identity is not None and (
            self.adapter.boundary_kind != HarnessEffectBoundaryKind.EXTERNAL_CALL
        ):
            raise ValueError("harness_effect_provider_identity_boundary_mismatch")

        if self.outcome == HarnessEffectTerminalOutcome.COMMITTED:
            if (
                self.commit_started_at is None
                or self.read_back_outcome != HarnessEffectReadBackOutcome.VERIFIED
                or self.compensation_outcome
                != HarnessEffectCompensationOutcome.NOT_APPLICABLE
                or self.failure_code
            ):
                raise ValueError("harness_effect_committed_evidence_invalid")
            if self.adapter.boundary_kind == HarnessEffectBoundaryKind.EXTERNAL_CALL:
                if self.provider_effect_identity is None:
                    raise ValueError("harness_effect_provider_identity_required")
                if (
                    self.adapter.read_back_policy == HarnessEffectReadBackPolicy.UNSUPPORTED
                    or not self.provider_effect_identity.read_back_supported
                ):
                    raise ValueError("harness_effect_external_commit_unverifiable")
        elif self.outcome == HarnessEffectTerminalOutcome.NOT_COMMITTED:
            if (
                self.read_back_outcome != HarnessEffectReadBackOutcome.NOT_ATTEMPTED
                or any(value is not None for value in projection_fields)
                or self.provider_effect_identity is not None
                or self.failure_code
            ):
                raise ValueError("harness_effect_not_committed_evidence_invalid")
            if self.commit_started_at is None:
                if self.compensation_outcome != HarnessEffectCompensationOutcome.NOT_APPLICABLE:
                    raise ValueError("harness_effect_unstarted_compensation_forbidden")
            elif (
                self.adapter.boundary_kind == HarnessEffectBoundaryKind.EXTERNAL_CALL
                or self.compensation_outcome != HarnessEffectCompensationOutcome.SUCCEEDED
            ):
                raise ValueError("harness_effect_started_not_committed_unproven")
        else:
            if self.commit_started_at is None or not self.failure_code:
                raise ValueError("harness_effect_uncertain_evidence_incomplete")
            if self.read_back_outcome == HarnessEffectReadBackOutcome.VERIFIED:
                raise ValueError("harness_effect_uncertain_verified_read_back_forbidden")
        return self

    @property
    def evidence_digest(self) -> str:
        return canonical_harness_digest(self.model_dump(mode="json", exclude_none=False))


def _validate_effect_identity(
    *,
    harness_operation_id: str,
    effect_batch_id: str,
    effect_id: str,
    slot: int,
    adapter: HarnessEffectAdapterRefV1,
    proposal_contract: HarnessContractRef,
    target_refs: tuple[HarnessEffectTargetRefV1, ...],
) -> None:
    if effect_batch_id != harness_effect_batch_id(harness_operation_id):
        raise ValueError("harness_effect_batch_identity_mismatch")
    if effect_id != harness_effect_id(harness_operation_id, slot):
        raise ValueError("harness_effect_identity_mismatch")
    registered = HARNESS_EFFECT_ADAPTER_POLICIES.get(adapter.name)
    if registered is None or registered != adapter:
        raise ValueError("harness_effect_adapter_unregistered")
    require_versioned_harness_contract(proposal_contract)
    identities = [(item.resource_type.value, item.resource_id) for item in target_refs]
    if identities != sorted(identities) or len(identities) != len(set(identities)):
        raise ValueError("harness_effect_targets_not_canonical")


class HarnessPreparedEffectV1(HarnessEffectModel, Generic[EffectProposalT]):
    schema_name: Literal["HarnessPreparedEffectV1"] = "HarnessPreparedEffectV1"
    schema_version: Literal[HARNESS_PREPARED_EFFECT_SCHEMA_VERSION] = (
        HARNESS_PREPARED_EFFECT_SCHEMA_VERSION
    )
    operation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    effect_batch_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    effect_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    slot: int = Field(ge=0, le=127)
    adapter: HarnessEffectAdapterRefV1
    proposal_contract: HarnessContractRef
    target_refs: list[HarnessEffectTargetRefV1] = Field(min_length=1, max_length=8)
    proposal: EffectProposalT

    @model_validator(mode="after")
    def reject_reads_and_permissive_proposals(self) -> "HarnessPreparedEffectV1[EffectProposalT]":
        if self.adapter.boundary_kind == HarnessEffectBoundaryKind.PURE_READ:
            raise ValueError("harness_prepared_effect_pure_read_forbidden")
        if not isinstance(self.proposal, BaseModel):
            raise ValueError("harness_prepared_effect_typed_proposal_required")
        if self.proposal.model_config.get("extra") != "forbid":
            raise ValueError("harness_prepared_effect_proposal_extra_forbid_required")
        if len(self.target_refs) != len(
            {(item.resource_type, item.resource_id) for item in self.target_refs}
        ):
            raise ValueError("harness_prepared_effect_target_duplicate")
        return self


class HarnessPreparedEffectBatchV1(HarnessEffectModel, Generic[EffectProposalT]):
    schema_name: Literal["HarnessPreparedEffectBatchV1"] = "HarnessPreparedEffectBatchV1"
    schema_version: Literal[HARNESS_PREPARED_EFFECT_BATCH_SCHEMA_VERSION] = (
        HARNESS_PREPARED_EFFECT_BATCH_SCHEMA_VERSION
    )
    operation_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    effect_batch_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    effects: list[HarnessPreparedEffectV1[EffectProposalT]] = Field(
        min_length=1,
        max_length=128,
    )

    @model_validator(mode="after")
    def validate_batch_identity_and_slots(self) -> "HarnessPreparedEffectBatchV1[EffectProposalT]":
        if any(
            item.operation_id != self.operation_id
            or item.effect_batch_id != self.effect_batch_id
            for item in self.effects
        ):
            raise ValueError("harness_prepared_effect_batch_identity_mismatch")
        if [item.slot for item in self.effects] != list(range(len(self.effects))):
            raise ValueError("harness_prepared_effect_batch_slots_not_contiguous")
        if len({item.effect_id for item in self.effects}) != len(self.effects):
            raise ValueError("harness_prepared_effect_batch_effect_id_duplicate")
        return self
