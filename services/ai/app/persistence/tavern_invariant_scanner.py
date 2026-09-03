"""Database independent validation for Tavern's deliberately soft references."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
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


def scan_tavern_reference_integrity(session: Session) -> tuple[TavernReferenceViolation, ...]:
    """Validate every Run/Message/Step soft edge in one consistent snapshot.

    Empty legacy sentinel values mean "no reference".  Non-empty references
    must resolve to an object in the same Room (and generated messages must be
    owned by the Step's Run).  This is intentionally SQLAlchemy-only so the
    rule behaves identically on SQLite and PostgreSQL.
    """
    runs = list(session.scalars(select(TavernRunRow)))
    messages = list(session.scalars(select(TavernMessageRow)))
    steps = list(session.scalars(select(TavernRunStepRow)))
    run_by_id = {row.id: row for row in runs}
    message_by_id = {row.id: row for row in messages}
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


def require_tavern_reference_integrity(session: Session) -> None:
    violations = list(scan_tavern_reference_integrity(session))
    if violations:
        raise TavernReferenceIntegrityError(violations)
