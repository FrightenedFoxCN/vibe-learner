from __future__ import annotations
from sqlalchemy import select
from app.models.tavern import (
    TavernAuthorKind,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRunRecord,
    TavernSpeakerStepRecord,
)
from app.persistence.models import (
    TavernMessageRow,
    TavernParticipantRow,
    TavernRunRow,
    TavernRunStepRow,
)

from app.persistence.tavern_rows import (
    _message_from_row,
    _participant_from_row,
    _run_from_row,
)


class TavernMessageOps:
    def list_run_messages(self, run_id: str) -> list[TavernMessageRecord]:
        with self.database.session() as session:
            rows = session.scalars(
                select(TavernMessageRow)
                .where(
                    TavernMessageRow.run_id == run_id,
                    TavernMessageRow.author_kind == "persona",
                )
                .order_by(TavernMessageRow.sequence)
            ).all()
        return [_message_from_row(row) for row in rows]

    def get_message(self, message_id: str) -> TavernMessageRecord | None:
        with self.database.session() as session:
            row = session.get(TavernMessageRow, message_id)
            return _message_from_row(row) if row is not None else None

    def get_actor_commit_read_back(
        self,
        *,
        message_id: str,
    ) -> tuple[
        TavernMessageRecord,
        TavernRunRecord,
        TavernSpeakerStepRecord,
        list[TavernParticipantRecord],
        TavernMessageRecord,
    ]:
        """Read one actor commit graph from a single consistent DB snapshot."""

        with self.database.session() as session:
            return self.get_actor_commit_read_back_in_session(
                session,
                message_id=message_id,
            )

    def get_actor_commit_read_back_in_session(
        self,
        session,
        *,
        message_id: str,
    ) -> tuple[
        TavernMessageRecord,
        TavernRunRecord,
        TavernSpeakerStepRecord,
        list[TavernParticipantRecord],
        TavernMessageRecord,
    ]:
        """Read an actor commit graph from the caller's transaction snapshot."""

        message_row = session.get(TavernMessageRow, message_id)
        if message_row is None:
            raise LookupError("tavern_message_not_found")
        message = _message_from_row(message_row)
        if message.author_kind != TavernAuthorKind.PERSONA:
            raise ValueError("tavern_actor_commit_message_required")
        run_row = session.get(TavernRunRow, message.run_id)
        if run_row is None or run_row.room_id != message.room_id:
            raise LookupError("tavern_run_not_found")
        step_rows = session.scalars(
            select(TavernRunStepRow)
            .where(TavernRunStepRow.run_id == run_row.id)
            .order_by(TavernRunStepRow.step_index)
        ).all()
        run = _run_from_row(run_row, step_rows)
        matching_steps = [
            item for item in run.speaker_steps if item.message_id == message.id
        ]
        if len(matching_steps) != 1:
            raise ValueError("tavern_actor_commit_step_mismatch")
        participant_rows = session.scalars(
            select(TavernParticipantRow)
            .where(TavernParticipantRow.room_id == message.room_id)
            .order_by(TavernParticipantRow.display_order)
        ).all()
        anchor_row = session.get(TavernMessageRow, message.reply_to_message_id)
        if anchor_row is None:
            raise LookupError("tavern_actor_commit_reply_anchor_not_found")
        return (
            message,
            run,
            matching_steps[0],
            [_participant_from_row(row) for row in participant_rows],
            _message_from_row(anchor_row),
        )

    def get_latest_message(self, room_id: str) -> TavernMessageRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(TavernMessageRow)
                .where(TavernMessageRow.room_id == room_id)
                .order_by(TavernMessageRow.sequence.desc())
                .limit(1)
            )
            return _message_from_row(row) if row is not None else None

    def list_recent_messages(
        self,
        room_id: str,
        *,
        limit: int,
        exclude_message_id: str = "",
    ) -> list[TavernMessageRecord]:
        bounded_limit = max(1, min(limit, 40))
        with self.database.session() as session:
            filters = [TavernMessageRow.room_id == room_id]
            if exclude_message_id:
                filters.append(TavernMessageRow.id != exclude_message_id)
            rows = session.scalars(
                select(TavernMessageRow)
                .where(*filters)
                .order_by(TavernMessageRow.sequence.desc())
                .limit(bounded_limit)
            ).all()
        return [_message_from_row(row) for row in reversed(rows)]
