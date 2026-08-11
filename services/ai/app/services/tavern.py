from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from threading import RLock
import time
from uuid import uuid4

from fastapi import HTTPException

from app.models.tavern import (
    CreateTavernRoomRequest,
    TavernAuthorKind,
    TavernInteractionMode,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomDetail,
    TavernRoomRecord,
    TavernRoomStatus,
    TavernRoomSummary,
    TavernRunRecord,
    TavernRunStatus,
    TavernTurnRequest,
    TavernTurnResponse,
    UpdateTavernRoomRequest,
)
from app.persistence.tavern_repository import (
    TavernIdempotencyConflict,
    TavernRepository,
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
        limit: int = 200,
    ) -> TavernRoomDetail:
        room = self.repository.get_room(
            room_id,
            after_sequence=after_sequence,
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
        if payload.mode != TavernInteractionMode.DIRECT:
            raise HTTPException(status_code=501, detail="tavern_facilitated_mode_not_available")
        with self._room_lock(room_id):
            request_digest = tavern_payload_digest(
                payload.model_dump(mode="json", exclude={"idempotency_key"})
            )
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
            if len(payload.target_persona_ids) != 1:
                raise HTTPException(status_code=422, detail="tavern_direct_target_required")
            actor_id = payload.target_persona_ids[0]
            actor = participant_map.get(actor_id)
            if actor is None:
                raise HTTPException(status_code=422, detail="tavern_target_not_in_room")

            now = _now()
            run = TavernRunRecord(
                id=f"tavern-run-{uuid4().hex[:12]}",
                room_id=room_id,
                idempotency_key=payload.idempotency_key,
                request_digest=request_digest,
                mode=payload.mode,
                requested_participant_ids=payload.target_persona_ids,
                max_character_messages=1,
                guidance=payload.guidance.strip(),
                expected_room_revision=payload.expected_room_revision,
                created_at=now,
            )
            user_message = TavernMessageRecord(
                id=f"tavern-message-{uuid4().hex[:12]}",
                room_id=room_id,
                sequence=1,
                run_id=run.id,
                author_kind=TavernAuthorKind.USER,
                content=payload.message.strip(),
                addressed_participant_ids=[actor_id],
                client_request_id=payload.idempotency_key,
                created_at=now,
            )
            try:
                run, _, created = self.repository.begin_run(
                    run=run,
                    user_message=user_message,
                )
            except TavernRevisionConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except TavernRunInProgress as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except TavernIdempotencyConflict as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            if not created:
                return self._replay_run(run)

            recent_messages = self.repository.list_recent_messages(
                room_id,
                limit=detail.room.harness_policy.context_message_limit,
                exclude_message_id=run.input_message_id,
            )
            trace = None
            model_recoveries = []
            reset_model_recovery_state()
            generation_started_at = time.perf_counter()
            try:
                raw_reply = self.model_provider.generate_tavern_actor_reply(
                    persona=actor.persona_snapshot,
                    participants=detail.participants,
                    scene_profile=detail.room.scene_profile,
                    recent_messages=recent_messages,
                    user_message=payload.message,
                    guidance=payload.guidance,
                    allowed_target_ids=list(participant_map),
                )
                model_recoveries = consume_model_recovery_state()
                reply, trace = self.actor_harness.validate_and_repair(
                    reply=raw_reply,
                    actor=actor,
                    participants=detail.participants,
                    recent_messages=recent_messages,
                    user_message=payload.message,
                    guidance=payload.guidance,
                    allowed_target_ids=list(participant_map),
                    policy=detail.room.harness_policy,
                )
                trace = self.actor_harness.merge_model_recoveries(trace, model_recoveries)
                trace.duration_ms = max(
                    trace.duration_ms,
                    int((time.perf_counter() - generation_started_at) * 1000),
                )
                generated = TavernMessageRecord(
                    id=f"tavern-message-{uuid4().hex[:12]}",
                    room_id=room_id,
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
                    client_request_id=payload.idempotency_key,
                    created_at=_now(),
                    harness_trace=trace,
                )
                completed_run = self.repository.complete_run(
                    run_id=run.id,
                    generated_messages=[generated],
                    completed_at=_now(),
                )
            except TavernHarnessViolation as exc:
                failed_trace = self.actor_harness.merge_model_recoveries(
                    exc.trace,
                    [*model_recoveries, *consume_model_recovery_state()],
                )
                failed_trace.duration_ms = max(
                    failed_trace.duration_ms,
                    int((time.perf_counter() - generation_started_at) * 1000),
                )
                self.repository.fail_run(
                    run_id=run.id,
                    error_code=str(exc),
                    completed_at=_now(),
                    harness_trace=[failed_trace],
                )
                raise HTTPException(status_code=502, detail="tavern_actor_validation_failed") from exc
            except Exception as exc:
                recoveries = consume_model_recovery_state()
                failure_traces = []
                if trace is not None:
                    failure_traces.append(trace)
                failure_traces.append(
                    self.actor_harness.build_failure_trace(
                        stage=(
                            "atomic_commit"
                            if trace is not None
                            else "actor_decode"
                            if str(exc) == "tavern_actor_invalid_payload"
                            else "actor_generation"
                        ),
                        error_code=_error_code(exc),
                        actor=actor,
                        participants=detail.participants,
                        recent_messages=recent_messages,
                        user_message=payload.message,
                        guidance=payload.guidance,
                        policy=detail.room.harness_policy,
                        recoveries=recoveries,
                        duration_ms=int(
                            (time.perf_counter() - generation_started_at) * 1000
                        ),
                    )
                )
                self.repository.fail_run(
                    run_id=run.id,
                    error_code=_error_code(exc),
                    completed_at=_now(),
                    harness_trace=failure_traces,
                )
                raise

            return TavernTurnResponse(
                run=completed_run,
                generated_messages=[generated],
                room=self.require_room(room_id),
            )

    def _replay_run(self, run: TavernRunRecord) -> TavernTurnResponse:
        if run.status == TavernRunStatus.PENDING:
            raise HTTPException(status_code=409, detail=f"tavern_run_in_progress:{run.id}")
        if run.status != TavernRunStatus.COMPLETED:
            raise HTTPException(
                status_code=409,
                detail=f"tavern_run_not_replayable:{run.status.value}:{run.error_code}",
            )
        return TavernTurnResponse(
            run=run,
            generated_messages=self.repository.list_run_messages(run.id),
            room=self.require_room(run.room_id),
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
