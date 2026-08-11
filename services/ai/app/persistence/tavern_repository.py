from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, func, select

from app.models.harness import HarnessTraceRecord
from app.models.tavern import (
    TavernHarnessPolicy,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomDetail,
    TavernRoomRecord,
    TavernRoomStatus,
    TavernRoomSummary,
    TavernRunRecord,
)
from app.persistence.database import Database
from app.persistence.models import (
    TavernMessageRow,
    TavernParticipantRow,
    TavernRoomRow,
    TavernRunRow,
)


class TavernRepository:
    """Normalized persistence boundary for rooms, cast snapshots, messages, and runs."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create_room(
        self,
        *,
        room: TavernRoomRecord,
        participants: list[TavernParticipantRecord],
        messages: list[TavernMessageRecord] | None = None,
    ) -> TavernRoomDetail:
        initial_messages = messages or []
        with self.database.session() as session:
            session.add(_room_to_row(room))
            session.add_all(_participant_to_row(item) for item in participants)
            session.add_all(_message_to_row(item) for item in initial_messages)
        return self.require_room(room.id)

    def list_rooms(self) -> list[TavernRoomSummary]:
        with self.database.session() as session:
            room_rows = session.scalars(
                select(TavernRoomRow).order_by(
                    TavernRoomRow.updated_at.desc(),
                    TavernRoomRow.id.desc(),
                )
            ).all()
            if not room_rows:
                return []
            room_ids = [row.id for row in room_rows]
            participant_rows = session.scalars(
                select(TavernParticipantRow)
                .where(TavernParticipantRow.room_id.in_(room_ids))
                .order_by(TavernParticipantRow.room_id, TavernParticipantRow.display_order)
            ).all()
            counts = dict(
                session.execute(
                    select(TavernMessageRow.room_id, func.count(TavernMessageRow.id))
                    .where(TavernMessageRow.room_id.in_(room_ids))
                    .group_by(TavernMessageRow.room_id)
                ).all()
            )

        participants_by_room: defaultdict[str, list[TavernParticipantRow]] = defaultdict(list)
        for row in participant_rows:
            participants_by_room[row.room_id].append(row)
        return [
            TavernRoomSummary(
                id=row.id,
                title=row.title,
                participant_persona_ids=[item.persona_id for item in participants_by_room[row.id]],
                participant_names=[item.display_name for item in participants_by_room[row.id]],
                message_count=int(counts.get(row.id, 0)),
                revision=row.revision,
                status=TavernRoomStatus(row.status),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in room_rows
        ]

    def get_room(
        self,
        room_id: str,
        *,
        after_sequence: int = 0,
        limit: int = 200,
    ) -> TavernRoomDetail | None:
        bounded_limit = max(1, min(limit, 200))
        with self.database.session() as session:
            room_row = session.get(TavernRoomRow, room_id)
            if room_row is None:
                return None
            participant_rows = session.scalars(
                select(TavernParticipantRow)
                .where(TavernParticipantRow.room_id == room_id)
                .order_by(TavernParticipantRow.display_order)
            ).all()
            message_rows = session.scalars(
                select(TavernMessageRow)
                .where(
                    TavernMessageRow.room_id == room_id,
                    TavernMessageRow.sequence > max(0, after_sequence),
                )
                .order_by(TavernMessageRow.sequence)
                .limit(bounded_limit + 1)
            ).all()
            message_count = int(
                session.scalar(
                    select(func.count(TavernMessageRow.id)).where(
                        TavernMessageRow.room_id == room_id
                    )
                )
                or 0
            )

        has_more = len(message_rows) > bounded_limit
        selected_rows = message_rows[:bounded_limit]
        return TavernRoomDetail(
            room=_room_from_row(room_row),
            participants=[_participant_from_row(row) for row in participant_rows],
            messages=[_message_from_row(row) for row in selected_rows],
            message_count=message_count,
            next_after_sequence=(selected_rows[-1].sequence if has_more and selected_rows else None),
        )

    def require_room(self, room_id: str) -> TavernRoomDetail:
        room = self.get_room(room_id)
        if room is None:
            raise LookupError("tavern_room_not_found")
        return room

    def get_run_by_idempotency_key(
        self,
        *,
        room_id: str,
        idempotency_key: str,
    ) -> TavernRunRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(TavernRunRow).where(
                    TavernRunRow.room_id == room_id,
                    TavernRunRow.idempotency_key == idempotency_key,
                )
            )
            return _run_from_row(row) if row is not None else None

    def count_persona_references(self, persona_id: str) -> int:
        with self.database.session() as session:
            return int(
                session.scalar(
                    select(func.count(TavernParticipantRow.persona_id)).where(
                        TavernParticipantRow.persona_id == persona_id
                    )
                )
                or 0
            )

    def delete_room(self, room_id: str) -> bool:
        with self.database.session() as session:
            room = session.get(TavernRoomRow, room_id)
            if room is None:
                return False
            session.execute(delete(TavernMessageRow).where(TavernMessageRow.room_id == room_id))
            session.execute(delete(TavernRunRow).where(TavernRunRow.room_id == room_id))
            session.execute(
                delete(TavernParticipantRow).where(TavernParticipantRow.room_id == room_id)
            )
            session.delete(room)
        return True


def _room_to_row(room: TavernRoomRecord) -> TavernRoomRow:
    return TavernRoomRow(
        id=room.id,
        title=room.title,
        status=room.status.value,
        scene_profile=(room.scene_profile.model_dump(mode="json") if room.scene_profile else None),
        harness_policy=room.harness_policy.model_dump(mode="json"),
        revision=room.revision,
        last_sequence=room.last_sequence,
        created_at=room.created_at,
        updated_at=room.updated_at,
    )


def _room_from_row(row: TavernRoomRow) -> TavernRoomRecord:
    return TavernRoomRecord(
        id=row.id,
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
            "harness_trace": (
                item.harness_trace.model_dump(mode="json") if item.harness_trace else None
            ),
        },
    )


def _message_from_row(row: TavernMessageRow) -> TavernMessageRecord:
    payload = row.payload or {}
    harness_payload = payload.get("harness_trace")
    return TavernMessageRecord(
        id=row.id,
        room_id=row.room_id,
        sequence=row.sequence,
        run_id=row.run_id,
        author_kind=row.author_kind,
        persona_id=row.persona_id,
        persona_name=str(payload.get("persona_name") or ""),
        content=row.content,
        emotion=str(payload.get("emotion") or "calm"),
        action=str(payload.get("action") or ""),
        speech_style=str(payload.get("speech_style") or ""),
        addressed_participant_ids=[
            str(item) for item in (payload.get("addressed_participant_ids") or [])
        ],
        client_request_id=row.client_request_id,
        created_at=row.created_at,
        harness_trace=(
            HarnessTraceRecord.model_validate(harness_payload) if harness_payload else None
        ),
    )


def _run_from_row(row: TavernRunRow) -> TavernRunRecord:
    payload = row.payload or {}
    return TavernRunRecord(
        id=row.id,
        room_id=row.room_id,
        idempotency_key=row.idempotency_key,
        mode=row.mode,
        input_message_id=row.input_message_id,
        requested_participant_ids=[
            str(item) for item in (payload.get("requested_participant_ids") or [])
        ],
        max_character_messages=int(payload.get("max_character_messages") or 1),
        guidance=str(payload.get("guidance") or ""),
        status=row.status,
        expected_room_revision=row.expected_room_revision,
        generated_message_ids=[
            str(item) for item in (payload.get("generated_message_ids") or [])
        ],
        harness_trace=[
            HarnessTraceRecord.model_validate(item)
            for item in (payload.get("harness_trace") or [])
        ],
        error_code=row.error_code,
        created_at=row.created_at,
        completed_at=row.completed_at,
    )
