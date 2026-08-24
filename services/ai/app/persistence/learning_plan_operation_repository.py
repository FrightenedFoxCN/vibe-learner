from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    LearningPlanRecord,
    PlanGenerationTraceRecord,
)
from app.models.planning import (
    LEARNING_PLAN_COMMIT_CONTRACT_VERSION,
    LEARNING_PLAN_OPERATION_FINGERPRINT_VERSION,
    LEARNING_PLAN_OPERATION_REQUEST_SCHEMA_VERSION,
    LearningPlanCommittedProjectionV1,
    LearningPlanOperationRecord,
    LearningPlanOperationRequestV1,
    LearningPlanOperationStatus,
    LearningPlanProjectionState,
    LearningPlanProjectionState,
    learning_plan_request_fingerprint,
    planning_projection_digest,
)
from app.persistence.database import Database
from app.persistence.models import (
    DocumentDebugRow,
    DocumentRow,
    LearningPlanOperationRow,
    LearningPlanRow,
    PlanningTraceRow,
)


class LearningPlanOperationRepository:
    """Durable admission and atomic projection commit for Learning Plan creation."""

    def __init__(
        self,
        database: Database,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.database = database
        self.fault_injector = fault_injector

    def admit(
        self,
        *,
        request: LearningPlanOperationRequestV1,
    ) -> tuple[LearningPlanOperationRecord, bool]:
        fingerprint = learning_plan_request_fingerprint(request)
        operation_id = f"learning-plan-op-{uuid4().hex[:16]}"
        now = _now()
        try:
            with self.database.session() as session:
                existing = session.scalar(
                    select(LearningPlanOperationRow).where(
                        LearningPlanOperationRow.client_request_id
                        == request.client_request_id
                    )
                )
                if existing is not None:
                    record = _from_row(existing)
                    _validate_duplicate(record, fingerprint=fingerprint)
                    return record, True

                document_id: str | None = request.document_id or None
                base_document_updated_at = ""
                base_document_digest = ""
                base_debug_digest = ""
                if document_id is not None:
                    document_row = session.get(DocumentRow, document_id)
                    if document_row is None:
                        raise LearningPlanDocumentNotFound(document_id)
                    if document_row.updated_at != request.expected_document_updated_at:
                        raise LearningPlanStaleDocument(
                            document_id,
                            expected=request.expected_document_updated_at,
                            actual=document_row.updated_at,
                        )
                    base_document_updated_at = document_row.updated_at
                    base_document_digest = planning_projection_digest(
                        document_row.payload or {}
                    )
                    base_document = DocumentRecord.model_validate(
                        document_row.payload or {}
                    )
                    if base_document.debug_ready:
                        debug_row = session.get(DocumentDebugRow, document_id)
                        if debug_row is None:
                            raise LearningPlanProjectionPrerequisiteMissing(
                                document_id,
                                "document_debug",
                            )
                        base_debug_digest = planning_projection_digest(
                            debug_row.payload or {}
                        )

                scope_key = (
                    f"document:{request.document_id}"
                    if request.document_id
                    else f"goal:{request.client_request_id}"
                )
                active = session.scalar(
                    select(LearningPlanOperationRow).where(
                        LearningPlanOperationRow.scope_key == scope_key,
                        LearningPlanOperationRow.active_slot == 1,
                    )
                )
                if active is not None:
                    raise LearningPlanAlreadyActive(scope_key, active.operation_id)

                row = LearningPlanOperationRow(
                    operation_id=operation_id,
                    client_request_id=request.client_request_id,
                    scope_key=scope_key,
                    document_id=document_id,
                    persona_id=request.persona_id,
                    request_schema_version=LEARNING_PLAN_OPERATION_REQUEST_SCHEMA_VERSION,
                    fingerprint_contract_version=LEARNING_PLAN_OPERATION_FINGERPRINT_VERSION,
                    request_fingerprint=fingerprint,
                    request_payload=request.model_dump(mode="json"),
                    base_document_updated_at=base_document_updated_at,
                    base_document_digest=base_document_digest,
                    base_debug_digest=base_debug_digest,
                    status=LearningPlanOperationStatus.RUNNING.value,
                    active_slot=1,
                    projection_state=LearningPlanProjectionState.PENDING.value,
                    provider_started_at="",
                    plan_id="",
                    commit_contract_version="",
                    committed_projection_digest="",
                    committed_projection_payload=None,
                    error_code="",
                    created_at=now,
                    updated_at=now,
                    completed_at="",
                )
                session.add(row)
                session.flush()
                return _from_row(row), False
        except IntegrityError as exc:
            existing = self.get_by_client_request_id(
                client_request_id=request.client_request_id,
                validate_current=False,
            )
            if existing is not None:
                _validate_duplicate(existing, fingerprint=fingerprint)
                return existing, True
            raise LearningPlanAdmissionRace(request.client_request_id) from exc

    def mark_provider_started(self, *, operation_id: str) -> LearningPlanOperationRecord:
        with self.database.session() as session:
            row = session.get(LearningPlanOperationRow, operation_id)
            if row is None:
                raise LearningPlanOperationNotFound(operation_id)
            if row.status != LearningPlanOperationStatus.RUNNING.value:
                raise LearningPlanOperationNotRunning(operation_id, row.status)
            if not row.provider_started_at:
                now = _now()
                row.provider_started_at = now
                row.updated_at = now
        return self.require(operation_id=operation_id, validate_current=False)

    def commit_success(
        self,
        *,
        operation_id: str,
        plan: LearningPlanRecord,
        document: DocumentRecord | None,
        debug_report: DocumentDebugRecord | None,
        trace: PlanGenerationTraceRecord | None,
    ) -> LearningPlanOperationRecord:
        now = _now()
        with self.database.session() as session:
            operation = session.get(LearningPlanOperationRow, operation_id)
            if operation is None:
                raise LearningPlanOperationNotFound(operation_id)
            if operation.status != LearningPlanOperationStatus.RUNNING.value:
                raise LearningPlanOperationNotRunning(operation_id, operation.status)
            request = LearningPlanOperationRequestV1.model_validate(
                operation.request_payload or {}
            )
            if plan.persona_id != operation.persona_id:
                raise LearningPlanProjectionIdentityMismatch(
                    operation_id,
                    "persona_id",
                )
            if plan.document_id != request.document_id:
                raise LearningPlanProjectionIdentityMismatch(
                    operation_id,
                    "document_id",
                )
            if trace is not None and trace.plan_id != plan.id:
                raise LearningPlanProjectionIdentityMismatch(
                    operation_id,
                    "trace_plan_id",
                )

            document_row: DocumentRow | None = None
            debug_row: DocumentDebugRow | None = None
            if request.document_id:
                if document is None or document.id != request.document_id:
                    raise LearningPlanProjectionIdentityMismatch(
                        operation_id,
                        "document_projection",
                    )
                document_row = session.get(DocumentRow, request.document_id)
                if document_row is None:
                    raise LearningPlanDocumentNotFound(request.document_id)
                current_digest = planning_projection_digest(document_row.payload or {})
                if (
                    document_row.updated_at != operation.base_document_updated_at
                    or current_digest != operation.base_document_digest
                ):
                    raise LearningPlanStaleDocument(
                        request.document_id,
                        expected=operation.base_document_updated_at,
                        actual=document_row.updated_at,
                    )
                if operation.base_debug_digest:
                    debug_row = session.get(DocumentDebugRow, request.document_id)
                    if debug_row is None:
                        raise LearningPlanProjectionPrerequisiteMissing(
                            request.document_id,
                            "document_debug",
                        )
                    current_debug_digest = planning_projection_digest(
                        debug_row.payload or {}
                    )
                    if current_debug_digest != operation.base_debug_digest:
                        raise LearningPlanStaleDebugProjection(request.document_id)
                    if debug_report is None:
                        raise LearningPlanProjectionPrerequisiteMissing(
                            request.document_id,
                            "document_debug_projection",
                        )
                elif debug_report is not None:
                    raise LearningPlanProjectionIdentityMismatch(
                        operation_id,
                        "unexpected_debug_projection",
                    )
                if debug_report is not None:
                    if debug_report.document_id != request.document_id:
                        raise LearningPlanProjectionIdentityMismatch(
                            operation_id,
                            "debug_projection",
                        )
            elif document is not None or debug_report is not None:
                raise LearningPlanProjectionIdentityMismatch(
                    operation_id,
                    "goal_only_projection",
                )

            self._inject("before_document_projection")
            if document_row is not None and document is not None:
                _apply_document_row(document_row, document)
                session.flush()
            self._inject("after_document_projection")

            if debug_row is not None and debug_report is not None:
                _apply_debug_row(debug_row, debug_report)
                session.flush()
            self._inject("after_debug_projection")

            trace_key = request.document_id or plan.id
            if trace is not None:
                trace_row = session.get(PlanningTraceRow, trace_key) or PlanningTraceRow()
                _apply_trace_row(trace_row, trace_key=trace_key, trace=trace)
                session.add(trace_row)
                session.flush()
            self._inject("after_trace_projection")

            if session.get(LearningPlanRow, plan.id) is not None:
                raise LearningPlanProjectionIdentityMismatch(
                    operation_id,
                    "plan_id_already_exists",
                )
            plan_row = LearningPlanRow()
            _apply_plan_row(plan_row, plan)
            session.add(plan_row)
            session.flush()
            self._inject("after_plan_projection")

            projection = LearningPlanCommittedProjectionV1(
                operation_id=operation.operation_id,
                client_request_id=operation.client_request_id,
                plan_id=plan.id,
                document_id=request.document_id,
                plan=plan,
                document=document,
                debug_report=debug_report,
                trace=trace,
                plan_digest=planning_projection_digest(plan.model_dump(mode="json")),
                document_digest=(
                    planning_projection_digest(document.model_dump(mode="json"))
                    if document is not None
                    else ""
                ),
                debug_digest=(
                    planning_projection_digest(debug_report.model_dump(mode="json"))
                    if debug_report is not None
                    else ""
                ),
                trace_digest=(
                    planning_projection_digest(trace.model_dump(mode="json"))
                    if trace is not None
                    else ""
                ),
            )
            operation.status = LearningPlanOperationStatus.COMMITTED.value
            operation.active_slot = None
            operation.projection_state = LearningPlanProjectionState.COMMITTED.value
            operation.plan_id = plan.id
            operation.commit_contract_version = LEARNING_PLAN_COMMIT_CONTRACT_VERSION
            operation.committed_projection_payload = projection.model_dump(mode="json")
            operation.committed_projection_digest = planning_projection_digest(
                projection.model_dump(mode="json")
            )
            operation.error_code = ""
            operation.updated_at = now
            operation.completed_at = now
            session.flush()
            self._inject("before_terminal_commit")

        return self.require(operation_id=operation_id, validate_current=True)

    def mark_terminal(
        self,
        *,
        operation_id: str,
        status: LearningPlanOperationStatus,
        error_code: str,
    ) -> LearningPlanOperationRecord:
        if status not in {
            LearningPlanOperationStatus.NOT_COMMITTED,
            LearningPlanOperationStatus.INTERRUPTED,
            LearningPlanOperationStatus.UNCERTAIN,
        }:
            raise ValueError("invalid_learning_plan_terminal_failure_status")
        now = _now()
        with self.database.session() as session:
            row = session.get(LearningPlanOperationRow, operation_id)
            if row is None:
                raise LearningPlanOperationNotFound(operation_id)
            if row.status == LearningPlanOperationStatus.COMMITTED.value:
                return _from_row(row)
            if row.status != LearningPlanOperationStatus.RUNNING.value:
                return _from_row(row)
            row.status = status.value
            row.active_slot = None
            row.projection_state = LearningPlanProjectionState.NOT_COMMITTED.value
            row.plan_id = ""
            row.commit_contract_version = ""
            row.committed_projection_digest = ""
            row.committed_projection_payload = None
            row.error_code = (error_code or "learning_plan_failed")[:128]
            row.updated_at = now
            row.completed_at = now
        return self.require(operation_id=operation_id, validate_current=False)

    def recover_abandoned(self) -> list[LearningPlanOperationRecord]:
        recovered_ids: list[str] = []
        with self.database.session() as session:
            rows = session.scalars(
                select(LearningPlanOperationRow).where(
                    LearningPlanOperationRow.status
                    == LearningPlanOperationStatus.RUNNING.value,
                    LearningPlanOperationRow.active_slot == 1,
                )
            ).all()
            for row in rows:
                now = _now()
                if row.provider_started_at:
                    row.status = LearningPlanOperationStatus.UNCERTAIN.value
                    row.error_code = "learning_plan_abandoned_after_provider_start"
                else:
                    row.status = LearningPlanOperationStatus.NOT_COMMITTED.value
                    row.error_code = "learning_plan_abandoned_before_provider_start"
                row.active_slot = None
                row.projection_state = LearningPlanProjectionState.NOT_COMMITTED.value
                row.plan_id = ""
                row.commit_contract_version = ""
                row.committed_projection_digest = ""
                row.committed_projection_payload = None
                row.updated_at = now
                row.completed_at = now
                recovered_ids.append(row.operation_id)
        return [
            self.require(operation_id=operation_id, validate_current=False)
            for operation_id in recovered_ids
        ]

    def get_by_client_request_id(
        self,
        *,
        client_request_id: str,
        validate_current: bool = False,
    ) -> LearningPlanOperationRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(LearningPlanOperationRow).where(
                    LearningPlanOperationRow.client_request_id == client_request_id
                )
            )
            if row is None:
                return None
            record = _from_row(row)
            _validate_committed_projection_snapshot(record)
            if validate_current and record.status == LearningPlanOperationStatus.COMMITTED:
                _validate_current_projection(session, record)
            return record

    def require(
        self,
        *,
        operation_id: str,
        validate_current: bool = False,
    ) -> LearningPlanOperationRecord:
        with self.database.session() as session:
            row = session.get(LearningPlanOperationRow, operation_id)
            if row is None:
                raise LearningPlanOperationNotFound(operation_id)
            record = _from_row(row)
            _validate_committed_projection_snapshot(record)
            if validate_current and record.status == LearningPlanOperationStatus.COMMITTED:
                _validate_current_projection(session, record)
            return record

    def _inject(self, stage: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(stage)


def _validate_duplicate(
    record: LearningPlanOperationRecord,
    *,
    fingerprint: str,
) -> None:
    if record.request_fingerprint != fingerprint:
        raise LearningPlanRequestConflict(record.client_request_id)
    if record.status == LearningPlanOperationStatus.RUNNING:
        raise LearningPlanAlreadyActive(record.document_id, record.operation_id)
    if record.status != LearningPlanOperationStatus.COMMITTED:
        raise LearningPlanTerminalReplayBlocked(
            record.client_request_id,
            record.status.value,
        )


def _validate_committed_projection_snapshot(record: LearningPlanOperationRecord) -> None:
    if record.status != LearningPlanOperationStatus.COMMITTED:
        return
    if record.committed_projection is None:
        raise LearningPlanReadBackError(record.operation_id, "projection_missing")
    LearningPlanCommittedProjectionV1.model_validate(
        record.committed_projection.model_dump(mode="json")
    )


def _validate_current_projection(session, record: LearningPlanOperationRecord) -> None:
    projection = record.committed_projection
    if projection is None:
        raise LearningPlanReadBackError(record.operation_id, "projection_missing")
    plan_row = session.get(LearningPlanRow, projection.plan_id)
    if plan_row is None:
        raise LearningPlanReadBackError(record.operation_id, "plan_missing")
    if planning_projection_digest(plan_row.payload or {}) != projection.plan_digest:
        raise LearningPlanReadBackError(record.operation_id, "plan_digest_mismatch")
    if projection.document is not None:
        document_row = session.get(DocumentRow, projection.document_id)
        if document_row is None:
            raise LearningPlanReadBackError(record.operation_id, "document_missing")
        if planning_projection_digest(document_row.payload or {}) != projection.document_digest:
            raise LearningPlanReadBackError(record.operation_id, "document_digest_mismatch")
    if projection.debug_report is not None:
        debug_row = session.get(DocumentDebugRow, projection.document_id)
        if debug_row is None:
            raise LearningPlanReadBackError(record.operation_id, "debug_missing")
        if planning_projection_digest(debug_row.payload or {}) != projection.debug_digest:
            raise LearningPlanReadBackError(record.operation_id, "debug_digest_mismatch")
    if projection.trace is not None:
        trace_key = projection.document_id or projection.plan_id
        trace_row = session.get(PlanningTraceRow, trace_key)
        if trace_row is None:
            raise LearningPlanReadBackError(record.operation_id, "trace_missing")
        if planning_projection_digest(trace_row.payload or {}) != projection.trace_digest:
            raise LearningPlanReadBackError(record.operation_id, "trace_digest_mismatch")


def _apply_document_row(row: DocumentRow, document: DocumentRecord) -> None:
    row.id = document.id
    row.title = document.title
    row.original_filename = document.original_filename
    row.stored_path = document.stored_path
    row.status = document.status
    row.ocr_status = document.ocr_status
    row.created_at = document.created_at
    row.updated_at = document.updated_at
    row.payload = document.model_dump(mode="json")


def _apply_debug_row(row: DocumentDebugRow, report: DocumentDebugRecord) -> None:
    row.document_id = report.document_id
    row.processed_at = report.processed_at
    row.page_count = report.page_count
    row.extraction_method = report.extraction_method
    row.payload = report.model_dump(mode="json")


def _apply_trace_row(
    row: PlanningTraceRow,
    *,
    trace_key: str,
    trace: PlanGenerationTraceRecord,
) -> None:
    row.document_id = trace_key
    row.plan_id = trace.plan_id or ""
    row.model = trace.model
    row.created_at = trace.created_at
    row.payload = trace.model_dump(mode="json")


def _apply_plan_row(row: LearningPlanRow, plan: LearningPlanRecord) -> None:
    row.id = plan.id
    row.document_id = plan.document_id
    row.persona_id = plan.persona_id
    row.creation_mode = plan.creation_mode
    row.course_title = plan.course_title
    row.created_at = plan.created_at
    row.payload = plan.model_dump(mode="json")


def _from_row(row: LearningPlanOperationRow) -> LearningPlanOperationRecord:
    return LearningPlanOperationRecord.model_validate(
        {
            "operation_id": row.operation_id,
            "client_request_id": row.client_request_id,
            "document_id": row.document_id or "",
            "persona_id": row.persona_id,
            "request_schema_version": row.request_schema_version,
            "fingerprint_contract_version": row.fingerprint_contract_version,
            "request_fingerprint": row.request_fingerprint,
            "request_payload": row.request_payload,
            "base_document_updated_at": row.base_document_updated_at,
            "base_document_digest": row.base_document_digest,
            "base_debug_digest": row.base_debug_digest,
            "status": LearningPlanOperationStatus(row.status),
            "projection_state": LearningPlanProjectionState(row.projection_state),
            "provider_started_at": row.provider_started_at,
            "plan_id": row.plan_id,
            "commit_contract_version": row.commit_contract_version,
            "committed_projection_digest": row.committed_projection_digest,
            "committed_projection": row.committed_projection_payload,
            "error_code": row.error_code,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "completed_at": row.completed_at,
        }
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LearningPlanOperationError(RuntimeError):
    pass


class LearningPlanDocumentNotFound(LearningPlanOperationError):
    pass


class LearningPlanStaleDocument(LearningPlanOperationError):
    def __init__(self, document_id: str, *, expected: str, actual: str) -> None:
        super().__init__(f"learning_plan_stale_document:{document_id}:{expected}:{actual}")
        self.document_id = document_id
        self.expected = expected
        self.actual = actual


class LearningPlanProjectionPrerequisiteMissing(LearningPlanOperationError):
    pass


class LearningPlanStaleDebugProjection(LearningPlanOperationError):
    def __init__(self, document_id: str) -> None:
        super().__init__(f"learning_plan_stale_debug_projection:{document_id}")
        self.document_id = document_id


class LearningPlanAlreadyActive(LearningPlanOperationError):
    def __init__(self, scope_key: str, operation_id: str) -> None:
        super().__init__(f"learning_plan_already_active:{scope_key}:{operation_id}")
        self.scope_key = scope_key
        self.operation_id = operation_id


class LearningPlanRequestConflict(LearningPlanOperationError):
    pass


class LearningPlanTerminalReplayBlocked(LearningPlanOperationError):
    def __init__(self, client_request_id: str, status: str) -> None:
        super().__init__(f"learning_plan_terminal_replay_blocked:{status}")
        self.client_request_id = client_request_id
        self.status = status


class LearningPlanAdmissionRace(LearningPlanOperationError):
    pass


class LearningPlanOperationNotFound(LearningPlanOperationError):
    pass


class LearningPlanOperationNotRunning(LearningPlanOperationError):
    pass


class LearningPlanProjectionIdentityMismatch(LearningPlanOperationError):
    pass


class LearningPlanReadBackError(LearningPlanOperationError):
    def __init__(self, operation_id: str, reason: str) -> None:
        super().__init__(f"learning_plan_read_back_failed:{reason}")
        self.operation_id = operation_id
        self.reason = reason
