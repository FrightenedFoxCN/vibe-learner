from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
from threading import Event, RLock, Thread
import time
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException

from app.core.harness_component_versions import TAVERN_SCHEDULER_CONTRACT_VERSION
from app.models.harness import HarnessTraceRecord
from app.models.tavern import (
    CreateTavernRoomRequest,
    TavernAuthorKind,
    TavernActorReply,
    TavernInteractionMode,
    TavernContinueInput,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomDetail,
    TavernRoomListResponse,
    TavernRoomRecord,
    TavernRoomState,
    TavernRoomStatus,
    TavernRecoveryAction,
    TavernRunRecord,
    TavernRunChainStatus,
    TavernRunRecoveryChain,
    TavernRunStatus,
    TavernRunTriggerKind,
    TavernSpeakerStepRecord,
    TavernSpeakerStepStatus,
    TavernTurnRequest,
    TavernTurnResponse,
    TavernUserMessageInput,
    RetryTavernRunRequest,
    UpdateTavernRoomRequest,
)
from app.models.tavern_commit import TavernPersonaMessageCommitMetadataV1
from app.persistence.tavern_repository import (
    TavernIdempotencyConflict,
    TavernRepository,
    TavernRoomCursorInvalid,
    TavernRetryAlreadyCreated,
    TavernRevisionConflict,
    TavernRunTerminalConflict,
    TavernRunInProgress,
    TavernStepClaimConflict,
    TavernStepClaimsExhausted,
)
from app.services.model_recovery import (
    consume_model_recovery_state,
    reset_model_recovery_state,
)
from app.services.model_provider import ModelProvider
from app.services.persona import PersonaEngine
from app.services.tavern_harness import (
    TavernActorHarness,
    TavernHarnessViolation,
    persona_prompt_hash,
    tavern_payload_digest,
)
from app.services.tavern_prompt import (
    TavernPromptBudgetError,
    preflight_tavern_actor_prompt,
)


TAVERN_STEP_LEASE_SECONDS = 120
TAVERN_MAX_STEP_CLAIMS = 3


class TavernService:
    def __init__(
        self,
        *,
        repository: TavernRepository,
        persona_engine: PersonaEngine,
        model_provider: ModelProvider,
        step_lease_seconds: int = TAVERN_STEP_LEASE_SECONDS,
        max_step_claims: int = TAVERN_MAX_STEP_CLAIMS,
    ) -> None:
        self.repository = repository
        self.persona_engine = persona_engine
        self.model_provider = model_provider
        self.actor_harness = TavernActorHarness()
        self.step_lease_seconds = max(1, min(900, step_lease_seconds))
        self.max_step_claims = max(1, min(5, max_step_claims))
        self._worker_id = f"tavern-worker-{uuid4().hex[:12]}"
        self._locks_guard = RLock()
        self._room_locks: defaultdict[str, RLock] = defaultdict(RLock)
        self._creation_lock = RLock()

    def create_room(self, payload: CreateTavernRoomRequest) -> TavernRoomDetail:
        with self._creation_lock:
            creation_input_digest = tavern_payload_digest(
                payload.model_dump(mode="json", exclude={"idempotency_key"})
            )
            existing = self.repository.get_room_by_creation_key(payload.idempotency_key)
            if existing is not None:
                if (
                    existing.room.creation_input_digest
                    and existing.room.creation_input_digest != creation_input_digest
                ):
                    raise HTTPException(
                        status_code=409,
                        detail="tavern_idempotency_key_reused:room_creation",
                    )
                return existing
            room_id = f"tavern-{uuid4().hex[:12]}"
            now = _now()
            participants = self._build_participants(
                room_id=room_id,
                persona_ids=payload.persona_ids,
                existing={},
                joined_at=now,
            )
            messages: list[TavernMessageRecord] = []
            if payload.opening_prompt.strip():
                messages.append(
                    TavernMessageRecord(
                        id=f"tavern-message-{uuid4().hex[:12]}",
                        room_id=room_id,
                        sequence=1,
                        author_kind=TavernAuthorKind.DIRECTOR,
                        content=payload.opening_prompt.strip(),
                        created_at=now,
                    )
                )
            room = TavernRoomRecord(
                id=room_id,
                creation_key=payload.idempotency_key,
                creation_input_digest=creation_input_digest,
                title=payload.title.strip(),
                scene_profile=payload.scene_profile,
                harness_policy=payload.harness_policy,
                last_sequence=len(messages),
                created_at=now,
                updated_at=now,
            )
            try:
                return self.repository.create_room(
                    room=room,
                    participants=participants,
                    messages=messages,
                )
            except TavernIdempotencyConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    def list_rooms(
        self,
        *,
        limit: int = 30,
        cursor: str | None = None,
    ) -> TavernRoomListResponse:
        try:
            return self.repository.list_rooms(limit=limit, cursor=cursor)
        except TavernRoomCursorInvalid as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def require_room(
        self,
        room_id: str,
        *,
        after_sequence: int = 0,
        before_sequence: int | None = None,
        tail: bool = False,
        limit: int = 200,
    ) -> TavernRoomDetail:
        room = self.repository.get_room(
            room_id,
            after_sequence=after_sequence,
            before_sequence=(
                2**63 - 1
                if tail
                else before_sequence
            ),
            limit=limit,
        )
        if room is None:
            raise HTTPException(status_code=404, detail="tavern_room_not_found")
        return room

    def list_runs(self, room_id: str, *, limit: int = 50) -> list[TavernRunRecord]:
        self.require_room(room_id, limit=1)
        return self.repository.list_runs(room_id, limit=limit)

    def list_run_recovery(
        self,
        room_id: str,
        *,
        limit: int = 50,
    ) -> list[TavernRunRecoveryChain]:
        self.require_room(room_id, limit=1)
        runs = self.repository.list_all_runs(room_id)
        by_id = {run.id: run for run in runs}
        children: defaultdict[str, list[TavernRunRecord]] = defaultdict(list)
        roots: list[TavernRunRecord] = []
        for run in runs:
            if run.parent_run_id:
                parent = by_id.get(run.parent_run_id)
                if parent is None or parent.room_id != room_id:
                    raise RuntimeError("tavern_retry_chain_parent_missing")
                children[parent.id].append(run)
            else:
                roots.append(run)
        if any(len(items) != 1 for items in children.values()):
            raise RuntimeError("tavern_retry_chain_branch_detected")

        projections: list[TavernRunRecoveryChain] = []
        visited: set[str] = set()
        for root in sorted(
            roots,
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        ):
            chain = [root]
            seen = {root.id}
            current = root
            while children.get(current.id):
                child = children[current.id][0]
                if child.id in seen:
                    raise RuntimeError("tavern_retry_chain_cycle_detected")
                if (child.root_run_id or child.id) != root.id:
                    raise RuntimeError("tavern_retry_chain_root_mismatch")
                chain.append(child)
                seen.add(child.id)
                current = child
            visited.update(seen)
            leaf = chain[-1]
            completed = {
                step.persona_id
                for member in chain
                for step in member.speaker_steps
                if step.status == TavernSpeakerStepStatus.COMPLETED
            }
            completed_ids = [
                persona_id
                for persona_id in root.scheduled_participant_ids
                if persona_id in completed
            ]
            unfinished_ids = [
                persona_id
                for persona_id in root.scheduled_participant_ids
                if persona_id not in completed
            ]
            if leaf.status == TavernRunStatus.PENDING:
                chain_status = TavernRunChainStatus.ACTIVE
                action = TavernRecoveryAction.WAIT_AND_RESUME
            elif leaf.status in {TavernRunStatus.PARTIAL, TavernRunStatus.FAILED}:
                chain_status = TavernRunChainStatus.RECOVERABLE
                action = TavernRecoveryAction.RETRY_LEAF
            elif leaf.status == TavernRunStatus.CANCELED:
                chain_status = TavernRunChainStatus.CANCELED
                action = TavernRecoveryAction.NONE
            elif len(chain) > 1:
                chain_status = TavernRunChainStatus.RECOVERED
                action = TavernRecoveryAction.NONE
            else:
                chain_status = TavernRunChainStatus.COMPLETED
                action = TavernRecoveryAction.NONE
            projections.append(
                TavernRunRecoveryChain(
                    root_run_id=root.id,
                    run_ids=[member.id for member in chain],
                    root_status=root.status,
                    leaf_run=leaf,
                    chain_status=chain_status,
                    recovery_action=action,
                    completed_participant_ids=completed_ids,
                    unfinished_participant_ids=unfinished_ids,
                )
            )
        if visited != set(by_id):
            raise RuntimeError("tavern_retry_chain_orphan_detected")
        return projections[: max(1, min(limit, 100))]

    def update_room(
        self,
        *,
        room_id: str,
        payload: UpdateTavernRoomRequest,
    ) -> TavernRoomDetail:
        with self._room_lock(room_id):
            detail = self.require_room(room_id)
            room = detail.room.model_copy(deep=True)
            if payload.title is not None:
                room.title = payload.title.strip()
            if "scene_profile" in payload.model_fields_set:
                room.scene_profile = payload.scene_profile
            if payload.status is not None:
                room.status = payload.status
            room.updated_at = _now()
            if payload.persona_ids is None:
                participants = detail.participants
            else:
                existing = {item.persona_id: item for item in detail.participants}
                participants = self._build_participants(
                    room_id=room_id,
                    persona_ids=payload.persona_ids,
                    existing=existing,
                    joined_at=room.updated_at,
                )
            try:
                return self.repository.update_room(
                    room=room,
                    participants=participants,
                    expected_revision=payload.expected_revision,
                )
            except TavernRevisionConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except TavernRunInProgress as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    def delete_room(self, room_id: str, *, expected_revision: int) -> None:
        with self._room_lock(room_id):
            try:
                if not self.repository.delete_room(
                    room_id,
                    expected_revision=expected_revision,
                ):
                    raise HTTPException(status_code=404, detail="tavern_room_not_found")
            except TavernRunInProgress as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except TavernRevisionConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

    def run_turn(self, *, room_id: str, payload: TavernTurnRequest) -> TavernTurnResponse:
        digest_payload = payload.model_dump(mode="json", exclude={"idempotency_key"})
        digest_payload["target_persona_ids"] = sorted(payload.target_persona_ids)
        request_digest = tavern_payload_digest(digest_payload)
        duplicate = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        if duplicate is not None:
            if duplicate.request_digest and duplicate.request_digest != request_digest:
                raise HTTPException(
                    status_code=409,
                    detail="tavern_idempotency_key_reused:turn",
                )
            return self._resume_or_replay_run(duplicate)

        detail = self.require_room(room_id)
        if detail.room.status != TavernRoomStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="tavern_room_not_active")
        participant_map = {item.persona_id: item for item in detail.participants}
        missing_targets = [
            item for item in payload.target_persona_ids if item not in participant_map
        ]
        if missing_targets:
            raise HTTPException(status_code=422, detail="tavern_target_not_in_room")
        scheduled = [
            item
            for item in detail.participants
            if item.persona_id in set(payload.target_persona_ids)
        ]
        if len(scheduled) > detail.room.harness_policy.max_character_messages:
            raise HTTPException(
                status_code=422,
                detail="tavern_target_count_exceeds_room_policy",
            )

        now = _now()
        run_id = f"tavern-run-{uuid4().hex[:12]}"
        user_message = None
        input_content = ""
        if isinstance(payload.input, TavernUserMessageInput):
            input_content = payload.input.content
            user_message = TavernMessageRecord(
                id=f"tavern-message-{uuid4().hex[:12]}",
                room_id=room_id,
                sequence=1,
                run_id=run_id,
                author_kind=TavernAuthorKind.USER,
                content=input_content,
                addressed_participant_ids=[item.persona_id for item in scheduled],
                client_request_id=payload.idempotency_key,
                created_at=now,
            )
            anchor_message_id = user_message.id
            trigger_kind = TavernRunTriggerKind.USER_MESSAGE
        else:
            latest = self.repository.get_latest_message(room_id)
            if latest is None or latest.id != payload.input.anchor_message_id:
                raise HTTPException(status_code=409, detail="tavern_continue_anchor_stale")
            anchor_message_id = latest.id
            trigger_kind = TavernRunTriggerKind.CONTINUE

        run = self._new_run(
            run_id=run_id,
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
            request_digest=request_digest,
            context_digest=_room_context_digest(detail),
            mode=payload.mode,
            trigger_kind=trigger_kind,
            scheduled=scheduled,
            anchor_message_id=anchor_message_id,
            guidance=payload.guidance,
            expected_room_revision=payload.expected_room_revision,
            created_at=now,
        )
        run, created = self._begin_run(run=run, user_message=user_message)
        if not created:
            return self._replay_run(run)
        return self._execute_run(
            run=run,
            detail=detail,
            input_content=input_content,
        )

    def retry_run(
        self,
        *,
        room_id: str,
        source_run_id: str,
        payload: RetryTavernRunRequest,
    ) -> TavernTurnResponse:
        digest = tavern_payload_digest(
            {
                "source_run_id": source_run_id,
                "expected_room_revision": payload.expected_room_revision,
            }
        )
        duplicate = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        if duplicate is not None:
            if duplicate.request_digest and duplicate.request_digest != digest:
                raise HTTPException(status_code=409, detail="tavern_idempotency_key_reused:retry")
            return self._resume_or_replay_run(duplicate)

        detail = self.require_room(room_id)
        if detail.room.status != TavernRoomStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="tavern_room_not_active")
        source = self.repository.get_run(source_run_id)
        if source is None or source.room_id != room_id:
            raise HTTPException(status_code=404, detail="tavern_run_not_found")
        if source.status not in {TavernRunStatus.PARTIAL, TavernRunStatus.FAILED}:
            raise HTTPException(status_code=409, detail="tavern_run_not_retryable")
        existing_child = self.repository.get_retry_child(source.id)
        if existing_child is not None:
            raise HTTPException(
                status_code=409,
                detail=f"tavern_retry_already_created:{existing_child.id}",
            )
        current_context_digest = _room_context_digest(detail)
        if (
            detail.room.revision != source.expected_room_revision + 1
            or source.terminal_sequence != detail.room.last_sequence
            or (
                source.context_digest
                and source.context_digest != current_context_digest
            )
        ):
            raise HTTPException(status_code=409, detail="tavern_retry_context_changed")
        remaining_ids = [
            step.persona_id
            for step in source.speaker_steps
            if step.status in {TavernSpeakerStepStatus.FAILED, TavernSpeakerStepStatus.BLOCKED}
        ]
        if not remaining_ids:
            raise HTTPException(status_code=409, detail="tavern_run_has_no_remaining_steps")
        participant_map = {item.persona_id: item for item in detail.participants}
        try:
            scheduled = [participant_map[item] for item in remaining_ids]
        except KeyError as exc:
            raise HTTPException(status_code=409, detail="tavern_retry_participant_changed") from exc
        source_steps_by_persona = {step.persona_id: step for step in source.speaker_steps}
        if any(
            source_steps_by_persona[item.persona_id].participant_prompt_hash
            != item.prompt_hash
            for item in scheduled
        ):
            raise HTTPException(status_code=409, detail="tavern_retry_participant_changed")
        completed_steps = [
            step
            for step in source.speaker_steps
            if step.status == TavernSpeakerStepStatus.COMPLETED and step.message_id
        ]
        anchor_message_id = (
            completed_steps[-1].message_id if completed_steps else source.anchor_message_id
        )
        root = self.repository.get_run(source.root_run_id or source.id)
        if root is None:
            raise HTTPException(status_code=409, detail="tavern_retry_root_missing")
        input_content = ""
        if root.input_message_id:
            input_message = self.repository.get_message(root.input_message_id)
            if input_message is None:
                raise HTTPException(status_code=409, detail="tavern_run_input_message_missing")
            input_content = input_message.content

        now = _now()
        run = self._new_run(
            run_id=f"tavern-run-{uuid4().hex[:12]}",
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
            request_digest=digest,
            context_digest=current_context_digest,
            mode=source.mode,
            trigger_kind=TavernRunTriggerKind.RETRY,
            scheduled=scheduled,
            anchor_message_id=anchor_message_id,
            guidance=source.guidance,
            expected_room_revision=payload.expected_room_revision,
            created_at=now,
            parent_run_id=source.id,
            root_run_id=source.root_run_id or source.id,
            input_message_id=root.input_message_id,
        )
        run, created = self._begin_run(run=run, user_message=None)
        if not created:
            return self._replay_run(run)
        return self._execute_run(run=run, detail=detail, input_content=input_content)

    def _new_run(
        self,
        *,
        run_id: str,
        room_id: str,
        idempotency_key: str,
        request_digest: str,
        context_digest: str,
        mode: TavernInteractionMode,
        trigger_kind: TavernRunTriggerKind,
        scheduled: list[TavernParticipantRecord],
        anchor_message_id: str,
        guidance: str,
        expected_room_revision: int,
        created_at: str,
        parent_run_id: str = "",
        root_run_id: str = "",
        input_message_id: str | None = None,
    ) -> TavernRunRecord:
        steps = [
            TavernSpeakerStepRecord(
                run_id=run_id,
                step_index=index,
                persona_id=participant.persona_id,
                participant_prompt_hash=participant.prompt_hash,
                reply_to_message_id=anchor_message_id if index == 0 else "",
            )
            for index, participant in enumerate(scheduled)
        ]
        return TavernRunRecord(
            id=run_id,
            room_id=room_id,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            context_digest=context_digest,
            mode=mode,
            trigger_kind=trigger_kind,
            parent_run_id=parent_run_id,
            root_run_id=root_run_id or run_id,
            input_message_id=input_message_id,
            anchor_message_id=anchor_message_id,
            scheduled_participant_ids=[item.persona_id for item in scheduled],
            speaker_steps=steps,
            guidance=guidance,
            expected_room_revision=expected_room_revision,
            created_at=created_at,
        )

    def _begin_run(
        self,
        *,
        run: TavernRunRecord,
        user_message: TavernMessageRecord | None,
    ) -> tuple[TavernRunRecord, bool]:
        try:
            persisted, _, created = self.repository.begin_run(
                run=run,
                user_message=user_message,
            )
        except (
            TavernRevisionConflict,
            TavernRunInProgress,
            TavernIdempotencyConflict,
            TavernRetryAlreadyCreated,
        ) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return (persisted if not created else run), created

    def _execute_run(
        self,
        *,
        run: TavernRunRecord,
        detail: TavernRoomDetail,
        input_content: str,
    ) -> TavernTurnResponse:
        persisted = self.repository.get_run(run.id)
        if persisted is None:
            raise HTTPException(status_code=404, detail="tavern_run_not_found")
        run = persisted
        participant_map = {item.persona_id: item for item in detail.participants}
        generated_messages: list[TavernMessageRecord] = []
        reply_anchor_id = run.anchor_message_id
        execution_owner = f"{self._worker_id}-{uuid4().hex[:12]}"
        for index, actor_id in enumerate(run.scheduled_participant_ids):
            persisted_step = run.speaker_steps[index]
            if persisted_step.status == TavernSpeakerStepStatus.COMPLETED:
                committed = self.repository.get_message(persisted_step.message_id)
                if committed is None:
                    raise HTTPException(
                        status_code=409,
                        detail="tavern_completed_step_message_missing",
                    )
                generated_messages.append(committed)
                reply_anchor_id = committed.id
                continue
            actor = participant_map[actor_id]
            recent_messages: list[TavernMessageRecord] = []
            step_claimed = False
            execution_stage = "step_claim"
            try:
                step = self.repository.claim_step(
                    run_id=run.id,
                    step_index=index,
                    lease_owner=execution_owner,
                    lease_seconds=self.step_lease_seconds,
                    max_claims=self.max_step_claims,
                    exhaustion_trace=self.actor_harness.build_lease_exhaustion_trace(
                        actor=actor,
                        policy=detail.room.harness_policy,
                        claim_count=self.max_step_claims,
                        max_claims=self.max_step_claims,
                    ),
                    reply_to_message_id=(reply_anchor_id if index > 0 else None),
                )
                step_claimed = True
                with _StepLeaseHeartbeat(
                    repository=self.repository,
                    run_id=run.id,
                    step_index=index,
                    lease_owner=execution_owner,
                    claim_count=step.claim_count,
                    lease_seconds=self.step_lease_seconds,
                ) as heartbeat:
                    execution_stage = "context_load"
                    recent_messages = self.repository.list_recent_messages(
                        run.room_id,
                        limit=detail.room.harness_policy.context_message_limit,
                        exclude_message_id=run.input_message_id or "",
                    )
                    anchor_message = self.repository.get_message(step.reply_to_message_id)
                    required_target_id = (
                        anchor_message.persona_id
                        if anchor_message is not None
                        and anchor_message.author_kind == TavernAuthorKind.PERSONA
                        and anchor_message.persona_id != actor.persona_id
                        else ""
                    )
                    execution_stage = "actor_generation"
                    generated = self._generate_actor_message(
                        run=run,
                        actor=actor,
                        detail=detail,
                        recent_messages=recent_messages,
                        input_content=input_content,
                        required_target_id=required_target_id,
                        should_continue=heartbeat.should_continue,
                    )
                    heartbeat.ensure_active()
                    execution_stage = "atomic_commit"
                    generated.commit_metadata = TavernPersonaMessageCommitMetadataV1(
                        operation_id=f"harness-operation-{uuid4().hex}",
                        effect_batch_id=f"effect-{generated.id}",
                    )
                    completed_run = self.repository.complete_step(
                        run_id=run.id,
                        step_index=index,
                        message=generated,
                        completed_at=_now(),
                        finalize_run=index == len(run.scheduled_participant_ids) - 1,
                        lease_owner=execution_owner,
                        claim_count=step.claim_count,
                    )
            except TavernActorExecutionError as exc:
                try:
                    failed_run = self.repository.fail_step(
                        run_id=run.id,
                        step_index=index,
                        error_code=exc.error_code,
                        completed_at=_now(),
                        harness_trace=exc.trace,
                        lease_owner=execution_owner,
                        claim_count=step.claim_count,
                    )
                except TavernStepClaimConflict as conflict:
                    raise self._step_conflict_response(run.id, conflict) from conflict
                if failed_run.status == TavernRunStatus.CANCELED:
                    raise HTTPException(
                        status_code=409,
                        detail=f"tavern_run_canceled:{run.id}",
                    ) from exc
                if failed_run.status not in {
                    TavernRunStatus.FAILED,
                    TavernRunStatus.PARTIAL,
                }:
                    raise HTTPException(
                        status_code=409,
                        detail=f"tavern_run_superseded:{run.id}:{failed_run.status.value}",
                    ) from exc
                raise HTTPException(
                    status_code=502,
                    detail=f"tavern_run_failed:{failed_run.id}:{failed_run.status.value}",
                ) from exc.cause
            except TavernStepClaimsExhausted as exc:
                return self._replay_run(exc.run)
            except TavernStepClaimConflict as exc:
                raise self._step_conflict_response(run.id, exc) from exc
            except TavernRunTerminalConflict as exc:
                if exc.status == TavernRunStatus.CANCELED.value:
                    raise HTTPException(
                        status_code=409,
                        detail=f"tavern_run_canceled:{run.id}",
                    ) from exc
                raise HTTPException(
                    status_code=409,
                    detail=f"tavern_run_superseded:{run.id}:{exc.status}",
                ) from exc
            except Exception as exc:
                if not step_claimed:
                    raise
                failure_trace = self.actor_harness.build_failure_trace(
                    stage=execution_stage,
                    error_code=_error_code(exc),
                    actor=actor,
                    participants=detail.participants,
                    recent_messages=recent_messages,
                    user_message=input_content,
                    guidance=run.guidance,
                    policy=detail.room.harness_policy,
                    recoveries=[],
                )
                try:
                    failed_run = self.repository.fail_step(
                        run_id=run.id,
                        step_index=index,
                        error_code=_error_code(exc),
                        completed_at=_now(),
                        harness_trace=failure_trace,
                        lease_owner=execution_owner,
                        claim_count=step.claim_count,
                    )
                except TavernStepClaimConflict as conflict:
                    raise self._step_conflict_response(run.id, conflict) from conflict
                if failed_run.status == TavernRunStatus.CANCELED:
                    raise HTTPException(
                        status_code=409,
                        detail=f"tavern_run_canceled:{run.id}",
                    ) from exc
                if failed_run.status not in {
                    TavernRunStatus.FAILED,
                    TavernRunStatus.PARTIAL,
                }:
                    raise HTTPException(
                        status_code=409,
                        detail=f"tavern_run_superseded:{run.id}:{failed_run.status.value}",
                    ) from exc
                raise
            generated_messages.append(generated)
            reply_anchor_id = generated.id
            run = completed_run

        return TavernTurnResponse(
            run=completed_run,
            input_message=(
                self.repository.get_message(run.input_message_id)
                if run.trigger_kind == TavernRunTriggerKind.USER_MESSAGE
                and run.input_message_id
                else None
            ),
            generated_messages=generated_messages,
            room_state=_to_room_state(self.require_room(run.room_id, limit=1).room),
        )

    def _generate_actor_message(
        self,
        *,
        run: TavernRunRecord,
        actor: TavernParticipantRecord,
        detail: TavernRoomDetail,
        recent_messages: list[TavernMessageRecord],
        input_content: str,
        required_target_id: str,
        should_continue: Callable[[], bool] | None = None,
    ) -> TavernMessageRecord:
        reset_model_recovery_state()
        generation_started_at = time.perf_counter()
        model_recoveries = []
        prompt_preflight = None
        try:
            prompt_preflight = preflight_tavern_actor_prompt(
                persona=actor.persona_snapshot,
                participants=detail.participants,
                scene_profile=detail.room.scene_profile,
                recent_messages=recent_messages,
                user_message=input_content,
                guidance=run.guidance,
                allowed_target_ids=[item.persona_id for item in detail.participants],
                actor_reply_schema=json.dumps(
                    TavernActorReply.transport_json_schema(),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                turn_kind=run.trigger_kind.value,
                required_target_id=required_target_id,
            )
            recent_messages = prompt_preflight.recent_messages
            raw_reply = self.model_provider.generate_tavern_actor_reply(
                persona=actor.persona_snapshot,
                participants=detail.participants,
                scene_profile=detail.room.scene_profile,
                recent_messages=recent_messages,
                user_message=input_content,
                guidance=run.guidance,
                allowed_target_ids=[item.persona_id for item in detail.participants],
                turn_kind=run.trigger_kind.value,
                required_target_id=required_target_id,
                should_continue=should_continue,
            )
            model_recoveries = consume_model_recovery_state()
            reply, trace = self.actor_harness.validate_and_repair(
                reply=raw_reply,
                actor=actor,
                participants=detail.participants,
                recent_messages=recent_messages,
                user_message=input_content,
                guidance=run.guidance,
                allowed_target_ids=[item.persona_id for item in detail.participants],
                required_target_id=required_target_id,
                policy=detail.room.harness_policy,
            )
            trace = self.actor_harness.merge_model_recoveries(trace, model_recoveries)
            trace = self.actor_harness.merge_prompt_budget_report(
                trace,
                prompt_preflight.report,
            )
            trace.duration_ms = max(
                trace.duration_ms,
                int((time.perf_counter() - generation_started_at) * 1000),
            )
        except TavernHarnessViolation as exc:
            trace = self.actor_harness.merge_model_recoveries(
                exc.trace,
                [*model_recoveries, *consume_model_recovery_state()],
            )
            if prompt_preflight is not None:
                trace = self.actor_harness.merge_prompt_budget_report(
                    trace,
                    prompt_preflight.report,
                )
            trace.duration_ms = max(
                trace.duration_ms,
                int((time.perf_counter() - generation_started_at) * 1000),
            )
            raise TavernActorExecutionError(str(exc), trace, exc) from exc
        except Exception as exc:
            trace = self.actor_harness.build_failure_trace(
                stage=(
                    "prompt_preflight"
                    if isinstance(exc, TavernPromptBudgetError)
                    else "actor_decode"
                    if str(exc) == "tavern_actor_invalid_payload"
                    else "actor_generation"
                ),
                error_code=_error_code(exc),
                actor=actor,
                participants=detail.participants,
                recent_messages=recent_messages,
                user_message=input_content,
                guidance=run.guidance,
                policy=detail.room.harness_policy,
                recoveries=consume_model_recovery_state(),
                duration_ms=int((time.perf_counter() - generation_started_at) * 1000),
            )
            if prompt_preflight is not None:
                trace = self.actor_harness.merge_prompt_budget_report(
                    trace,
                    prompt_preflight.report,
                )
            if isinstance(exc, TavernPromptBudgetError):
                trace = self.actor_harness.merge_prompt_budget_failure(trace, exc)
            raise TavernActorExecutionError(_error_code(exc), trace, exc) from exc
        return TavernMessageRecord(
            id=f"tavern-message-{uuid4().hex[:12]}",
            room_id=run.room_id,
            sequence=1,
            run_id=run.id,
            author_kind=TavernAuthorKind.PERSONA,
            persona_id=actor.persona_id,
            persona_name=actor.display_name,
            content=reply.text,
            emotion=reply.mood,
            action=reply.action,
            speech_style=reply.speech_style,
            addressed_participant_ids=reply.addressed_participant_ids,
            client_request_id=run.idempotency_key,
            created_at=_now(),
            harness_trace=trace,
        )

    def _replay_run(self, run: TavernRunRecord) -> TavernTurnResponse:
        if run.status == TavernRunStatus.PENDING:
            raise HTTPException(status_code=409, detail=f"tavern_run_in_progress:{run.id}")
        return TavernTurnResponse(
            run=run,
            input_message=(
                self.repository.get_message(run.input_message_id)
                if run.trigger_kind == TavernRunTriggerKind.USER_MESSAGE
                and run.input_message_id
                else None
            ),
            generated_messages=self.repository.list_run_messages(run.id),
            room_state=_to_room_state(self.require_room(run.room_id, limit=1).room),
        )

    def _resume_or_replay_run(self, run: TavernRunRecord) -> TavernTurnResponse:
        if run.status != TavernRunStatus.PENDING:
            return self._replay_run(run)
        detail = self.require_room(run.room_id)
        if detail.room.status != TavernRoomStatus.ACTIVE:
            raise HTTPException(status_code=409, detail="tavern_room_not_active")
        if (
            detail.room.revision != run.expected_room_revision + 1
            or (
                run.context_digest
                and run.context_digest != _room_context_digest(detail)
            )
        ):
            raise HTTPException(status_code=409, detail="tavern_run_context_changed")
        participant_map = {item.persona_id: item for item in detail.participants}
        if any(
            step.persona_id not in participant_map
            or participant_map[step.persona_id].prompt_hash
            != step.participant_prompt_hash
            for step in run.speaker_steps
        ):
            raise HTTPException(status_code=409, detail="tavern_run_participant_changed")
        root = self.repository.get_run(run.root_run_id or run.id)
        if root is None:
            raise HTTPException(status_code=409, detail="tavern_retry_root_missing")
        input_content = ""
        if root.input_message_id:
            input_message = self.repository.get_message(root.input_message_id)
            if input_message is None:
                raise HTTPException(status_code=409, detail="tavern_run_input_message_missing")
            input_content = input_message.content
        try:
            return self._execute_run(
                run=run,
                detail=detail,
                input_content=input_content,
            )
        except TavernStepClaimConflict as exc:
            raise HTTPException(
                status_code=409,
                detail=f"tavern_run_in_progress:{run.id}",
            ) from exc

    def cancel_run(self, *, room_id: str, run_id: str) -> TavernTurnResponse:
        self.require_room(room_id, limit=1)
        try:
            run, changed = self.repository.cancel_run(
                room_id=room_id,
                run_id=run_id,
                canceled_at=_now(),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="tavern_run_not_found") from exc
        if not changed and run.status != TavernRunStatus.CANCELED:
            raise HTTPException(
                status_code=409,
                detail=f"tavern_run_not_cancelable:{run.status.value}",
            )
        return self._replay_run(run)

    def _step_conflict_response(
        self,
        run_id: str,
        conflict: TavernStepClaimConflict,
    ) -> HTTPException:
        current = self.repository.get_run(run_id)
        if current is not None and current.status == TavernRunStatus.CANCELED:
            detail = f"tavern_run_canceled:{run_id}"
        elif current is not None and current.status != TavernRunStatus.PENDING:
            detail = f"tavern_run_superseded:{run_id}:{current.status.value}"
        else:
            detail = f"tavern_run_in_progress:{run_id}"
        return HTTPException(status_code=409, detail=detail)

    def resume_run(self, *, room_id: str, run_id: str) -> TavernTurnResponse:
        run = self.repository.get_run(run_id)
        if run is None or run.room_id != room_id:
            raise HTTPException(status_code=404, detail="tavern_run_not_found")
        return self._resume_or_replay_run(run)

    def _build_participants(
        self,
        *,
        room_id: str,
        persona_ids: list[str],
        existing: dict[str, TavernParticipantRecord],
        joined_at: str,
    ) -> list[TavernParticipantRecord]:
        participants: list[TavernParticipantRecord] = []
        for index, persona_id in enumerate(persona_ids):
            current = existing.get(persona_id)
            if current is not None:
                current.display_order = index
                participants.append(current)
                continue
            persona = self.persona_engine.require_persona(persona_id)
            participants.append(
                TavernParticipantRecord(
                    room_id=room_id,
                    persona_id=persona.id,
                    display_order=index,
                    display_name=persona.name,
                    persona_snapshot=persona.model_copy(deep=True),
                    prompt_hash=persona_prompt_hash(persona.model_dump(mode="json")),
                    joined_at=joined_at,
                )
            )
        return participants

    def _room_lock(self, room_id: str) -> RLock:
        with self._locks_guard:
            return self._room_locks[room_id]


class _StepLeaseHeartbeat:
    """Renew a claimed step while synchronous provider work is in flight."""

    def __init__(
        self,
        *,
        repository: TavernRepository,
        run_id: str,
        step_index: int,
        lease_owner: str,
        claim_count: int,
        lease_seconds: float,
    ) -> None:
        self.repository = repository
        self.run_id = run_id
        self.step_index = step_index
        self.lease_owner = lease_owner
        self.claim_count = claim_count
        self.lease_seconds = lease_seconds
        self.interval_seconds = max(0.25, lease_seconds / 3)
        self._stop = Event()
        self._lost = Event()
        self._thread: Thread | None = None

    def __enter__(self) -> _StepLeaseHeartbeat:
        self._thread = Thread(
            target=self._run,
            name=f"tavern-lease-{self.run_id[-8:]}-{self.step_index}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval_seconds + 0.25))

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                renewed = self.repository.renew_step_lease(
                    run_id=self.run_id,
                    step_index=self.step_index,
                    lease_owner=self.lease_owner,
                    claim_count=self.claim_count,
                    lease_seconds=self.lease_seconds,
                )
            except Exception:
                self._lost.set()
                return
            if renewed is None:
                self._lost.set()
                return

    def should_continue(self) -> bool:
        if self._lost.is_set() or self._stop.is_set():
            return False
        try:
            return self.repository.has_active_step_lease(
                run_id=self.run_id,
                step_index=self.step_index,
                lease_owner=self.lease_owner,
                claim_count=self.claim_count,
            )
        except Exception:
            self._lost.set()
            return False

    def ensure_active(self) -> None:
        if not self.should_continue():
            raise TavernStepClaimConflict(self.step_index, "lease_lost")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _error_code(exc: Exception) -> str:
    code = str(exc).strip() or exc.__class__.__name__
    return code[:128]


def _room_context_digest(detail: TavernRoomDetail) -> str:
    return tavern_payload_digest(
        {
            "title": detail.room.title,
            "scene_profile": (
                detail.room.scene_profile.model_dump(mode="json")
                if detail.room.scene_profile
                else None
            ),
            "harness_policy": detail.room.harness_policy.model_dump(mode="json"),
            "participants": [
                {
                    "persona_id": item.persona_id,
                    "display_order": item.display_order,
                    "prompt_hash": item.prompt_hash,
                }
                for item in detail.participants
            ],
        }
    )


def _to_room_state(room: TavernRoomRecord) -> TavernRoomState:
    return TavernRoomState(
        id=room.id,
        status=room.status,
        revision=room.revision,
        last_sequence=room.last_sequence,
        updated_at=room.updated_at,
    )


class TavernActorExecutionError(RuntimeError):
    def __init__(
        self,
        error_code: str,
        trace: HarnessTraceRecord,
        cause: Exception,
    ) -> None:
        super().__init__(error_code)
        self.error_code = error_code
        self.trace = trace
        self.cause = cause
