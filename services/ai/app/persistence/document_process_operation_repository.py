from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.document_process_operation import (
    DOCUMENT_PROCESS_COMMIT_CONTRACT_VERSION,
    DOCUMENT_PROCESS_FINGERPRINT_CONTRACT_VERSION,
    DOCUMENT_PROCESS_REQUEST_SCHEMA_VERSION,
    DocumentProcessOperationRecord,
    DocumentProcessOperationStatus,
    DocumentProcessProjectionState,
    DocumentProcessRequestPayload,
    DocumentProcessCommittedProjectionV1,
    document_process_projection_digest,
    document_process_request_fingerprint,
)
from app.models.harness import (
    HarnessAttemptPhase,
    HarnessAttemptStatus,
    HarnessCommitEvidenceV3,
    HarnessCommitStatus,
    HarnessCommittedResourceRefV3,
    HarnessContractRef,
    HarnessDigestAlgorithm,
    HarnessDigestScope,
    HarnessResourceRefV3,
    HarnessResourceType,
    HarnessStage,
    HarnessWorkflow,
    canonical_harness_digest,
)
from app.services.harness_runtime import HarnessOperationRuntime, HarnessRuntimePreparedOutput
from app.models.domain import DocumentDebugRecord, DocumentRecord, DocumentSection
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.persistence.database import Database
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.models import (
    DocumentDebugRow,
    DocumentProcessOperationRow,
    DocumentRow,
)


class DocumentProcessOperationRepository:
    """Durable terminal truth and atomic projection boundary for Document processing."""

    def __init__(
        self,
        database: Database,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ) -> None:
        self.database = database
        self.fault_injector = fault_injector
        self.harness_operations = HarnessOperationBindingRepository(database)

    def admit(
        self,
        *,
        document_id: str,
        force_ocr: bool,
    ) -> tuple[DocumentProcessOperationRecord, DocumentRecord]:
        operation_id = f"document-process-op-{uuid4().hex[:16]}"
        request_payload = DocumentProcessRequestPayload(
            document_id=document_id,
            force_ocr=force_ocr,
        )
        now = _now()
        try:
            with self.database.session() as session:
                document_row = session.get(DocumentRow, document_id)
                if document_row is None:
                    raise DocumentProcessDocumentNotFound(document_id)
                active = session.scalar(
                    select(DocumentProcessOperationRow).where(
                        DocumentProcessOperationRow.document_id == document_id,
                        DocumentProcessOperationRow.active_slot == 1,
                    )
                )
                if active is not None:
                    raise DocumentProcessAlreadyActive(document_id, active.operation_id)
                base_document = DocumentRecord.model_validate(document_row.payload or {})
                if base_document.status == "processing":
                    raise DocumentProcessStateConflict(document_id)
                processing_document = base_document.model_copy(deep=True)
                processing_document.status = "processing"
                processing_document.updated_at = now
                _apply_document_row(document_row, processing_document)
                row = DocumentProcessOperationRow(
                    operation_id=operation_id,
                    document_id=document_id,
                    request_schema_version=DOCUMENT_PROCESS_REQUEST_SCHEMA_VERSION,
                    fingerprint_contract_version=DOCUMENT_PROCESS_FINGERPRINT_CONTRACT_VERSION,
                    request_fingerprint=document_process_request_fingerprint(request_payload),
                    request_payload=request_payload.model_dump(mode="json"),
                    status=DocumentProcessOperationStatus.RUNNING.value,
                    active_slot=1,
                    projection_state=DocumentProcessProjectionState.PENDING.value,
                    base_document_payload=base_document.model_dump(mode="json"),
                    document_digest="",
                    debug_digest="",
                    commit_contract_version="",
                    error_code="",
                    created_at=now,
                    updated_at=now,
                    completed_at="",
                )
                session.add(row)
                self.harness_operations._admit_domain_in_session(
                    session,
                    domain_row=row,
                    domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                    domain_operation_id=operation_id,
                    admitted_at=now,
                )
                session.flush()
                return _from_row(row), processing_document
        except IntegrityError as exc:
            active = self.get_active(document_id=document_id)
            if active is not None:
                raise DocumentProcessAlreadyActive(document_id, active.operation_id) from exc
            raise DocumentProcessAdmissionRace(document_id) from exc

    def commit_success(
        self,
        *,
        operation_id: str,
        document: DocumentRecord,
        debug_report: DocumentDebugRecord,
        harness_runtime: HarnessOperationRuntime | None = None,
        runtime_prepared: HarnessRuntimePreparedOutput | None = None,
    ) -> DocumentProcessOperationRecord:
        document_payload = document.model_dump(mode="json")
        debug_payload = debug_report.model_dump(mode="json")
        now = _now()
        with self.database.session() as session:
            operation = session.get(DocumentProcessOperationRow, operation_id)
            if operation is None:
                raise DocumentProcessOperationNotFound(operation_id)
            if operation.status != DocumentProcessOperationStatus.RUNNING.value:
                raise DocumentProcessOperationNotRunning(operation_id, operation.status)
            binding = self.harness_operations.require_domain_in_session(
                session,
                domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                domain_operation_id=operation_id,
            )
            self._validate_runtime_prepared_in_session(
                session,
                binding=binding,
                harness_runtime=harness_runtime,
                runtime_prepared=runtime_prepared,
            )
            if operation.document_id != document.id or debug_report.document_id != document.id:
                raise DocumentProcessProjectionIdentityMismatch(operation_id)
            if runtime_prepared is not None:
                _validate_runtime_document_projection(
                    runtime_prepared=runtime_prepared,
                    base=DocumentRecord.model_validate(operation.base_document_payload or {}),
                    document=document,
                    debug_report=debug_report,
                )
            document_row = session.get(DocumentRow, document.id)
            if document_row is None:
                raise DocumentProcessDocumentNotFound(document.id)

            self._inject("before_debug_projection")
            debug_row = session.get(DocumentDebugRow, document.id) or DocumentDebugRow()
            _apply_debug_row(debug_row, debug_report)
            session.add(debug_row)
            session.flush()
            self._inject("after_debug_projection")

            _apply_document_row(document_row, document)
            session.flush()
            self._inject("after_document_projection")

            operation.status = DocumentProcessOperationStatus.COMMITTED.value
            operation.active_slot = None
            operation.projection_state = DocumentProcessProjectionState.COMMITTED.value
            operation.document_digest = document_process_projection_digest(document_payload)
            operation.debug_digest = document_process_projection_digest(debug_payload)
            operation.commit_contract_version = DOCUMENT_PROCESS_COMMIT_CONTRACT_VERSION
            operation.error_code = ""
            operation.updated_at = now
            operation.completed_at = now
            session.flush()
            if (harness_runtime is None) != (runtime_prepared is None):
                raise ValueError("document_process_runtime_commit_pair_required")
            if harness_runtime is not None and runtime_prepared is not None:
                projection = DocumentProcessCommittedProjectionV1(
                    operation_id=operation_id,
                    document_id=document.id,
                    document=document,
                    debug_report=debug_report,
                    document_digest=operation.document_digest,
                    debug_digest=operation.debug_digest,
                )
                projection_digest = canonical_harness_digest(projection)
                harness_runtime.finalize_prepared_in_session(
                    session,
                    prepared=runtime_prepared,
                    commit_evidence=HarnessCommitEvidenceV3(
                        status=HarnessCommitStatus.COMMITTED,
                        effect_batch_id=f"document-commit-{operation_id}",
                        payload_contract=HarnessContractRef(
                            name="DocumentProcessCommittedProjection",
                            version="document-process-committed-projection-v1",
                        ),
                        digest_algorithm=HarnessDigestAlgorithm.SHA256,
                        digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                        attempted_resource_refs=[
                            HarnessResourceRefV3(
                                resource_type=HarnessResourceType.DOCUMENT,
                                resource_id=document.id,
                            )
                        ],
                        committed_resources=[
                            HarnessCommittedResourceRefV3(
                                resource_type=HarnessResourceType.DOCUMENT,
                                resource_id=document.id,
                                payload_digest=projection_digest,
                            )
                        ],
                        payload_digest=projection_digest,
                        committed_at=datetime.now(timezone.utc),
                        rollback_reason_code="",
                    ),
                )
            self._inject("before_terminal_commit")

        return self.require(operation_id=operation_id, validate_read_back=True)

    def mark_failed(
        self,
        *,
        operation_id: str,
        error_code: str,
        harness_runtime: HarnessOperationRuntime | None = None,
        runtime_prepared: HarnessRuntimePreparedOutput | None = None,
    ) -> DocumentProcessOperationRecord:
        return self._mark_not_committed(
            operation_id=operation_id,
            status=DocumentProcessOperationStatus.FAILED,
            error_code=error_code,
            restore_base=False,
            harness_runtime=harness_runtime,
            runtime_prepared=runtime_prepared,
        )

    def mark_interrupted(
        self,
        *,
        operation_id: str,
        error_code: str = "document_process_interrupted",
        harness_runtime: HarnessOperationRuntime | None = None,
        runtime_prepared: HarnessRuntimePreparedOutput | None = None,
    ) -> DocumentProcessOperationRecord:
        return self._mark_not_committed(
            operation_id=operation_id,
            status=DocumentProcessOperationStatus.INTERRUPTED,
            error_code=error_code,
            restore_base=True,
            harness_runtime=harness_runtime,
            runtime_prepared=runtime_prepared,
        )

    def recover_abandoned(self) -> list[DocumentProcessOperationRecord]:
        recovered_ids: list[str] = []
        with self.database.session() as session:
            rows = session.scalars(
                select(DocumentProcessOperationRow).where(
                    DocumentProcessOperationRow.status == DocumentProcessOperationStatus.RUNNING.value,
                    DocumentProcessOperationRow.active_slot == 1,
                )
            ).all()
            for row in rows:
                document_row = session.get(DocumentRow, row.document_id)
                if document_row is not None:
                    base = DocumentRecord.model_validate(row.base_document_payload or {})
                    failed_document = _failed_document_from_base(base, now=_now())
                    _apply_document_row(document_row, failed_document)
                now = _now()
                row.status = DocumentProcessOperationStatus.FAILED.value
                row.active_slot = None
                row.projection_state = DocumentProcessProjectionState.NOT_COMMITTED.value
                resolution = self.harness_operations.resolve_domain_in_session(
                    session,
                    domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                    domain_operation_id=row.operation_id,
                )
                row.error_code = (
                    "document_process_harness_operation_legacy_unbound"
                    if resolution.binding is None
                    else "document_process_abandoned_on_startup"
                )
                row.document_digest = ""
                row.debug_digest = ""
                row.commit_contract_version = ""
                row.updated_at = now
                row.completed_at = now
                recovered_ids.append(row.operation_id)
        return [self.require(operation_id=item) for item in recovered_ids]

    def require_harness_operation(
        self,
        operation_id: str,
    ) -> HarnessOperationBindingV1:
        return self.harness_operations.require_domain(
            domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
            domain_operation_id=operation_id,
        )

    def get_active(self, *, document_id: str) -> DocumentProcessOperationRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(DocumentProcessOperationRow).where(
                    DocumentProcessOperationRow.document_id == document_id,
                    DocumentProcessOperationRow.active_slot == 1,
                )
            )
            return _from_row(row) if row is not None else None

    def latest(
        self,
        *,
        document_id: str,
        validate_read_back: bool = True,
    ) -> DocumentProcessOperationRecord | None:
        with self.database.session() as session:
            row = session.scalar(
                select(DocumentProcessOperationRow)
                .where(DocumentProcessOperationRow.document_id == document_id)
                .order_by(
                    DocumentProcessOperationRow.created_at.desc(),
                    DocumentProcessOperationRow.operation_id.desc(),
                )
                .limit(1)
            )
            if row is None:
                return None
            record = _from_row(row)
            if validate_read_back and record.status == DocumentProcessOperationStatus.COMMITTED:
                _validate_read_back(
                    record,
                    document_row=session.get(DocumentRow, document_id),
                    debug_row=session.get(DocumentDebugRow, document_id),
                )
            return record

    def require(
        self,
        *,
        operation_id: str,
        validate_read_back: bool = True,
    ) -> DocumentProcessOperationRecord:
        with self.database.session() as session:
            row = session.get(DocumentProcessOperationRow, operation_id)
            if row is None:
                raise DocumentProcessOperationNotFound(operation_id)
            record = _from_row(row)
            if validate_read_back and record.status == DocumentProcessOperationStatus.COMMITTED:
                _validate_read_back(
                    record,
                    document_row=session.get(DocumentRow, record.document_id),
                    debug_row=session.get(DocumentDebugRow, record.document_id),
                )
            return record

    def _mark_not_committed(
        self,
        *,
        operation_id: str,
        status: DocumentProcessOperationStatus,
        error_code: str,
        restore_base: bool,
        harness_runtime: HarnessOperationRuntime | None = None,
        runtime_prepared: HarnessRuntimePreparedOutput | None = None,
    ) -> DocumentProcessOperationRecord:
        now = _now()
        with self.database.session() as session:
            row = session.get(DocumentProcessOperationRow, operation_id)
            if row is None:
                raise DocumentProcessOperationNotFound(operation_id)
            if row.status == DocumentProcessOperationStatus.COMMITTED.value:
                return _from_row(row)
            if row.status != DocumentProcessOperationStatus.RUNNING.value:
                return _from_row(row)
            resolution = self.harness_operations.resolve_domain_in_session(
                session,
                domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                domain_operation_id=operation_id,
            )
            self._validate_runtime_prepared_in_session(
                session,
                binding=resolution.binding,
                harness_runtime=harness_runtime,
                runtime_prepared=runtime_prepared,
            )
            document_row = session.get(DocumentRow, row.document_id)
            if document_row is not None:
                base = DocumentRecord.model_validate(row.base_document_payload or {})
                terminal_document = (
                    base.model_copy(deep=True)
                    if restore_base
                    else _failed_document_from_base(base, now=now)
                )
                terminal_document.updated_at = now
                _apply_document_row(document_row, terminal_document)
            row.status = status.value
            row.active_slot = None
            row.projection_state = DocumentProcessProjectionState.NOT_COMMITTED.value
            row.document_digest = ""
            row.debug_digest = ""
            row.commit_contract_version = ""
            row.error_code = (
                "document_process_harness_operation_legacy_unbound"
                if resolution.binding is None
                else error_code[:128] or "document_process_failed"
            )
            row.updated_at = now
            row.completed_at = now
            if (harness_runtime is None) != (runtime_prepared is None):
                raise ValueError("document_process_runtime_failure_pair_required")
            if harness_runtime is not None and runtime_prepared is not None:
                harness_runtime.fail_prepared_in_session(
                    session,
                    prepared=runtime_prepared,
                    commit_evidence=HarnessCommitEvidenceV3(
                        status=HarnessCommitStatus.NOT_COMMITTED,
                        effect_batch_id=f"document-commit-{operation_id}",
                        payload_contract=HarnessContractRef(
                            name="DocumentProcessCommittedProjection",
                            version="document-process-committed-projection-v1",
                        ),
                        digest_algorithm=HarnessDigestAlgorithm.SHA256,
                        digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                        attempted_resource_refs=[
                            HarnessResourceRefV3(
                                resource_type=HarnessResourceType.DOCUMENT,
                                resource_id=row.document_id,
                            )
                        ],
                        rollback_reason_code="",
                    ),
                    error_code=row.error_code,
                )
        return self.require(operation_id=operation_id, validate_read_back=False)

    def _validate_runtime_prepared_in_session(
        self,
        session: Session,
        *,
        binding: HarnessOperationBindingV1 | None,
        harness_runtime: HarnessOperationRuntime | None,
        runtime_prepared: HarnessRuntimePreparedOutput | None,
    ) -> None:
        if (harness_runtime is None) != (runtime_prepared is None):
            raise ValueError("document_process_runtime_pair_required")
        if harness_runtime is None or runtime_prepared is None:
            return
        from app.services.harness_broad_adoption import DocumentProcessRuntimeOutputV1

        current = harness_runtime.repository.get_in_session(
            session, runtime_prepared.claim.trace_id
        )
        if (
            binding is None
            or binding.domain_operation_kind != HarnessDomainOperationKind.DOCUMENT_PROCESS
            or current is None
            or current.trace_id != runtime_prepared.execution.trace_id
            or current.harness_operation_id != binding.harness_operation_id
            or current.workflow != HarnessWorkflow.DOCUMENT_PARSE
            or current.stage != HarnessStage.DOCUMENT_PARSE
            or current.trace_slot != 0
            or current.parent_trace_id is not None
            or current.trace_contract != HarnessContractRef(
                name="DocumentProcessRuntimeOutput",
                version="document-process-runtime-output-v1",
            )
            or runtime_prepared.execution.harness_operation_id != binding.harness_operation_id
        ):
            raise ValueError("document_process_runtime_binding_mismatch")
        attempts = current.attempt_records
        if (
            not isinstance(runtime_prepared.output, DocumentProcessRuntimeOutputV1)
            or not attempts
            or attempts[-1].phase != HarnessAttemptPhase.VALIDATE
            or attempts[-1].status != HarnessAttemptStatus.PASSED
            or attempts[-1].output_digest != runtime_prepared.output_digest
            or canonical_harness_digest(runtime_prepared.output) != runtime_prepared.output_digest
        ):
            raise ValueError("document_process_runtime_output_mismatch")

    def _inject(self, stage: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(stage)


def _validate_runtime_document_projection(
    *,
    runtime_prepared: HarnessRuntimePreparedOutput,
    base: DocumentRecord,
    document: DocumentRecord,
    debug_report: DocumentDebugRecord,
) -> None:
    output = runtime_prepared.output
    report = output.debug_report.model_copy(deep=True)
    units = output.study_units
    report.study_units = units
    expected = base.model_copy(deep=True)
    expected.status = "processed"
    expected.ocr_status = report.ocr_status
    expected.study_units = units
    expected.study_unit_count = len(units)
    expected.sections = [
        DocumentSection(
            id=unit.id,
            document_id=unit.document_id,
            title=unit.title,
            page_start=unit.page_start,
            page_end=unit.page_end,
            level=1,
        )
        for unit in units
        if unit.include_in_plan
    ]
    expected.page_count = report.page_count
    expected.chunk_count = len(report.chunks)
    expected.preview_excerpt = next(
        (page.text_preview for page in report.pages if page.text_preview), ""
    )
    expected.debug_ready = True
    expected.updated_at = document.updated_at
    if (
        canonical_harness_digest(document) != canonical_harness_digest(expected)
        or canonical_harness_digest(debug_report) != canonical_harness_digest(report)
    ):
        raise ValueError("document_process_runtime_projection_mismatch")


def _apply_document_row(row: DocumentRow, document: DocumentRecord) -> None:
    payload = document.model_dump(mode="json")
    row.id = document.id
    row.title = document.title
    row.original_filename = document.original_filename
    row.stored_path = document.stored_path
    row.status = document.status
    row.ocr_status = document.ocr_status
    row.created_at = document.created_at
    row.updated_at = document.updated_at
    row.payload = payload


def _apply_debug_row(row: DocumentDebugRow, report: DocumentDebugRecord) -> None:
    row.document_id = report.document_id
    row.processed_at = report.processed_at
    row.page_count = report.page_count
    row.extraction_method = report.extraction_method
    row.payload = report.model_dump(mode="json")


def _failed_document_from_base(base: DocumentRecord, *, now: str) -> DocumentRecord:
    failed = base.model_copy(deep=True)
    failed.status = "failed"
    failed.ocr_status = "failed"
    failed.updated_at = now
    return failed


def _from_row(row: DocumentProcessOperationRow) -> DocumentProcessOperationRecord:
    return DocumentProcessOperationRecord.model_validate(
        {
            "operation_id": row.operation_id,
            "document_id": row.document_id,
            "request_schema_version": row.request_schema_version,
            "fingerprint_contract_version": row.fingerprint_contract_version,
            "request_fingerprint": row.request_fingerprint,
            "request_payload": row.request_payload,
            "status": row.status,
            "projection_state": row.projection_state,
            "base_document_payload": row.base_document_payload,
            "document_digest": row.document_digest,
            "debug_digest": row.debug_digest,
            "commit_contract_version": row.commit_contract_version,
            "error_code": row.error_code,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "completed_at": row.completed_at,
        }
    )


def _validate_read_back(
    record: DocumentProcessOperationRecord,
    *,
    document_row: DocumentRow | None,
    debug_row: DocumentDebugRow | None,
) -> None:
    if document_row is None or debug_row is None:
        raise DocumentProcessReadBackError(record.operation_id, "projection_missing")
    document_digest = document_process_projection_digest(document_row.payload or {})
    debug_digest = document_process_projection_digest(debug_row.payload or {})
    if document_digest != record.document_digest:
        raise DocumentProcessReadBackError(record.operation_id, "document_digest_mismatch")
    if debug_digest != record.debug_digest:
        raise DocumentProcessReadBackError(record.operation_id, "debug_digest_mismatch")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentProcessError(RuntimeError):
    pass


class DocumentProcessDocumentNotFound(DocumentProcessError):
    pass


class DocumentProcessAlreadyActive(DocumentProcessError):
    def __init__(self, document_id: str, operation_id: str) -> None:
        super().__init__(f"document_process_already_active:{document_id}:{operation_id}")
        self.document_id = document_id
        self.operation_id = operation_id


class DocumentProcessStateConflict(DocumentProcessError):
    pass


class DocumentProcessAdmissionRace(DocumentProcessError):
    pass


class DocumentProcessOperationNotFound(DocumentProcessError):
    pass


class DocumentProcessOperationNotRunning(DocumentProcessError):
    pass


class DocumentProcessProjectionIdentityMismatch(DocumentProcessError):
    pass


class DocumentProcessReadBackError(DocumentProcessError):
    def __init__(self, operation_id: str, reason: str) -> None:
        super().__init__(f"document_process_read_back_failed:{reason}")
        self.operation_id = operation_id
        self.reason = reason
