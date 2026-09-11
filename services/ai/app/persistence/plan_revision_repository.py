from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.models.domain import VersionedLearningPlanRecord
from app.models.harness import (HarnessCommitEvidenceV3, HarnessCommitStatus, HarnessContractRef,
    HarnessDigestAlgorithm, HarnessDigestScope, HarnessResourceRefV3, HarnessResourceType,
    HarnessCommittedResourceRefV3, canonical_harness_digest)
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.harness_runtime_commit import HarnessTransactionFinalizer, HarnessRuntimePreparedOutput
from app.models.plan_revision import (PlanRevisionRequestV1, PlanRevisionResponseV1,
    PlanRevisionProposalV1, PlanRevisionCommittedProjectionV1, apply_patch)
from app.models.plan_progress import refresh_plan_progress
from app.persistence.database import Database
from app.persistence.harness_runtime_repository import _database_utc_now
from app.persistence.harness_operation_repository import HarnessOperationBindingRepository
from app.persistence.learning_plan_repository import archive_plan, plan_from_row
from app.persistence.models import LearningPlanRow, LearningPlanRevisionRow, PlanRevisionOperationRow


class PlanRevisionRepository:
    def __init__(self, database: Database):
        self.database = database
        self.bindings = HarnessOperationBindingRepository(database)

    def admit(self, plan_id: str, request: PlanRevisionRequestV1):
        try:
            with self.database.session() as session:
                existing = session.scalar(select(PlanRevisionOperationRow).where(
                    PlanRevisionOperationRow.plan_id == plan_id,
                    PlanRevisionOperationRow.client_request_id == request.client_request_id))
                if existing is not None:
                    if existing.request != request.model_dump(mode="json"):
                        raise HTTPException(409, "plan_revision_request_mismatch")
                    return response(existing), None
                plan_row = session.get(LearningPlanRow, plan_id)
                if plan_row is None or plan_row.deleted:
                    raise HTTPException(404, "plan_not_found")
                plan = refresh_plan_progress(plan_from_row(plan_row))
                if plan.revision != request.base_revision:
                    raise HTTPException(409, "learning_plan_revision_conflict")
                now = _database_utc_now(session)
                row = PlanRevisionOperationRow(operation_id=f"plan-revision-{uuid4().hex}",
                    plan_id=plan_id, client_request_id=request.client_request_id,
                    base_revision=plan.revision, status="generating", request=request.model_dump(mode="json"),
                    base_plan=plan.model_dump(mode="json"), proposal=None, preview_receipt=None,
                    decision_receipt=None, error_code="", created_at=now.isoformat())
                binding = self.bindings._admit_domain_in_session(session, domain_row=row,
                    domain_operation_kind=HarnessDomainOperationKind.LEARNING_PLAN_REVISION,
                    domain_operation_id=row.operation_id, admitted_at=now)
                return response(row), binding
        except IntegrityError:
            with self.database.session() as session:
                existing = session.scalar(select(PlanRevisionOperationRow).where(
                    PlanRevisionOperationRow.plan_id == plan_id,
                    PlanRevisionOperationRow.client_request_id == request.client_request_id))
                if existing is None or existing.request != request.model_dump(mode="json"):
                    raise HTTPException(409, "plan_revision_request_mismatch")
                return response(existing), None

    def get(self, plan_id: str, request_id: str) -> PlanRevisionResponseV1:
        with self.database.session() as session:
            row = session.scalar(select(PlanRevisionOperationRow).where(
                PlanRevisionOperationRow.plan_id == plan_id,
                PlanRevisionOperationRow.client_request_id == request_id))
            if row is None:
                raise HTTPException(404, "plan_revision_not_found")
            self._recover_interrupted_in_session(session, row)
            return response(row)

    def _recover_interrupted_in_session(self, session, row) -> None:
        """Fence the domain and its existing trace together, without provider replay."""
        from app.models.harness import HarnessStatus, HarnessTraceV3, HarnessAttemptRecord, HarnessAttemptPhase, HarnessAttemptStatus
        from app.models.harness_runtime import harness_runtime_terminal_trace_digest, expected_harness_runtime_attempt_id
        from app.persistence.harness_runtime_repository import HarnessRuntimeRepository, _database_utc_now
        from app.persistence.models import HarnessRuntimeExecutionRow

        if row.status not in {"generating", "applying"}:
            return
        now = _database_utc_now(session)
        if (now - datetime.fromisoformat(row.created_at)).total_seconds() <= 240:
            return
        old = row.status
        changed = session.execute(update(PlanRevisionOperationRow).where(
            PlanRevisionOperationRow.operation_id == row.operation_id,
            PlanRevisionOperationRow.status == old,
            PlanRevisionOperationRow.created_at == row.created_at,
        ).values(status="uncertain" if old == "generating" else "failed",
                 error_code="plan_revision_interrupted"))
        if changed.rowcount != 1:
            session.refresh(row)
            return
        runtimes = HarnessRuntimeRepository(self.database)
        active_rows = session.scalars(select(HarnessRuntimeExecutionRow).where(
            HarnessRuntimeExecutionRow.harness_operation_id == row.harness_operation_id,
            HarnessRuntimeExecutionRow.stage == "plan_revision",
            HarnessRuntimeExecutionRow.trace_slot == (0 if old == "generating" else 1),
            HarnessRuntimeExecutionRow.state != "terminal",
        ).with_for_update()).all()
        for active in active_rows:
            execution = runtimes.get_in_session(session, active.trace_id)
            started = execution.execution_started_at or execution.created_at
            index = len(execution.attempt_records) + 1
            attempts = [*execution.attempt_records, HarnessAttemptRecord(
                attempt_id=expected_harness_runtime_attempt_id(execution.trace_id, index),
                attempt_index=index, phase=HarnessAttemptPhase.COMMIT,
                status=HarnessAttemptStatus.FAILED, error_code="plan_revision_interrupted",
                duration_ms=0,
            )]
            trace = HarnessTraceV3(
                trace_schema_version="harness-trace-v3", trace_id=execution.trace_id,
                operation_id=execution.harness_operation_id,
                parent_trace_id=execution.parent_trace_id, workflow=execution.workflow,
                stage=execution.stage, status=HarnessStatus.FAILED,
                contract=execution.trace_contract, context=execution.context,
                output_digest=None, checks=execution.checks,
                attempt_records=attempts,
                recovery_strategy="query_only_interruption",
                error_code="plan_revision_interrupted",
                duration_ms=max(0, int((now - started).total_seconds() * 1000)),
                commit_evidence=HarnessCommitEvidenceV3(status=HarnessCommitStatus.NOT_COMMITTED,
                    rollback_reason_code="", effect_batch_id=f"{row.operation_id}:interruption",
                    payload_contract=HarnessContractRef(name="PlanRevisionCommittedProjection", version="plan-revision-committed-projection-v1"),
                    digest_algorithm=HarnessDigestAlgorithm.SHA256, digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                    attempted_resource_refs=[HarnessResourceRefV3(resource_type=HarnessResourceType.PLAN_REVISION,
                        resource_id=f"{row.operation_id}:preview" if old == "generating" else f"{row.operation_id}:accept")]),
                started_at=started, completed_at=now,
            )
            # The operation fence above authorizes interruption even if the provider
            # is still running. Exact claim/state fencing prevents a stale writer
            # from appending or committing after this atomic recovery transaction.
            fenced = session.execute(update(HarnessRuntimeExecutionRow).where(
                HarnessRuntimeExecutionRow.trace_id == active.trace_id,
                HarnessRuntimeExecutionRow.state == active.state,
                HarnessRuntimeExecutionRow.claim_token == active.claim_token,
                HarnessRuntimeExecutionRow.claim_count == active.claim_count,
                HarnessRuntimeExecutionRow.updated_at == active.updated_at,
            ).values(state="terminal", claim_owner="", claim_token="", lease_expires_at="",
                     attempt_records=[item.model_dump(mode="json") for item in attempts],
                     terminal_trace=trace.model_dump(mode="json", exclude_none=False),
                     terminal_trace_digest=harness_runtime_terminal_trace_digest(trace),
                     updated_at=now.isoformat()))
            if fenced.rowcount != 1:
                raise HTTPException(409, "plan_revision_recovery_conflict")
        session.refresh(row)

    def history(self, plan_id: str) -> list[int]:
        with self.database.session() as session:
            row = session.get(LearningPlanRow, plan_id)
            if row is None or row.deleted:
                raise HTTPException(404, "plan_not_found")
            return sorted(set(session.scalars(select(LearningPlanRevisionRow.revision).where(
                LearningPlanRevisionRow.plan_id == plan_id))) | {row.revision}, reverse=True)

    def historical(self, plan_id: str, revision: int) -> VersionedLearningPlanRecord:
        with self.database.session() as session:
            current = session.get(LearningPlanRow, plan_id)
            if current is None or current.deleted:
                raise HTTPException(404, "plan_not_found")
            if current.revision == revision:
                return plan_from_row(current)
            row = session.get(LearningPlanRevisionRow, (plan_id, revision))
            if row is None:
                raise HTTPException(404, "plan_revision_history_not_found")
            return VersionedLearningPlanRecord.model_validate(deepcopy(row.payload))

    def begin_accept(self, record: PlanRevisionResponseV1) -> bool:
        with self.database.session() as session:
            changed = session.execute(update(PlanRevisionOperationRow).where(
                PlanRevisionOperationRow.operation_id == record.operation_id,
                PlanRevisionOperationRow.status == "ready",
            ).values(status="applying", created_at=_database_utc_now(session).isoformat()))
            return changed.rowcount == 1

    def reject(self, record: PlanRevisionResponseV1) -> None:
        with self.database.session() as session:
            changed = session.execute(update(PlanRevisionOperationRow).where(
                PlanRevisionOperationRow.operation_id == record.operation_id,
                PlanRevisionOperationRow.status == "ready",
            ).values(status="rejected"))
            if changed.rowcount != 1:
                raise HTTPException(409, "plan_revision_decision_conflict")

    def fail(self, operation_id: str, *, status: str, prepared=None, runtime=None):
        with self.database.session() as session:
            session.execute(update(PlanRevisionOperationRow).where(
                PlanRevisionOperationRow.operation_id == operation_id,
                PlanRevisionOperationRow.status.in_(["generating", "applying"]),
            ).values(status=status, error_code=f"plan_revision_{status}"))
            if prepared is not None:
                runtime.fail_prepared_in_session(session, prepared=prepared,
                    commit_evidence=HarnessCommitEvidenceV3(status=HarnessCommitStatus.NOT_COMMITTED, rollback_reason_code="",
                        effect_batch_id=f"{operation_id}:failure",
                        payload_contract=HarnessContractRef(name="PlanRevisionCommittedProjection", version="plan-revision-committed-projection-v1"),
                        digest_algorithm=HarnessDigestAlgorithm.SHA256, digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                        attempted_resource_refs=[HarnessResourceRefV3(resource_type=HarnessResourceType.PLAN_REVISION,
                            resource_id=f"{operation_id}:accept" if prepared.execution.trace_slot else f"{operation_id}:preview")]),
                    error_code=f"plan_revision_{status}")

    def commit(self, record: PlanRevisionResponseV1, *, proposal: PlanRevisionProposalV1,
               action: str, prepared: HarnessRuntimePreparedOutput, runtime: HarnessTransactionFinalizer):
        with self.database.session() as session:
            row = session.get(PlanRevisionOperationRow, record.operation_id)
            expected_status = "generating" if action == "preview" else "applying"
            if row is None or row.status != expected_status:
                raise HTTPException(409, "plan_revision_fenced")
            current = runtime.get_execution_in_session(session, prepared.claim.trace_id)
            if (current is None or current.harness_operation_id != row.harness_operation_id
                or prepared.execution.harness_operation_id != row.harness_operation_id
                or current.stage.value != "plan_revision" or current.trace_slot != (0 if action == "preview" else 1)
                or not isinstance(prepared.output, PlanRevisionProposalV1)
                or canonical_harness_digest(prepared.output) != prepared.output_digest
                or prepared.output != proposal
                or not current.attempt_records or current.attempt_records[-1].output_digest != prepared.output_digest):
                raise ValueError("plan_revision_runtime_binding_mismatch")
            validated = response(row)
            if action == "accept" and proposal != validated.proposal:
                raise ValueError("plan_revision_accepted_proposal_mismatch")
            base = validated.base_plan
            proposal = PlanRevisionProposalV1.model_validate(proposal.model_dump(mode="json"))
            candidate = apply_patch(base, proposal)
            if action == "accept":
                plan_row = session.get(LearningPlanRow, row.plan_id)
                if plan_row is None or plan_row.deleted or plan_row.revision != row.base_revision:
                    raise HTTPException(409, "learning_plan_revision_conflict")
                if refresh_plan_progress(plan_from_row(plan_row)) != base:
                    raise ValueError("plan_revision_base_projection_mismatch")
                candidate.revision = base.revision + 1
                changed = session.execute(update(LearningPlanRow).where(
                    LearningPlanRow.id == base.id, LearningPlanRow.revision == base.revision,
                    LearningPlanRow.deleted == 0,
                ).values(revision=candidate.revision, course_title=candidate.course_title,
                         payload=candidate.model_dump(mode="json")), execution_options={"synchronize_session": False})
                if changed.rowcount != 1:
                    raise HTTPException(409, "learning_plan_revision_conflict")
                archive_plan(session, plan_row)
                session.add(LearningPlanRevisionRow(plan_id=base.id, revision=candidate.revision,
                    payload=candidate.model_dump(mode="json")))
            projection = PlanRevisionCommittedProjectionV1(operation_id=row.operation_id, plan_id=row.plan_id,
                base_revision=row.base_revision, action=action, proposal=proposal,
                plan=candidate if action == "accept" else base)
            receipt = projection.model_dump(mode="json")
            updates = {"status": "ready" if action == "preview" else "accepted",
                       "preview_receipt" if action == "preview" else "decision_receipt": receipt}
            if action == "preview":
                updates["proposal"] = proposal.model_dump(mode="json")
            changed = session.execute(update(PlanRevisionOperationRow).where(
                PlanRevisionOperationRow.operation_id == row.operation_id,
                PlanRevisionOperationRow.status == expected_status,
            ).values(**updates))
            if changed.rowcount != 1:
                raise HTTPException(409, "plan_revision_fenced")
            session.flush()
            session.refresh(row)
            if action == "accept":
                session.refresh(plan_row)
                if plan_row.deleted or plan_from_row(plan_row) != candidate:
                    raise ValueError("plan_revision_plan_readback_mismatch")
            stored = row.preview_receipt if action == "preview" else row.decision_receipt
            if PlanRevisionCommittedProjectionV1.model_validate(stored) != projection:
                raise ValueError("plan_revision_receipt_readback_mismatch")
            digest = canonical_harness_digest(projection)
            resource_id = f"{row.operation_id}:{action}"
            runtime.finalize_prepared_in_session(session, prepared=prepared,
                commit_evidence=HarnessCommitEvidenceV3(status=HarnessCommitStatus.COMMITTED,
                    effect_batch_id=resource_id,
                    payload_contract=HarnessContractRef(name="PlanRevisionCommittedProjection", version="plan-revision-committed-projection-v1"),
                    digest_algorithm=HarnessDigestAlgorithm.SHA256, digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
                    attempted_resource_refs=[HarnessResourceRefV3(resource_type=HarnessResourceType.PLAN_REVISION, resource_id=resource_id)],
                    committed_resources=[HarnessCommittedResourceRefV3(resource_type=HarnessResourceType.PLAN_REVISION,
                        resource_id=resource_id, payload_digest=digest)],
                    payload_digest=digest, committed_at=datetime.now(timezone.utc), rollback_reason_code=""))


def response(row: PlanRevisionOperationRow) -> PlanRevisionResponseV1:
    preview = PlanRevisionCommittedProjectionV1.model_validate(row.preview_receipt) if row.preview_receipt else None
    result = PlanRevisionCommittedProjectionV1.model_validate(row.decision_receipt) if row.decision_receipt else None
    base = VersionedLearningPlanRecord.model_validate(deepcopy(row.base_plan))
    request = PlanRevisionRequestV1.model_validate(row.request)
    if (base.id != row.plan_id or base.revision != row.base_revision
        or request.base_revision != row.base_revision or request.client_request_id != row.client_request_id):
        raise ValueError("plan_revision_base_identity_mismatch")
    for receipt, action in ((preview, "preview"), (result, "accept")):
        if receipt is not None and (receipt.operation_id != row.operation_id or receipt.plan_id != row.plan_id
            or receipt.base_revision != row.base_revision or receipt.action != action):
            raise ValueError("plan_revision_receipt_identity_mismatch")
    if preview is not None and (preview.plan != base or preview.proposal.model_dump(mode="json") != row.proposal):
        raise ValueError("plan_revision_preview_projection_mismatch")
    if result is not None:
        if preview is None or result.proposal != preview.proposal:
            raise ValueError("plan_revision_decision_proposal_mismatch")
        expected = apply_patch(base, preview.proposal)
        expected.revision = base.revision + 1
        if result.plan != expected or row.status != "accepted":
            raise ValueError("plan_revision_decision_projection_mismatch")
    if row.status in {"ready", "applying", "accepted", "rejected", "conflict"} and preview is None:
        raise ValueError("plan_revision_preview_receipt_missing")
    if row.status == "accepted" and result is None:
        raise ValueError("plan_revision_decision_receipt_missing")
    return PlanRevisionResponseV1(operation_id=row.operation_id, client_request_id=row.client_request_id,
        plan_id=row.plan_id, base_revision=row.base_revision, status=row.status,
        instruction=row.request["instruction"], rollback_revision=row.request["rollback_revision"],
        proposal=preview.proposal if preview else None,
        base_plan=VersionedLearningPlanRecord.model_validate(deepcopy(row.base_plan)),
        result=result.plan if result else None, error_code=row.error_code or "")
