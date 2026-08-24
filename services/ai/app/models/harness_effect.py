from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.harness import HarnessContractRef, HarnessResourceType


HARNESS_PREPARED_EFFECT_SCHEMA_VERSION = "harness-prepared-effect-v1"
HARNESS_PREPARED_EFFECT_BATCH_SCHEMA_VERSION = "harness-prepared-effect-batch-v1"

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
