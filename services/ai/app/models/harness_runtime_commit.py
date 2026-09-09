from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, TYPE_CHECKING
from pydantic import BaseModel
from app.models.harness import (
    HarnessCheckV2,
    HarnessStatus,
    HarnessTraceV3,
    HarnessCommitEvidenceV3,
)
from app.models.harness_runtime import HarnessRuntimeExecutionV1, HarnessRuntimeClaimV1

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(frozen=True)
class HarnessRuntimePreparedOutput:
    """Validated, content-owned output awaiting a domain transaction commit."""

    execution: HarnessRuntimeExecutionV1
    claim: HarnessRuntimeClaimV1
    output: BaseModel
    output_digest: str
    checks: tuple[HarnessCheckV2, ...]
    started_at: datetime
    prepared_at: datetime
    status: HarnessStatus
    recovery_strategy: str


@dataclass(frozen=True)
class HarnessRuntimeFinalizeResult:
    execution: HarnessRuntimeExecutionV1
    trace: HarnessTraceV3

class HarnessTransactionFinalizer(Protocol):
    """Validate/finalize using the domain-owned session; never open a transaction."""

    def get_execution_in_session(self, session: Session, trace_id: str) -> HarnessRuntimeExecutionV1 | None: ...

    def finalize_prepared_in_session(
        self,
        session: Session,
        *,
        prepared: HarnessRuntimePreparedOutput,
        commit_evidence: HarnessCommitEvidenceV3,
        status: HarnessStatus | None = None,
        error_code: str = "",
        recovery_strategy: str = "none",
    ) -> HarnessRuntimeFinalizeResult:
        ...

    def fail_prepared_in_session(
        self,
        session: Session,
        *,
        prepared: HarnessRuntimePreparedOutput,
        commit_evidence: HarnessCommitEvidenceV3,
        error_code: str,
    ) -> HarnessRuntimeFinalizeResult:
        ...
