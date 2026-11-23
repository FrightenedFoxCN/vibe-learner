from __future__ import annotations
from collections import defaultdict
from datetime import timedelta
from typing import Any, Callable
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from app.models.harness import HarnessTraceRecord, validate_harness_trace
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
    HarnessOperationResolutionV1,
)
from app.models.tavern import (
    TavernMessageRecord,
    TavernRunRecord,
    TavernRunStatus,
    TavernSpeakerStepRecord,
    TavernSpeakerStepStatus,
)
from app.persistence.models import (
    TavernMessageRow,
    TavernRoomRow,
    TavernRunRow,
    TavernRunStepRow,
)

from app.persistence.tavern_errors import (
    TavernRetryAlreadyCreated,
    TavernRevisionConflict,
    TavernRunInProgress,
    TavernRunTerminalConflict,
    TavernStepClaimConflict,
    TavernStepClaimsExhausted,
)
from app.persistence.tavern_rows import (
    _assert_run_replay_matches,
    _canonical_utc_timestamp,
    _database_utc_now,
    _message_from_row,
    _message_to_row,
    _run_from_row,
    _run_to_row,
    _step_from_row,
    _step_to_row,
    _validate_new_run_schedule,
)
from app.persistence.row_mapping import payload_of


class TavernRunOps:
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
            step_rows = (
                session.scalars(
                    select(TavernRunStepRow)
                    .where(TavernRunStepRow.run_id.in_([row.id for row in rows]))
                    .order_by(TavernRunStepRow.run_id, TavernRunStepRow.step_index)
                ).all()
                if rows
                else []
            )
        steps_by_run: defaultdict[str, list[TavernRunStepRow]] = defaultdict(list)
        for step_row in step_rows:
            steps_by_run[step_row.run_id].append(step_row)
        return [_run_from_row(row, steps_by_run[row.id]) for row in rows]

    def list_all_runs(self, room_id: str) -> list[TavernRunRecord]:
        """Load complete room run lineage for an authoritative recovery projection."""
        with self.database.session() as session:
            rows = session.scalars(
                select(TavernRunRow)
                .where(TavernRunRow.room_id == room_id)
                .order_by(TavernRunRow.created_at.asc(), TavernRunRow.id.asc())
            ).all()
            step_rows = (
                session.scalars(
                    select(TavernRunStepRow)
                    .where(TavernRunStepRow.run_id.in_([row.id for row in rows]))
                    .order_by(TavernRunStepRow.run_id, TavernRunStepRow.step_index)
                ).all()
                if rows
                else []
            )
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

                pending_run_exists = (
                    select(TavernRunRow.id)
                    .where(
                        TavernRunRow.room_id == run.room_id,
                        TavernRunRow.status == TavernRunStatus.PENDING.value,
                    )
                    .exists()
                )
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
                run_row = _run_to_row(run)
                session.add(run_row)
                parent_harness_operation_id = None
                if run.parent_run_id:
                    parent_binding = self.harness_operations.require_domain_in_session(
                        session,
                        domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
                        domain_operation_id=run.parent_run_id,
                    )
                    parent_harness_operation_id = parent_binding.harness_operation_id
                self.harness_operations._admit_domain_in_session(
                    session,
                    domain_row=run_row,
                    domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
                    domain_operation_id=run.id,
                    admitted_at=run.created_at,
                    parent_harness_operation_id=parent_harness_operation_id,
                )
                session.add_all(_step_to_row(step) for step in run.speaker_steps)
                if user_message is not None:
                    session.add(_message_to_row(user_message))
        except IntegrityError:
            replay = self._resolve_begin_run_collision(run)
            if replay is not None:
                return replay
            raise
        return run, user_message, True

    def resolve_harness_operation(
        self,
        run_id: str,
    ) -> HarnessOperationResolutionV1:
        return self.harness_operations.resolve_domain(
            domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
            domain_operation_id=run_id,
        )

    def require_harness_operation(
        self,
        run_id: str,
    ) -> HarnessOperationBindingV1:
        return self.harness_operations.require_domain(
            domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
            domain_operation_id=run_id,
        )

    def fail_legacy_unbound_run(
        self,
        *,
        run_id: str,
        completed_at: str,
    ) -> TavernRunRecord:
        """Fence a pre-binding pending Run without fabricating admission identity."""

        error_code = "tavern_harness_operation_legacy_unbound"
        with self.database.session() as session:
            resolution = self.harness_operations.resolve_domain_in_session(
                session,
                domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
                domain_operation_id=run_id,
            )
            if resolution.binding is not None:
                raise ValueError("tavern_harness_operation_binding_exists")
            claimed = session.execute(
                update(TavernRunRow)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .values(status=TavernRunRow.status)
            )
            run_row = session.get(TavernRunRow, run_id)
            if run_row is None:
                raise LookupError("tavern_run_not_found")
            if claimed.rowcount != 1:
                return self._hydrate_run(session, run_row)

            unfinished_rows = session.scalars(
                select(TavernRunStepRow)
                .where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.status != TavernSpeakerStepStatus.COMPLETED.value,
                )
                .order_by(TavernRunStepRow.step_index)
            ).all()
            for index, step_row in enumerate(unfinished_rows):
                step_row.status = (
                    TavernSpeakerStepStatus.FAILED.value
                    if index == 0
                    else TavernSpeakerStepStatus.BLOCKED.value
                )
                step_row.error_code = error_code
                step_row.completed_at = completed_at if index == 0 else ""
                step_row.lease_owner = ""
                step_row.lease_expires_at = ""

            completed_count = int(
                session.scalar(
                    select(func.count(TavernRunStepRow.step_index)).where(
                        TavernRunStepRow.run_id == run_id,
                        TavernRunStepRow.status
                        == TavernSpeakerStepStatus.COMPLETED.value,
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
            run_row.error_code = error_code
            run_row.completed_at = completed_at
            payload = dict(payload_of(run_row))
            payload["terminal_sequence"] = room_row.last_sequence
            run_row.payload = payload
            session.flush()
            return self._hydrate_run(session, run_row)

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
        lease_owner: str,
        lease_seconds: float,
        max_claims: int,
        exhaustion_trace: HarnessTraceRecord,
        reply_to_message_id: str | None = None,
    ) -> TavernSpeakerStepRecord:
        normalized_owner = lease_owner.strip()
        if not normalized_owner:
            raise ValueError("tavern_step_lease_owner_required")
        if lease_seconds < 1 or lease_seconds > 900:
            raise ValueError("tavern_step_lease_seconds_invalid")
        if max_claims < 1 or max_claims > 5:
            raise ValueError("tavern_step_max_claims_invalid")
        exhausted_run: TavernRunRecord | None = None
        with self.database.session() as session:
            database_now = _database_utc_now(session)
            canonical_started_at = _canonical_utc_timestamp(database_now)
            canonical_lease_expires_at = _canonical_utc_timestamp(
                database_now + timedelta(seconds=lease_seconds)
            )
            # All run/step mutations take the run row first. This keeps the
            # PostgreSQL lock order aligned with complete/fail/cancel and avoids
            # an exhaustion-vs-cancel run<->step deadlock.
            run_claim = session.execute(
                update(TavernRunRow)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .values(status=TavernRunRow.status)
            )
            run_row = session.get(TavernRunRow, run_id)
            if run_row is None:
                raise LookupError("tavern_run_not_found")
            if run_claim.rowcount != 1:
                raise TavernRunTerminalConflict(run_id, run_row.status)
            run_pending = (
                select(TavernRunRow.id)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .exists()
            )
            claim_conditions = [
                TavernRunStepRow.run_id == run_id,
                TavernRunStepRow.step_index == step_index,
                (
                    (TavernRunStepRow.status == TavernSpeakerStepStatus.PENDING.value)
                    | (
                        (
                            TavernRunStepRow.status
                            == TavernSpeakerStepStatus.GENERATING.value
                        )
                        & (TavernRunStepRow.lease_expires_at <= canonical_started_at)
                    )
                ),
                TavernRunStepRow.claim_count < max_claims,
                run_pending,
            ]
            if step_index > 0:
                previous_step_completed = (
                    select(TavernRunStepRow.run_id)
                    .where(
                        TavernRunStepRow.run_id == run_id,
                        TavernRunStepRow.step_index == step_index - 1,
                        TavernRunStepRow.status
                        == TavernSpeakerStepStatus.COMPLETED.value,
                    )
                    .exists()
                )
                claim_conditions.append(previous_step_completed)
            claimed = session.execute(
                update(TavernRunStepRow)
                .where(*claim_conditions)
                .values(
                    status=TavernSpeakerStepStatus.GENERATING.value,
                    started_at=canonical_started_at,
                    lease_owner=normalized_owner,
                    lease_expires_at=canonical_lease_expires_at,
                    claim_count=TavernRunStepRow.claim_count + 1,
                    **(
                        {"reply_to_message_id": reply_to_message_id}
                        if reply_to_message_id is not None
                        else {}
                    ),
                )
            )
            if claimed.rowcount != 1:
                step_row = session.get(TavernRunStepRow, (run_id, step_index))
                if step_row is None:
                    raise LookupError("tavern_run_step_not_found")
                exhausted = session.execute(
                    update(TavernRunStepRow)
                    .where(
                        TavernRunStepRow.run_id == run_id,
                        TavernRunStepRow.step_index == step_index,
                        TavernRunStepRow.claim_count >= max_claims,
                        (
                            (
                                TavernRunStepRow.status
                                == TavernSpeakerStepStatus.PENDING.value
                            )
                            | (
                                (
                                    TavernRunStepRow.status
                                    == TavernSpeakerStepStatus.GENERATING.value
                                )
                                & (
                                    TavernRunStepRow.lease_expires_at
                                    <= canonical_started_at
                                )
                            )
                        ),
                        run_pending,
                    )
                    .values(
                        status=TavernSpeakerStepStatus.FAILED.value,
                        error_code="tavern_step_claims_exhausted",
                        completed_at=canonical_started_at,
                        lease_owner="",
                        lease_expires_at="",
                        payload={
                            "harness_trace": exhaustion_trace.model_dump(mode="json")
                        },
                    )
                )
                if exhausted.rowcount == 1:
                    session.execute(
                        update(TavernRunStepRow)
                        .where(
                            TavernRunStepRow.run_id == run_id,
                            TavernRunStepRow.step_index > step_index,
                            TavernRunStepRow.status
                            == TavernSpeakerStepStatus.PENDING.value,
                        )
                        .values(
                            status=TavernSpeakerStepStatus.BLOCKED.value,
                            error_code="tavern_previous_step_claims_exhausted",
                        )
                    )
                    completed_count = int(
                        session.scalar(
                            select(func.count(TavernRunStepRow.step_index)).where(
                                TavernRunStepRow.run_id == run_id,
                                TavernRunStepRow.status
                                == TavernSpeakerStepStatus.COMPLETED.value,
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
                    run_row.error_code = "tavern_run_claims_exhausted"
                    run_row.completed_at = canonical_started_at
                    payload = dict(payload_of(run_row))
                    payload["terminal_sequence"] = room_row.last_sequence
                    run_row.payload = payload
                    session.flush()
                    exhausted_run = self._hydrate_run(session, run_row)
                else:
                    session.refresh(run_row)
                    session.refresh(step_row)
                    raise TavernStepClaimConflict(step_index, step_row.status)
            step_row = session.get(TavernRunStepRow, (run_id, step_index))
            if step_row is None:
                raise LookupError("tavern_run_step_not_found")
            if exhausted_run is None:
                return _step_from_row(step_row)
        if exhausted_run is None:
            raise RuntimeError("tavern_step_claim_exhaustion_state_missing")
        raise TavernStepClaimsExhausted(exhausted_run)

    def renew_step_lease(
        self,
        *,
        run_id: str,
        step_index: int,
        lease_owner: str,
        claim_count: int,
        lease_seconds: float,
    ) -> str | None:
        if lease_seconds < 1 or lease_seconds > 900:
            raise ValueError("tavern_step_lease_seconds_invalid")
        with self.database.session() as session:
            database_now = _database_utc_now(session)
            canonical_now = _canonical_utc_timestamp(database_now)
            canonical_expiry = _canonical_utc_timestamp(
                database_now + timedelta(seconds=lease_seconds)
            )
            run_claim = session.execute(
                update(TavernRunRow)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .values(status=TavernRunRow.status)
            )
            if run_claim.rowcount != 1:
                return None
            run_pending = (
                select(TavernRunRow.id)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .exists()
            )
            renewed = session.execute(
                update(TavernRunStepRow)
                .where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.step_index == step_index,
                    TavernRunStepRow.status == TavernSpeakerStepStatus.GENERATING.value,
                    TavernRunStepRow.lease_owner == lease_owner,
                    TavernRunStepRow.claim_count == claim_count,
                    TavernRunStepRow.lease_expires_at > canonical_now,
                    run_pending,
                )
                .values(lease_expires_at=canonical_expiry)
            )
            return canonical_expiry if renewed.rowcount == 1 else None

    def has_active_step_lease(
        self,
        *,
        run_id: str,
        step_index: int,
        lease_owner: str,
        claim_count: int,
    ) -> bool:
        with self.database.session() as session:
            canonical_now = _canonical_utc_timestamp(_database_utc_now(session))
            run_pending = (
                select(TavernRunRow.id)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .exists()
            )
            return bool(
                session.scalar(
                    select(TavernRunStepRow.run_id).where(
                        TavernRunStepRow.run_id == run_id,
                        TavernRunStepRow.step_index == step_index,
                        TavernRunStepRow.status
                        == TavernSpeakerStepStatus.GENERATING.value,
                        TavernRunStepRow.lease_owner == lease_owner,
                        TavernRunStepRow.claim_count == claim_count,
                        TavernRunStepRow.lease_expires_at > canonical_now,
                        run_pending,
                    )
                )
            )

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
        lease_owner: str,
        claim_count: int,
        runtime_commit: Callable[
            [Any, TavernMessageRecord, TavernRunRecord, TavernSpeakerStepRecord], None
        ]
        | None = None,
    ) -> TavernRunRecord:
        with self.database.session() as session:
            canonical_now = _canonical_utc_timestamp(_database_utc_now(session))
            run_claim = session.execute(
                update(TavernRunRow)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .values(status=TavernRunRow.status)
            )
            run_row = session.get(TavernRunRow, run_id)
            if run_row is None:
                raise LookupError("tavern_run_not_found")
            if run_claim.rowcount != 1:
                raise TavernRunTerminalConflict(run_id, run_row.status)
            step_row = session.get(TavernRunStepRow, (run_id, step_index))
            if step_row is None:
                raise LookupError("tavern_run_step_not_found")
            if step_row.status != TavernSpeakerStepStatus.GENERATING.value:
                raise TavernStepClaimConflict(step_index, step_row.status)
            if step_row.lease_owner != lease_owner:
                raise TavernStepClaimConflict(step_index, "lease_lost")
            if step_row.claim_count != claim_count:
                raise TavernStepClaimConflict(step_index, "fencing_epoch_lost")
            if step_row.lease_expires_at <= canonical_now:
                raise TavernStepClaimConflict(step_index, "lease_expired")
            operation_binding = self.harness_operations.require_domain_in_session(
                session,
                domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
                domain_operation_id=run_id,
            )
            if message.commit_metadata is None:
                raise ValueError("tavern_commit_metadata_missing")
            if (
                message.commit_metadata.operation_id
                != operation_binding.harness_operation_id
            ):
                raise ValueError("tavern_commit_operation_binding_mismatch")

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
                    TavernRunStepRow.lease_owner == lease_owner,
                    TavernRunStepRow.claim_count == claim_count,
                    TavernRunStepRow.lease_expires_at > canonical_now,
                )
                .values(
                    status=TavernSpeakerStepStatus.COMPLETED.value,
                    message_id=message.id,
                    completed_at=completed_at,
                    lease_owner="",
                    lease_expires_at="",
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
            if runtime_commit is not None:
                # The callback receives the live transaction and the freshly
                # persisted graph, so runtime terminalization can be fenced in
                # the same commit as Message/Step/Run.
                session.flush()
                hydrated = self._hydrate_run(session, run_row)
                current_step = next(
                    item
                    for item in hydrated.speaker_steps
                    if item.step_index == step_index
                )
                anchor_row = session.get(TavernMessageRow, step_row.reply_to_message_id)
                if anchor_row is None:
                    raise LookupError("tavern_actor_commit_reply_anchor_not_found")
                runtime_commit(
                    session,
                    message,
                    hydrated,
                    current_step,
                )
                if message.harness_trace is None:
                    raise ValueError("tavern_runtime_commit_trace_missing")
                message_row = session.get(TavernMessageRow, message.id)
                if message_row is None:
                    raise LookupError("tavern_message_not_found")
                message_payload = dict(payload_of(message_row))
                message_payload["harness_trace"] = message.harness_trace.model_dump(
                    mode="json", exclude_none=False
                )
                message_row.payload = message_payload
                step_payload = dict(payload_of(step_row))
                step_payload["harness_trace"] = message.harness_trace.model_dump(
                    mode="json", exclude_none=False
                )
                step_row.payload = step_payload
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
                payload = dict(payload_of(run_row))
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
        lease_owner: str,
        claim_count: int,
        runtime_failure: Callable[[Any], HarnessTraceRecord] | None = None,
    ) -> TavernRunRecord:
        with self.database.session() as session:
            canonical_now = _canonical_utc_timestamp(_database_utc_now(session))
            run_claim = session.execute(
                update(TavernRunRow)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .values(status=TavernRunRow.status)
            )
            run_row = session.get(TavernRunRow, run_id)
            if run_row is None:
                raise LookupError("tavern_run_not_found")
            if run_claim.rowcount != 1:
                existing = self._hydrate_run(session, run_row)
                return existing
            step_row = session.get(TavernRunStepRow, (run_id, step_index))
            if step_row is None:
                raise LookupError("tavern_run_step_not_found")
            if step_row.status != TavernSpeakerStepStatus.GENERATING.value:
                raise TavernStepClaimConflict(step_index, step_row.status)
            if step_row.lease_owner != lease_owner:
                raise TavernStepClaimConflict(step_index, "lease_lost")
            if step_row.claim_count != claim_count:
                raise TavernStepClaimConflict(step_index, "fencing_epoch_lost")
            if step_row.lease_expires_at <= canonical_now:
                raise TavernStepClaimConflict(step_index, "lease_expired")
            if runtime_failure is not None:
                harness_trace = runtime_failure(session)
            failed_step = session.execute(
                update(TavernRunStepRow)
                .where(
                    TavernRunStepRow.run_id == run_id,
                    TavernRunStepRow.step_index == step_index,
                    TavernRunStepRow.status == TavernSpeakerStepStatus.GENERATING.value,
                    TavernRunStepRow.lease_owner == lease_owner,
                    TavernRunStepRow.claim_count == claim_count,
                    TavernRunStepRow.lease_expires_at > canonical_now,
                )
                .values(
                    status=TavernSpeakerStepStatus.FAILED.value,
                    error_code=error_code[:128],
                    completed_at=completed_at,
                    lease_owner="",
                    lease_expires_at="",
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
                        TavernRunStepRow.status
                        == TavernSpeakerStepStatus.COMPLETED.value,
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
            payload = dict(payload_of(run_row))
            payload["terminal_sequence"] = room_row.last_sequence
            run_row.payload = payload
        failed = self.get_run(run_id)
        if failed is None:
            raise LookupError("tavern_run_not_found")
        return failed

    def record_terminal_step_trace(
        self,
        *,
        run_id: str,
        step_index: int,
        harness_trace,
        claim_count: int,
    ) -> None:
        """Attach late fenced evidence to a canceled step without reviving it."""

        strict_trace = validate_harness_trace(
            harness_trace.model_dump(mode="json", exclude_none=False)
        )
        with self.database.session() as session:
            row = session.get(TavernRunStepRow, (run_id, step_index))
            if row is None:
                raise LookupError("tavern_run_step_not_found")
            if (
                row.status != TavernSpeakerStepStatus.CANCELED.value
                or row.claim_count != claim_count
            ):
                return
            payload = dict(payload_of(row))
            payload["harness_trace"] = strict_trace.model_dump(
                mode="json",
                exclude_none=False,
            )
            row.payload = payload

    def cancel_run(
        self,
        *,
        room_id: str,
        run_id: str,
        canceled_at: str,
    ) -> tuple[TavernRunRecord, bool]:
        """Cancel a pending run with the same database CAS used by step commits.

        Returns ``(run, changed)``. Repeating cancellation of an already canceled
        run is idempotent; other terminal runs are returned unchanged so the
        service can report a conflict.
        """

        with self.database.session() as session:
            canceled = session.execute(
                update(TavernRunRow)
                .where(
                    TavernRunRow.id == run_id,
                    TavernRunRow.room_id == room_id,
                    TavernRunRow.status == TavernRunStatus.PENDING.value,
                )
                .values(
                    status=TavernRunStatus.CANCELED.value,
                    error_code="tavern_run_canceled",
                    completed_at=canceled_at,
                )
            )
            run_row = session.get(TavernRunRow, run_id)
            if run_row is None or run_row.room_id != room_id:
                raise LookupError("tavern_run_not_found")
            if canceled.rowcount == 1:
                session.execute(
                    update(TavernRunStepRow)
                    .where(
                        TavernRunStepRow.run_id == run_id,
                        TavernRunStepRow.status.in_(
                            [
                                TavernSpeakerStepStatus.PENDING.value,
                                TavernSpeakerStepStatus.GENERATING.value,
                            ]
                        ),
                    )
                    .values(
                        status=TavernSpeakerStepStatus.CANCELED.value,
                        error_code="tavern_run_canceled",
                        completed_at=canceled_at,
                        lease_owner="",
                        lease_expires_at="",
                    )
                )
                room_row = session.get(TavernRoomRow, room_id)
                if room_row is None:
                    raise LookupError("tavern_room_not_found")
                payload = dict(payload_of(run_row))
                payload["terminal_sequence"] = room_row.last_sequence
                run_row.payload = payload
            hydrated = self._hydrate_run(session, run_row)
            return hydrated, canceled.rowcount == 1

    @staticmethod
    def _hydrate_run(session, row: TavernRunRow) -> TavernRunRecord:
        step_rows = session.scalars(
            select(TavernRunStepRow)
            .where(TavernRunStepRow.run_id == row.id)
            .order_by(TavernRunStepRow.step_index)
        ).all()
        return _run_from_row(row, step_rows)
