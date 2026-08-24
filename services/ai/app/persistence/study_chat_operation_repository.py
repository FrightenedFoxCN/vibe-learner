from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.study_chat_operation import (
    STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION,
    STUDY_CHAT_REQUEST_SCHEMA_VERSION,
    STUDY_CHAT_RESPONSE_SCHEMA_VERSION,
    StudyChatOperationRecord,
    StudyChatOperationReceipt,
    StudyChatOperationRequestPayload,
    StudyChatOperationStatus,
    study_chat_request_fingerprint,
    study_chat_response_digest,
)
from app.models.study_chat_effect import (
    StudyChatCommittedEffectBatchV1,
    StudySceneReplaceCommittedProjectionV1,
)
from app.persistence.database import Database
from app.models.domain import SessionSceneRecord, StudySessionRecord
from app.persistence.models import (
    SessionSceneRow,
    StudyChatOperationRow,
    StudySessionRow,
)
from app.services.study_chat_effects import (
    validate_study_chat_committed_effect_read_back,
)


class StudyChatOperationRepository:
    """Durable admission and execution fence for one Study Chat request."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def admit(
        self,
        *,
        session_id: str,
        client_request_id: str,
        request_payload: StudyChatOperationRequestPayload,
    ) -> StudyChatOperationRecord:
        operation_id = f"study-chat-op-{uuid4().hex[:16]}"
        now = _now()
        fingerprint = study_chat_request_fingerprint(request_payload)
        try:
            with self.database.session() as session:
                existing = session.scalar(
                    select(StudyChatOperationRow).where(
                        StudyChatOperationRow.session_id == session_id,
                        StudyChatOperationRow.client_request_id == client_request_id,
                    )
                )
                if existing is not None:
                    record = _from_row(existing)
                    if record.request_fingerprint != fingerprint:
                        raise StudyChatOperationRequestMismatch(client_request_id)
                    if record.status == StudyChatOperationStatus.COMMITTED:
                        _validate_committed_read_back(
                            record,
                            session_row=session.get(StudySessionRow, session_id),
                            scene_records=_load_operation_scene_records(
                                session,
                                record,
                            ),
                        )
                    return record
                session_row = session.get(StudySessionRow, session_id)
                if session_row is None:
                    raise StudyChatOperationSessionNotFound(session_id)
                if session_row.revision != request_payload.expected_session_revision:
                    raise StudyChatOperationRevisionConflict(
                        session_id,
                        actual_revision=session_row.revision,
                    )
                row = StudyChatOperationRow(
                    operation_id=operation_id,
                    session_id=session_id,
                    client_request_id=client_request_id,
                    request_schema_version=STUDY_CHAT_REQUEST_SCHEMA_VERSION,
                    fingerprint_contract_version=STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION,
                    request_fingerprint=fingerprint,
                    request_payload=request_payload.model_dump(mode="json"),
                    status=StudyChatOperationStatus.ADMITTED.value,
                    active_slot=1,
                    admitted_session_revision=session_row.revision,
                    execution_token="",
                    claim_count=0,
                    execution_started_at="",
                    provider_started_at="",
                    execution_deadline_at="",
                    heartbeat_at="",
                    committed_session_revision=None,
                    committed_turn_id=None,
                    committed_turn_sequence=None,
                    response_schema_version="",
                    response_payload=None,
                    response_digest="",
                    error_code="",
                    created_at=now,
                    updated_at=now,
                    completed_at="",
                )
                session.add(row)
                session.flush()
                return _from_row(row)
        except IntegrityError:
            existing = self.get(session_id=session_id, client_request_id=client_request_id)
            if existing is not None:
                if existing.request_fingerprint != fingerprint:
                    raise StudyChatOperationRequestMismatch(client_request_id)
                return existing
            active = self.get_active(session_id=session_id)
            if active is not None:
                raise StudyChatOperationAlreadyActive(active.client_request_id)
            raise StudyChatOperationAdmissionRace(session_id)

    def get(
        self,
        *,
        session_id: str,
        client_request_id: str,
    ) -> StudyChatOperationRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(StudyChatOperationRow).where(
                    StudyChatOperationRow.session_id == session_id,
                    StudyChatOperationRow.client_request_id == client_request_id,
                )
            )
            if row is None:
                return None
            session_row = (
                session.get(StudySessionRow, session_id)
                if row.status == StudyChatOperationStatus.COMMITTED.value
                else None
            )
            record = _from_row(row)
            if record.status == StudyChatOperationStatus.COMMITTED:
                _validate_committed_read_back(
                    record,
                    session_row=session_row,
                    scene_records=_load_operation_scene_records(session, record),
                )
        if (
            record.status == StudyChatOperationStatus.RUNNING
            and _timestamp_expired(record.execution_deadline_at)
        ):
            return self.mark_uncertain(
                operation_id=record.operation_id,
                execution_token=record.execution_token,
                error_code="study_chat_execution_deadline_expired",
            )
        if (
            record.status == StudyChatOperationStatus.ADMITTED
            and _timestamp_older_than(record.created_at, seconds=30)
        ):
            return self.mark_not_committed(
                operation_id=record.operation_id,
                error_code="study_chat_admission_abandoned",
            )
        return record

    def require(
        self,
        *,
        session_id: str,
        client_request_id: str,
    ) -> StudyChatOperationRecord:
        record = self.get(session_id=session_id, client_request_id=client_request_id)
        if record is None:
            raise StudyChatOperationNotFound(client_request_id)
        return record

    def get_active(self, *, session_id: str) -> StudyChatOperationRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(StudyChatOperationRow).where(
                    StudyChatOperationRow.session_id == session_id,
                    StudyChatOperationRow.active_slot == 1,
                )
            )
            if row is None:
                return None
            record = _from_row(row)
        if (
            record.status == StudyChatOperationStatus.RUNNING
            and _timestamp_expired(record.execution_deadline_at)
        ):
            return self.mark_uncertain(
                operation_id=record.operation_id,
                execution_token=record.execution_token,
                error_code="study_chat_execution_deadline_expired",
            )
        return record

    def claim(
        self,
        *,
        operation_id: str,
        timeout_seconds: int,
    ) -> tuple[StudyChatOperationRecord, bool]:
        now = _now()
        token = f"study-chat-exec-{uuid4().hex}"
        deadline = (
            datetime.now(timezone.utc) + timedelta(seconds=max(1, min(timeout_seconds, 900)))
        ).isoformat()
        with self.database.session() as session:
            claimed = session.execute(
                update(StudyChatOperationRow)
                .where(
                    StudyChatOperationRow.operation_id == operation_id,
                    StudyChatOperationRow.status == StudyChatOperationStatus.ADMITTED.value,
                    StudyChatOperationRow.claim_count == 0,
                    StudyChatOperationRow.active_slot == 1,
                )
                .values(
                    status=StudyChatOperationStatus.RUNNING.value,
                    execution_token=token,
                    claim_count=1,
                    execution_started_at=now,
                    execution_deadline_at=deadline,
                    heartbeat_at=now,
                    updated_at=now,
                )
            )
            if claimed.rowcount != 1:
                row = session.get(StudyChatOperationRow, operation_id)
                if row is None:
                    raise StudyChatOperationNotFound(operation_id)
                return _from_row(row), False
            row = session.get(StudyChatOperationRow, operation_id)
            assert row is not None
            return _from_row(row), True

    def mark_provider_started(self, *, operation_id: str, execution_token: str) -> None:
        now = _now()
        with self.database.session() as session:
            marked = session.execute(
                update(StudyChatOperationRow)
                .where(
                    StudyChatOperationRow.operation_id == operation_id,
                    StudyChatOperationRow.status == StudyChatOperationStatus.RUNNING.value,
                    StudyChatOperationRow.execution_token == execution_token,
                )
                .values(provider_started_at=now, heartbeat_at=now, updated_at=now)
            )
            if marked.rowcount != 1:
                raise StudyChatOperationExecutionFenced(operation_id)

    def mark_not_committed(self, *, operation_id: str, error_code: str) -> StudyChatOperationRecord:
        now = _now()
        with self.database.session() as session:
            marked = session.execute(
                update(StudyChatOperationRow)
                .where(
                    StudyChatOperationRow.operation_id == operation_id,
                    StudyChatOperationRow.status == StudyChatOperationStatus.ADMITTED.value,
                    StudyChatOperationRow.claim_count == 0,
                )
                .values(
                    status=StudyChatOperationStatus.NOT_COMMITTED.value,
                    active_slot=None,
                    error_code=error_code,
                    completed_at=now,
                    updated_at=now,
                )
            )
            if marked.rowcount != 1:
                raise StudyChatOperationExecutionFenced(operation_id)
            row = session.get(StudyChatOperationRow, operation_id)
            assert row is not None
            return _from_row(row)

    def mark_uncertain(self, *, operation_id: str, execution_token: str, error_code: str) -> StudyChatOperationRecord:
        now = _now()
        with self.database.session() as session:
            marked = session.execute(
                update(StudyChatOperationRow)
                .where(
                    StudyChatOperationRow.operation_id == operation_id,
                    StudyChatOperationRow.status == StudyChatOperationStatus.RUNNING.value,
                    StudyChatOperationRow.execution_token == execution_token,
                )
                .values(
                    status=StudyChatOperationStatus.UNCERTAIN.value,
                    active_slot=None,
                    error_code=error_code,
                    completed_at=now,
                    updated_at=now,
                )
            )
            if marked.rowcount != 1:
                row = session.get(StudyChatOperationRow, operation_id)
                if row is None:
                    raise StudyChatOperationNotFound(operation_id)
                return _from_row(row)
            row = session.get(StudyChatOperationRow, operation_id)
            assert row is not None
            return _from_row(row)

    def receipt(self, record: StudyChatOperationRecord) -> StudyChatOperationReceipt:
        return StudyChatOperationReceipt(
            operation_id=record.operation_id,
            session_id=record.session_id,
            client_request_id=record.client_request_id,
            status=record.status,
            safe_to_retry=record.status == StudyChatOperationStatus.NOT_COMMITTED,
            created_at=record.created_at,
            updated_at=record.updated_at,
            completed_at=record.completed_at or None,
            admitted_session_revision=record.admitted_session_revision,
            committed_session_revision=record.committed_session_revision,
            committed_turn_id=record.committed_turn_id,
            committed_turn_sequence=record.committed_turn_sequence,
            error_code=record.error_code,
            result=record.response_payload,
        )


class StudyChatOperationRepositoryError(RuntimeError):
    pass


class StudyChatOperationNotFound(StudyChatOperationRepositoryError):
    pass


class StudyChatOperationSessionNotFound(StudyChatOperationRepositoryError):
    pass


class StudyChatOperationRevisionConflict(StudyChatOperationRepositoryError):
    def __init__(self, session_id: str, *, actual_revision: int) -> None:
        self.actual_revision = actual_revision
        super().__init__(f"study_chat_session_revision_conflict:{session_id}:{actual_revision}")


class StudyChatOperationRequestMismatch(StudyChatOperationRepositoryError):
    pass


class StudyChatOperationAlreadyActive(StudyChatOperationRepositoryError):
    pass


class StudyChatOperationAdmissionRace(StudyChatOperationRepositoryError):
    pass


class StudyChatOperationExecutionFenced(StudyChatOperationRepositoryError):
    pass


def _from_row(
    row: StudyChatOperationRow,
) -> StudyChatOperationRecord:
    record = StudyChatOperationRecord(
        operation_id=row.operation_id,
        session_id=row.session_id,
        client_request_id=row.client_request_id,
        request_schema_version=row.request_schema_version,
        fingerprint_contract_version=row.fingerprint_contract_version,
        request_fingerprint=row.request_fingerprint,
        request_payload=row.request_payload,
        status=row.status,
        admitted_session_revision=row.admitted_session_revision,
        execution_token=row.execution_token,
        claim_count=row.claim_count,
        execution_started_at=row.execution_started_at,
        provider_started_at=row.provider_started_at,
        execution_deadline_at=row.execution_deadline_at,
        heartbeat_at=row.heartbeat_at,
        committed_session_revision=row.committed_session_revision,
        committed_turn_id=row.committed_turn_id,
        committed_turn_sequence=row.committed_turn_sequence,
        response_schema_version=row.response_schema_version,
        response_payload=row.response_payload,
        response_digest=row.response_digest,
        error_code=row.error_code,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )
    return record


def _validate_committed_read_back(
    record: StudyChatOperationRecord,
    *,
    session_row: StudySessionRow | None,
    scene_records: dict[str, SessionSceneRecord],
) -> None:
    if session_row is None or record.response_payload is None:
        raise ValueError("study_chat_operation_committed_session_missing")
    raw_response_session = record.response_payload.get("session")
    if not isinstance(raw_response_session, dict):
        raise ValueError("study_chat_operation_committed_response_session_missing")
    response_session = StudySessionRecord.model_validate(raw_response_session)
    if (
        response_session.id != record.session_id
        or response_session.revision != record.committed_session_revision
        or response_session.last_turn_sequence != record.committed_turn_sequence
    ):
        raise ValueError("study_chat_operation_committed_response_binding_mismatch")
    matching_response_turns = [
        turn
        for turn in response_session.turns
        if turn.id == record.committed_turn_id
        and turn.sequence == record.committed_turn_sequence
    ]
    if len(matching_response_turns) != 1:
        raise ValueError("study_chat_operation_committed_response_turn_missing")
    raw_effect_batch = record.response_payload.get("_committed_effect_batch")
    if raw_effect_batch is not None:
        effect_batch = StudyChatCommittedEffectBatchV1.model_validate(
            raw_effect_batch
        )
        if effect_batch.operation_id != record.operation_id:
            raise ValueError("study_chat_operation_effect_operation_mismatch")
        validate_study_chat_committed_effect_read_back(
            batch=effect_batch,
            record=response_session,
            scene_records=scene_records,
        )
    current_payload = dict(session_row.payload or {})
    current_payload["revision"] = session_row.revision
    current_payload["last_turn_sequence"] = session_row.last_turn_sequence
    current_session = StudySessionRecord.model_validate(current_payload)
    if (
        current_session.id != record.session_id
        or current_session.revision < (record.committed_session_revision or 0)
        or current_session.last_turn_sequence < (record.committed_turn_sequence or 0)
    ):
        raise ValueError("study_chat_operation_committed_session_watermark_regressed")
    matching_current_turns = [
        turn
        for turn in current_session.turns
        if turn.id == record.committed_turn_id
        and turn.sequence == record.committed_turn_sequence
    ]
    if len(matching_current_turns) != 1 or matching_current_turns[0] != matching_response_turns[0]:
        raise ValueError("study_chat_operation_committed_turn_read_back_mismatch")


def _load_operation_scene_records(
    session,
    record: StudyChatOperationRecord,
) -> dict[str, SessionSceneRecord]:
    if record.response_payload is None:
        return {}
    raw_effect_batch = record.response_payload.get("_committed_effect_batch")
    if raw_effect_batch is None:
        return {}
    effect_batch = StudyChatCommittedEffectBatchV1.model_validate(raw_effect_batch)
    scene_ids = {
        projection.scene_instance_id
        for projection in effect_batch.effects
        if isinstance(projection, StudySceneReplaceCommittedProjectionV1)
    }
    result: dict[str, SessionSceneRecord] = {}
    for scene_id in scene_ids:
        row = session.get(SessionSceneRow, scene_id)
        if row is None:
            raise ValueError("study_chat_operation_committed_scene_missing")
        scene_record = SessionSceneRecord.model_validate(row.payload or {})
        expected = {
            "scene_instance_id": row.scene_instance_id,
            "session_id": row.session_id,
            "document_id": row.document_id,
            "persona_id": row.persona_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for field_name, expected_value in expected.items():
            if getattr(scene_record, field_name) != expected_value:
                raise ValueError(
                    f"study_chat_operation_scene_projection_mismatch:{field_name}"
                )
        result[scene_id] = scene_record
    return result


def _timestamp_expired(value: str) -> bool:
    try:
        return datetime.fromisoformat(value) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _timestamp_older_than(value: str, *, seconds: int) -> bool:
    try:
        return datetime.fromisoformat(value) + timedelta(seconds=seconds) <= datetime.now(timezone.utc)
    except ValueError:
        return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
