from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.domain import DialogueTurnRecord, StudySessionRecord
from app.persistence.database import Database
from app.persistence.models import StudySessionRow


class StudySessionRepository:
    """Database-authoritative CAS boundary for the Study Session aggregate."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, record: StudySessionRecord) -> StudySessionRecord:
        payload = record.model_dump(mode="json")
        try:
            with self.database.session() as session:
                session.add(_to_row(record, payload))
                session.flush()
        except IntegrityError as exc:
            raise StudySessionAlreadyExists(record.id) from exc
        return self.require(record.id)

    def import_legacy(
        self,
        records: list[StudySessionRecord],
        *,
        max_attempts: int = 8,
    ) -> None:
        """Atomically insert absent legacy aggregates and reject divergence."""
        if max_attempts < 1 or max_attempts > 32:
            raise ValueError("study_session_legacy_import_attempts_invalid")
        unique_records: dict[str, StudySessionRecord] = {}
        for record in records:
            prior = unique_records.get(record.id)
            if prior is not None and prior != record:
                raise StudySessionLegacyImportConflict(record.id)
            unique_records[record.id] = record

        for _ in range(max_attempts):
            try:
                with self.database.session() as session:
                    for record in unique_records.values():
                        existing = session.get(StudySessionRow, record.id)
                        if existing is not None:
                            if _from_row(existing) != record:
                                raise StudySessionLegacyImportConflict(record.id)
                            continue
                        payload = record.model_dump(mode="json")
                        session.add(_to_row(record, payload))
                    session.flush()
                return
            except IntegrityError:
                # A concurrent importer may claim an ID after the transaction
                # checked it. Roll back the entire batch and revalidate every
                # now-visible row on the next bounded attempt.
                continue
            except OperationalError as exc:
                if not _is_retryable_sqlite_lock(self.database, exc):
                    raise
        raise StudySessionLegacyImportRace

    def get(self, session_id: str) -> StudySessionRecord | None:
        with self.database.session() as session:
            row = session.get(StudySessionRow, session_id)
            return _from_row(row) if row is not None else None

    def require(self, session_id: str) -> StudySessionRecord:
        record = self.get(session_id)
        if record is None:
            raise StudySessionNotFound(session_id)
        return record

    def list(self) -> list[StudySessionRecord]:
        with self.database.session() as session:
            rows = session.scalars(
                select(StudySessionRow).order_by(
                    StudySessionRow.created_at,
                    StudySessionRow.id,
                )
            ).all()
            return [_from_row(row) for row in rows]

    def mutate(
        self,
        *,
        session_id: str,
        mutation: Callable[[StudySessionRecord], bool | None],
        committed_turn_policy: Literal["immutable", "answer_patch"] = "immutable",
        max_attempts: int = 8,
    ) -> StudySessionRecord:
        if max_attempts < 1 or max_attempts > 32:
            raise ValueError("study_session_cas_attempts_invalid")

        for _ in range(max_attempts):
            try:
                with self.database.session() as session:
                    row = session.get(StudySessionRow, session_id)
                    if row is None:
                        raise StudySessionNotFound(session_id)
                    record = _from_row(row)
                    expected_revision = record.revision
                    before_mutation = record.model_copy(deep=True)
                    immutable_projection = _immutable_projection(before_mutation)
                    mutation_result = mutation(record)
                    _validate_immutable_projection(
                        record,
                        expected=immutable_projection,
                    )
                    _validate_turn_identity_prefix(
                        before=before_mutation,
                        after=record,
                        committed_turn_policy=committed_turn_policy,
                    )
                    if record.revision != expected_revision:
                        raise ValueError(
                            "study_session_repository_owned_field_changed:revision"
                        )
                    if mutation_result is False:
                        if record != before_mutation:
                            raise ValueError("study_session_noop_mutation_changed_record")
                        return before_mutation
                    record.revision = expected_revision + 1
                    record = StudySessionRecord.model_validate(
                        record.model_dump(mode="json")
                    )
                    payload = record.model_dump(mode="json")
                    claimed = session.execute(
                        update(StudySessionRow)
                        .where(
                            StudySessionRow.id == session_id,
                            StudySessionRow.revision == expected_revision,
                        )
                        .values(payload=payload, **_mutable_metadata(record))
                    )
                    if claimed.rowcount == 1:
                        return record
            except OperationalError as exc:
                if not _is_retryable_sqlite_lock(self.database, exc):
                    raise
        raise StudySessionRevisionConflict(session_id)


class StudySessionRepositoryError(RuntimeError):
    pass


class StudySessionNotFound(StudySessionRepositoryError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"study_session_not_found:{session_id}")


class StudySessionAlreadyExists(StudySessionRepositoryError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"study_session_already_exists:{session_id}")


class StudySessionRevisionConflict(StudySessionRepositoryError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"study_session_revision_conflict:{session_id}")


class StudySessionLegacyImportConflict(StudySessionRepositoryError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"study_session_legacy_import_conflict:{session_id}")


class StudySessionLegacyImportRace(StudySessionRepositoryError):
    def __init__(self) -> None:
        super().__init__("study_session_legacy_import_race")


def _to_row(record: StudySessionRecord, payload: dict[str, object]) -> StudySessionRow:
    row = StudySessionRow(payload=payload)
    for key, value in _metadata(record).items():
        setattr(row, key, value)
    return row


def _metadata(record: StudySessionRecord) -> dict[str, object]:
    return {
        "id": record.id,
        "document_id": record.document_id,
        "persona_id": record.persona_id,
        "plan_id": record.plan_id or "",
        "study_unit_id": record.study_unit_id,
        "status": record.status,
        "revision": record.revision,
        "last_turn_sequence": record.last_turn_sequence,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _mutable_metadata(record: StudySessionRecord) -> dict[str, object]:
    return {
        "study_unit_id": record.study_unit_id,
        "status": record.status,
        "revision": record.revision,
        "last_turn_sequence": record.last_turn_sequence,
        "updated_at": record.updated_at,
    }


def _immutable_projection(record: StudySessionRecord) -> dict[str, str]:
    return {
        "id": record.id,
        "document_id": record.document_id,
        "persona_id": record.persona_id,
        "plan_id": record.plan_id or "",
        "created_at": record.created_at,
    }


def _validate_immutable_projection(
    record: StudySessionRecord,
    *,
    expected: dict[str, str],
) -> None:
    actual = _immutable_projection(record)
    for field_name, expected_value in expected.items():
        if actual[field_name] != expected_value:
            raise ValueError(f"study_session_immutable_field_changed:{field_name}")


def _validate_turn_identity_prefix(
    *,
    before: StudySessionRecord,
    after: StudySessionRecord,
    committed_turn_policy: Literal["immutable", "answer_patch"],
) -> None:
    if len(after.turns) < len(before.turns):
        raise ValueError("study_session_committed_turn_removed")
    for index, committed_turn in enumerate(before.turns):
        candidate = after.turns[index]
        if candidate.id != committed_turn.id:
            raise ValueError("study_session_committed_turn_identity_changed:id")
        if candidate.sequence != committed_turn.sequence:
            raise ValueError("study_session_committed_turn_identity_changed:sequence")
        if _committed_turn_projection(
            candidate,
            committed_turn_policy=committed_turn_policy,
        ) != _committed_turn_projection(
            committed_turn,
            committed_turn_policy=committed_turn_policy,
        ):
            raise ValueError("study_session_committed_turn_content_changed")


def _committed_turn_projection(
    turn: DialogueTurnRecord,
    *,
    committed_turn_policy: Literal["immutable", "answer_patch"],
) -> dict[str, object]:
    projection = turn.model_dump(mode="json")
    question = projection.get("interactive_question")
    if committed_turn_policy == "answer_patch" and isinstance(question, dict):
        # These fields are the persisted learner answer state updated by the
        # dedicated attempt endpoint. The prompt/reply/citations/performance
        # and all other committed Turn content remain immutable.
        question["submitted_answer"] = ""
        question["is_correct"] = None
        question["feedback_text"] = ""
    return projection


def _from_row(row: StudySessionRow) -> StudySessionRecord:
    raw_payload = dict(row.payload or {})
    _validate_stored_watermark(raw_payload, "revision", row.revision)
    _validate_stored_watermark(
        raw_payload,
        "last_turn_sequence",
        row.last_turn_sequence,
        allow_legacy_missing=True,
    )
    payload = dict(raw_payload)
    payload["revision"] = row.revision
    payload["last_turn_sequence"] = row.last_turn_sequence
    record = StudySessionRecord.model_validate(payload)
    _validate_row_projection(row, record, raw_payload=raw_payload)
    return record


def _validate_stored_watermark(
    payload: dict[str, object],
    field_name: str,
    authoritative_value: int,
    *,
    allow_legacy_missing: bool = False,
) -> None:
    if field_name not in payload:
        if authoritative_value == 0 and allow_legacy_missing:
            return
        if authoritative_value == 0 and field_name == "revision":
            return
        raise ValueError(f"study_session_projection_mismatch:{field_name}")
    payload_value = payload[field_name]
    if isinstance(payload_value, bool) or not isinstance(payload_value, int):
        raise ValueError(f"study_session_projection_mismatch:{field_name}")
    if payload_value != authoritative_value:
        raise ValueError(f"study_session_projection_mismatch:{field_name}")


def _validate_row_projection(
    row: StudySessionRow,
    record: StudySessionRecord,
    *,
    raw_payload: dict[str, object],
) -> None:
    legacy_turns = raw_payload.get("turns")
    legacy_turn_watermark = (
        "last_turn_sequence" not in raw_payload
        and row.last_turn_sequence == 0
        and isinstance(legacy_turns, list)
        and bool(legacy_turns)
    )
    projections = {
        "id": (record.id, row.id),
        "document_id": (record.document_id, row.document_id),
        "persona_id": (record.persona_id, row.persona_id),
        "plan_id": (record.plan_id or "", row.plan_id),
        "study_unit_id": (record.study_unit_id, row.study_unit_id),
        "status": (record.status, row.status),
        "revision": (record.revision, row.revision),
        "created_at": (record.created_at, row.created_at),
        "updated_at": (record.updated_at, row.updated_at),
    }
    if not legacy_turn_watermark:
        projections["last_turn_sequence"] = (
            record.last_turn_sequence,
            row.last_turn_sequence,
        )
    for field_name, (payload_value, row_value) in projections.items():
        if payload_value != row_value:
            raise ValueError(f"study_session_projection_mismatch:{field_name}")


def _is_retryable_sqlite_lock(database: Database, exc: OperationalError) -> bool:
    return database.url.startswith("sqlite") and "database is locked" in str(exc).lower()
