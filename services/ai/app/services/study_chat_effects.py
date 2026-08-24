from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from app.models.domain import (
    SessionAffinityEventRecord,
    SessionAffinityStateRecord,
    PdfRectRecord,
    ProjectedPdfOverlayRecord,
    SessionMemoryRecord,
    SessionPlanConfirmationRecord,
    SessionFollowUpRecord,
    SessionProjectedPdfRecord,
    SessionSceneRecord,
    StudySessionRecord,
)
from app.models.harness import HarnessResourceType
from app.models.harness_effect import HarnessEffectTargetRefV1
from app.models.study_chat_effect import (
    STUDY_AFFINITY_DELTA_ADAPTER,
    STUDY_AFFINITY_DELTA_PROPOSAL_CONTRACT,
    STUDY_FOLLOW_UP_ADAPTER,
    STUDY_FOLLOW_UP_PROPOSAL_CONTRACT,
    STUDY_MEMORY_UPSERT_ADAPTER,
    STUDY_MEMORY_UPSERT_PROPOSAL_CONTRACT,
    STUDY_PLAN_CONFIRMATION_ADAPTER,
    STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
    STUDY_PROJECTION_ADAPTER,
    STUDY_PROJECTION_PROPOSAL_CONTRACT,
    STUDY_SCENE_REPLACE_ADAPTER,
    STUDY_SCENE_REPLACE_PROPOSAL_CONTRACT,
    StudyAffinityDeltaCommittedProjectionV1,
    StudyAffinityDeltaEffectProposalV1,
    StudyChatCommittedEffectBatchV1,
    StudyChatCommittedEffectProjectionV1,
    StudyChatEffectProposalV1,
    StudyChatPreparedEffectBatchV1,
    StudyChatPreparedEffectV1,
    StudyFollowUpCommittedProjectionV1,
    StudyFollowUpEffectAction,
    StudyFollowUpEffectProposalV1,
    StudyMemoryUpsertCommittedProjectionV1,
    StudyMemoryUpsertEffectProposalV1,
    StudyPlanConfirmationCommittedProjectionV1,
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
    StudyProjectedStateV1,
    StudyProjectionCommittedProjectionV1,
    StudyProjectionEffectAction,
    StudyProjectionEffectProposalV1,
    StudySceneReplaceCommittedProjectionV1,
    StudySceneReplaceEffectProposalV1,
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

    def prepare_follow_up(
        self,
        proposal: StudyFollowUpEffectProposalV1,
    ) -> StudyChatPreparedEffectV1:
        return self._prepare_effect(
            proposal=proposal,
            adapter=STUDY_FOLLOW_UP_ADAPTER,
            proposal_contract=STUDY_FOLLOW_UP_PROPOSAL_CONTRACT,
            target_refs=[self._session_target()],
        )

    def prepare_projection(
        self,
        proposal: StudyProjectionEffectProposalV1,
    ) -> StudyChatPreparedEffectV1:
        return self._prepare_effect(
            proposal=proposal,
            adapter=STUDY_PROJECTION_ADAPTER,
            proposal_contract=STUDY_PROJECTION_PROPOSAL_CONTRACT,
            target_refs=[self._session_target()],
        )

    def next_effect_id(self) -> str:
        if len(self._effects) >= MAX_STUDY_CHAT_EFFECTS_PER_OPERATION:
            raise ValueError("study_chat_effect_limit_exceeded")
        return _stable_id(
            "study-effect",
            f"{self.operation_id}:{len(self._effects)}",
        )

    def prepare_scene_replace(
        self,
        proposal: StudySceneReplaceEffectProposalV1,
    ) -> StudyChatPreparedEffectV1:
        return self._prepare_effect(
            proposal=proposal,
            adapter=STUDY_SCENE_REPLACE_ADAPTER,
            proposal_contract=STUDY_SCENE_REPLACE_PROPOSAL_CONTRACT,
            target_refs=[
                self._session_target(),
                HarnessEffectTargetRefV1(
                    resource_type=HarnessResourceType.SCENE,
                    resource_id=proposal.proposed_record.scene_instance_id,
                ),
            ],
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

    def preview_follow_ups(
        self,
        base_items: list[SessionFollowUpRecord],
    ) -> list[dict[str, object]]:
        items = [item.model_dump(mode="json") for item in base_items]
        for effect in self._effects:
            proposal = effect.proposal
            if not isinstance(proposal, StudyFollowUpEffectProposalV1):
                continue
            if proposal.action == StudyFollowUpEffectAction.SCHEDULE:
                items.append(
                    {
                        "id": _stable_id("follow-up", effect.effect_id),
                        "trigger_kind": "scheduled_reply",
                        "status": "pending",
                        "delay_seconds": proposal.delay_seconds,
                        "due_at": "",
                        "hidden_message": proposal.hidden_message,
                        "reason": proposal.reason,
                        "created_at": "",
                        "completed_at": "",
                        "canceled_at": "",
                        "effect_state": "prepared",
                        "committed": False,
                        "effect_id": effect.effect_id,
                    }
                )
            elif proposal.action == StudyFollowUpEffectAction.COMPLETE:
                target = next(
                    (item for item in items if item["id"] == proposal.follow_up_id),
                    None,
                )
                if target is None or target["status"] != "pending":
                    raise ValueError("study_follow_up_complete_target_invalid")
                target.update(
                    {
                        "status": "completed",
                        "completed_at": "",
                        "effect_state": "prepared",
                        "committed": False,
                        "effect_id": effect.effect_id,
                    }
                )
            else:
                for item in items:
                    if item["status"] != "pending":
                        continue
                    item.update(
                        {
                            "status": "canceled",
                            "canceled_at": "",
                            "effect_state": "prepared",
                            "committed": False,
                            "effect_id": effect.effect_id,
                        }
                    )
        return items

    def preview_projected_state(
        self,
        base_state: SessionProjectedPdfRecord | None,
    ) -> SessionProjectedPdfRecord | None:
        state = base_state.model_copy(deep=True) if base_state is not None else None
        for effect in self._effects:
            proposal = effect.proposal
            if not isinstance(proposal, StudyProjectionEffectProposalV1):
                continue
            state = _apply_projection_proposal(
                current=state,
                proposal=proposal,
                effect_id=effect.effect_id,
                mutation_time="",
            )
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
    allowed_projection_sources: set[tuple[str, str]] | frozenset[tuple[str, str]],
    scene_records: dict[str, SessionSceneRecord],
    committed_at: str,
) -> StudyChatCommittedEffectBatchV1 | None:
    if batch is None:
        return None
    _validate_prepared_batch(
        record=record,
        batch=batch,
        expected_operation_id=expected_operation_id,
        allowed_schedule_ids=allowed_schedule_ids,
        allowed_projection_sources=allowed_projection_sources,
    )
    validation_record = record.model_copy(deep=True)
    validation_scenes = {
        key: value.model_copy(deep=True) for key, value in scene_records.items()
    }
    for effect in batch.effects:
        _apply_prepared_effect(
            record=validation_record,
            effect=effect,
            scene_records=validation_scenes,
            committed_at=committed_at,
        )
    projections: list[StudyChatCommittedEffectProjectionV1] = []
    for effect in batch.effects:
        projections.append(
            _apply_prepared_effect(
                record=record,
                effect=effect,
                scene_records=scene_records,
                committed_at=committed_at,
            )
        )
    committed = StudyChatCommittedEffectBatchV1(
        operation_id=batch.operation_id,
        effect_batch_id=batch.effect_batch_id,
        effects=projections,
    )
    validate_study_chat_committed_effect_read_back(
        batch=committed,
        record=record,
        scene_records=scene_records,
    )
    return committed


def validate_study_chat_committed_effect_read_back(
    *,
    batch: StudyChatCommittedEffectBatchV1,
    record: StudySessionRecord,
    scene_records: dict[str, SessionSceneRecord] | None = None,
) -> None:
    if batch.effect_batch_id != _stable_id("study-effect-batch", batch.operation_id):
        raise ValueError("study_chat_committed_effect_batch_identity_mismatch")
    last_memory_by_key: dict[str, StudyMemoryUpsertCommittedProjectionV1] = {}
    affinity_projections: list[StudyAffinityDeltaCommittedProjectionV1] = []
    last_projection: StudyProjectionCommittedProjectionV1 | None = None
    last_scene_by_id: dict[str, StudySceneReplaceCommittedProjectionV1] = {}
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
        elif isinstance(projection, StudyFollowUpCommittedProjectionV1):
            affected = {
                item.id: item
                for item in record.pending_follow_ups
                if item.id in projection.affected_follow_up_ids
            }
            if set(affected) != set(projection.affected_follow_up_ids):
                raise ValueError("study_follow_up_read_back_missing")
            if projection.action == StudyFollowUpEffectAction.SCHEDULE:
                target = affected.get(projection.follow_up_id)
                if (
                    len(affected) != 1
                    or target is None
                    or target.status != "pending"
                    or target.created_at != projection.committed_at
                ):
                    raise ValueError("study_follow_up_schedule_read_back_mismatch")
            elif projection.action == StudyFollowUpEffectAction.COMPLETE:
                target = affected.get(projection.follow_up_id)
                if (
                    len(affected) != 1
                    or target is None
                    or target.status != "completed"
                    or target.completed_at != projection.committed_at
                ):
                    raise ValueError("study_follow_up_complete_read_back_mismatch")
            else:
                canceled_ids = {
                    item.id
                    for item in record.pending_follow_ups
                    if item.status == "canceled"
                    and item.canceled_at == projection.committed_at
                }
                if canceled_ids != set(projection.affected_follow_up_ids):
                    raise ValueError("study_follow_up_cancel_read_back_mismatch")
        elif isinstance(projection, StudyProjectionCommittedProjectionV1):
            last_projection = projection
        elif isinstance(projection, StudySceneReplaceCommittedProjectionV1):
            last_scene_by_id[projection.scene_instance_id] = projection
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
    if last_projection is not None:
        if record.projected_pdf is None or (
            StudyProjectedStateV1.model_validate(
                record.projected_pdf.model_dump(mode="json")
            )
            != last_projection.projected_state
        ):
            raise ValueError("study_projection_read_back_mismatch")
    for scene_id, projection in last_scene_by_id.items():
        committed_scene = projection.committed_record
        _validate_scene_record(committed_scene)
        if (
            committed_scene.session_id != record.id
            or committed_scene.updated_at != projection.updated_at
            or scene_state_digest(committed_scene) != projection.scene_state_digest
        ):
            raise ValueError("study_scene_committed_projection_read_back_mismatch")
        if (
            record.scene_instance_id == scene_id
            and record.scene_profile != committed_scene.scene_profile
        ):
            raise ValueError("study_scene_session_projection_read_back_mismatch")
        if scene_records is None:
            continue
        scene = scene_records.get(scene_id)
        if scene is None:
            raise ValueError("study_scene_read_back_missing")
        _validate_scene_record(scene)
        _validate_scene_immutable_projection(scene, expected=committed_scene)
        if scene.updated_at == projection.updated_at:
            if scene_state_digest(scene) != projection.scene_state_digest:
                raise ValueError("study_scene_read_back_mismatch")
        elif _parse_scene_timestamp(scene.updated_at) < _parse_scene_timestamp(
            projection.updated_at
        ):
            raise ValueError("study_scene_read_back_watermark_regressed")


def _validate_prepared_batch(
    *,
    record: StudySessionRecord,
    batch: StudyChatPreparedEffectBatchV1,
    expected_operation_id: str,
    allowed_schedule_ids: set[str] | frozenset[str],
    allowed_projection_sources: set[tuple[str, str]] | frozenset[tuple[str, str]],
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
        elif isinstance(proposal, StudyFollowUpEffectProposalV1):
            expected_adapter = STUDY_FOLLOW_UP_ADAPTER
            expected_contract = STUDY_FOLLOW_UP_PROPOSAL_CONTRACT
        elif isinstance(proposal, StudyProjectionEffectProposalV1):
            expected_adapter = STUDY_PROJECTION_ADAPTER
            expected_contract = STUDY_PROJECTION_PROPOSAL_CONTRACT
            if (
                proposal.action == StudyProjectionEffectAction.SET
                and proposal.source_kind != "generated_image"
                and (proposal.source_kind, proposal.source_id)
                not in allowed_projection_sources
            ):
                raise ValueError("study_projection_source_target_unknown")
        elif isinstance(proposal, StudySceneReplaceEffectProposalV1):
            expected_adapter = STUDY_SCENE_REPLACE_ADAPTER
            expected_contract = STUDY_SCENE_REPLACE_PROPOSAL_CONTRACT
            if proposal.proposed_record.session_id != record.id:
                raise ValueError("study_scene_session_target_mismatch")
            if proposal.proposed_record.scene_instance_id != record.scene_instance_id:
                raise ValueError("study_scene_binding_target_mismatch")
            expected_targets.add(
                (
                    HarnessResourceType.SCENE,
                    proposal.proposed_record.scene_instance_id,
                )
            )
        elif isinstance(proposal, StudyPlanConfirmationEffectProposalV1):
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
        else:
            raise ValueError("study_chat_effect_proposal_unsupported")
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
    scene_records: dict[str, SessionSceneRecord],
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
    if isinstance(proposal, StudyFollowUpEffectProposalV1):
        affected_ids: list[str] = []
        follow_up_id = proposal.follow_up_id
        if proposal.action == StudyFollowUpEffectAction.SCHEDULE:
            follow_up_id = _stable_id("follow-up", effect.effect_id)
            if any(item.id == follow_up_id for item in record.pending_follow_ups):
                raise ValueError("study_follow_up_identity_duplicate")
            due_at = (
                datetime.fromisoformat(committed_at)
                + timedelta(seconds=proposal.delay_seconds)
            ).isoformat()
            record.pending_follow_ups.append(
                SessionFollowUpRecord(
                    id=follow_up_id,
                    trigger_kind="scheduled_reply",
                    status="pending",
                    delay_seconds=proposal.delay_seconds,
                    due_at=due_at,
                    hidden_message=proposal.hidden_message,
                    reason=proposal.reason,
                    created_at=committed_at,
                )
            )
            affected_ids.append(follow_up_id)
        elif proposal.action == StudyFollowUpEffectAction.COMPLETE:
            target = next(
                (
                    item
                    for item in record.pending_follow_ups
                    if item.id == proposal.follow_up_id and item.status == "pending"
                ),
                None,
            )
            if target is None:
                raise ValueError("study_follow_up_complete_target_invalid")
            target.status = "completed"
            target.completed_at = committed_at
            affected_ids.append(target.id)
        else:
            for item in record.pending_follow_ups:
                if item.status != "pending":
                    continue
                item.status = "canceled"
                item.canceled_at = committed_at
                affected_ids.append(item.id)
        return StudyFollowUpCommittedProjectionV1(
            operation_id=effect.operation_id,
            effect_batch_id=effect.effect_batch_id,
            effect_id=effect.effect_id,
            slot=effect.slot,
            session_id=record.id,
            action=proposal.action,
            follow_up_id=follow_up_id,
            affected_follow_up_ids=affected_ids,
            committed_at=committed_at,
        )
    if isinstance(proposal, StudyProjectionEffectProposalV1):
        record.projected_pdf = _apply_projection_proposal(
            current=record.projected_pdf,
            proposal=proposal,
            effect_id=effect.effect_id,
            mutation_time=committed_at,
        )
        if record.projected_pdf is None:
            raise ValueError("study_projection_read_back_missing")
        return StudyProjectionCommittedProjectionV1(
            operation_id=effect.operation_id,
            effect_batch_id=effect.effect_batch_id,
            effect_id=effect.effect_id,
            slot=effect.slot,
            session_id=record.id,
            action=proposal.action,
            projected_state=StudyProjectedStateV1.model_validate(
                record.projected_pdf.model_dump(mode="json")
            ),
        )
    if isinstance(proposal, StudySceneReplaceEffectProposalV1):
        scene_id = proposal.proposed_record.scene_instance_id
        current_scene = scene_records.get(scene_id)
        if current_scene is None:
            raise ValueError("study_scene_target_missing")
        if scene_state_digest(current_scene) != proposal.before_state_digest:
            raise ValueError("study_scene_before_digest_mismatch")
        proposed = proposal.proposed_record.model_copy(deep=True)
        if (
            proposed.scene_instance_id != current_scene.scene_instance_id
            or proposed.session_id != current_scene.session_id
            or proposed.document_id != current_scene.document_id
            or proposed.persona_id != current_scene.persona_id
            or proposed.source_scene_id != current_scene.source_scene_id
            or proposed.source_scene_name != current_scene.source_scene_name
            or proposed.config_id != current_scene.config_id
            or proposed.created_at != current_scene.created_at
        ):
            raise ValueError("study_scene_immutable_projection_mismatch")
        _validate_scene_record(proposed)
        proposed.updated_at = committed_at
        scene_records[scene_id] = proposed
        return StudySceneReplaceCommittedProjectionV1(
            operation_id=effect.operation_id,
            effect_batch_id=effect.effect_batch_id,
            effect_id=effect.effect_id,
            slot=effect.slot,
            session_id=record.id,
            scene_instance_id=scene_id,
            tool_name=proposal.tool_name,
            scene_state_digest=scene_state_digest(proposed),
            updated_at=committed_at,
            committed_record=proposed.model_copy(deep=True),
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


def _apply_projection_proposal(
    *,
    current: SessionProjectedPdfRecord | None,
    proposal: StudyProjectionEffectProposalV1,
    effect_id: str,
    mutation_time: str,
) -> SessionProjectedPdfRecord:
    if proposal.action == StudyProjectionEffectAction.SET:
        source_id = (
            _stable_id("generated-image", effect_id)
            if proposal.source_kind == "generated_image"
            else proposal.source_id
        )
        return SessionProjectedPdfRecord(
            source_kind=proposal.source_kind,
            source_id=source_id,
            title=proposal.title,
            page_number=min(proposal.page_number, proposal.page_count),
            page_count=proposal.page_count,
            image_url=proposal.image_url,
            overlays=[],
            updated_at=mutation_time,
        )
    if current is None:
        raise ValueError("study_projection_target_missing")
    projected = current.model_copy(deep=True)
    if proposal.action == StudyProjectionEffectAction.FOCUS:
        projected.page_number = min(proposal.page_number, projected.page_count)
    elif proposal.action == StudyProjectionEffectAction.APPEND_OVERLAY:
        overlay_prefix = (
            "image-overlay"
            if projected.source_kind in {"attachment_image", "generated_image"}
            else "pdf-overlay"
        )
        projected.overlays.append(
            ProjectedPdfOverlayRecord(
                id=_stable_id(overlay_prefix, effect_id),
                kind=proposal.overlay_kind,
                page_number=min(proposal.page_number, projected.page_count),
                rects=[
                    PdfRectRecord.model_validate(item.model_dump(mode="json"))
                    for item in proposal.rects
                ],
                label=proposal.label,
                quote_text=proposal.quote_text,
                color=proposal.color or "#FACC15",
                created_at=mutation_time,
            )
        )
        projected.overlays = projected.overlays[-24:]
        projected.page_number = min(proposal.page_number, projected.page_count)
    else:
        if proposal.page_number:
            projected.overlays = [
                item
                for item in projected.overlays
                if item.page_number != proposal.page_number
            ]
        else:
            projected.overlays = []
    projected.updated_at = mutation_time
    return projected


def _clamp_affinity(score: int) -> int:
    return max(-100, min(100, int(score)))


def scene_state_digest(record: SessionSceneRecord) -> str:
    payload = record.model_dump(mode="json")
    payload["updated_at"] = ""
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_scene_record(record: SessionSceneRecord) -> None:
    layer_ids: list[str] = []
    object_ids: list[str] = []

    def visit(layers) -> None:
        for layer in layers:
            layer_ids.append(layer.id)
            object_ids.extend(item.id for item in layer.objects)
            visit(layer.children)

    visit(record.scene_layers)
    if (
        len(layer_ids) != len(set(layer_ids))
        or len(object_ids) != len(set(object_ids))
    ):
        raise ValueError("study_scene_identity_duplicate")
    if record.selected_layer_id and record.selected_layer_id not in set(layer_ids):
        raise ValueError("study_scene_selected_layer_missing")
    if record.scene_profile is None:
        raise ValueError("study_scene_profile_missing")
    if (
        record.scene_profile.scene_id != record.selected_layer_id
        or record.scene_profile.scene_tree != record.scene_layers
    ):
        raise ValueError("study_scene_profile_projection_mismatch")


def _validate_scene_immutable_projection(
    record: SessionSceneRecord,
    *,
    expected: SessionSceneRecord,
) -> None:
    for field_name in (
        "scene_instance_id",
        "session_id",
        "document_id",
        "persona_id",
        "source_scene_id",
        "source_scene_name",
        "config_id",
        "created_at",
    ):
        if getattr(record, field_name) != getattr(expected, field_name):
            raise ValueError(f"study_scene_immutable_read_back_mismatch:{field_name}")


def _parse_scene_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("study_scene_updated_at_invalid") from exc
    if parsed.tzinfo is None:
        raise ValueError("study_scene_updated_at_timezone_required")
    return parsed


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
