from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from threading import RLock
import time
from uuid import uuid4

from fastapi import HTTPException

from app.models.harness import HarnessTraceRecord
from app.models.tavern import (
    CreateTavernRoomRequest,
    TavernAuthorKind,
    TavernInteractionMode,
    TavernContinueInput,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomDetail,
    TavernRoomRecord,
    TavernRoomState,
    TavernRoomStatus,
    TavernRoomSummary,
    TavernRunRecord,
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
from app.persistence.tavern_repository import (
    TavernIdempotencyConflict,
    TavernRepository,
    TavernRetryAlreadyCreated,
    TavernRevisionConflict,
    TavernRunInProgress,
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


class TavernService:
    def __init__(
        self,
        *,
        repository: TavernRepository,
        persona_engine: PersonaEngine,
        model_provider: ModelProvider,
    ) -> None:
        self.repository = repository
        self.persona_engine = persona_engine
        self.model_provider = model_provider
        self.actor_harness = TavernActorHarness()
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

    def list_rooms(self) -> list[TavernRoomSummary]:
        return self.repository.list_rooms()

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
            return self._replay_run(duplicate)

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
            return self._replay_run(duplicate)

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
        participant_map = {item.persona_id: item for item in detail.participants}
        generated_messages: list[TavernMessageRecord] = []
        reply_anchor_id = run.anchor_message_id
        for index, actor_id in enumerate(run.scheduled_participant_ids):
            actor = participant_map[actor_id]
            recent_messages: list[TavernMessageRecord] = []
            step_claimed = False
            execution_stage = "step_claim"
            try:
                if index > 0:
                    self.repository.set_step_reply_anchor(
                        run_id=run.id,
                        step_index=index,
                        reply_to_message_id=reply_anchor_id,
                    )
                step = self.repository.claim_step(
                    run_id=run.id,
                    step_index=index,
                    started_at=_now(),
                )
                step_claimed = True
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
                )
                execution_stage = "atomic_commit"
                completed_run = self.repository.complete_step(
                    run_id=run.id,
                    step_index=index,
                    message=generated,
                    completed_at=_now(),
                    finalize_run=index == len(run.scheduled_participant_ids) - 1,
                )
            except TavernActorExecutionError as exc:
                failed_run = self.repository.fail_step(
                    run_id=run.id,
                    step_index=index,
                    error_code=exc.error_code,
                    completed_at=_now(),
                    harness_trace=exc.trace,
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"tavern_run_failed:{failed_run.id}:{failed_run.status.value}",
                ) from exc.cause
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
                self.repository.fail_step(
                    run_id=run.id,
                    step_index=index,
                    error_code=_error_code(exc),
                    completed_at=_now(),
                    harness_trace=failure_trace,
                )
                raise
            generated_messages.append(generated)
            reply_anchor_id = generated.id

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
    ) -> TavernMessageRecord:
        reset_model_recovery_state()
        generation_started_at = time.perf_counter()
        model_recoveries = []
        try:
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
            trace.duration_ms = max(
                trace.duration_ms,
                int((time.perf_counter() - generation_started_at) * 1000),
            )
        except TavernHarnessViolation as exc:
            trace = self.actor_harness.merge_model_recoveries(
                exc.trace,
                [*model_recoveries, *consume_model_recovery_state()],
            )
            trace.duration_ms = max(
                trace.duration_ms,
                int((time.perf_counter() - generation_started_at) * 1000),
            )
            raise TavernActorExecutionError(str(exc), trace, exc) from exc
        except Exception as exc:
            trace = self.actor_harness.build_failure_trace(
                stage=(
                    "actor_decode"
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
