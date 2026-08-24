from __future__ import annotations

import hashlib

from app.models.domain import (
    SessionAffinityEventRecord,
    SessionAffinityStateRecord,
    SessionMemoryRecord,
    SessionPlanConfirmationRecord,
    StudySessionRecord,
)
from app.models.harness import HarnessResourceType
from app.models.harness_effect import HarnessEffectTargetRefV1
from app.models.study_chat_effect import (
    STUDY_AFFINITY_DELTA_ADAPTER,
    STUDY_AFFINITY_DELTA_PROPOSAL_CONTRACT,
    STUDY_MEMORY_UPSERT_ADAPTER,
    STUDY_MEMORY_UPSERT_PROPOSAL_CONTRACT,
    STUDY_PLAN_CONFIRMATION_ADAPTER,
    STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
    StudyAffinityDeltaCommittedProjectionV1,
    StudyAffinityDeltaEffectProposalV1,
    StudyChatCommittedEffectBatchV1,
    StudyChatCommittedEffectProjectionV1,
    StudyChatEffectProposalV1,
    StudyChatPreparedEffectBatchV1,
    StudyChatPreparedEffectV1,
    StudyMemoryUpsertCommittedProjectionV1,
    StudyMemoryUpsertEffectProposalV1,
    StudyPlanConfirmationCommittedProjectionV1,
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
)


MAX_STUDY_CHAT_EFFECTS_PER_OPERATION = 12


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
        self._effects: list[StudyChatPreparedEffectV1] = []

    def prepare_memory_upsert(
        self,
        proposal: StudyMemoryUpsertEffectProposalV1,
    ) -> StudyChatPreparedEffectV1:
        return self._prepare_effect(
            proposal=proposal,
            adapter=STUDY_MEMORY_UPSERT_ADAPTER,
            proposal_contract=STUDY_MEMORY_UPSERT_PROPOSAL_CONTRACT,
            target_refs=[self._session_target()],
        )

    def prepare_affinity_delta(
        self,
        proposal: StudyAffinityDeltaEffectProposalV1,
    ) -> StudyChatPreparedEffectV1:
        return self._prepare_effect(
            proposal=proposal,
            adapter=STUDY_AFFINITY_DELTA_ADAPTER,
            proposal_contract=STUDY_AFFINITY_DELTA_PROPOSAL_CONTRACT,
            target_refs=[self._session_target()],
        )

    def prepare_plan_confirmation(
        self,
        proposal: StudyPlanConfirmationEffectProposalV1,
    ) -> StudyChatPreparedEffectV1:
        if not self.plan_id:
            raise ValueError("study_plan_confirmation_plan_target_required")
        if (
            proposal.action == StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS
            and not set(proposal.schedule_ids).issubset(self.allowed_schedule_ids)
        ):
            raise ValueError("study_plan_confirmation_schedule_target_unknown")
        return self._prepare_effect(
            proposal=proposal,
            adapter=STUDY_PLAN_CONFIRMATION_ADAPTER,
            proposal_contract=STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
            target_refs=[
                self._session_target(),
                HarnessEffectTargetRefV1(
                    resource_type=HarnessResourceType.LEARNING_PLAN,
                    resource_id=self.plan_id,
                ),
            ],
        )

    def prepared_batch(self) -> StudyChatPreparedEffectBatchV1 | None:
        if not self._effects:
            return None
        return StudyChatPreparedEffectBatchV1(
            operation_id=self.operation_id,
            effect_batch_id=self.effect_batch_id,
            effects=list(self._effects),
        )

    def preview_session_memory(
        self,
        base_items: list[SessionMemoryRecord],
    ) -> list[dict[str, object]]:
        items = [item.model_dump(mode="json") for item in base_items]
        for effect in self._effects:
            proposal = effect.proposal
            if not isinstance(proposal, StudyMemoryUpsertEffectProposalV1):
                continue
            existing = next((item for item in items if item["key"] == proposal.key), None)
            if existing is None:
                existing = {
                    "id": _stable_id("memory", effect.effect_id),
                    "key": proposal.key,
                    "created_at": "",
                }
                items.append(existing)
            existing.update(
                {
                    "content": proposal.content,
                    "source": "tool_call",
                    "updated_at": "",
                    "effect_state": "prepared",
                    "committed": False,
                    "effect_id": effect.effect_id,
                }
            )
        return items

    def preview_affinity_state(
        self,
        base_state: SessionAffinityStateRecord,
    ) -> dict[str, object]:
        state = base_state.model_dump(mode="json")
        events = list(state.get("events") or [])
        for effect in self._effects:
            proposal = effect.proposal
            if not isinstance(proposal, StudyAffinityDeltaEffectProposalV1):
                continue
            score = _clamp_affinity(int(state.get("score") or 0) + proposal.delta)
            state.update(
                {
                    "score": score,
                    "level": _affinity_level(score),
                    "summary": proposal.reason,
                    "updated_at": "",
                    "effect_state": "prepared",
                    "committed": False,
                    "effect_id": effect.effect_id,
                }
            )
            events.append(
                {
                    "id": _stable_id("affinity", effect.effect_id),
                    "delta": proposal.delta,
                    "reason": proposal.reason,
                    "source": "tool_call",
                    "created_at": "",
                    "effect_state": "prepared",
                    "committed": False,
                    "effect_id": effect.effect_id,
                }
            )
        state["events"] = events[-12:]
        return state

    def _prepare_effect(
        self,
        *,
        proposal: StudyChatEffectProposalV1,
        adapter,
        proposal_contract,
        target_refs: list[HarnessEffectTargetRefV1],
    ) -> StudyChatPreparedEffectV1:
        if len(self._effects) >= MAX_STUDY_CHAT_EFFECTS_PER_OPERATION:
            raise ValueError("study_chat_effect_limit_exceeded")
        slot = len(self._effects)
        effect = StudyChatPreparedEffectV1(
            operation_id=self.operation_id,
            effect_batch_id=self.effect_batch_id,
            effect_id=_stable_id("study-effect", f"{self.operation_id}:{slot}"),
            slot=slot,
            adapter=adapter,
            proposal_contract=proposal_contract,
            target_refs=target_refs,
            proposal=proposal,
        )
        self._effects.append(effect)
        return effect

    def _session_target(self) -> HarnessEffectTargetRefV1:
        return HarnessEffectTargetRefV1(
            resource_type=HarnessResourceType.STUDY_SESSION,
            resource_id=self.session_id,
        )


def commit_study_chat_effects(
    *,
    record: StudySessionRecord,
    batch: StudyChatPreparedEffectBatchV1 | None,
    expected_operation_id: str,
    allowed_schedule_ids: set[str] | frozenset[str],
    committed_at: str,
) -> StudyChatCommittedEffectBatchV1 | None:
    if batch is None:
        return None
    _validate_prepared_batch(
        record=record,
        batch=batch,
        expected_operation_id=expected_operation_id,
        allowed_schedule_ids=allowed_schedule_ids,
    )
    projections: list[StudyChatCommittedEffectProjectionV1] = []
    for effect in batch.effects:
        projections.append(
            _apply_prepared_effect(
                record=record,
                effect=effect,
                committed_at=committed_at,
            )
        )
    committed = StudyChatCommittedEffectBatchV1(
        operation_id=batch.operation_id,
        effect_batch_id=batch.effect_batch_id,
        effects=projections,
    )
    validate_study_chat_committed_effect_read_back(batch=committed, record=record)
    return committed


def validate_study_chat_committed_effect_read_back(
    *,
    batch: StudyChatCommittedEffectBatchV1,
    record: StudySessionRecord,
) -> None:
    if batch.effect_batch_id != _stable_id("study-effect-batch", batch.operation_id):
        raise ValueError("study_chat_committed_effect_batch_identity_mismatch")
    last_memory_by_key: dict[str, StudyMemoryUpsertCommittedProjectionV1] = {}
    affinity_projections: list[StudyAffinityDeltaCommittedProjectionV1] = []
    for projection in batch.effects:
        if projection.session_id != record.id:
            raise ValueError("study_chat_committed_effect_session_mismatch")
        if projection.effect_id != _stable_id(
            "study-effect",
            f"{batch.operation_id}:{projection.slot}",
        ):
            raise ValueError("study_chat_committed_effect_identity_mismatch")
        if isinstance(projection, StudyMemoryUpsertCommittedProjectionV1):
            last_memory_by_key[projection.key] = projection
        elif isinstance(projection, StudyAffinityDeltaCommittedProjectionV1):
            affinity_projections.append(projection)
        elif isinstance(projection, StudyPlanConfirmationCommittedProjectionV1):
            matches = [
                item
                for item in record.plan_confirmations
                if item.id == projection.confirmation_id
                and item.plan_id == projection.plan_id
                and item.action_type == projection.action.value
                and item.status == projection.status
                and item.created_at == projection.created_at
            ]
            if len(matches) != 1:
                raise ValueError("study_plan_confirmation_read_back_mismatch")
    for key, projection in last_memory_by_key.items():
        matches = [
            item
            for item in record.session_memory
            if item.key == key
            and item.id == projection.memory_id
            and item.content == projection.content
            and item.source == projection.source
            and item.created_at == projection.created_at
            and item.updated_at == projection.updated_at
        ]
        if len(matches) != 1:
            raise ValueError("study_memory_upsert_read_back_mismatch")
    for index, projection in enumerate(affinity_projections):
        matches = [
            item
            for item in record.affinity_state.events
            if item.id == projection.event_id
            and item.delta == projection.delta
            and item.reason == projection.reason
            and item.source == projection.source
            and item.created_at == projection.created_at
        ]
        if len(matches) != 1:
            raise ValueError("study_affinity_delta_read_back_mismatch")
        if index and projection.score != _clamp_affinity(
            affinity_projections[index - 1].score + projection.delta
        ):
            raise ValueError("study_affinity_delta_projection_sequence_mismatch")
    if affinity_projections:
        final = affinity_projections[-1]
        if (
            record.affinity_state.score != final.score
            or record.affinity_state.level != final.level
            or record.affinity_state.summary != final.summary
            or record.affinity_state.updated_at != final.updated_at
        ):
            raise ValueError("study_affinity_state_read_back_mismatch")


def _validate_prepared_batch(
    *,
    record: StudySessionRecord,
    batch: StudyChatPreparedEffectBatchV1,
    expected_operation_id: str,
    allowed_schedule_ids: set[str] | frozenset[str],
) -> None:
    if batch.operation_id != expected_operation_id:
        raise ValueError("study_chat_effect_operation_mismatch")
    if batch.effect_batch_id != _stable_id("study-effect-batch", expected_operation_id):
        raise ValueError("study_chat_effect_batch_identity_mismatch")
    if len(batch.effects) > MAX_STUDY_CHAT_EFFECTS_PER_OPERATION:
        raise ValueError("study_chat_effect_limit_exceeded")
    if [effect.slot for effect in batch.effects] != list(range(len(batch.effects))):
        raise ValueError("study_chat_effect_slots_not_contiguous")
    if len({effect.effect_id for effect in batch.effects}) != len(batch.effects):
        raise ValueError("study_chat_effect_identity_duplicate")
    for effect in batch.effects:
        if (
            effect.operation_id != batch.operation_id
            or effect.effect_batch_id != batch.effect_batch_id
        ):
            raise ValueError("study_chat_effect_member_identity_mismatch")
        if effect.effect_id != _stable_id(
            "study-effect",
            f"{expected_operation_id}:{effect.slot}",
        ):
            raise ValueError("study_chat_effect_identity_mismatch")
        proposal = effect.proposal
        expected_targets = {
            (HarnessResourceType.STUDY_SESSION, record.id),
        }
        if isinstance(proposal, StudyMemoryUpsertEffectProposalV1):
            expected_adapter = STUDY_MEMORY_UPSERT_ADAPTER
            expected_contract = STUDY_MEMORY_UPSERT_PROPOSAL_CONTRACT
        elif isinstance(proposal, StudyAffinityDeltaEffectProposalV1):
            expected_adapter = STUDY_AFFINITY_DELTA_ADAPTER
            expected_contract = STUDY_AFFINITY_DELTA_PROPOSAL_CONTRACT
        else:
            expected_adapter = STUDY_PLAN_CONFIRMATION_ADAPTER
            expected_contract = STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT
            if not record.plan_id:
                raise ValueError("study_plan_confirmation_plan_target_required")
            expected_targets.add(
                (HarnessResourceType.LEARNING_PLAN, record.plan_id)
            )
            if (
                proposal.action == StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS
                and not set(proposal.schedule_ids).issubset(allowed_schedule_ids)
            ):
                raise ValueError("study_plan_confirmation_schedule_target_unknown")
        if effect.adapter != expected_adapter:
            raise ValueError("study_chat_effect_adapter_mismatch")
        if effect.proposal_contract != expected_contract:
            raise ValueError("study_chat_effect_contract_mismatch")
        actual_targets = {
            (target.resource_type, target.resource_id)
            for target in effect.target_refs
        }
        if actual_targets != expected_targets:
            raise ValueError("study_chat_effect_target_mismatch")


def _apply_prepared_effect(
    *,
    record: StudySessionRecord,
    effect: StudyChatPreparedEffectV1,
    committed_at: str,
) -> StudyChatCommittedEffectProjectionV1:
    proposal = effect.proposal
    if isinstance(proposal, StudyMemoryUpsertEffectProposalV1):
        existing = next(
            (item for item in record.session_memory if item.key == proposal.key),
            None,
        )
        if existing is None:
            existing = SessionMemoryRecord(
                id=_stable_id("memory", effect.effect_id),
                key=proposal.key,
                content=proposal.content,
                source="tool_call",
                created_at=committed_at,
                updated_at=committed_at,
            )
            record.session_memory.append(existing)
        else:
            existing.content = proposal.content
            existing.source = "tool_call"
            existing.updated_at = committed_at
        return StudyMemoryUpsertCommittedProjectionV1(
            operation_id=effect.operation_id,
            effect_batch_id=effect.effect_batch_id,
            effect_id=effect.effect_id,
            slot=effect.slot,
            session_id=record.id,
            memory_id=existing.id,
            key=existing.key,
            content=existing.content,
            source="tool_call",
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )
    if isinstance(proposal, StudyAffinityDeltaEffectProposalV1):
        next_score = _clamp_affinity(record.affinity_state.score + proposal.delta)
        event = SessionAffinityEventRecord(
            id=_stable_id("affinity", effect.effect_id),
            delta=proposal.delta,
            reason=proposal.reason,
            source="tool_call",
            created_at=committed_at,
        )
        record.affinity_state.score = next_score
        record.affinity_state.level = _affinity_level(next_score)
        record.affinity_state.summary = proposal.reason
        record.affinity_state.updated_at = committed_at
        record.affinity_state.events.append(event)
        record.affinity_state.events = record.affinity_state.events[-12:]
        return StudyAffinityDeltaCommittedProjectionV1(
            operation_id=effect.operation_id,
            effect_batch_id=effect.effect_batch_id,
            effect_id=effect.effect_id,
            slot=effect.slot,
            session_id=record.id,
            event_id=event.id,
            delta=event.delta,
            reason=event.reason,
            source="tool_call",
            score=record.affinity_state.score,
            level=record.affinity_state.level,
            summary=record.affinity_state.summary,
            created_at=event.created_at,
            updated_at=record.affinity_state.updated_at,
        )
    confirmation_id = _stable_id("plan-confirm", effect.effect_id)
    if any(item.id == confirmation_id for item in record.plan_confirmations):
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
        plan_id=record.plan_id or "",
        title=title,
        summary=summary,
        preview_lines=preview_lines,
        payload=payload,
        status="pending",
        created_at=committed_at,
    )
    record.plan_confirmations.append(confirmation)
    return StudyPlanConfirmationCommittedProjectionV1(
        operation_id=effect.operation_id,
        effect_batch_id=effect.effect_batch_id,
        effect_id=effect.effect_id,
        slot=effect.slot,
        session_id=record.id,
        confirmation_id=confirmation.id,
        action=proposal.action,
        plan_id=confirmation.plan_id,
        status="pending",
        created_at=confirmation.created_at,
    )


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


def _clamp_affinity(score: int) -> int:
    return max(-100, min(100, int(score)))


def _affinity_level(score: int) -> str:
    if score >= 60:
        return "trusted"
    if score >= 20:
        return "warm"
    if score <= -60:
        return "hostile"
    if score <= -20:
        return "cold"
    return "neutral"
