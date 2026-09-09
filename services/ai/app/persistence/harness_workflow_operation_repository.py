from __future__ import annotations

from datetime import UTC, datetime
from typing import Mapping
from uuid import uuid4

from sqlalchemy import select

from app.models.harness import HarnessStatus, HarnessTraceV3, canonical_harness_digest
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.persistence.database import Database
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.models import HarnessRuntimeExecutionRow, HarnessWorkflowOperationRow


_SUPPORTED_KINDS = {
    HarnessDomainOperationKind.FRONTEND_DECODE,
    HarnessDomainOperationKind.DOCUMENT_OCR,
    HarnessDomainOperationKind.STUDY_UNIT_CLEANUP,
    HarnessDomainOperationKind.PERSONA_GENERATION,
    HarnessDomainOperationKind.SCENE_GENERATION,
}


class HarnessWorkflowOperationRepository:
    """Admit proposal/heuristic workflows that have no domain operation table."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.bindings = HarnessOperationBindingRepository(database)

    def admit(
        self,
        *,
        kind: HarnessDomainOperationKind,
        request_manifest: Mapping[str, object],
        operation_id: str | None = None,
    ) -> HarnessOperationBindingV1:
        if kind not in _SUPPORTED_KINDS:
            raise ValueError("harness_workflow_operation_kind_unsupported")
        identity = operation_id or f"{kind.value}-op-{uuid4().hex}"
        now = datetime.now(UTC)
        row = HarnessWorkflowOperationRow(
            operation_id=identity,
            domain_operation_kind=kind.value,
            request_digest=canonical_harness_digest(dict(request_manifest)),
            status="running",
            error_code="",
            created_at=now.isoformat(),
            completed_at="",
        )
        with self.database.session() as session:
            binding = self.bindings._admit_domain_in_session(
                session,
                domain_row=row,
                domain_operation_kind=kind,
                domain_operation_id=identity,
                admitted_at=now,
            )
        return binding

    def terminalize(
        self,
        *,
        binding: HarnessOperationBindingV1,
        success: bool,
        error_code: str = "",
    ) -> None:
        with self.database.session() as session:
            row = session.get(
                HarnessWorkflowOperationRow,
                binding.domain_operation_id,
            )
            if row is None or row.harness_operation_id != binding.harness_operation_id:
                raise ValueError("harness_workflow_operation_binding_mismatch")
            if row.status != "running":
                return
            row.status = "completed" if success else "failed"
            row.error_code = "" if success else (error_code.strip()[:160] or "workflow_failed")
            row.completed_at = datetime.now(UTC).isoformat()

    def recover_abandoned_operations(self) -> int:
        """Close generic operations left running across a process restart.

        A terminal runtime trace is authoritative when it exists; otherwise the
        operation is failed closed so callers cannot replay an unknown proposal.
        """
        recovered = 0
        with self.database.session() as session:
            rows = session.scalars(
                select(HarnessWorkflowOperationRow).where(
                    HarnessWorkflowOperationRow.status == "running"
                )
            )
            for row in rows:
                traces = session.scalars(
                    select(HarnessRuntimeExecutionRow).where(
                        HarnessRuntimeExecutionRow.harness_operation_id
                        == row.harness_operation_id
                    )
                )
                terminal = [
                    HarnessTraceV3.model_validate(item.terminal_trace)
                    for item in traces
                    if item.terminal_trace is not None
                ]
                if terminal and all(
                    trace.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}
                    for trace in terminal
                ):
                    row.status = "completed"
                    row.error_code = ""
                else:
                    row.status = "failed"
                    row.error_code = "harness_workflow_operation_abandoned"
                row.completed_at = datetime.now(UTC).isoformat()
                recovered += 1
        return recovered
