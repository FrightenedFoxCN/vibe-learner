from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Literal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.domain import DocumentDebugRecord
from app.models.harness import (
    HarnessAttemptPhase,
    HarnessAttemptRecord,
    HarnessAttemptStatus,
    HarnessCommitEvidenceV3,
    HarnessCommitStatus,
    HarnessCommittedResourceRefV3,
    HarnessDigestAlgorithm,
    HarnessDigestScope,
    HarnessResourceRefV3,
    HarnessResourceType,
    HarnessStage,
    HarnessStatus,
    HarnessTraceV3,
    canonical_harness_digest,
)
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.models.harness_runtime import (
    expected_harness_runtime_attempt_id,
    harness_runtime_terminal_trace_digest,
)
from app.models.harness_runtime_commit import (
    HarnessRuntimePreparedOutput,
    HarnessTransactionFinalizer,
)
from app.models.study_unit_revision import (
    UNIT_REVISION_COMMIT,
    StudyUnitRevisionCommittedProjectionV1,
    StudyUnitRevisionOutputV1,
    StudyUnitRevisionPreviewV1,
    StudyUnitRevisionResponseV1,
    apply_unit_suggestions,
)
from app.persistence.database import Database
from app.persistence.document_repository import (
    document_from_row,
    replace_document_in_session,
)
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.harness_runtime_repository import (
    HarnessRuntimeRepository,
    _database_utc_now,
)
from app.persistence.models import (
    DocumentDebugRow,
    DocumentRow,
    HarnessRuntimeExecutionRow,
    LearningPlanOperationRow,
    StudyUnitRevisionOperationRow,
)


class StudyUnitRevisionRepository:
    def __init__(
        self, database: Database, *, fault_injector: Callable[[str], None] | None = None
    ) -> None:
        self.database = database
        self.bindings = HarnessOperationBindingRepository(database)
        self.fault_injector = fault_injector

    def admit_preview_in_session(
        self,
        session: Session,
        *,
        preview: StudyUnitRevisionPreviewV1,
        debug: DocumentDebugRecord,
    ) -> HarnessOperationBindingV1:
        if canonical_harness_digest(debug) != preview.base_debug_digest:
            raise ValueError("study_unit_revision_debug_snapshot_mismatch")
        row = StudyUnitRevisionOperationRow(
            operation_id=preview.operation_id,
            plan_id=preview.plan_id,
            document_id=preview.base_document.id,
            parent_operation_id=preview.parent_operation_id,
            preview=preview.model_dump(mode="json"),
            base_debug_report=debug.model_dump(mode="json"),
            status="ready",
            decision_receipt=None,
            error_code="",
            updated_at=_database_utc_now(session).isoformat(),
        )
        session.add(row)
        return self.bindings._admit_domain_in_session(
            session,
            domain_row=row,
            domain_operation_kind=HarnessDomainOperationKind.STUDY_UNIT_REVISION,
            domain_operation_id=row.operation_id,
            admitted_at=_database_utc_now(session),
        )

    def get(self, plan_id: str) -> StudyUnitRevisionResponseV1:
        with self.database.session() as session:
            row = self._require_row(session, plan_id)
            self._recover_in_session(session, row)
            return self._response(session, row)

    def validate_preview_in_session(
        self, session: Session, preview: StudyUnitRevisionPreviewV1
    ) -> None:
        record = self._response(session, self._require_row(session, preview.plan_id))
        if record.preview != preview:
            raise ValueError("study_unit_revision_admission_read_back_mismatch")

    def begin_accept(self, plan_id: str, operation_id: str) -> bool:
        with self.database.session() as session:
            row = self._require_row(session, plan_id)
            self._response(session, row)
            changed = session.execute(
                update(StudyUnitRevisionOperationRow)
                .where(
                    StudyUnitRevisionOperationRow.operation_id == operation_id,
                    StudyUnitRevisionOperationRow.plan_id == plan_id,
                    StudyUnitRevisionOperationRow.status == "ready",
                )
                .values(
                    status="applying", updated_at=_database_utc_now(session).isoformat()
                )
            )
            return changed.rowcount == 1

    def reject(self, plan_id: str, operation_id: str) -> None:
        with self.database.session() as session:
            row = self._require_row(session, plan_id)
            self._response(session, row)
            changed = session.execute(
                update(StudyUnitRevisionOperationRow)
                .where(
                    StudyUnitRevisionOperationRow.operation_id == operation_id,
                    StudyUnitRevisionOperationRow.plan_id == plan_id,
                    StudyUnitRevisionOperationRow.status == "ready",
                )
                .values(
                    status="rejected", updated_at=_database_utc_now(session).isoformat()
                )
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "study_unit_revision_decision_conflict")

    def protected_snapshot(self, plan_id: str) -> dict[str, object]:
        with self.database.session() as session:
            row = self._require_row(session, plan_id)
            record = self._response(session, row)
            return {
                "preview": record.preview.model_dump(mode="json"),
                "debug_report": row.base_debug_report,
            }

    def commit(
        self,
        plan_id: str,
        *,
        prepared: HarnessRuntimePreparedOutput,
        runtime: HarnessTransactionFinalizer,
    ) -> None:
        with self.database.session() as session:
            row = self._require_row(session, plan_id)
            # SQLite needs a write fence before reading either projection.
            changed = session.execute(
                update(StudyUnitRevisionOperationRow)
                .where(
                    StudyUnitRevisionOperationRow.operation_id == row.operation_id,
                    StudyUnitRevisionOperationRow.status == "applying",
                )
                .values(updated_at=StudyUnitRevisionOperationRow.updated_at)
            )
            if changed.rowcount != 1:
                raise HTTPException(409, "study_unit_revision_fenced")
            record = self._response(session, row)
            execution = runtime.get_execution_in_session(
                session, prepared.claim.trace_id
            )
            if (
                execution is None
                or execution.harness_operation_id != row.harness_operation_id
                or prepared.execution.harness_operation_id != row.harness_operation_id
                or execution.stage != HarnessStage.STUDY_UNIT_REVISION
                or execution.trace_slot != 0
                or not isinstance(prepared.output, StudyUnitRevisionOutputV1)
                or canonical_harness_digest(prepared.output) != prepared.output_digest
                or not execution.attempt_records
                or execution.attempt_records[-1].output_digest != prepared.output_digest
            ):
                raise ValueError("study_unit_revision_runtime_binding_mismatch")
            debug = DocumentDebugRecord.model_validate(row.base_debug_report)
            output = prepared.output
            expected = apply_unit_suggestions(
                record.preview, debug, output.document.updated_at
            )
            if output != expected:
                raise ValueError("study_unit_revision_prepared_projection_mismatch")
            current_row = session.get(DocumentRow, row.document_id)
            current_debug = session.get(DocumentDebugRow, row.document_id)
            if (
                current_row is None
                or document_from_row(current_row) != record.preview.base_document
                or current_debug is None
                or canonical_harness_digest(current_debug.payload)
                != record.preview.base_debug_digest
            ):
                raise HTTPException(409, "study_unit_revision_base_conflict")
            replace_document_in_session(
                session,
                output.document,
                expected_revision=record.preview.base_document.revision,
            )
            self._inject("after_document_projection")
            current_debug.payload = output.debug_report.model_dump(mode="json")
            session.flush()
            self._inject("after_debug_projection")
            projection = StudyUnitRevisionCommittedProjectionV1(
                operation_id=row.operation_id,
                preview=record.preview,
                base_debug_report=debug,
                document=output.document,
                debug_report=output.debug_report,
                planning_context_revision=output.document.revision,
            )
            row.status = "accepted"
            row.decision_receipt = projection.model_dump(mode="json")
            row.error_code = ""
            row.updated_at = _database_utc_now(session).isoformat()
            session.flush()
            # Read the stored rows back in the same transaction before claiming commit.
            session.expire(current_row)
            session.expire(current_debug)
            if (
                document_from_row(current_row) != projection.document
                or DocumentDebugRecord.model_validate(current_debug.payload)
                != projection.debug_report
            ):
                raise ValueError("study_unit_revision_commit_read_back_mismatch")
            digest = canonical_harness_digest(projection)
            runtime.finalize_prepared_in_session(
                session,
                prepared=prepared,
                commit_evidence=HarnessCommitEvidenceV3(
                    status=HarnessCommitStatus.COMMITTED,
                    effect_batch_id=f"{row.operation_id}:accept",
                    payload_contract=UNIT_REVISION_COMMIT,
                    digest_algorithm=HarnessDigestAlgorithm.SHA256,
                    digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                    attempted_resource_refs=[self._resource(row.operation_id)],
                    committed_resources=[
                        HarnessCommittedResourceRefV3(
                            resource_type=HarnessResourceType.STUDY_UNIT_REVISION,
                            resource_id=row.operation_id,
                            payload_digest=digest,
                        )
                    ],
                    payload_digest=digest,
                    committed_at=datetime.now(timezone.utc),
                    rollback_reason_code="",
                ),
            )
            self._response(session, row)
            self._inject("before_terminal_commit")

    def fail(
        self,
        plan_id: str,
        *,
        status: Literal["conflict", "failed"],
        prepared: HarnessRuntimePreparedOutput | None = None,
        runtime: HarnessTransactionFinalizer | None = None,
    ) -> None:
        with self.database.session() as session:
            row = self._require_row(session, plan_id)
            changed = session.execute(
                update(StudyUnitRevisionOperationRow)
                .where(
                    StudyUnitRevisionOperationRow.operation_id == row.operation_id,
                    StudyUnitRevisionOperationRow.status == "applying",
                )
                .values(status=status, error_code=f"study_unit_revision_{status}")
            )
            if changed.rowcount == 1 and prepared is not None and runtime is not None:
                runtime.fail_prepared_in_session(
                    session,
                    prepared=prepared,
                    commit_evidence=HarnessCommitEvidenceV3(
                        status=HarnessCommitStatus.NOT_COMMITTED,
                        effect_batch_id=f"{row.operation_id}:accept",
                        payload_contract=UNIT_REVISION_COMMIT,
                        digest_algorithm=HarnessDigestAlgorithm.SHA256,
                        digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                        attempted_resource_refs=[self._resource(row.operation_id)],
                        rollback_reason_code="",
                    ),
                    error_code=f"study_unit_revision_{status}",
                )

    def _require_row(
        self, session: Session, plan_id: str
    ) -> StudyUnitRevisionOperationRow:
        row = session.scalar(
            select(StudyUnitRevisionOperationRow).where(
                StudyUnitRevisionOperationRow.plan_id == plan_id
            )
        )
        if row is None:
            raise HTTPException(404, "study_unit_revision_not_found")
        return row

    def _response(
        self, session: Session, row: StudyUnitRevisionOperationRow
    ) -> StudyUnitRevisionResponseV1:
        from app.models.planning import LearningPlanCommittedProjectionV2

        preview = StudyUnitRevisionPreviewV1.model_validate(row.preview)
        parent = session.get(LearningPlanOperationRow, row.parent_operation_id)
        if parent is None or parent.status != "committed":
            raise ValueError("study_unit_revision_parent_commit_missing")
        projection = LearningPlanCommittedProjectionV2.model_validate(
            parent.committed_projection_payload
        )
        binding = self.bindings.require_domain_in_session(
            session,
            domain_operation_kind=HarnessDomainOperationKind.STUDY_UNIT_REVISION,
            domain_operation_id=row.operation_id,
        )
        if (
            canonical_harness_digest(projection) != parent.committed_projection_digest
            or projection.study_unit_revision != preview
            or projection.study_unit_revision_binding != binding
            or preview.operation_id != row.operation_id
            or preview.plan_id != row.plan_id
            or preview.parent_operation_id != row.parent_operation_id
            or preview.base_document.id != row.document_id
            or canonical_harness_digest(row.base_debug_report)
            != preview.base_debug_digest
        ):
            raise ValueError("study_unit_revision_preview_receipt_mismatch")
        receipt = (
            StudyUnitRevisionCommittedProjectionV1.model_validate(row.decision_receipt)
            if row.decision_receipt is not None
            else None
        )
        if (row.status == "accepted") != (receipt is not None):
            raise ValueError("study_unit_revision_decision_receipt_missing")
        if receipt is not None and (
            receipt.preview != preview or receipt.operation_id != row.operation_id
        ):
            raise ValueError("study_unit_revision_decision_receipt_mismatch")
        if receipt is not None:
            executions = session.scalars(
                select(HarnessRuntimeExecutionRow).where(
                    HarnessRuntimeExecutionRow.harness_operation_id
                    == row.harness_operation_id,
                    HarnessRuntimeExecutionRow.stage
                    == HarnessStage.STUDY_UNIT_REVISION.value,
                    HarnessRuntimeExecutionRow.trace_slot == 0,
                )
            ).all()
            if len(executions) != 1:
                raise ValueError("study_unit_revision_terminal_trace_missing")
            execution = HarnessRuntimeRepository(self.database).get_in_session(
                session, executions[0].trace_id
            )
            trace = execution.terminal_trace if execution is not None else None
            expected_output = StudyUnitRevisionOutputV1(
                document=receipt.document, debug_report=receipt.debug_report
            )
            if (
                trace is None
                or trace.commit_evidence.status != HarnessCommitStatus.COMMITTED
                or trace.commit_evidence.payload_digest
                != canonical_harness_digest(receipt)
                or trace.output_digest != canonical_harness_digest(expected_output)
            ):
                raise ValueError("study_unit_revision_receipt_trace_mismatch")
        return StudyUnitRevisionResponseV1(
            preview=preview,
            status=row.status,
            result=receipt.document if receipt else None,
            planning_context_revision=receipt.planning_context_revision
            if receipt
            else None,
            error_code=row.error_code or "",
        )

    def _recover_in_session(
        self, session: Session, row: StudyUnitRevisionOperationRow
    ) -> None:
        if row.status != "applying":
            return
        now = _database_utc_now(session)
        if (now - datetime.fromisoformat(row.updated_at)).total_seconds() <= 240:
            return
        changed = session.execute(
            update(StudyUnitRevisionOperationRow)
            .where(
                StudyUnitRevisionOperationRow.operation_id == row.operation_id,
                StudyUnitRevisionOperationRow.status == "applying",
                StudyUnitRevisionOperationRow.updated_at == row.updated_at,
            )
            .values(status="failed", error_code="study_unit_revision_interrupted")
        )
        if changed.rowcount != 1:
            session.refresh(row)
            return
        runtimes = HarnessRuntimeRepository(self.database)
        active_rows = session.scalars(
            select(HarnessRuntimeExecutionRow)
            .where(
                HarnessRuntimeExecutionRow.harness_operation_id
                == row.harness_operation_id,
                HarnessRuntimeExecutionRow.stage
                == HarnessStage.STUDY_UNIT_REVISION.value,
                HarnessRuntimeExecutionRow.state != "terminal",
            )
            .with_for_update()
        ).all()
        for active in active_rows:
            execution = runtimes.get_in_session(session, active.trace_id)
            started = execution.execution_started_at or execution.created_at
            index = len(execution.attempt_records) + 1
            attempts = [
                *execution.attempt_records,
                HarnessAttemptRecord(
                    attempt_id=expected_harness_runtime_attempt_id(
                        execution.trace_id, index
                    ),
                    attempt_index=index,
                    phase=HarnessAttemptPhase.COMMIT,
                    status=HarnessAttemptStatus.FAILED,
                    error_code="study_unit_revision_interrupted",
                    duration_ms=0,
                ),
            ]
            trace = HarnessTraceV3(
                trace_schema_version="harness-trace-v3",
                trace_id=execution.trace_id,
                operation_id=execution.harness_operation_id,
                parent_trace_id=execution.parent_trace_id,
                workflow=execution.workflow,
                stage=execution.stage,
                status=HarnessStatus.FAILED,
                contract=execution.trace_contract,
                context=execution.context,
                output_digest=None,
                checks=execution.checks,
                attempt_records=attempts,
                recovery_strategy="query_only_interruption",
                error_code="study_unit_revision_interrupted",
                started_at=started,
                completed_at=now,
                duration_ms=max(0, int((now - started).total_seconds() * 1000)),
                commit_evidence=HarnessCommitEvidenceV3(
                    status=HarnessCommitStatus.NOT_COMMITTED,
                    effect_batch_id=f"{row.operation_id}:accept",
                    payload_contract=UNIT_REVISION_COMMIT,
                    digest_algorithm=HarnessDigestAlgorithm.SHA256,
                    digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                    attempted_resource_refs=[self._resource(row.operation_id)],
                    rollback_reason_code="",
                ),
            )
            fenced = session.execute(
                update(HarnessRuntimeExecutionRow)
                .where(
                    HarnessRuntimeExecutionRow.trace_id == active.trace_id,
                    HarnessRuntimeExecutionRow.state == active.state,
                    HarnessRuntimeExecutionRow.claim_token == active.claim_token,
                    HarnessRuntimeExecutionRow.claim_count == active.claim_count,
                    HarnessRuntimeExecutionRow.updated_at == active.updated_at,
                )
                .values(
                    state="terminal",
                    claim_owner="",
                    claim_token="",
                    lease_expires_at="",
                    attempt_records=[item.model_dump(mode="json") for item in attempts],
                    terminal_trace=trace.model_dump(mode="json", exclude_none=False),
                    terminal_trace_digest=harness_runtime_terminal_trace_digest(trace),
                    updated_at=now.isoformat(),
                )
            )
            if fenced.rowcount != 1:
                raise HTTPException(409, "study_unit_revision_recovery_conflict")
        session.refresh(row)

    @staticmethod
    def _resource(operation_id: str) -> HarnessResourceRefV3:
        return HarnessResourceRefV3(
            resource_type=HarnessResourceType.STUDY_UNIT_REVISION,
            resource_id=operation_id,
        )

    def _inject(self, stage: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(stage)
