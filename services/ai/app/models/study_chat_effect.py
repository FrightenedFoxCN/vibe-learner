from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, TypeAlias

from pydantic import ConfigDict, Field, model_validator

from app.models.harness import HarnessContractRef
from app.models.harness_effect import (
    HARNESS_EFFECT_ADAPTER_POLICIES,
    HarnessEffectModel,
    HarnessPreparedEffectBatchV1,
    HarnessPreparedEffectV1,
)


STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_NAME = "StudyPlanConfirmationEffectProposalV1"
STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_VERSION = "study-plan-confirmation-effect-v1"
STUDY_PLAN_CONFIRMATION_ADAPTER_NAME = "study_plan_confirmation_create"
STUDY_PLAN_CONFIRMATION_ADAPTER_VERSION = "study-plan-confirmation-create-v1"
STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_NAME = "StudyMemoryUpsertEffectProposalV1"
STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_VERSION = "study-memory-upsert-effect-v1"
STUDY_MEMORY_UPSERT_ADAPTER_NAME = "study_memory_upsert"
STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_NAME = "StudyAffinityDeltaEffectProposalV1"
STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_VERSION = "study-affinity-delta-effect-v1"
STUDY_AFFINITY_DELTA_ADAPTER_NAME = "study_affinity_delta"
STUDY_CHAT_COMMITTED_EFFECT_BATCH_SCHEMA_VERSION = (
    "study-chat-committed-effect-batch-v1"
)


class StudyPlanConfirmationEffectAction(StrEnum):
    UPDATE_PLAN = "update_plan"
    UPDATE_PLAN_PROGRESS = "update_plan_progress"


class StudyPlanConfirmationEffectProposalV1(HarnessEffectModel):
    """Model-suggestible content only; application identity is assigned later."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal[STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_NAME] = (
        STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_NAME
    )
    schema_version: Literal[STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_VERSION] = (
        STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_VERSION
    )
    effect_kind: Literal["plan_confirmation"] = "plan_confirmation"
    action: StudyPlanConfirmationEffectAction
    course_title: str = Field(default="", max_length=240)
    schedule_ids: list[str] = Field(default_factory=list, max_length=64)
    schedule_status: str = Field(
        default="",
        pattern=r"^(|planned|in_progress|completed|blocked|skipped)$",
    )
    note: str = Field(default="", max_length=1200)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "StudyPlanConfirmationEffectProposalV1":
        if len(self.schedule_ids) != len(set(self.schedule_ids)):
            raise ValueError("study_plan_confirmation_schedule_id_duplicate")
        if any(not item.strip() or len(item) > 160 for item in self.schedule_ids):
            raise ValueError("study_plan_confirmation_schedule_id_invalid")
        if self.action == StudyPlanConfirmationEffectAction.UPDATE_PLAN:
            if not self.course_title.strip() or self.schedule_ids or self.schedule_status:
                raise ValueError("study_plan_confirmation_update_plan_shape_invalid")
        elif (
            self.course_title
            or not self.schedule_ids
            or not self.schedule_status
        ):
            raise ValueError("study_plan_confirmation_progress_shape_invalid")
        return self


class StudyMemoryUpsertEffectProposalV1(HarnessEffectModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal[STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_NAME] = (
        STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_NAME
    )
    schema_version: Literal[STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_VERSION] = (
        STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_VERSION
    )
    effect_kind: Literal["memory_upsert"] = "memory_upsert"
    key: str = Field(min_length=1, max_length=120)
    content: str = Field(min_length=1, max_length=4_000)

    @model_validator(mode="after")
    def validate_normalized_content(self) -> "StudyMemoryUpsertEffectProposalV1":
        if self.key != self.key.strip() or self.content != self.content.strip():
            raise ValueError("study_memory_upsert_not_normalized")
        return self


class StudyAffinityDeltaEffectProposalV1(HarnessEffectModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal[STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_NAME] = (
        STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_NAME
    )
    schema_version: Literal[STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_VERSION] = (
        STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_VERSION
    )
    effect_kind: Literal["affinity_delta"] = "affinity_delta"
    delta: int = Field(ge=-20, le=20)
    reason: str = Field(default="", max_length=1_200)

    @model_validator(mode="after")
    def validate_normalized_reason(self) -> "StudyAffinityDeltaEffectProposalV1":
        if self.reason != self.reason.strip():
            raise ValueError("study_affinity_delta_reason_not_normalized")
        return self


StudyChatEffectProposalV1: TypeAlias = Annotated[
    StudyMemoryUpsertEffectProposalV1
    | StudyAffinityDeltaEffectProposalV1
    | StudyPlanConfirmationEffectProposalV1,
    Field(discriminator="effect_kind"),
]


STUDY_PLAN_CONFIRMATION_ADAPTER = HARNESS_EFFECT_ADAPTER_POLICIES[
    STUDY_PLAN_CONFIRMATION_ADAPTER_NAME
]
STUDY_MEMORY_UPSERT_ADAPTER = HARNESS_EFFECT_ADAPTER_POLICIES[
    STUDY_MEMORY_UPSERT_ADAPTER_NAME
]
STUDY_AFFINITY_DELTA_ADAPTER = HARNESS_EFFECT_ADAPTER_POLICIES[
    STUDY_AFFINITY_DELTA_ADAPTER_NAME
]

STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT = HarnessContractRef(
    name=STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_NAME,
    version=STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_VERSION,
)
STUDY_MEMORY_UPSERT_PROPOSAL_CONTRACT = HarnessContractRef(
    name=STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_NAME,
    version=STUDY_MEMORY_UPSERT_EFFECT_CONTRACT_VERSION,
)
STUDY_AFFINITY_DELTA_PROPOSAL_CONTRACT = HarnessContractRef(
    name=STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_NAME,
    version=STUDY_AFFINITY_DELTA_EFFECT_CONTRACT_VERSION,
)

StudyChatPreparedEffectV1 = HarnessPreparedEffectV1[StudyChatEffectProposalV1]
StudyChatPreparedEffectBatchV1 = HarnessPreparedEffectBatchV1[
    StudyChatEffectProposalV1
]


class StudyPlanConfirmationCommittedProjectionV1(HarnessEffectModel):
    schema_name: Literal["StudyPlanConfirmationCommittedProjectionV1"] = (
        "StudyPlanConfirmationCommittedProjectionV1"
    )
    schema_version: Literal["study-plan-confirmation-committed-projection-v1"] = (
        "study-plan-confirmation-committed-projection-v1"
    )
    effect_kind: Literal["plan_confirmation"] = "plan_confirmation"
    operation_id: str
    effect_batch_id: str
    effect_id: str
    slot: int = Field(ge=0, le=127)
    session_id: str
    confirmation_id: str
    action: StudyPlanConfirmationEffectAction
    plan_id: str
    status: Literal["pending"] = "pending"
    created_at: str


class StudyMemoryUpsertCommittedProjectionV1(HarnessEffectModel):
    schema_name: Literal["StudyMemoryUpsertCommittedProjectionV1"] = (
        "StudyMemoryUpsertCommittedProjectionV1"
    )
    schema_version: Literal["study-memory-upsert-committed-projection-v1"] = (
        "study-memory-upsert-committed-projection-v1"
    )
    effect_kind: Literal["memory_upsert"] = "memory_upsert"
    operation_id: str
    effect_batch_id: str
    effect_id: str
    slot: int = Field(ge=0, le=127)
    session_id: str
    memory_id: str
    key: str
    content: str
    source: Literal["tool_call"] = "tool_call"
    created_at: str
    updated_at: str


class StudyAffinityDeltaCommittedProjectionV1(HarnessEffectModel):
    schema_name: Literal["StudyAffinityDeltaCommittedProjectionV1"] = (
        "StudyAffinityDeltaCommittedProjectionV1"
    )
    schema_version: Literal["study-affinity-delta-committed-projection-v1"] = (
        "study-affinity-delta-committed-projection-v1"
    )
    effect_kind: Literal["affinity_delta"] = "affinity_delta"
    operation_id: str
    effect_batch_id: str
    effect_id: str
    slot: int = Field(ge=0, le=127)
    session_id: str
    event_id: str
    delta: int = Field(ge=-20, le=20)
    reason: str
    source: Literal["tool_call"] = "tool_call"
    score: int = Field(ge=-100, le=100)
    level: str
    summary: str
    created_at: str
    updated_at: str


StudyChatCommittedEffectProjectionV1: TypeAlias = Annotated[
    StudyMemoryUpsertCommittedProjectionV1
    | StudyAffinityDeltaCommittedProjectionV1
    | StudyPlanConfirmationCommittedProjectionV1,
    Field(discriminator="effect_kind"),
]


class StudyChatCommittedEffectBatchV1(HarnessEffectModel):
    schema_name: Literal["StudyChatCommittedEffectBatchV1"] = (
        "StudyChatCommittedEffectBatchV1"
    )
    schema_version: Literal[STUDY_CHAT_COMMITTED_EFFECT_BATCH_SCHEMA_VERSION] = (
        STUDY_CHAT_COMMITTED_EFFECT_BATCH_SCHEMA_VERSION
    )
    operation_id: str
    effect_batch_id: str
    effects: list[StudyChatCommittedEffectProjectionV1] = Field(
        min_length=1,
        max_length=12,
    )

    @model_validator(mode="after")
    def validate_identity_and_slots(self) -> "StudyChatCommittedEffectBatchV1":
        if any(
            item.operation_id != self.operation_id
            or item.effect_batch_id != self.effect_batch_id
            for item in self.effects
        ):
            raise ValueError("study_chat_committed_effect_batch_identity_mismatch")
        if [item.slot for item in self.effects] != list(range(len(self.effects))):
            raise ValueError("study_chat_committed_effect_slots_not_contiguous")
        if len({item.effect_id for item in self.effects}) != len(self.effects):
            raise ValueError("study_chat_committed_effect_identity_duplicate")
        return self
