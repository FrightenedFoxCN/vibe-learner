from __future__ import annotations
from collections import defaultdict
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from app.models.tavern import (
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomDetail,
    TavernRoomListResponse,
    TavernRoomRecord,
    TavernRoomStatus,
    TavernRoomSummary,
    TavernRunStatus,
)
from app.persistence.models import (
    TavernMessageRow,
    TavernParticipantRow,
    TavernRoomRow,
    TavernRunRow,
    TavernRunStepRow,
)

from app.persistence.tavern_errors import (
    TavernParticipantHistoryConflict,
    TavernRevisionConflict,
    TavernRoomCursorInvalid,
    TavernRunInProgress,
)
from app.persistence.tavern_rows import (
    _assert_creation_replay_matches,
    _decode_room_cursor,
    _encode_room_cursor,
    _message_from_row,
    _message_to_row,
    _participant_from_row,
    _participant_to_row,
    _room_from_row,
    _room_to_row,
)


class TavernRoomOps:
    def create_room(
        self,
        *,
        room: TavernRoomRecord,
        participants: list[TavernParticipantRecord],
        messages: list[TavernMessageRecord] | None = None,
    ) -> TavernRoomDetail:
        initial_messages = messages or []
        try:
            with self.database.session() as session:
                if room.creation_key:
                    existing_id = session.scalar(
                        select(TavernRoomRow.id).where(
                            TavernRoomRow.creation_key == room.creation_key
                        )
                    )
                    if existing_id:
                        existing = self.require_room(existing_id)
                        _assert_creation_replay_matches(existing.room, room)
                        return existing
                session.add(_room_to_row(room))
                session.flush()
                session.add_all(_participant_to_row(item) for item in participants)
                session.add_all(_message_to_row(item) for item in initial_messages)
        except IntegrityError:
            existing = self.get_room_by_creation_key(room.creation_key)
            if existing is not None:
                _assert_creation_replay_matches(existing.room, room)
                return existing
            raise
        return self.require_room(room.id)

    def get_room_by_creation_key(self, creation_key: str) -> TavernRoomDetail | None:
        normalized = creation_key.strip()
        if not normalized:
            return None
        with self.database.session() as session:
            room_id = session.scalar(
                select(TavernRoomRow.id).where(TavernRoomRow.creation_key == normalized)
            )
        return self.get_room(room_id) if room_id else None

    def list_rooms(
        self,
        *,
        limit: int = 30,
        cursor: str | None = None,
    ) -> TavernRoomListResponse:
        bounded_limit = max(1, min(limit, 50))
        cursor_boundary = _decode_room_cursor(cursor) if cursor else None
        with self.database.session() as session:
            if cursor_boundary is not None:
                cursor_updated_at, cursor_id = cursor_boundary
                cursor_room_id = session.scalar(
                    select(TavernRoomRow.id).where(
                        TavernRoomRow.updated_at == cursor_updated_at,
                        TavernRoomRow.id == cursor_id,
                    )
                )
                if cursor_room_id is None:
                    raise TavernRoomCursorInvalid("tavern_room_cursor_unknown")

            room_id_query = select(TavernRoomRow.id)
            if cursor_boundary is not None:
                cursor_updated_at, cursor_id = cursor_boundary
                room_id_query = room_id_query.where(
                    or_(
                        TavernRoomRow.updated_at < cursor_updated_at,
                        and_(
                            TavernRoomRow.updated_at == cursor_updated_at,
                            TavernRoomRow.id < cursor_id,
                        ),
                    )
                )
            fetched_room_ids = session.scalars(
                room_id_query.order_by(
                    TavernRoomRow.updated_at.desc(),
                    TavernRoomRow.id.desc(),
                ).limit(bounded_limit + 1)
            ).all()
            room_ids = fetched_room_ids[:bounded_limit]
            if not room_ids:
                return TavernRoomListResponse(items=[], next_cursor=None)

            room_participant_rows = session.execute(
                select(TavernRoomRow, TavernParticipantRow)
                .outerjoin(
                    TavernParticipantRow,
                    TavernParticipantRow.room_id == TavernRoomRow.id,
                )
                .where(TavernRoomRow.id.in_(room_ids))
                .order_by(TavernRoomRow.id, TavernParticipantRow.display_order)
            ).all()
            counts = dict(
                session.execute(
                    select(TavernMessageRow.room_id, func.count(TavernMessageRow.id))
                    .where(TavernMessageRow.room_id.in_(room_ids))
                    .group_by(TavernMessageRow.room_id)
                ).all()
            )

        room_rows_by_id: dict[str, TavernRoomRow] = {}
        participants_by_room: defaultdict[str, list[TavernParticipantRow]] = (
            defaultdict(list)
        )
        for room_row, participant_row in room_participant_rows:
            room_rows_by_id[room_row.id] = room_row
            if participant_row is not None:
                participants_by_room[room_row.id].append(participant_row)
        summaries = [
            TavernRoomSummary(
                id=row.id,
                title=row.title,
                participant_persona_ids=[
                    item.persona_id for item in participants_by_room[row.id]
                ],
                participant_names=[
                    item.display_name for item in participants_by_room[row.id]
                ],
                message_count=int(counts.get(row.id, 0)),
                revision=row.revision,
                status=TavernRoomStatus(row.status),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for room_id in room_ids
            for row in [room_rows_by_id[room_id]]
        ]
        next_cursor = None
        if len(fetched_room_ids) > bounded_limit:
            last_row = room_rows_by_id[room_ids[-1]]
            next_cursor = _encode_room_cursor(last_row.updated_at, last_row.id)
        return TavernRoomListResponse(items=summaries, next_cursor=next_cursor)

    def get_room(
        self,
        room_id: str,
        *,
        after_sequence: int = 0,
        before_sequence: int | None = None,
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
            if before_sequence is None:
                message_rows = session.scalars(
                    select(TavernMessageRow)
                    .where(
                        TavernMessageRow.room_id == room_id,
                        TavernMessageRow.sequence > max(0, after_sequence),
                    )
                    .order_by(TavernMessageRow.sequence)
                    .limit(bounded_limit + 1)
                ).all()
                selected_rows = message_rows[:bounded_limit]
                has_more = len(message_rows) > bounded_limit
                next_after_sequence = (
                    selected_rows[-1].sequence if has_more and selected_rows else None
                )
                next_before_sequence = None
            else:
                message_rows = session.scalars(
                    select(TavernMessageRow)
                    .where(
                        TavernMessageRow.room_id == room_id,
                        TavernMessageRow.sequence < max(1, before_sequence),
                    )
                    .order_by(TavernMessageRow.sequence.desc())
                    .limit(bounded_limit + 1)
                ).all()
                selected_desc = message_rows[:bounded_limit]
                selected_rows = list(reversed(selected_desc))
                has_more = len(message_rows) > bounded_limit
                next_after_sequence = None
                next_before_sequence = (
                    selected_rows[0].sequence if has_more and selected_rows else None
                )
            message_count = int(
                session.scalar(
                    select(func.count(TavernMessageRow.id)).where(
                        TavernMessageRow.room_id == room_id
                    )
                )
                or 0
            )

        return TavernRoomDetail(
            room=_room_from_row(room_row),
            participants=[_participant_from_row(row) for row in participant_rows],
            messages=[_message_from_row(row) for row in selected_rows],
            message_count=message_count,
            next_after_sequence=next_after_sequence,
            next_before_sequence=next_before_sequence,
        )

    def require_room(self, room_id: str) -> TavernRoomDetail:
        room = self.get_room(room_id)
        if room is None:
            raise LookupError("tavern_room_not_found")
        return room

    def update_room(
        self,
        *,
        room: TavernRoomRecord,
        participants: list[TavernParticipantRecord],
        expected_revision: int,
    ) -> TavernRoomDetail:
        with self.database.session() as session:
            pending_run_exists = (
                select(TavernRunRow.id)
                .where(
                    TavernRunRow.room_id == room.id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .exists()
            )
            # Claim the room before checking history, so admission cannot race
            # the history guard. A rejected update rolls this transaction back.
            claimed = session.execute(
                update(TavernRoomRow)
                .where(
                    TavernRoomRow.id == room.id,
                    TavernRoomRow.revision == expected_revision,
                    ~pending_run_exists,
                )
                .values(revision=TavernRoomRow.revision)
            )
            if claimed.rowcount != 1:
                self._raise_room_claim_failure(session, room_id=room.id)
            current_orders = dict(
                session.execute(
                    select(
                        TavernParticipantRow.persona_id,
                        TavernParticipantRow.display_order,
                    ).where(TavernParticipantRow.room_id == room.id)
                ).all()
            )
            next_orders = {item.persona_id: item.display_order for item in participants}
            changed_persona_ids = {
                persona_id
                for persona_id, order in current_orders.items()
                if next_orders.get(persona_id) != order
            }
            if changed_persona_ids:
                referenced_message_persona = session.scalar(
                    select(TavernMessageRow.persona_id)
                    .where(
                        TavernMessageRow.room_id == room.id,
                        TavernMessageRow.persona_id.in_(changed_persona_ids),
                    )
                    .limit(1)
                )
                referenced_step_persona = session.scalar(
                    select(TavernRunStepRow.persona_id)
                    .join(TavernRunRow, TavernRunRow.id == TavernRunStepRow.run_id)
                    .where(
                        TavernRunRow.room_id == room.id,
                        TavernRunStepRow.persona_id.in_(changed_persona_ids),
                    )
                    .limit(1)
                )
                if referenced_message_persona or referenced_step_persona:
                    raise TavernParticipantHistoryConflict(sorted(changed_persona_ids))
            pending_run_exists = (
                select(TavernRunRow.id)
                .where(
                    TavernRunRow.room_id == room.id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .exists()
            )
            updated = session.execute(
                update(TavernRoomRow)
                .where(
                    TavernRoomRow.id == room.id,
                    TavernRoomRow.revision == expected_revision,
                    ~pending_run_exists,
                )
                .values(
                    title=room.title,
                    status=room.status.value,
                    scene_profile=(
                        room.scene_profile.model_dump(mode="json")
                        if room.scene_profile
                        else None
                    ),
                    harness_policy=room.harness_policy.model_dump(mode="json"),
                    revision=TavernRoomRow.revision + 1,
                    updated_at=room.updated_at,
                )
            )
            if updated.rowcount != 1:
                self._raise_room_claim_failure(session, room_id=room.id)
            room_row = session.get(TavernRoomRow, room.id)
            if room_row is None:
                raise LookupError("tavern_room_not_found")
            room.revision = room_row.revision
            room.last_sequence = room_row.last_sequence
            session.execute(
                delete(TavernParticipantRow).where(
                    TavernParticipantRow.room_id == room.id
                )
            )
            session.add_all(_participant_to_row(item) for item in participants)
        return self.require_room(room.id)

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

    def delete_room(self, room_id: str, *, expected_revision: int) -> bool:
        with self.database.session() as session:
            pending_run_exists = (
                select(TavernRunRow.id)
                .where(
                    TavernRunRow.room_id == room_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .exists()
            )
            claimed = session.execute(
                update(TavernRoomRow)
                .where(
                    TavernRoomRow.id == room_id,
                    TavernRoomRow.revision == expected_revision,
                    ~pending_run_exists,
                )
                .values(revision=TavernRoomRow.revision)
            )
            if claimed.rowcount != 1:
                room = session.get(TavernRoomRow, room_id)
                if room is None:
                    return False
                pending_id = session.scalar(
                    select(TavernRunRow.id).where(
                        TavernRunRow.room_id == room_id,
                        TavernRunRow.status == TavernRunStatus.PENDING.value,
                    )
                )
                if pending_id is not None:
                    raise TavernRunInProgress(pending_id)
                raise TavernRevisionConflict(room.revision)
            session.execute(
                delete(TavernMessageRow).where(TavernMessageRow.room_id == room_id)
            )
            session.execute(
                delete(TavernRunStepRow).where(
                    TavernRunStepRow.run_id.in_(
                        select(TavernRunRow.id).where(TavernRunRow.room_id == room_id)
                    )
                )
            )
            session.execute(delete(TavernRunRow).where(TavernRunRow.room_id == room_id))
            session.execute(
                delete(TavernParticipantRow).where(
                    TavernParticipantRow.room_id == room_id
                )
            )
            session.execute(delete(TavernRoomRow).where(TavernRoomRow.id == room_id))
        return True

    @staticmethod
    def _raise_room_claim_failure(session, *, room_id: str) -> None:
        room_row = session.get(TavernRoomRow, room_id)
        if room_row is None:
            raise LookupError("tavern_room_not_found")
        pending_id = session.scalar(
            select(TavernRunRow.id).where(
                TavernRunRow.room_id == room_id,
                TavernRunRow.status == TavernRunStatus.PENDING.value,
            )
        )
        if pending_id is not None:
            raise TavernRunInProgress(pending_id)
        raise TavernRevisionConflict(room_row.revision)
