from __future__ import annotations

from enum import StrEnum
from typing import Literal

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


STUDY_PLAN_CONFIRMATION_ADAPTER = HARNESS_EFFECT_ADAPTER_POLICIES[
    STUDY_PLAN_CONFIRMATION_ADAPTER_NAME
]

STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT = HarnessContractRef(
    name=STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_NAME,
    version=STUDY_PLAN_CONFIRMATION_EFFECT_CONTRACT_VERSION,
)

StudyPlanConfirmationPreparedEffectV1 = HarnessPreparedEffectV1[
    StudyPlanConfirmationEffectProposalV1
]
StudyPlanConfirmationPreparedEffectBatchV1 = HarnessPreparedEffectBatchV1[
    StudyPlanConfirmationEffectProposalV1
]


class StudyPlanConfirmationCommittedProjectionV1(HarnessEffectModel):
    schema_name: Literal["StudyPlanConfirmationCommittedProjectionV1"] = (
        "StudyPlanConfirmationCommittedProjectionV1"
    )
    schema_version: Literal["study-plan-confirmation-committed-projection-v1"] = (
        "study-plan-confirmation-committed-projection-v1"
    )
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
