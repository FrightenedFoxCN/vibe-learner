from __future__ import annotations
import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
from sqlalchemy import func, select
from app.models.harness import validate_harness_trace
from app.models.tavern import (
    TavernHarnessPolicy,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomRecord,
    TavernRoomStatus,
    TavernRunRecord,
    TavernSpeakerStepRecord,
    TavernSpeakerStepStatus,
)
from app.persistence.models import (
    TavernMessageRow,
    TavernParticipantRow,
    TavernRoomRow,
    TavernRunRow,
    TavernRunStepRow,
)
from app.core.coerce import text_at, text_or_empty
from app.persistence.row_mapping import harness_traces, payload_of


_TAVERN_ROOM_CURSOR_VERSION = 1
_TAVERN_ROOM_CURSOR_KEY = b"vibe-learner:tavern-room-list-v1:cursor"
from app.persistence.tavern_errors import (
    TavernIdempotencyConflict,
    TavernRoomCursorInvalid,
)


def _room_to_row(room: TavernRoomRecord) -> TavernRoomRow:
    return TavernRoomRow(
        id=room.id,
        creation_key=room.creation_key or None,
        creation_input_digest=room.creation_input_digest,
        title=room.title,
        status=room.status.value,
        scene_profile=(
            room.scene_profile.model_dump(mode="json") if room.scene_profile else None
        ),
        harness_policy=room.harness_policy.model_dump(mode="json"),
        revision=room.revision,
        last_sequence=room.last_sequence,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


def _room_from_row(row: TavernRoomRow) -> TavernRoomRecord:
    return TavernRoomRecord(
        id=row.id,
        creation_key=text_or_empty(row.creation_key),
        creation_input_digest=text_or_empty(row.creation_input_digest),
        title=row.title,
        scene_profile=row.scene_profile,
        harness_policy=TavernHarnessPolicy.model_validate(row.harness_policy or {}),
        status=TavernRoomStatus(row.status),
        revision=row.revision,
        last_sequence=row.last_sequence,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _participant_to_row(item: TavernParticipantRecord) -> TavernParticipantRow:
    return TavernParticipantRow(
        room_id=item.room_id,
        persona_id=item.persona_id,
        display_order=item.display_order,
        display_name=item.display_name,
        persona_snapshot=item.persona_snapshot.model_dump(mode="json"),
        prompt_hash=item.prompt_hash,
        joined_at=item.joined_at,
    )


def _participant_from_row(row: TavernParticipantRow) -> TavernParticipantRecord:
    return TavernParticipantRecord(
        room_id=row.room_id,
        persona_id=row.persona_id,
        display_order=row.display_order,
        display_name=row.display_name,
        persona_snapshot=row.persona_snapshot,
        prompt_hash=row.prompt_hash,
        joined_at=row.joined_at,
    )


def _message_to_row(item: TavernMessageRecord) -> TavernMessageRow:
    return TavernMessageRow(
        id=item.id,
        room_id=item.room_id,
        sequence=item.sequence,
        run_id=item.run_id,
        author_kind=item.author_kind.value,
        persona_id=item.persona_id,
        client_request_id=item.client_request_id,
        content=item.content,
        created_at=item.created_at,
        payload={
            "persona_name": item.persona_name,
            "emotion": item.emotion,
            "action": item.action,
            "speech_style": item.speech_style,
            "addressed_participant_ids": item.addressed_participant_ids,
            "reply_to_message_id": item.reply_to_message_id,
            "harness_trace": (
                item.harness_trace.model_dump(mode="json")
                if item.harness_trace
                else None
            ),
            "commit_metadata": (
                item.commit_metadata.model_dump(mode="json")
                if item.commit_metadata
                else None
            ),
        },
    )


def _message_from_row(row: TavernMessageRow) -> TavernMessageRecord:
    payload = payload_of(row)
    harness_payload = payload.get("harness_trace")
    commit_metadata_payload = payload.get("commit_metadata")
    return TavernMessageRecord(
        id=row.id,
        room_id=row.room_id,
        sequence=row.sequence,
        run_id=row.run_id,
        author_kind=row.author_kind,
        persona_id=row.persona_id,
        persona_name=text_at(payload, "persona_name"),
        content=row.content,
        emotion=str(payload.get("emotion") or "calm"),
        action=text_at(payload, "action"),
        speech_style=text_at(payload, "speech_style"),
        addressed_participant_ids=[
            str(item) for item in (payload.get("addressed_participant_ids") or [])
        ],
        reply_to_message_id=text_at(payload, "reply_to_message_id"),
        client_request_id=row.client_request_id,
        created_at=row.created_at,
        harness_trace=(
            validate_harness_trace(harness_payload) if harness_payload else None
        ),
        commit_metadata=commit_metadata_payload,
    )


def _run_from_row(
    row: TavernRunRow,
    step_rows: list[TavernRunStepRow] | None = None,
) -> TavernRunRecord:
    payload = payload_of(row)
    speaker_steps = [_step_from_row(item) for item in (step_rows or [])]
    generated_message_ids = [
        item.message_id
        for item in speaker_steps
        if item.status == TavernSpeakerStepStatus.COMPLETED and item.message_id
    ]
    harness_trace = [
        item.harness_trace for item in speaker_steps if item.harness_trace is not None
    ]
    return TavernRunRecord(
        id=row.id,
        room_id=row.room_id,
        idempotency_key=row.idempotency_key,
        request_digest=text_at(payload, "request_digest"),
        context_digest=text_at(payload, "context_digest"),
        execution_config_binding=text_at(payload, "execution_config_binding"),
        mode=row.mode,
        trigger_kind=str(payload.get("trigger_kind") or "user_message"),
        parent_run_id=text_or_empty(row.parent_run_id),
        root_run_id=str(payload.get("root_run_id") or row.id),
        input_message_id=row.input_message_id or None,
        anchor_message_id=str(
            text_or_empty(payload.get("anchor_message_id") or row.input_message_id)
        ),
        scheduled_participant_ids=[
            str(item)
            for item in (
                payload.get("scheduled_participant_ids")
                or payload.get("requested_participant_ids")
                or []
            )
        ],
        speaker_steps=speaker_steps,
        guidance=text_at(payload, "guidance"),
        status=row.status,
        expected_room_revision=row.expected_room_revision,
        generated_message_ids=(
            generated_message_ids
            if speaker_steps
            else [str(item) for item in (payload.get("generated_message_ids") or [])]
        ),
        harness_trace=(harness_trace if speaker_steps else harness_traces(payload)),
        error_code=row.error_code,
        terminal_sequence=int(payload.get("terminal_sequence") or 0),
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _run_to_row(run: TavernRunRecord) -> TavernRunRow:
    row = TavernRunRow(id=run.id, room_id=run.room_id)
    _apply_run_to_row(row, run)
    return row


def _apply_run_to_row(row: TavernRunRow, run: TavernRunRecord) -> None:
    row.idempotency_key = run.idempotency_key
    row.parent_run_id = run.parent_run_id or None
    row.status = run.status.value
    row.mode = run.mode.value
    row.input_message_id = text_or_empty(run.input_message_id)
    row.expected_room_revision = run.expected_room_revision
    row.error_code = run.error_code
    row.created_at = run.created_at
    row.completed_at = run.completed_at
    row.payload = {
        "request_digest": run.request_digest,
        "context_digest": run.context_digest,
        "execution_config_binding": run.execution_config_binding,
        "trigger_kind": run.trigger_kind.value,
        "root_run_id": run.root_run_id or run.id,
        "anchor_message_id": run.anchor_message_id,
        "scheduled_participant_ids": run.scheduled_participant_ids,
        "guidance": run.guidance,
        "generated_message_ids": run.generated_message_ids,
        "harness_trace": [item.model_dump(mode="json") for item in run.harness_trace],
        "terminal_sequence": run.terminal_sequence,
    }


def _step_to_row(step: TavernSpeakerStepRecord) -> TavernRunStepRow:
    return TavernRunStepRow(
        run_id=step.run_id,
        step_index=step.step_index,
        persona_id=step.persona_id,
        participant_prompt_hash=step.participant_prompt_hash,
        status=step.status.value,
        message_id=step.message_id or None,
        reply_to_message_id=step.reply_to_message_id,
        error_code=step.error_code,
        started_at=step.started_at,
        completed_at=step.completed_at,
        claim_count=step.claim_count,
        payload={
            "harness_trace": (
                step.harness_trace.model_dump(mode="json")
                if step.harness_trace
                else None
            )
        },
    )


def _step_from_row(row: TavernRunStepRow) -> TavernSpeakerStepRecord:
    payload = payload_of(row)
    trace_payload = payload.get("harness_trace")
    return TavernSpeakerStepRecord(
        run_id=row.run_id,
        step_index=row.step_index,
        persona_id=row.persona_id,
        participant_prompt_hash=row.participant_prompt_hash,
        status=row.status,
        message_id=text_or_empty(row.message_id),
        reply_to_message_id=row.reply_to_message_id,
        error_code=row.error_code,
        harness_trace=(
            validate_harness_trace(trace_payload) if trace_payload else None
        ),
        claim_count=row.claim_count,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _assert_creation_replay_matches(
    existing: TavernRoomRecord,
    requested: TavernRoomRecord,
) -> None:
    if (
        existing.creation_input_digest
        and requested.creation_input_digest
        and existing.creation_input_digest != requested.creation_input_digest
    ):
        raise TavernIdempotencyConflict("room_creation")


def _validate_new_run_schedule(run: TavernRunRecord) -> None:
    scheduled_ids = run.scheduled_participant_ids
    steps = run.speaker_steps
    if not scheduled_ids or len(scheduled_ids) > 4:
        raise ValueError("tavern_run_schedule_size_invalid")
    if len(scheduled_ids) != len(steps):
        raise ValueError("tavern_run_schedule_step_count_mismatch")
    if len(scheduled_ids) != len(set(scheduled_ids)):
        raise ValueError("tavern_run_schedule_personas_not_distinct")
    if [step.persona_id for step in steps] != scheduled_ids:
        raise ValueError("tavern_run_schedule_persona_order_mismatch")
    if any(
        step.run_id != run.id
        or step.step_index != index
        or step.status != TavernSpeakerStepStatus.PENDING
        for index, step in enumerate(steps)
    ):
        raise ValueError("tavern_run_schedule_step_identity_invalid")


def _encode_room_cursor(updated_at: str, room_id: str) -> str:
    payload = json.dumps(
        {
            "v": _TAVERN_ROOM_CURSOR_VERSION,
            "updated_at": updated_at,
            "id": room_id,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=")
    signature = hmac.new(
        _TAVERN_ROOM_CURSOR_KEY,
        encoded_payload,
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded_payload.decode('ascii')}.{signature}"


def _decode_room_cursor(cursor: str) -> tuple[str, str]:
    if not cursor or len(cursor) > 512 or cursor.count(".") != 1:
        raise TavernRoomCursorInvalid("tavern_room_cursor_malformed")
    encoded_payload_text, signature = cursor.split(".", 1)
    try:
        encoded_payload = encoded_payload_text.encode("ascii")
        supplied_signature = bytes.fromhex(signature)
    except (UnicodeEncodeError, ValueError) as exc:
        raise TavernRoomCursorInvalid("tavern_room_cursor_malformed") from exc
    expected_signature = hmac.new(
        _TAVERN_ROOM_CURSOR_KEY,
        encoded_payload,
        hashlib.sha256,
    ).digest()
    if len(supplied_signature) != len(expected_signature) or not hmac.compare_digest(
        supplied_signature,
        expected_signature,
    ):
        raise TavernRoomCursorInvalid("tavern_room_cursor_tampered")
    try:
        padding = b"=" * (-len(encoded_payload) % 4)
        raw_payload = base64.b64decode(
            encoded_payload + padding,
            altchars=b"-_",
            validate=True,
        )
        payload = json.loads(raw_payload.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise TavernRoomCursorInvalid("tavern_room_cursor_malformed") from exc
    if not isinstance(payload, dict) or set(payload) != {"v", "updated_at", "id"}:
        raise TavernRoomCursorInvalid("tavern_room_cursor_malformed")
    if payload["v"] != _TAVERN_ROOM_CURSOR_VERSION:
        raise TavernRoomCursorInvalid("tavern_room_cursor_version_unknown")
    updated_at = payload["updated_at"]
    room_id = payload["id"]
    if (
        not isinstance(updated_at, str)
        or not updated_at
        or len(updated_at) > 64
        or not isinstance(room_id, str)
        or not room_id
        or len(room_id) > 64
    ):
        raise TavernRoomCursorInvalid("tavern_room_cursor_malformed")
    return updated_at, room_id


def _assert_run_replay_matches(
    existing: TavernRunRecord,
    requested: TavernRunRecord,
) -> None:
    if (
        existing.request_digest
        and requested.request_digest
        and existing.request_digest != requested.request_digest
    ):
        raise TavernIdempotencyConflict("turn")


def _database_utc_now(session) -> datetime:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        value = session.scalar(select(func.strftime("%Y-%m-%dT%H:%M:%f", "now")))
    elif session.bind is not None and session.bind.dialect.name == "postgresql":
        value = session.scalar(select(func.clock_timestamp()))
    else:
        value = session.scalar(select(func.current_timestamp()))
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise RuntimeError("tavern_database_clock_unavailable")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical_utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
