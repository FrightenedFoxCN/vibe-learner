from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.domain import VersionedLearningPlanRecord as LearningPlanRecord, StudySessionRecord
from app.persistence.database import Database
from app.persistence.models import LearningPlanRow, LearningPlanRevisionRow, StudySessionRow


def plan_from_row(row: LearningPlanRow) -> LearningPlanRecord:
    record = LearningPlanRecord.model_validate(deepcopy(row.payload))
    if record.id != row.id or record.revision != row.revision:
        raise ValueError("learning_plan_projection_identity_mismatch")
    return record


def archive_plan(session, row: LearningPlanRow) -> None:
    key = (row.id, row.revision)
    previous = session.get(LearningPlanRevisionRow, key)
    if previous is None:
        session.add(LearningPlanRevisionRow(plan_id=row.id, revision=row.revision, payload=deepcopy(row.payload)))
    elif previous.payload != row.payload:
        raise ValueError("learning_plan_history_divergence")


class LearningPlanRepository:
    """Plan aggregate CAS. History and the new revision commit together."""

    def __init__(self, database: Database):
        self.database = database

    def list(self) -> list[LearningPlanRecord]:
        with self.database.session() as session:
            return [plan_from_row(row) for row in session.scalars(
                select(LearningPlanRow).where(LearningPlanRow.deleted == 0)
                .order_by(LearningPlanRow.created_at, LearningPlanRow.id)
            )]

    def require(self, plan_id: str) -> LearningPlanRecord:
        with self.database.session() as session:
            row = session.get(LearningPlanRow, plan_id)
            if row is None or row.deleted:
                raise HTTPException(404, "plan_not_found")
            return plan_from_row(row)

    def import_legacy(self, records: list[LearningPlanRecord]) -> None:
        # Insert-only: absence from a legacy list never deletes runtime data.
        with self.database.session() as session:
            for record in records:
                record = LearningPlanRecord.model_validate(record.model_dump(mode="json"))
                row = session.get(LearningPlanRow, record.id)
                if row is not None:
                    if row.deleted or plan_from_row(row) != record:
                        raise ValueError("learning_plan_legacy_import_conflict")
                    continue
                row = LearningPlanRow(
                    id=record.id, revision=record.revision, deleted=0,
                    document_id=record.document_id, persona_id=record.persona_id,
                    creation_mode=record.creation_mode, course_title=record.course_title,
                    created_at=record.created_at, payload=record.model_dump(mode="json"),
                )
                session.add(row)
                session.flush()
                archive_plan(session, row)

    def mutate(self, plan_id: str, mutation: Callable[[LearningPlanRecord], LearningPlanRecord],
               *, expected_revision: int | None = None, deleted: bool = False) -> LearningPlanRecord:
        for _ in range(8):
            try:
                with self.database.session() as session:
                    row = session.get(LearningPlanRow, plan_id)
                    if row is None or row.deleted:
                        raise HTTPException(404, "plan_not_found")
                    before = plan_from_row(row)
                    if expected_revision is not None and before.revision != expected_revision:
                        raise HTTPException(409, "learning_plan_revision_conflict")
                    after = mutation(before.model_copy(deep=True))
                    for field in ("id", "document_id", "persona_id", "creation_mode", "created_at", "revision"):
                        if getattr(before, field) != getattr(after, field):
                            raise ValueError(f"learning_plan_owned_field_changed:{field}")
                    after.revision = before.revision + 1
                    after = LearningPlanRecord.model_validate(after.model_dump(mode="json"))
                    changed = session.execute(update(LearningPlanRow).where(
                        LearningPlanRow.id == plan_id, LearningPlanRow.revision == before.revision,
                        LearningPlanRow.deleted == 0,
                    ).values(revision=after.revision, deleted=int(deleted), course_title=after.course_title,
                             payload=after.model_dump(mode="json")), execution_options={"synchronize_session": False})
                    if changed.rowcount != 1:
                        if expected_revision is not None:
                            raise HTTPException(409, "learning_plan_revision_conflict")
                        continue
                    archive_plan(session, row)
                    session.add(LearningPlanRevisionRow(plan_id=plan_id, revision=after.revision,
                                                       payload=after.model_dump(mode="json")))
                    return after
            except OperationalError as exc:
                if not self.database.url.startswith("sqlite") or "locked" not in str(exc).lower():
                    raise
            except IntegrityError:
                if expected_revision is not None:
                    raise HTTPException(409, "learning_plan_revision_conflict")
        raise HTTPException(409, "learning_plan_revision_conflict")

    def resolve_confirmation(self, session_id: str, confirmation_id: str, decision: str,
                             note: str, now: str, apply) -> tuple[StudySessionRecord, LearningPlanRecord | None]:
        for _ in range(8):
            try:
                with self.database.session() as session:
                    session_row = session.get(StudySessionRow, session_id)
                    if session_row is None:
                        raise HTTPException(404, "session_not_found")
                    record = StudySessionRecord.model_validate(deepcopy(session_row.payload))
                    confirmation = next((item for item in record.plan_confirmations if item.id == confirmation_id), None)
                    if confirmation is None:
                        raise HTTPException(404, "plan_confirmation_not_found")
                    target = "approved" if decision == "approve" else "rejected"
                    if confirmation.status not in {"pending", target}:
                        raise HTTPException(409, "plan_confirmation_decision_conflict")
                    plan_row = session.get(LearningPlanRow, confirmation.plan_id)
                    plan = plan_from_row(plan_row) if plan_row is not None and not plan_row.deleted else None
                    if confirmation.status == target:
                        return record, plan if decision == "approve" else None
                    if decision == "approve":
                        if plan is None or confirmation.plan_id != record.plan_id:
                            raise HTTPException(409, "plan_confirmation_target_unavailable")
                        after = apply(plan.model_copy(deep=True), confirmation)
                        after.revision = plan.revision + 1
                        written = session.execute(update(LearningPlanRow).where(
                            LearningPlanRow.id == plan.id, LearningPlanRow.revision == plan.revision,
                            LearningPlanRow.deleted == 0,
                        ).values(revision=after.revision, course_title=after.course_title,
                                 payload=after.model_dump(mode="json")), execution_options={"synchronize_session": False})
                        if written.rowcount != 1:
                            raise _ConfirmationRace()
                        archive_plan(session, plan_row)
                        session.add(LearningPlanRevisionRow(plan_id=plan.id, revision=after.revision,
                                                           payload=after.model_dump(mode="json")))
                        plan = after
                    confirmation.status = target
                    confirmation.resolution_note = note.strip()
                    confirmation.resolved_at = now
                    record.updated_at = now
                    record.revision += 1
                    written = session.execute(update(StudySessionRow).where(
                        StudySessionRow.id == session_id, StudySessionRow.revision == record.revision - 1,
                    ).values(revision=record.revision, updated_at=now, payload=record.model_dump(mode="json")))
                    if written.rowcount != 1:
                        raise _ConfirmationRace()
                    return record, plan if decision == "approve" else None
            except _ConfirmationRace:
                continue
            except OperationalError as exc:
                if not self.database.url.startswith("sqlite") or "locked" not in str(exc).lower():
                    raise
        raise HTTPException(409, "plan_confirmation_revision_conflict")


class _ConfirmationRace(Exception):
    pass
