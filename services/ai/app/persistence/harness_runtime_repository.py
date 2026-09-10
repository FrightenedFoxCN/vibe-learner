from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.harness import (
    HarnessAttemptPhase,
    HarnessAttemptRecord,
    HarnessAttemptStatus,
    HarnessCheckV2,
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.harness_manifest import (
    HarnessManifestRegisteredContractSlotV1,
    require_executable_workflow_manifest_entry,
)
from app.models.harness_operation import HarnessOperationBindingV1
from app.models.harness_runtime import (
    HARNESS_RUNTIME_EXECUTION_SCHEMA_VERSION,
    HarnessRuntimeClaimV1,
    HarnessRuntimeExecutionV1,
    HarnessRuntimeRecoveryDecisionV1,
    HarnessRuntimeRecoveryDisposition,
    HarnessRuntimeState,
    expected_harness_runtime_attempt_id,
    expected_harness_runtime_trace_id,
    harness_runtime_terminal_trace_digest,
)
from app.persistence.database import Database
from app.persistence.models import (
    HarnessOperationBindingRow,
    HarnessRuntimeExecutionRow,
)


MAX_RUNTIME_CLAIMS = 3


class HarnessRuntimeRepository:
    """Durable, fenced stage execution and terminal v3 trace store."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def prepare(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        stage: HarnessStage,
        trace_slot: int,
        adapter_contract: HarnessContractRef,
        trace_contract: HarnessContractRef,
        context: HarnessContextEnvelopeV3,
        parent_trace_id: str | None = None,
    ) -> HarnessRuntimeExecutionV1:
        if trace_slot < 0 or trace_slot > 127:
            raise HarnessRuntimeError("harness_runtime_trace_slot_out_of_bounds")
        entry = require_executable_workflow_manifest_entry(
            operation_binding.workflow,
            stage,
        )
        if not isinstance(
            entry.owner_adapter,
            HarnessManifestRegisteredContractSlotV1,
        ) or entry.owner_adapter.contract.to_harness_ref() != adapter_contract:
            raise HarnessRuntimeError("harness_runtime_adapter_contract_mismatch")
        if (
            context.operation_id != operation_binding.harness_operation_id
            or context.workflow != operation_binding.workflow
            or context.stage != stage
        ):
            raise HarnessRuntimeError("harness_runtime_context_identity_mismatch")
        trace_id = expected_harness_runtime_trace_id(
            harness_operation_id=operation_binding.harness_operation_id,
            stage=stage,
            trace_slot=trace_slot,
        )
        with self.database.session() as session:
            authoritative = session.get(
                HarnessOperationBindingRow,
                operation_binding.harness_operation_id,
            )
            if authoritative is None or _binding_from_row(authoritative) != operation_binding:
                raise HarnessRuntimeError("harness_runtime_operation_binding_invalid")
            if parent_trace_id is not None:
                parent = session.get(HarnessRuntimeExecutionRow, parent_trace_id)
                if parent is None:
                    raise HarnessRuntimeError("harness_runtime_parent_trace_not_found")
                if parent.trace_id == trace_id or parent.workflow != context.workflow.value:
                    raise HarnessRuntimeError("harness_runtime_parent_trace_invalid")
                if parent.harness_operation_id not in {
                    operation_binding.harness_operation_id,
                    operation_binding.parent_harness_operation_id,
                }:
                    raise HarnessRuntimeError("harness_runtime_parent_operation_mismatch")
            existing = session.get(HarnessRuntimeExecutionRow, trace_id)
            if existing is not None:
                self._require_prepare_identity(
                    existing,
                    operation_binding=operation_binding,
                    stage=stage,
                    trace_slot=trace_slot,
                    adapter_contract=adapter_contract,
                    trace_contract=trace_contract,
                    context=context,
                    parent_trace_id=parent_trace_id,
                )
                return _from_row(existing)
            now = _database_utc_now(session)
            row = HarnessRuntimeExecutionRow(
                trace_id=trace_id,
                trace_slot=trace_slot,
                harness_operation_id=operation_binding.harness_operation_id,
                parent_trace_id=parent_trace_id,
                workflow=operation_binding.workflow.value,
                stage=stage.value,
                adapter_contract_name=adapter_contract.name,
                adapter_contract_version=adapter_contract.version,
                trace_contract_name=trace_contract.name,
                trace_contract_version=trace_contract.version,
                context_payload=context.model_dump(mode="json", exclude_none=False),
                context_digest=context.context_digest,
                state=HarnessRuntimeState.PREPARED.value,
                claim_owner="",
                claim_token="",
                claim_count=0,
                lease_expires_at="",
                execution_started_at="",
                attempt_records=[],
                checks=[],
                terminal_trace=None,
                terminal_trace_digest="",
                schema_name="HarnessRuntimeExecution",
                schema_version=HARNESS_RUNTIME_EXECUTION_SCHEMA_VERSION,
                created_at=_wire(now),
                updated_at=_wire(now),
            )
            session.add(row)
            session.flush()
            return _from_row(row)

    def get(self, trace_id: str) -> HarnessRuntimeExecutionV1 | None:
        with self.database.session() as session:
            row = session.get(HarnessRuntimeExecutionRow, trace_id)
            return _from_row(row) if row is not None else None

    def get_in_session(
        self, session: Session, trace_id: str
    ) -> HarnessRuntimeExecutionV1 | None:
        row = session.get(HarnessRuntimeExecutionRow, trace_id)
        return _from_row(row) if row is not None else None

    def list_trace_ids(self, *, after: str = "", limit: int = 25) -> tuple[str, ...]:
        """Bounded primary-key scan for disposable diagnostic projections."""
        if not 1 <= limit <= 100:
            raise ValueError("harness_trace_scan_limit")
        with self.database.session() as session:
            return tuple(session.scalars(select(HarnessRuntimeExecutionRow.trace_id)
                .where(HarnessRuntimeExecutionRow.trace_id > after)
                .order_by(HarnessRuntimeExecutionRow.trace_id).limit(limit)))

    def list_operation_traces(
        self,
        harness_operation_id: str,
    ) -> tuple[HarnessRuntimeExecutionV1, ...]:
        with self.database.session() as session:
            rows = session.scalars(
                select(HarnessRuntimeExecutionRow)
                .where(
                    HarnessRuntimeExecutionRow.harness_operation_id
                    == harness_operation_id
                )
                .order_by(
                    HarnessRuntimeExecutionRow.trace_slot,
                    HarnessRuntimeExecutionRow.stage,
                )
            )
            return tuple(_from_row(row) for row in rows)

    def claim(
        self,
        *,
        trace_id: str,
        claim_owner: str,
        lease_seconds: int = 30,
        recovery: bool = False,
    ) -> HarnessRuntimeClaimV1 | None:
        if not claim_owner:
            raise HarnessRuntimeError("harness_runtime_claim_owner_required")
        if lease_seconds < 1 or lease_seconds > 300:
            raise HarnessRuntimeError("harness_runtime_lease_seconds_invalid")
        with self.database.session() as session:
            row = session.get(HarnessRuntimeExecutionRow, trace_id)
            if row is None:
                raise HarnessRuntimeError("harness_runtime_trace_not_found")
            now = _database_utc_now(session)
            if row.state == HarnessRuntimeState.TERMINAL.value:
                return None
            active = (
                row.state == HarnessRuntimeState.CLAIMED.value
                and bool(row.lease_expires_at)
                and _parse(row.lease_expires_at) > now
            )
            if active or row.claim_count >= MAX_RUNTIME_CLAIMS:
                return None
            if row.execution_started_at and not recovery:
                return None
            token = f"harness-runtime-claim-{uuid4().hex}"
            expires = now + timedelta(seconds=lease_seconds)
            previous_state = row.state
            previous_count = row.claim_count
            previous_lease = row.lease_expires_at
            changed = session.execute(
                update(HarnessRuntimeExecutionRow)
                .where(
                    HarnessRuntimeExecutionRow.trace_id == trace_id,
                    HarnessRuntimeExecutionRow.state == previous_state,
                    HarnessRuntimeExecutionRow.claim_count == previous_count,
                    HarnessRuntimeExecutionRow.lease_expires_at == previous_lease,
                )
                .values(
                    state=HarnessRuntimeState.CLAIMED.value,
                    claim_owner=claim_owner,
                    claim_token=token,
                    claim_count=previous_count + 1,
                    lease_expires_at=_wire(expires),
                    updated_at=_wire(now),
                )
            )
            if changed.rowcount != 1:
                return None
            return HarnessRuntimeClaimV1(
                trace_id=trace_id,
                claim_owner=claim_owner,
                claim_token=token,
                claim_count=previous_count + 1,
                lease_expires_at=expires,
            )

    def mark_execution_started(
        self,
        claim: HarnessRuntimeClaimV1,
    ) -> HarnessRuntimeExecutionV1:
        with self.database.session() as session:
            row, now = self._require_active_claim(session, claim)
            if not row.execution_started_at:
                row.execution_started_at = _wire(now)
                row.updated_at = _wire(now)
                session.flush()
            return _from_row(row)

    def renew(
        self,
        *,
        claim: HarnessRuntimeClaimV1,
        lease_seconds: int = 30,
    ) -> HarnessRuntimeClaimV1:
        """Extend an active claim using the database clock and its fence."""
        if lease_seconds < 1 or lease_seconds > 300:
            raise HarnessRuntimeError("harness_runtime_lease_seconds_invalid")
        with self.database.session() as session:
            row, now = self._require_active_claim(session, claim)
            expires = now + timedelta(seconds=lease_seconds)
            changed = session.execute(
                update(HarnessRuntimeExecutionRow)
                .where(
                    HarnessRuntimeExecutionRow.trace_id == row.trace_id,
                    HarnessRuntimeExecutionRow.state == HarnessRuntimeState.CLAIMED.value,
                    HarnessRuntimeExecutionRow.claim_owner == claim.claim_owner,
                    HarnessRuntimeExecutionRow.claim_token == claim.claim_token,
                    HarnessRuntimeExecutionRow.claim_count == claim.claim_count,
                    HarnessRuntimeExecutionRow.lease_expires_at == row.lease_expires_at,
                )
                .values(lease_expires_at=_wire(expires), updated_at=_wire(now))
            )
            if changed.rowcount != 1:
                raise HarnessRuntimeFenced("harness_runtime_claim_fenced")
            return HarnessRuntimeClaimV1(
                trace_id=claim.trace_id,
                claim_owner=claim.claim_owner,
                claim_token=claim.claim_token,
                claim_count=claim.claim_count,
                lease_expires_at=expires,
            )

    def append_attempt(
        self,
        *,
        claim: HarnessRuntimeClaimV1,
        phase: HarnessAttemptPhase,
        status: HarnessAttemptStatus,
        duration_ms: int,
        output_digest: str | None = None,
        error_code: str = "",
    ) -> HarnessAttemptRecord:
        with self.database.session() as session:
            return self.append_attempt_in_session(
                session, claim=claim, phase=phase, status=status,
                duration_ms=duration_ms, output_digest=output_digest,
                error_code=error_code,
            )

    def append_attempt_in_session(
        self, session: Session, *, claim: HarnessRuntimeClaimV1,
        phase: HarnessAttemptPhase, status: HarnessAttemptStatus,
        duration_ms: int, output_digest: str | None = None, error_code: str = "",
    ) -> HarnessAttemptRecord:
        row, now = self._require_active_claim(session, claim)
        index = len(row.attempt_records) + 1
        attempt = HarnessAttemptRecord(
            attempt_id=expected_harness_runtime_attempt_id(row.trace_id, index),
            attempt_index=index, phase=phase, status=status,
            output_digest=output_digest, error_code=error_code,
            duration_ms=duration_ms,
        )
        attempts = [*row.attempt_records, attempt.model_dump(mode="json")]
        self._validate_attempt_budget(row, attempts)
        row.attempt_records = attempts
        row.updated_at = _wire(now)
        session.flush()
        return attempt

    def append_check(
        self,
        *,
        claim: HarnessRuntimeClaimV1,
        check: HarnessCheckV2,
    ) -> HarnessCheckV2:
        with self.database.session() as session:
            row, now = self._require_active_claim(session, claim)
            if len(row.checks) >= 256:
                raise HarnessRuntimeError("harness_runtime_check_limit_exceeded")
            row.checks = [*row.checks, check.model_dump(mode="json")]
            row.updated_at = _wire(now)
            session.flush()
            return check

    def append_check_in_session(
        self, session: Session, *, claim: HarnessRuntimeClaimV1,
        check: HarnessCheckV2,
    ) -> HarnessCheckV2:
        row, now = self._require_active_claim(session, claim)
        if len(row.checks) >= 256:
            raise HarnessRuntimeError("harness_runtime_check_limit_exceeded")
        row.checks = [*row.checks, check.model_dump(mode="json")]
        row.updated_at = _wire(now)
        session.flush()
        return check

    def terminalize(
        self,
        *,
        claim: HarnessRuntimeClaimV1,
        trace: HarnessTraceV3,
    ) -> HarnessRuntimeExecutionV1:
        with self.database.session() as session:
            return self.terminalize_in_session(session, claim=claim, trace=trace)

    def terminalize_in_session(
        self,
        session: Session,
        *,
        claim: HarnessRuntimeClaimV1,
        trace: HarnessTraceV3,
    ) -> HarnessRuntimeExecutionV1:
        """Terminalize using a caller's transaction (Tavern commit boundary)."""
        row, now = self._require_active_claim(session, claim)
        strict_trace = HarnessTraceV3.model_validate(
            trace.model_dump(mode="json", exclude_none=False)
        )
        expected = _from_row(row)
        if (
            strict_trace.trace_id != expected.trace_id
            or strict_trace.operation_id != expected.harness_operation_id
            or strict_trace.parent_trace_id != expected.parent_trace_id
            or strict_trace.workflow != expected.workflow
            or strict_trace.stage != expected.stage
            or strict_trace.contract != expected.trace_contract
            or strict_trace.context != expected.context
            or strict_trace.attempt_records != expected.attempt_records
            or strict_trace.checks != expected.checks
        ):
            raise HarnessRuntimeError("harness_runtime_terminal_trace_mismatch")
        changed = session.execute(
            update(HarnessRuntimeExecutionRow)
            .where(
                HarnessRuntimeExecutionRow.trace_id == row.trace_id,
                HarnessRuntimeExecutionRow.state == HarnessRuntimeState.CLAIMED.value,
                HarnessRuntimeExecutionRow.claim_owner == claim.claim_owner,
                HarnessRuntimeExecutionRow.claim_token == claim.claim_token,
                HarnessRuntimeExecutionRow.claim_count == claim.claim_count,
            )
            .values(
                state=HarnessRuntimeState.TERMINAL.value,
                claim_owner="", claim_token="", lease_expires_at="",
                terminal_trace=strict_trace.model_dump(mode="json", exclude_none=False),
                terminal_trace_digest=harness_runtime_terminal_trace_digest(strict_trace),
                updated_at=_wire(now),
            )
        )
        if changed.rowcount != 1:
            raise HarnessRuntimeFenced("harness_runtime_claim_fenced")
        session.flush()
        terminal = session.get(HarnessRuntimeExecutionRow, row.trace_id)
        assert terminal is not None
        return _from_row(terminal)

    def inspect_recovery(
        self,
        trace_id: str,
    ) -> HarnessRuntimeRecoveryDecisionV1:
        with self.database.session() as session:
            row = session.get(HarnessRuntimeExecutionRow, trace_id)
            if row is None:
                raise HarnessRuntimeError("harness_runtime_trace_not_found")
            now = _database_utc_now(session)
            if row.state == HarnessRuntimeState.TERMINAL.value:
                disposition = HarnessRuntimeRecoveryDisposition.ALREADY_TERMINAL
                reason = "harness_runtime_terminal_read_back"
                digest = row.terminal_trace_digest
            elif (
                row.state == HarnessRuntimeState.CLAIMED.value
                and row.lease_expires_at
                and _parse(row.lease_expires_at) > now
            ):
                disposition = HarnessRuntimeRecoveryDisposition.BUSY
                reason = "harness_runtime_active_lease"
                digest = None
            elif row.claim_count >= MAX_RUNTIME_CLAIMS:
                disposition = HarnessRuntimeRecoveryDisposition.ATTEMPTS_EXHAUSTED
                reason = "harness_runtime_claim_limit_exhausted"
                digest = None
            elif row.execution_started_at:
                disposition = HarnessRuntimeRecoveryDisposition.READ_BACK_REQUIRED
                reason = "harness_runtime_execution_outcome_requires_read_back"
                digest = None
            else:
                disposition = HarnessRuntimeRecoveryDisposition.SAFE_TO_RESUME
                reason = "harness_runtime_execution_not_started"
                digest = None
            return HarnessRuntimeRecoveryDecisionV1(
                trace_id=row.trace_id,
                disposition=disposition,
                reason_code=reason,
                claim_count=row.claim_count,
                execution_started=bool(row.execution_started_at),
                terminal_trace_digest=digest,
            )

    @staticmethod
    def _require_prepare_identity(
        row: HarnessRuntimeExecutionRow,
        *,
        operation_binding: HarnessOperationBindingV1,
        stage: HarnessStage,
        trace_slot: int,
        adapter_contract: HarnessContractRef,
        trace_contract: HarnessContractRef,
        context: HarnessContextEnvelopeV3,
        parent_trace_id: str | None,
    ) -> None:
        actual = (
            row.harness_operation_id,
            row.workflow,
            row.stage,
            row.trace_slot,
            row.parent_trace_id,
            row.adapter_contract_name,
            row.adapter_contract_version,
            row.trace_contract_name,
            row.trace_contract_version,
            row.context_digest,
            row.context_payload,
        )
        expected = (
            operation_binding.harness_operation_id,
            operation_binding.workflow.value,
            stage.value,
            trace_slot,
            parent_trace_id,
            adapter_contract.name,
            adapter_contract.version,
            trace_contract.name,
            trace_contract.version,
            context.context_digest,
            context.model_dump(mode="json", exclude_none=False),
        )
        if actual != expected:
            raise HarnessRuntimeIdentityConflict(
                "harness_runtime_prepare_identity_conflict"
            )

    @staticmethod
    def _validate_attempt_budget(
        row: HarnessRuntimeExecutionRow,
        attempts: list[dict[str, object]],
    ) -> None:
        entry = require_executable_workflow_manifest_entry(
            HarnessWorkflow(row.workflow),
            HarnessStage(row.stage),
        )
        generated = sum(
            item["phase"] == HarnessAttemptPhase.GENERATE.value
            for item in attempts
        )
        repaired = sum(
            item["phase"] == HarnessAttemptPhase.REPAIR.value
            for item in attempts
        )
        if generated > entry.attempt_ceiling.max_attempts:
            raise HarnessRuntimeError("harness_runtime_attempt_limit_exceeded")
        if repaired > entry.attempt_ceiling.max_repair_attempts:
            raise HarnessRuntimeError("harness_runtime_repair_limit_exceeded")

    @staticmethod
    def _require_active_claim(
        session: Session,
        claim: HarnessRuntimeClaimV1,
    ) -> tuple[HarnessRuntimeExecutionRow, datetime]:
        row = session.get(HarnessRuntimeExecutionRow, claim.trace_id)
        if row is None:
            raise HarnessRuntimeError("harness_runtime_trace_not_found")
        now = _database_utc_now(session)
        if (
            row.state != HarnessRuntimeState.CLAIMED.value
            or row.claim_owner != claim.claim_owner
            or row.claim_token != claim.claim_token
            or row.claim_count != claim.claim_count
            or not row.lease_expires_at
            or _parse(row.lease_expires_at) <= now
        ):
            raise HarnessRuntimeFenced("harness_runtime_claim_fenced")
        return row, now


class HarnessRuntimeError(RuntimeError):
    pass


class HarnessRuntimeFenced(HarnessRuntimeError):
    pass


class HarnessRuntimeIdentityConflict(HarnessRuntimeError):
    pass


def _from_row(row: HarnessRuntimeExecutionRow) -> HarnessRuntimeExecutionV1:
    return HarnessRuntimeExecutionV1(
        trace_id=row.trace_id,
        trace_slot=row.trace_slot,
        harness_operation_id=row.harness_operation_id,
        parent_trace_id=row.parent_trace_id,
        workflow=HarnessWorkflow(row.workflow),
        stage=HarnessStage(row.stage),
        adapter_contract=HarnessContractRef(
            name=row.adapter_contract_name,
            version=row.adapter_contract_version,
        ),
        trace_contract=HarnessContractRef(
            name=row.trace_contract_name,
            version=row.trace_contract_version,
        ),
        context=HarnessContextEnvelopeV3.model_validate(row.context_payload),
        state=HarnessRuntimeState(row.state),
        claim_owner=row.claim_owner,
        claim_token=row.claim_token,
        claim_count=row.claim_count,
        lease_expires_at=_parse(row.lease_expires_at) if row.lease_expires_at else None,
        execution_started_at=(
            _parse(row.execution_started_at) if row.execution_started_at else None
        ),
        attempt_records=[
            HarnessAttemptRecord.model_validate(item) for item in row.attempt_records
        ],
        checks=[HarnessCheckV2.model_validate(item) for item in row.checks],
        terminal_trace=(
            HarnessTraceV3.model_validate(row.terminal_trace)
            if row.terminal_trace is not None
            else None
        ),
        created_at=_parse(row.created_at),
        updated_at=_parse(row.updated_at),
    )


def _binding_from_row(row: HarnessOperationBindingRow) -> HarnessOperationBindingV1:
    return HarnessOperationBindingV1(
        harness_operation_id=row.harness_operation_id,
        schema_name=row.schema_name,
        schema_version=row.schema_version,
        domain_operation_kind=row.domain_operation_kind,
        domain_operation_id=row.domain_operation_id,
        workflow=row.workflow,
        entry_stage=row.entry_stage,
        parent_harness_operation_id=row.parent_harness_operation_id,
        admitted_at=_parse(row.admitted_at),
    )


def _database_utc_now(session: Session) -> datetime:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        value = session.scalar(select(func.strftime("%Y-%m-%dT%H:%M:%f", "now")))
    elif session.bind is not None and session.bind.dialect.name == "postgresql":
        value = session.scalar(select(func.clock_timestamp()))
    else:
        value = session.scalar(select(func.current_timestamp()))
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise HarnessRuntimeError("harness_runtime_database_clock_unavailable")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _wire(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
