from __future__ import annotations

from typing import ClassVar, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.plan_progress import refresh_plan_progress
from app.models.domain import VersionedLearningPlanRecord
from app.models.harness import HarnessSafeManifest, HarnessContractRef


class PlanRevisionDecodeError(ValueError):
    """Provider returned a response that is known to be unusable."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PlanSchedulePatchV1(_Strict):
    # References select existing targets; they never allocate committed identity.
    schedule_ref: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=500)
    focus: str = Field(min_length=1, max_length=4000)


class PlanRevisionProposalV1(_Strict):
    schema_name: Literal["PlanRevisionProposal"] = "PlanRevisionProposal"
    schema_version: Literal["plan-revision-proposal-v1"] = "plan-revision-proposal-v1"
    explanation: str = Field(min_length=1, max_length=4000)
    course_title: str = Field(min_length=1, max_length=500)
    overview: str = Field(min_length=1, max_length=8000)
    today_tasks: list[str] = Field(min_length=1, max_length=24)
    schedule: list[PlanSchedulePatchV1] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def unique_targets(self):
        refs = [item.schedule_ref for item in self.schedule]
        if len(refs) != len(set(refs)):
            raise ValueError("plan_revision_duplicate_target")
        if any(not task.strip() or len(task) > 4000 for task in self.today_tasks):
            raise ValueError("plan_revision_invalid_task")
        return self


class PlanRevisionRequestV1(_Strict):
    client_request_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    base_revision: int = Field(ge=0)
    instruction: str = Field(default="", max_length=8000)
    rollback_revision: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def action(self):
        if self.rollback_revision is None and not self.instruction.strip():
            raise ValueError("plan_revision_instruction_required")
        if self.rollback_revision is not None and self.instruction:
            raise ValueError("plan_revision_rollback_instruction_forbidden")
        return self


class PlanRevisionDecisionV1(_Strict):
    decision: Literal["accept", "reject"]


class PlanRevisionInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"operation_id", "plan_id", "base_revision", "action"})
    operation_id: str
    plan_id: str
    base_revision: int
    action: Literal["preview", "accept"]


class PlanRevisionCommittedProjectionV1(_Strict):
    schema_name: Literal["PlanRevisionCommittedProjection"] = "PlanRevisionCommittedProjection"
    schema_version: Literal["plan-revision-committed-projection-v1"] = "plan-revision-committed-projection-v1"
    operation_id: str
    plan_id: str
    base_revision: int = Field(ge=0)
    action: Literal["preview", "accept"]
    proposal: PlanRevisionProposalV1
    plan: VersionedLearningPlanRecord

    @model_validator(mode="after")
    def scope(self):
        if self.plan.id != self.plan_id or self.plan.revision != self.base_revision + (self.action == "accept"):
            raise ValueError("plan_revision_commit_scope_mismatch")
        if {item.schedule_ref for item in self.proposal.schedule} != {item.id for item in self.plan.schedule}:
            raise ValueError("plan_revision_commit_targets_mismatch")
        if self.action == "accept" and apply_patch(self.plan, self.proposal) != self.plan:
            raise ValueError("plan_revision_commit_content_mismatch")
        return self


class PlanRevisionResponseV1(_Strict):
    operation_id: str
    client_request_id: str
    plan_id: str
    base_revision: int
    status: Literal["generating", "ready", "applying", "accepted", "rejected", "failed", "uncertain", "conflict"]
    instruction: str
    rollback_revision: int | None
    proposal: PlanRevisionProposalV1 | None
    base_plan: VersionedLearningPlanRecord
    result: VersionedLearningPlanRecord | None
    error_code: str


def apply_patch(plan: VersionedLearningPlanRecord, proposal: PlanRevisionProposalV1) -> VersionedLearningPlanRecord:
    existing = {item.id: item for item in plan.schedule}
    if set(existing) != {item.schedule_ref for item in proposal.schedule} or len(existing) != len(plan.schedule):
        raise ValueError("plan_revision_target_set_mismatch")
    result = plan.model_copy(deep=True)
    result.course_title = proposal.course_title
    result.overview = proposal.overview
    result.today_tasks = list(proposal.today_tasks)
    result.schedule = [existing[item.schedule_ref].model_copy(deep=True, update={"title": item.title, "focus": item.focus})
                       for item in proposal.schedule]
    # Unit/chapter IDs, grounding, progress/events and Session targets are unchanged.
    return refresh_plan_progress(result)


def proposal_from_plan(plan: VersionedLearningPlanRecord, explanation: str) -> PlanRevisionProposalV1:
    return PlanRevisionProposalV1(explanation=explanation, course_title=plan.course_title,
        overview=plan.overview, today_tasks=plan.today_tasks,
        schedule=[PlanSchedulePatchV1(schedule_ref=item.id, title=item.title, focus=item.focus) for item in plan.schedule])


REVISION_INPUT = HarnessContractRef(name="PlanRevisionInputManifest", version="plan-revision-input-v1")
REVISION_SNAPSHOT = HarnessContractRef(name="PlanRevisionProtectedInput", version="plan-revision-protected-input-v1")
REVISION_PROMPT = HarnessContractRef(name="PlanRevisionPrompt", version="plan-revision-prompt-v1")
REVISION_POLICY = HarnessContractRef(name="PlanRevisionPolicy", version="plan-revision-policy-v1")
REVISION_ADAPTER = HarnessContractRef(name="PlanRevisionAdapter", version="plan-revision-adapter-v1")
REVISION_TRACE = HarnessContractRef(name="PlanRevisionProposal", version="plan-revision-proposal-v1")
