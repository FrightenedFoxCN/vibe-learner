from __future__ import annotations

from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

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
    TavernRunStatus,
    TavernSpeakerStepRecord,
    TavernSpeakerStepStatus,
)
from app.persistence.database import Database
from app.persistence.models import (
    TavernMessageRow,
    TavernParticipantRow,
    TavernRoomRow,
    TavernRunRow,
    TavernRunStepRow,
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
                    selected_rows[-1].sequence
                    if has_more and selected_rows
                    else None
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
                    selected_rows[0].sequence
                    if has_more and selected_rows
                    else None
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
            return self._hydrate_run(session, row) if row is not None else None

    def get_run(self, run_id: str) -> TavernRunRecord | None:
        with self.database.session() as session:
            row = session.get(TavernRunRow, run_id)
            return self._hydrate_run(session, row) if row is not None else None

    def list_runs(self, room_id: str, *, limit: int = 50) -> list[TavernRunRecord]:
        bounded_limit = max(1, min(limit, 100))
        with self.database.session() as session:
            rows = session.scalars(
                select(TavernRunRow)
                .where(TavernRunRow.room_id == room_id)
                .order_by(TavernRunRow.created_at.desc(), TavernRunRow.id.desc())
                .limit(bounded_limit)
            ).all()
            step_rows = session.scalars(
                select(TavernRunStepRow)
                .where(TavernRunStepRow.run_id.in_([row.id for row in rows]))
                .order_by(TavernRunStepRow.run_id, TavernRunStepRow.step_index)
            ).all() if rows else []
        steps_by_run: defaultdict[str, list[TavernRunStepRow]] = defaultdict(list)
        for step_row in step_rows:
            steps_by_run[step_row.run_id].append(step_row)
        return [_run_from_row(row, steps_by_run[row.id]) for row in rows]

    def begin_run(
        self,
        *,
        run: TavernRunRecord,
        user_message: TavernMessageRecord | None,
    ) -> tuple[TavernRunRecord, TavernMessageRecord | None, bool]:
        _validate_new_run_schedule(run)
        try:
            with self.database.session() as session:
                existing = self._find_existing_run_replay(
                    session,
                    run=run,
                )
                if existing is not None:
                    return existing

                pending_run_exists = select(TavernRunRow.id).where(
                    TavernRunRow.room_id == run.room_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                ).exists()
                claimed = session.execute(
                    update(TavernRoomRow)
                    .where(
                        TavernRoomRow.id == run.room_id,
                        TavernRoomRow.revision == run.expected_room_revision,
                        ~pending_run_exists,
                    )
                    .values(
                        revision=TavernRoomRow.revision + 1,
                        last_sequence=(
                            TavernRoomRow.last_sequence + 1
                            if user_message is not None
                            else TavernRoomRow.last_sequence
                        ),
                        updated_at=run.created_at,
                    )
                )
                if claimed.rowcount != 1:
                    replay = self._resolve_unclaimed_run(session, run=run)
                    if replay is not None:
                        return replay

                room_row = session.get(TavernRoomRow, run.room_id)
                if room_row is None:
                    raise LookupError("tavern_room_not_found")
                if user_message is not None:
                    user_message.sequence = room_row.last_sequence
                    user_message.room_id = room_row.id
                    user_message.run_id = run.id
                    run.input_message_id = user_message.id
                    run.anchor_message_id = user_message.id
                session.add(_run_to_row(run))
                session.flush()
                session.add_all(_step_to_row(step) for step in run.speaker_steps)
                if user_message is not None:
                    session.add(_message_to_row(user_message))
        except IntegrityError:
            replay = self._resolve_begin_run_collision(run)
            if replay is not None:
                return replay
            raise
        return run, user_message, True

    def _find_existing_run_replay(
        self,
        session,
        *,
        run: TavernRunRecord,
    ) -> tuple[TavernRunRecord, TavernMessageRecord | None, bool] | None:
        existing_row = session.scalar(
            select(TavernRunRow).where(
                TavernRunRow.room_id == run.room_id,
                TavernRunRow.idempotency_key == run.idempotency_key,
            )
        )
        if existing_row is None:
            return None
        existing_run = self._hydrate_run(session, existing_row)
        _assert_run_replay_matches(existing_run, run)
        existing_message = None
        if existing_run.input_message_id:
            existing_message_row = session.get(
                TavernMessageRow,
                existing_run.input_message_id,
            )
            if existing_message_row is None:
                raise RuntimeError("tavern_run_input_message_missing")
            existing_message = _message_from_row(existing_message_row)
        return existing_run, existing_message, False

    def _resolve_unclaimed_run(
        self,
        session,
        *,
        run: TavernRunRecord,
    ) -> tuple[TavernRunRecord, TavernMessageRecord | None, bool] | None:
        replay = self._find_existing_run_replay(session, run=run)
        if replay is not None:
            return replay
        if run.parent_run_id:
            child_id = session.scalar(
                select(TavernRunRow.id).where(
                    TavernRunRow.parent_run_id == run.parent_run_id
                )
            )
            if child_id is not None:
                raise TavernRetryAlreadyCreated(child_id)
        room_row = session.get(TavernRoomRow, run.room_id)
        if room_row is None:
            raise LookupError("tavern_room_not_found")
        pending_id = session.scalar(
            select(TavernRunRow.id).where(
                TavernRunRow.room_id == run.room_id,
                TavernRunRow.status == TavernRunStatus.PENDING.value,
            )
        )
        if pending_id is not None:
            raise TavernRunInProgress(pending_id)
        raise TavernRevisionConflict(room_row.revision)

    def _resolve_begin_run_collision(
        self,
        run: TavernRunRecord,
    ) -> tuple[TavernRunRecord, TavernMessageRecord | None, bool] | None:
        with self.database.session() as session:
            return self._resolve_unclaimed_run(session, run=run)

    def claim_step(
        self,
        *,
        run_id: str,
        step_index: int,
        started_at: str,
    ) -> TavernSpeakerStepRecord:
        with self.database.session() as session:
            run_pending = select(TavernRunRow.id).where(
                TavernRunRow.id == run_id,
                TavernRunRow.status == TavernRunStatus.PENDING.value,
            ).exists()
            claim_conditions = [
                TavernRunStepRow.run_id == run_id,
                TavernRunStepRow.step_index == step_index,
                TavernRunStepRow.status == TavernSpeakerStepStatus.PENDING.value,
                run_pending,
            ]
            if step_index > 0:
                previous_step_completed = select(TavernRunStepRow.run_id).where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.step_index == step_index - 1,
                    TavernRunStepRow.status
                    == TavernSpeakerStepStatus.COMPLETED.value,
                ).exists()
                claim_conditions.append(previous_step_completed)
            claimed = session.execute(
                update(TavernRunStepRow)
                .where(*claim_conditions)
                .values(
                    status=TavernSpeakerStepStatus.GENERATING.value,
                    started_at=started_at,
                )
            )
            if claimed.rowcount != 1:
                run_row = session.get(TavernRunRow, run_id)
                if run_row is None:
                    raise LookupError("tavern_run_not_found")
                step_row = session.get(TavernRunStepRow, (run_id, step_index))
                if step_row is None:
                    raise LookupError("tavern_run_step_not_found")
                raise TavernStepClaimConflict(step_index, step_row.status)
            step_row = session.get(TavernRunStepRow, (run_id, step_index))
            if step_row is None:
                raise LookupError("tavern_run_step_not_found")
            return _step_from_row(step_row)

    def set_step_reply_anchor(
        self,
        *,
        run_id: str,
        step_index: int,
        reply_to_message_id: str,
    ) -> None:
        updated = None
        with self.database.session() as session:
            updated = session.execute(
                update(TavernRunStepRow)
                .where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.step_index == step_index,
                    TavernRunStepRow.status == TavernSpeakerStepStatus.PENDING.value,
                )
                .values(reply_to_message_id=reply_to_message_id)
            )
        if updated is None or updated.rowcount != 1:
            raise TavernStepClaimConflict(step_index, "anchor_not_pending")

    def get_retry_child(self, parent_run_id: str) -> TavernRunRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(TavernRunRow).where(TavernRunRow.parent_run_id == parent_run_id)
            )
            return self._hydrate_run(session, row) if row is not None else None

    def complete_step(
        self,
        *,
        run_id: str,
        step_index: int,
        message: TavernMessageRecord,
        completed_at: str,
        finalize_run: bool,
    ) -> TavernRunRecord:
        with self.database.session() as session:
            run_row = session.get(TavernRunRow, run_id)
            if run_row is None:
                raise LookupError("tavern_run_not_found")
            if run_row.status != TavernRunStatus.PENDING.value:
                raise RuntimeError(f"tavern_run_not_pending:{run_row.status}")
            step_row = session.get(TavernRunStepRow, (run_id, step_index))
            if step_row is None:
                raise LookupError("tavern_run_step_not_found")
            if step_row.status != TavernSpeakerStepStatus.GENERATING.value:
                raise TavernStepClaimConflict(step_index, step_row.status)

            advanced = session.execute(
                update(TavernRoomRow)
                .where(TavernRoomRow.id == run_row.room_id)
                .values(
                    last_sequence=TavernRoomRow.last_sequence + 1,
                    updated_at=completed_at,
                )
            )
            if advanced.rowcount != 1:
                raise LookupError("tavern_room_not_found")
            room_row = session.get(TavernRoomRow, run_row.room_id)
            if room_row is None:
                raise LookupError("tavern_room_not_found")
            message.room_id = room_row.id
            message.run_id = run_id
            message.sequence = room_row.last_sequence
            message.reply_to_message_id = step_row.reply_to_message_id
            session.add(_message_to_row(message))
            completed_step = session.execute(
                update(TavernRunStepRow)
                .where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.step_index == step_index,
                    TavernRunStepRow.status == TavernSpeakerStepStatus.GENERATING.value,
                )
                .values(
                    status=TavernSpeakerStepStatus.COMPLETED.value,
                    message_id=message.id,
                    completed_at=completed_at,
                    payload={
                        "harness_trace": (
                            message.harness_trace.model_dump(mode="json")
                            if message.harness_trace
                            else None
                        )
                    },
                )
            )
            if completed_step.rowcount != 1:
                raise TavernStepClaimConflict(step_index, step_row.status)
            if finalize_run:
                incomplete_count = int(
                    session.scalar(
                        select(func.count(TavernRunStepRow.step_index)).where(
                            TavernRunStepRow.run_id == run_id,
                            TavernRunStepRow.status
                            != TavernSpeakerStepStatus.COMPLETED.value,
                        )
                    )
                    or 0
                )
                if incomplete_count:
                    raise RuntimeError("tavern_run_steps_incomplete")
                run_row.status = TavernRunStatus.COMPLETED.value
                run_row.completed_at = completed_at
                payload = dict(run_row.payload or {})
                payload["terminal_sequence"] = room_row.last_sequence
                run_row.payload = payload
        completed = self.get_run(run_id)
        if completed is None:
            raise LookupError("tavern_run_not_found")
        return completed

    def fail_step(
        self,
        *,
        run_id: str,
        step_index: int,
        error_code: str,
        completed_at: str,
        harness_trace: HarnessTraceRecord,
    ) -> TavernRunRecord:
        with self.database.session() as session:
            run_row = session.get(TavernRunRow, run_id)
            if run_row is None:
                raise LookupError("tavern_run_not_found")
            if run_row.status != TavernRunStatus.PENDING.value:
                existing = self._hydrate_run(session, run_row)
                return existing
            step_row = session.get(TavernRunStepRow, (run_id, step_index))
            if step_row is None:
                raise LookupError("tavern_run_step_not_found")
            if step_row.status != TavernSpeakerStepStatus.GENERATING.value:
                raise TavernStepClaimConflict(step_index, step_row.status)
            failed_step = session.execute(
                update(TavernRunStepRow)
                .where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.step_index == step_index,
                    TavernRunStepRow.status == TavernSpeakerStepStatus.GENERATING.value,
                )
                .values(
                    status=TavernSpeakerStepStatus.FAILED.value,
                    error_code=error_code[:128],
                    completed_at=completed_at,
                    payload={"harness_trace": harness_trace.model_dump(mode="json")},
                )
            )
            if failed_step.rowcount != 1:
                raise TavernStepClaimConflict(step_index, step_row.status)
            session.execute(
                update(TavernRunStepRow)
                .where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.step_index > step_index,
                    TavernRunStepRow.status == TavernSpeakerStepStatus.PENDING.value,
                )
                .values(status=TavernSpeakerStepStatus.BLOCKED.value)
            )
            completed_count = int(
                session.scalar(
                    select(func.count(TavernRunStepRow.step_index)).where(
                        TavernRunStepRow.run_id == run_id,
                        TavernRunStepRow.status == TavernSpeakerStepStatus.COMPLETED.value,
                    )
                )
                or 0
            )
            room_row = session.get(TavernRoomRow, run_row.room_id)
            if room_row is None:
                raise LookupError("tavern_room_not_found")
            run_row.status = (
                TavernRunStatus.PARTIAL.value
                if completed_count
                else TavernRunStatus.FAILED.value
            )
            run_row.error_code = error_code[:128]
            run_row.completed_at = completed_at
            payload = dict(run_row.payload or {})
            payload["terminal_sequence"] = room_row.last_sequence
            run_row.payload = payload
        failed = self.get_run(run_id)
        if failed is None:
            raise LookupError("tavern_run_not_found")
        return failed

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

    def get_latest_message(self, room_id: str) -> TavernMessageRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(TavernMessageRow)
                .where(TavernMessageRow.room_id == room_id)
                .order_by(TavernMessageRow.sequence.desc())
                .limit(1)
            )
            return _message_from_row(row) if row is not None else None

    @staticmethod
    def _hydrate_run(session, row: TavernRunRow) -> TavernRunRecord:
        step_rows = session.scalars(
            select(TavernRunStepRow)
            .where(TavernRunStepRow.run_id == row.id)
            .order_by(TavernRunStepRow.step_index)
        ).all()
        return _run_from_row(row, step_rows)

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

    def update_room(
        self,
        *,
        room: TavernRoomRecord,
        participants: list[TavernParticipantRecord],
        expected_revision: int,
    ) -> TavernRoomDetail:
        with self.database.session() as session:
            pending_run_exists = select(TavernRunRow.id).where(
                TavernRunRow.room_id == room.id,
                TavernRunRow.status == TavernRunStatus.PENDING.value,
            ).exists()
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
                delete(TavernParticipantRow).where(TavernParticipantRow.room_id == room.id)
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
            pending_run_exists = select(TavernRunRow.id).where(
                TavernRunRow.room_id == room_id,
                TavernRunRow.status == TavernRunStatus.PENDING.value,
            ).exists()
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
            session.execute(delete(TavernMessageRow).where(TavernMessageRow.room_id == room_id))
            session.execute(
                delete(TavernRunStepRow).where(
                    TavernRunStepRow.run_id.in_(
                        select(TavernRunRow.id).where(TavernRunRow.room_id == room_id)
                    )
                )
            )
            session.execute(delete(TavernRunRow).where(TavernRunRow.room_id == room_id))
            session.execute(
                delete(TavernParticipantRow).where(TavernParticipantRow.room_id == room_id)
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


def _room_to_row(room: TavernRoomRecord) -> TavernRoomRow:
    return TavernRoomRow(
        id=room.id,
        creation_key=room.creation_key or None,
        creation_input_digest=room.creation_input_digest,
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
        creation_key=row.creation_key or "",
        creation_input_digest=row.creation_input_digest or "",
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
        reply_to_message_id=str(payload.get("reply_to_message_id") or ""),
        client_request_id=row.client_request_id,
        created_at=row.created_at,
        harness_trace=(
            HarnessTraceRecord.model_validate(harness_payload) if harness_payload else None
        ),
    )


def _run_from_row(
    row: TavernRunRow,
    step_rows: list[TavernRunStepRow] | None = None,
) -> TavernRunRecord:
    payload = row.payload or {}
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
        request_digest=str(payload.get("request_digest") or ""),
        context_digest=str(payload.get("context_digest") or ""),
        mode=row.mode,
        trigger_kind=str(payload.get("trigger_kind") or "user_message"),
        parent_run_id=row.parent_run_id or "",
        root_run_id=str(payload.get("root_run_id") or row.id),
        input_message_id=row.input_message_id or None,
        anchor_message_id=str(payload.get("anchor_message_id") or row.input_message_id or ""),
        scheduled_participant_ids=[
            str(item)
            for item in (
                payload.get("scheduled_participant_ids")
                or payload.get("requested_participant_ids")
                or []
            )
        ],
        speaker_steps=speaker_steps,
        guidance=str(payload.get("guidance") or ""),
        status=row.status,
        expected_room_revision=row.expected_room_revision,
        generated_message_ids=(
            generated_message_ids
            if speaker_steps
            else [str(item) for item in (payload.get("generated_message_ids") or [])]
        ),
        harness_trace=(
            harness_trace
            if speaker_steps
            else [
                HarnessTraceRecord.model_validate(item)
                for item in (payload.get("harness_trace") or [])
            ]
        ),
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
    row.input_message_id = run.input_message_id or ""
    row.expected_room_revision = run.expected_room_revision
    row.error_code = run.error_code
    row.created_at = run.created_at
    row.completed_at = run.completed_at
    row.payload = {
        "request_digest": run.request_digest,
        "context_digest": run.context_digest,
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
        payload={
            "harness_trace": (
                step.harness_trace.model_dump(mode="json")
                if step.harness_trace
                else None
            )
        },
    )


def _step_from_row(row: TavernRunStepRow) -> TavernSpeakerStepRecord:
    payload = row.payload or {}
    trace_payload = payload.get("harness_trace")
    return TavernSpeakerStepRecord(
        run_id=row.run_id,
        step_index=row.step_index,
        persona_id=row.persona_id,
        participant_prompt_hash=row.participant_prompt_hash,
        status=row.status,
        message_id=row.message_id or "",
        reply_to_message_id=row.reply_to_message_id,
        error_code=row.error_code,
        harness_trace=(
            HarnessTraceRecord.model_validate(trace_payload) if trace_payload else None
        ),
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


class TavernRevisionConflict(RuntimeError):
    def __init__(self, current_revision: int) -> None:
        super().__init__(f"tavern_revision_conflict:{current_revision}")
        self.current_revision = current_revision


class TavernRunInProgress(RuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"tavern_run_in_progress:{run_id}")
        self.run_id = run_id


class TavernIdempotencyConflict(RuntimeError):
    def __init__(self, operation: str) -> None:
        super().__init__(f"tavern_idempotency_key_reused:{operation}")
        self.operation = operation


class TavernRetryAlreadyCreated(RuntimeError):
    def __init__(self, child_run_id: str) -> None:
        super().__init__(f"tavern_retry_already_created:{child_run_id}")
        self.child_run_id = child_run_id


class TavernStepClaimConflict(RuntimeError):
    def __init__(self, step_index: int, status: str) -> None:
        super().__init__(f"tavern_step_claim_conflict:{step_index}:{status}")
        self.step_index = step_index
        self.status = status
