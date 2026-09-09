"""Database independent validation for Tavern's deliberately soft references."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.persistence.models import (
    TavernMessageRow,
    TavernRunRow,
    TavernRunStepRow,
)


@dataclass(frozen=True)
class TavernReferenceViolation:
    kind: str
    owner_id: str
    reference_id: str


class TavernReferenceIntegrityError(RuntimeError):
    def __init__(self, violations: list[TavernReferenceViolation]):
        self.violations = tuple(violations)
        detail = ",".join(
            f"{item.kind}:{item.owner_id}:{item.reference_id}"
            for item in self.violations
        )
        super().__init__(f"tavern_reference_integrity_violation:{detail}")


@dataclass(frozen=True)
class TavernReferenceWriteSet:
    """Old and new identities touched by one transaction, including deletions."""

    room_ids: frozenset[str] = frozenset()
    run_ids: frozenset[str] = frozenset()
    message_ids: frozenset[str] = frozenset()


def scan_tavern_reference_integrity(
    session: Session,
    *,
    write_set: TavernReferenceWriteSet | None = None,
) -> tuple[TavernReferenceViolation, ...]:
    """Validate every Run/Message/Step soft edge in one consistent snapshot.

    Empty legacy sentinel values mean "no reference".  Non-empty references
    must resolve to an object in the same Room (and generated messages must be
    owned by the Step's Run).  This is intentionally SQLAlchemy-only so the
    rule behaves identically on SQLite and PostgreSQL.
    """
    if write_set is None:
        # Explicit audit mode: callers opt into inspecting historical data.
        runs = list(session.scalars(select(TavernRunRow)))
        messages = list(session.scalars(select(TavernMessageRow)))
        steps = list(session.scalars(select(TavernRunStepRow)))
    else:
        if not (write_set.room_ids or write_set.run_ids or write_set.message_ids):
            return ()
        affected_runs = select(TavernRunRow.id).where(or_(
            TavernRunRow.room_id.in_(write_set.room_ids),
            TavernRunRow.id.in_(write_set.run_ids),
        ))
        affected_messages = select(TavernMessageRow.id).where(or_(
            TavernMessageRow.room_id.in_(write_set.room_ids),
            TavernMessageRow.id.in_(write_set.message_ids),
        ))
        # Include incoming references, even from another room, and retain
        # deleted IDs from the write set so deletion cannot hide a broken edge.
        run_edge = lambda column: or_(
            column.in_(affected_runs), column.in_(write_set.run_ids)
        )
        message_edge = lambda column: or_(
            column.in_(affected_messages), column.in_(write_set.message_ids)
        )
        runs = list(session.scalars(select(TavernRunRow).where(or_(
            TavernRunRow.id.in_(affected_runs),
            run_edge(TavernRunRow.parent_run_id),
            message_edge(TavernRunRow.input_message_id),
        ))))
        messages = list(session.scalars(select(TavernMessageRow).where(or_(
            TavernMessageRow.id.in_(affected_messages),
            run_edge(TavernMessageRow.run_id),
        ))))
        steps = list(session.scalars(select(TavernRunStepRow).where(or_(
            run_edge(TavernRunStepRow.run_id),
            message_edge(TavernRunStepRow.message_id),
            message_edge(TavernRunStepRow.reply_to_message_id),
        ))))
    run_by_id = {row.id: row for row in runs}
    message_by_id = {row.id: row for row in messages}
    if write_set is not None:
        # Resolve outgoing targets without recursively auditing unrelated rooms.
        run_targets = (
            {row.parent_run_id for row in runs}
            | {row.run_id for row in messages}
            | {row.run_id for row in steps}
        ) - {None, ""} - run_by_id.keys()
        message_targets = (
            {row.input_message_id for row in runs}
            | {row.message_id for row in steps}
            | {row.reply_to_message_id for row in steps}
        ) - {None, ""} - message_by_id.keys()
        if run_targets:
            run_by_id.update((row.id, row) for row in session.scalars(
                select(TavernRunRow).where(TavernRunRow.id.in_(run_targets))
            ))
        if message_targets:
            message_by_id.update((row.id, row) for row in session.scalars(
                select(TavernMessageRow).where(TavernMessageRow.id.in_(message_targets))
            ))
    violations: list[TavernReferenceViolation] = []

    for run in runs:
        if run.parent_run_id and run.parent_run_id not in run_by_id:
            violations.append(TavernReferenceViolation("run_parent", run.id, run.parent_run_id))
        elif run.parent_run_id and run_by_id[run.parent_run_id].room_id != run.room_id:
            violations.append(TavernReferenceViolation("run_parent_room", run.id, run.parent_run_id))
        if run.input_message_id:
            message = message_by_id.get(run.input_message_id)
            if message is None:
                violations.append(TavernReferenceViolation("run_input_message", run.id, run.input_message_id))
            elif message.room_id != run.room_id:
                violations.append(TavernReferenceViolation("run_input_message_room", run.id, message.id))

    for message in messages:
        if message.run_id:
            run = run_by_id.get(message.run_id)
            if run is None:
                violations.append(TavernReferenceViolation("message_run", message.id, message.run_id))
            elif run.room_id != message.room_id:
                violations.append(TavernReferenceViolation("message_run_room", message.id, run.id))

    for step in steps:
        run = run_by_id.get(step.run_id)
        if run is None:
            violations.append(TavernReferenceViolation("step_run", step.run_id, step.run_id))
            continue
        if step.message_id:
            message = message_by_id.get(step.message_id)
            if message is None:
                violations.append(TavernReferenceViolation("step_message", f"{step.run_id}:{step.step_index}", step.message_id))
            elif message.run_id != step.run_id or message.room_id != run.room_id:
                violations.append(TavernReferenceViolation("step_message_owner", f"{step.run_id}:{step.step_index}", message.id))
        if step.reply_to_message_id:
            anchor = message_by_id.get(step.reply_to_message_id)
            if anchor is None:
                violations.append(TavernReferenceViolation("step_reply_anchor", f"{step.run_id}:{step.step_index}", step.reply_to_message_id))
            elif anchor.room_id != run.room_id:
                violations.append(TavernReferenceViolation("step_reply_anchor_room", f"{step.run_id}:{step.step_index}", anchor.id))

    return tuple(violations)


def require_tavern_reference_integrity(
    session: Session, *, write_set: TavernReferenceWriteSet | None = None
) -> None:
    violations = list(scan_tavern_reference_integrity(session, write_set=write_set))
    if violations:
        raise TavernReferenceIntegrityError(violations)
