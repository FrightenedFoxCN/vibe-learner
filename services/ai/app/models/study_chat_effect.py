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
STUDY_FOLLOW_UP_EFFECT_CONTRACT_NAME = "StudyFollowUpEffectProposalV1"
STUDY_FOLLOW_UP_EFFECT_CONTRACT_VERSION = "study-follow-up-effect-v1"
STUDY_FOLLOW_UP_ADAPTER_NAME = "study_follow_up_mutation"
STUDY_PROJECTION_EFFECT_CONTRACT_NAME = "StudyProjectionEffectProposalV1"
STUDY_PROJECTION_EFFECT_CONTRACT_VERSION = "study-projection-effect-v1"
STUDY_PROJECTION_ADAPTER_NAME = "study_projection_mutation"
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


class StudyFollowUpEffectAction(StrEnum):
    SCHEDULE = "schedule"
    COMPLETE = "complete"
    CANCEL_PENDING = "cancel_pending"


class StudyFollowUpEffectProposalV1(HarnessEffectModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal[STUDY_FOLLOW_UP_EFFECT_CONTRACT_NAME] = (
        STUDY_FOLLOW_UP_EFFECT_CONTRACT_NAME
    )
    schema_version: Literal[STUDY_FOLLOW_UP_EFFECT_CONTRACT_VERSION] = (
        STUDY_FOLLOW_UP_EFFECT_CONTRACT_VERSION
    )
    effect_kind: Literal["follow_up"] = "follow_up"
    action: StudyFollowUpEffectAction
    follow_up_id: str = Field(default="", max_length=128)
    delay_seconds: int = Field(default=0, ge=0, le=1800)
    hidden_message: str = Field(default="", max_length=20_000)
    reason: str = Field(default="", max_length=1_200)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "StudyFollowUpEffectProposalV1":
        normalized = (
            self.follow_up_id == self.follow_up_id.strip()
            and self.hidden_message == self.hidden_message.strip()
            and self.reason == self.reason.strip()
        )
        if not normalized:
            raise ValueError("study_follow_up_not_normalized")
        if self.action == StudyFollowUpEffectAction.SCHEDULE:
            if (
                self.follow_up_id
                or self.delay_seconds < 10
                or not self.hidden_message
            ):
                raise ValueError("study_follow_up_schedule_shape_invalid")
        elif self.action == StudyFollowUpEffectAction.COMPLETE:
            if (
                not self.follow_up_id
                or self.delay_seconds
                or self.hidden_message
                or self.reason
            ):
                raise ValueError("study_follow_up_complete_shape_invalid")
        elif any(
            (self.follow_up_id, self.delay_seconds, self.hidden_message, self.reason)
        ):
            raise ValueError("study_follow_up_cancel_shape_invalid")
        return self


class StudyProjectionEffectAction(StrEnum):
    SET = "set"
    FOCUS = "focus"
    APPEND_OVERLAY = "append_overlay"
    CLEAR_OVERLAYS = "clear_overlays"


class StudyProjectionRectV1(HarnessEffectModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(ge=0.0, le=1.0)
    height: float = Field(ge=0.0, le=1.0)


class StudyProjectionEffectProposalV1(HarnessEffectModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal[STUDY_PROJECTION_EFFECT_CONTRACT_NAME] = (
        STUDY_PROJECTION_EFFECT_CONTRACT_NAME
    )
    schema_version: Literal[STUDY_PROJECTION_EFFECT_CONTRACT_VERSION] = (
        STUDY_PROJECTION_EFFECT_CONTRACT_VERSION
    )
    effect_kind: Literal["projection"] = "projection"
    action: StudyProjectionEffectAction
    source_kind: str = Field(default="", max_length=64)
    source_id: str = Field(default="", max_length=160)
    title: str = Field(default="", max_length=500)
    page_number: int = Field(default=0, ge=0, le=100_000)
    page_count: int = Field(default=0, ge=0, le=100_000)
    image_url: str = Field(default="", max_length=2_000_000)
    overlay_kind: str = Field(default="", max_length=64)
    rects: list[StudyProjectionRectV1] = Field(default_factory=list, max_length=128)
    label: str = Field(default="", max_length=1_200)
    quote_text: str = Field(default="", max_length=8_000)
    color: str = Field(default="", max_length=32)

    @model_validator(mode="after")
    def validate_action_shape(self) -> "StudyProjectionEffectProposalV1":
        if self.action == StudyProjectionEffectAction.SET:
            if (
                self.source_kind not in {
                    "attachment_pdf",
                    "attachment_image",
                    "generated_image",
                }
                or (self.source_kind != "generated_image" and not self.source_id)
                or (self.source_kind == "generated_image" and bool(self.source_id))
                or not self.title
                or self.page_number < 1
                or self.page_count < 1
                or self.overlay_kind
                or self.rects
                or self.label
                or self.quote_text
                or self.color
            ):
                raise ValueError("study_projection_set_shape_invalid")
        elif self.action == StudyProjectionEffectAction.FOCUS:
            if self.page_number < 1 or self._has_non_focus_fields():
                raise ValueError("study_projection_focus_shape_invalid")
        elif self.action == StudyProjectionEffectAction.APPEND_OVERLAY:
            if (
                self.page_number < 1
                or self.overlay_kind not in {"text_highlight", "region_box"}
                or not self.rects
                or self.source_kind
                or self.source_id
                or self.title
                or self.page_count
                or self.image_url
            ):
                raise ValueError("study_projection_overlay_shape_invalid")
        elif (
            self.source_kind
            or self.source_id
            or self.title
            or self.page_count
            or self.image_url
            or self.overlay_kind
            or self.rects
            or self.label
            or self.quote_text
            or self.color
        ):
            raise ValueError("study_projection_clear_shape_invalid")
        return self

    def _has_non_focus_fields(self) -> bool:
        return bool(
            self.source_kind
            or self.source_id
            or self.title
            or self.page_count
            or self.image_url
            or self.overlay_kind
            or self.rects
            or self.label
            or self.quote_text
            or self.color
        )


StudyChatEffectProposalV1: TypeAlias = Annotated[
    StudyMemoryUpsertEffectProposalV1
    | StudyAffinityDeltaEffectProposalV1
    | StudyFollowUpEffectProposalV1
    | StudyPlanConfirmationEffectProposalV1
    | StudyProjectionEffectProposalV1,
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
STUDY_FOLLOW_UP_ADAPTER = HARNESS_EFFECT_ADAPTER_POLICIES[
    STUDY_FOLLOW_UP_ADAPTER_NAME
]
STUDY_PROJECTION_ADAPTER = HARNESS_EFFECT_ADAPTER_POLICIES[
    STUDY_PROJECTION_ADAPTER_NAME
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
STUDY_FOLLOW_UP_PROPOSAL_CONTRACT = HarnessContractRef(
    name=STUDY_FOLLOW_UP_EFFECT_CONTRACT_NAME,
    version=STUDY_FOLLOW_UP_EFFECT_CONTRACT_VERSION,
)
STUDY_PROJECTION_PROPOSAL_CONTRACT = HarnessContractRef(
    name=STUDY_PROJECTION_EFFECT_CONTRACT_NAME,
    version=STUDY_PROJECTION_EFFECT_CONTRACT_VERSION,
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


class StudyFollowUpCommittedProjectionV1(HarnessEffectModel):
    schema_name: Literal["StudyFollowUpCommittedProjectionV1"] = (
        "StudyFollowUpCommittedProjectionV1"
    )
    schema_version: Literal["study-follow-up-committed-projection-v1"] = (
        "study-follow-up-committed-projection-v1"
    )
    effect_kind: Literal["follow_up"] = "follow_up"
    operation_id: str
    effect_batch_id: str
    effect_id: str
    slot: int = Field(ge=0, le=127)
    session_id: str
    action: StudyFollowUpEffectAction
    follow_up_id: str = ""
    affected_follow_up_ids: list[str] = Field(default_factory=list, max_length=128)
    committed_at: str


class StudyProjectionOverlayStateV1(HarnessEffectModel):
    id: str
    kind: str
    page_number: int = Field(ge=1)
    rects: list[StudyProjectionRectV1] = Field(default_factory=list, max_length=128)
    label: str = ""
    quote_text: str = ""
    color: str
    created_at: str


class StudyProjectedStateV1(HarnessEffectModel):
    source_kind: str
    source_id: str
    title: str
    page_number: int = Field(ge=1)
    page_count: int = Field(ge=1)
    image_url: str = ""
    overlays: list[StudyProjectionOverlayStateV1] = Field(
        default_factory=list,
        max_length=24,
    )
    updated_at: str


class StudyProjectionCommittedProjectionV1(HarnessEffectModel):
    schema_name: Literal["StudyProjectionCommittedProjectionV1"] = (
        "StudyProjectionCommittedProjectionV1"
    )
    schema_version: Literal["study-projection-committed-projection-v1"] = (
        "study-projection-committed-projection-v1"
    )
    effect_kind: Literal["projection"] = "projection"
    operation_id: str
    effect_batch_id: str
    effect_id: str
    slot: int = Field(ge=0, le=127)
    session_id: str
    action: StudyProjectionEffectAction
    projected_state: StudyProjectedStateV1


StudyChatCommittedEffectProjectionV1: TypeAlias = Annotated[
    StudyMemoryUpsertCommittedProjectionV1
    | StudyAffinityDeltaCommittedProjectionV1
    | StudyFollowUpCommittedProjectionV1
    | StudyPlanConfirmationCommittedProjectionV1
    | StudyProjectionCommittedProjectionV1,
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
