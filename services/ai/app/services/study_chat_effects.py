from __future__ import annotations

import hashlib

from app.models.domain import SessionPlanConfirmationRecord, StudySessionRecord
from app.models.harness import HarnessResourceType
from app.models.harness_effect import HarnessEffectTargetRefV1
from app.models.study_chat_effect import (
    STUDY_PLAN_CONFIRMATION_ADAPTER,
    STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
    StudyPlanConfirmationCommittedProjectionV1,
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
    StudyPlanConfirmationPreparedEffectBatchV1,
    StudyPlanConfirmationPreparedEffectV1,
)


class StudyChatEffectCollector:
    """In-process prepare boundary; no business state is written here."""

    def __init__(
        self,
        *,
        operation_id: str,
        session_id: str,
        plan_id: str | None,
        allowed_schedule_ids: set[str] | frozenset[str],
    ) -> None:
        self.operation_id = operation_id
        self.session_id = session_id
        self.plan_id = (plan_id or "").strip()
        self.allowed_schedule_ids = frozenset(allowed_schedule_ids)
        self.effect_batch_id = _stable_id("study-effect-batch", operation_id)
        self._effects: list[StudyPlanConfirmationPreparedEffectV1] = []

    def prepare_plan_confirmation(
        self,
        proposal: StudyPlanConfirmationEffectProposalV1,
    ) -> StudyPlanConfirmationPreparedEffectV1:
        if not self.plan_id:
            raise ValueError("study_plan_confirmation_plan_target_required")
        if (
            proposal.action == StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS
            and not set(proposal.schedule_ids).issubset(self.allowed_schedule_ids)
        ):
            raise ValueError("study_plan_confirmation_schedule_target_unknown")
        slot = len(self._effects)
        effect = StudyPlanConfirmationPreparedEffectV1(
            operation_id=self.operation_id,
            effect_batch_id=self.effect_batch_id,
            effect_id=_stable_id("study-effect", f"{self.operation_id}:{slot}"),
            slot=slot,
            adapter=STUDY_PLAN_CONFIRMATION_ADAPTER,
            proposal_contract=STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
            target_refs=[
                HarnessEffectTargetRefV1(
                    resource_type=HarnessResourceType.STUDY_SESSION,
                    resource_id=self.session_id,
                ),
                HarnessEffectTargetRefV1(
                    resource_type=HarnessResourceType.LEARNING_PLAN,
                    resource_id=self.plan_id,
                ),
            ],
            proposal=proposal,
        )
        self._effects.append(effect)
        return effect

    def prepared_batch(self) -> StudyPlanConfirmationPreparedEffectBatchV1 | None:
        if not self._effects:
            return None
        return StudyPlanConfirmationPreparedEffectBatchV1(
            operation_id=self.operation_id,
            effect_batch_id=self.effect_batch_id,
            effects=list(self._effects),
        )


def commit_study_plan_confirmation_effects(
    *,
    record: StudySessionRecord,
    batch: StudyPlanConfirmationPreparedEffectBatchV1 | None,
    expected_operation_id: str,
    committed_at: str,
) -> list[StudyPlanConfirmationCommittedProjectionV1]:
    if batch is None:
        return []
    if batch.operation_id != expected_operation_id:
        raise ValueError("study_plan_confirmation_operation_mismatch")
    if batch.effect_batch_id != _stable_id("study-effect-batch", expected_operation_id):
        raise ValueError("study_plan_confirmation_batch_identity_mismatch")
    projections: list[StudyPlanConfirmationCommittedProjectionV1] = []
    existing_ids = {item.id for item in record.plan_confirmations}
    for effect in batch.effects:
        if effect.effect_id != _stable_id(
            "study-effect",
            f"{expected_operation_id}:{effect.slot}",
        ):
            raise ValueError("study_plan_confirmation_effect_identity_mismatch")
        if effect.adapter != STUDY_PLAN_CONFIRMATION_ADAPTER:
            raise ValueError("study_plan_confirmation_adapter_mismatch")
        if effect.proposal_contract != STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT:
            raise ValueError("study_plan_confirmation_contract_mismatch")
        expected_targets = {
            (HarnessResourceType.STUDY_SESSION, record.id),
            (HarnessResourceType.LEARNING_PLAN, record.plan_id),
        }
        actual_targets = {
            (target.resource_type, target.resource_id)
            for target in effect.target_refs
        }
        if not record.plan_id or actual_targets != expected_targets:
            raise ValueError("study_plan_confirmation_target_mismatch")
        proposal = effect.proposal
        confirmation_id = _stable_id("plan-confirm", effect.effect_id)
        if confirmation_id in existing_ids:
            raise ValueError("study_plan_confirmation_identity_duplicate")
        title, summary, preview_lines, payload = _confirmation_content(proposal)
        confirmation = SessionPlanConfirmationRecord(
            id=confirmation_id,
            tool_name=(
                "update_learning_plan"
                if proposal.action == StudyPlanConfirmationEffectAction.UPDATE_PLAN
                else "update_learning_plan_progress"
            ),
            action_type=proposal.action.value,
            plan_id=record.plan_id,
            title=title,
            summary=summary,
            preview_lines=preview_lines,
            payload=payload,
            status="pending",
            created_at=committed_at,
        )
        record.plan_confirmations.append(confirmation)
        existing_ids.add(confirmation_id)
        projection = StudyPlanConfirmationCommittedProjectionV1(
            operation_id=effect.operation_id,
            effect_batch_id=effect.effect_batch_id,
            effect_id=effect.effect_id,
            slot=effect.slot,
            session_id=record.id,
            confirmation_id=confirmation.id,
            action=proposal.action,
            plan_id=record.plan_id,
            status="pending",
            created_at=confirmation.created_at,
        )
        if record.plan_confirmations[-1].id != projection.confirmation_id:
            raise ValueError("study_plan_confirmation_read_back_mismatch")
        projections.append(projection)
    return projections


def _confirmation_content(
    proposal: StudyPlanConfirmationEffectProposalV1,
) -> tuple[str, str, list[str], dict[str, object]]:
    if proposal.action == StudyPlanConfirmationEffectAction.UPDATE_PLAN:
        return (
            "待确认的计划修改",
            proposal.note or "模型建议调整当前学习计划结构。",
            [f"课程标题将更新为：{proposal.course_title}"],
            {"course_title": proposal.course_title, "note": proposal.note},
        )
    return (
        "待确认的完成度更新",
        proposal.note or "模型建议更新当前计划的完成状态。",
        [f"{item} -> {proposal.schedule_status}" for item in proposal.schedule_ids],
        {
            "schedule_ids": proposal.schedule_ids,
            "status": proposal.schedule_status,
            "note": proposal.note,
        },
    )


def _stable_id(prefix: str, seed: str) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"
