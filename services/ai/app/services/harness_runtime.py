from __future__ import annotations

from app.models.harness_runtime_commit import HarnessRuntimePreparedOutput, HarnessRuntimeFinalizeResult

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Event, Thread
from typing import Callable, Mapping, Protocol
from sqlalchemy.orm import Session

from pydantic import BaseModel

from app.models.harness import (
    HarnessAttemptPhase,
    HarnessAttemptStatus,
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessCommitEvidenceV3,
    HarnessCommitStatus,
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessStage,
    HarnessStatus,
    HarnessTraceV3,
    canonical_harness_digest,
)
from app.models.harness_manifest import require_executable_workflow_manifest_entry
from app.models import harness_performance as performance_budget
from app.models.harness_operation import HarnessOperationBindingV1
from app.models.harness_runtime import (
    HarnessRuntimeClaimV1,
    HarnessRuntimeExecutionV1,
    HarnessRuntimeRecoveryDecisionV1,
    HarnessRuntimeRecoveryDisposition,
)
from app.persistence.harness_runtime_repository import (
    HarnessRuntimeError,
    HarnessRuntimeRepository,
)


@dataclass(frozen=True)
class HarnessRuntimeResolvedArtifact:
    artifact_id: str
    payload_digest: str
    payload: object


class HarnessRuntimeArtifactResolver(Protocol):
    def resolve(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        context: HarnessContextEnvelopeV3,
    ) -> tuple[HarnessRuntimeResolvedArtifact, ...]: ...


@dataclass(frozen=True)
class HarnessRuntimeValidationResult:
    output: BaseModel
    checks: tuple[HarnessCheckV2, ...]
    status: HarnessStatus = HarnessStatus.PASSED
    recovery_strategy: str = "none"

    def validate(self) -> None:
        if self.output.model_config.get("extra") != "forbid":
            raise HarnessRuntimeError("harness_runtime_output_extra_forbid_required")
        if not self.checks:
            raise HarnessRuntimeError("harness_runtime_validation_checks_required")
        if self.status not in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}:
            raise HarnessRuntimeError("harness_runtime_validation_status_invalid")
        if (self.status == HarnessStatus.REPAIRED) != (
            self.recovery_strategy != "none"
        ):
            raise HarnessRuntimeError("harness_runtime_validation_recovery_mismatch")






GenerateCallback = Callable[
    [HarnessContextEnvelopeV3, Mapping[str, object]],
    object,
]
DecodeCallback = Callable[[object], BaseModel]
ValidateCallback = Callable[[BaseModel], HarnessRuntimeValidationResult]
RepairCallback = Callable[[object, str, int], object]
CommitCallback = Callable[[BaseModel], HarnessCommitEvidenceV3]
RollbackCallback = Callable[[BaseModel, str], HarnessCommitEvidenceV3]
ReadBackCallback = Callable[[HarnessRuntimeExecutionV1], HarnessTraceV3 | None]


@dataclass(frozen=True)
class HarnessRuntimeStageAdapter:
    adapter_contract: HarnessContractRef
    trace_contract: HarnessContractRef
    generate: GenerateCallback
    decode: DecodeCallback
    validate: ValidateCallback
    repair: RepairCallback | None = None
    commit: CommitCallback | None = None
    rollback: RollbackCallback | None = None
    read_back: ReadBackCallback | None = None
    recovery_strategy: str = "bounded_repair"


@dataclass(frozen=True)
class HarnessRuntimeRequest:
    operation_binding: HarnessOperationBindingV1
    stage: HarnessStage
    trace_slot: int
    context: HarnessContextEnvelopeV3
    parent_trace_id: str | None = None


class _HarnessLeaseHeartbeat:
    """Renew a runtime claim while synchronous provider/worker code is running."""

    def __init__(
        self,
        repository: HarnessRuntimeRepository,
        claim: HarnessRuntimeClaimV1,
        lease_seconds: int,
    ) -> None:
        self.repository = repository
        self.claim = claim
        self.lease_seconds = lease_seconds
        self._stop = Event()
        self._failure: Exception | None = None
        self._thread: Thread | None = None

    def __enter__(self) -> "_HarnessLeaseHeartbeat":
        interval = max(0.25, min(30.0, self.lease_seconds / 3))

        def run() -> None:
            while not self._stop.wait(interval):
                try:
                    self.claim = self.repository.renew(
                        claim=self.claim,
                        lease_seconds=self.lease_seconds,
                    )
                except Exception as error:  # pragma: no cover - timing dependent
                    self._failure = error
                    self._stop.set()
                    return

        self._thread = Thread(target=run, name="harness-runtime-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def raise_if_failed(self) -> None:
        if self._failure is not None:
            raise HarnessRuntimeError("harness_runtime_claim_renewal_failed") from self._failure


class HarnessOperationRuntime:
    """Shared v3 generate/decode/validate/repair/commit orchestration boundary."""

    def __init__(
        self,
        *,
        repository: HarnessRuntimeRepository,
        artifact_resolver: HarnessRuntimeArtifactResolver | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.artifact_resolver = artifact_resolver
        self.clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        *,
        request: HarnessRuntimeRequest,
        adapter: HarnessRuntimeStageAdapter,
        claim_owner: str,
        _prepare_only: bool = False,
    ) -> HarnessRuntimeExecutionV1 | HarnessRuntimePreparedOutput:
        manifest = require_executable_workflow_manifest_entry(
            request.operation_binding.workflow,
            request.stage,
        )
        execution = self.repository.prepare(
            operation_binding=request.operation_binding,
            stage=request.stage,
            trace_slot=request.trace_slot,
            adapter_contract=adapter.adapter_contract,
            trace_contract=adapter.trace_contract,
            context=request.context,
            parent_trace_id=request.parent_trace_id,
        )
        if execution.terminal_trace is not None:
            return execution
        recovery = self.repository.inspect_recovery(execution.trace_id)
        if recovery.disposition == HarnessRuntimeRecoveryDisposition.READ_BACK_REQUIRED:
            return self._recover_with_read_back(
                execution=execution,
                adapter=adapter,
                claim_owner=claim_owner,
            )
        if recovery.disposition not in {
            HarnessRuntimeRecoveryDisposition.SAFE_TO_RESUME,
        }:
            raise HarnessRuntimeError(
                f"harness_runtime_not_executable:{recovery.disposition.value}"
            )
        lease_seconds = _lease_seconds(manifest.execution_budget.max_wall_time_ms)
        claim = self.repository.claim(
            trace_id=execution.trace_id,
            claim_owner=claim_owner,
            lease_seconds=lease_seconds,
        )
        if claim is None:
            raise HarnessRuntimeError("harness_runtime_claim_unavailable")
        self.repository.mark_execution_started(claim)
        started_at = self.clock()
        deadline = started_at + timedelta(
            milliseconds=manifest.execution_budget.max_wall_time_ms
        )
        repaired = False
        raw: object | None = None
        artifacts: Mapping[str, object] = {}
        try:
            performance_budget.enforce_budget(
                "reference_count",
                len(request.context.subject_refs) + len(request.context.snapshot_refs),
                performance_budget.CONTEXT_MAX_REFERENCES,
            )
            performance_budget.enforce_budget(
                "context_bytes", performance_budget.canonical_byte_count(request.context),
                performance_budget.CONTEXT_MAX_BYTES,
            )
            artifacts = self._call_with_heartbeat(
                claim,
                lease_seconds,
                lambda: self._resolve_artifacts(request),
                deadline=deadline,
            )
            raw = self._call_with_heartbeat(
                claim,
                lease_seconds,
                lambda: adapter.generate(request.context, artifacts),
                deadline=deadline,
            )
            self._record_attempt(
                claim,
                HarnessAttemptPhase.GENERATE,
                HarnessAttemptStatus.PASSED,
                started_at,
                output=raw,
            )
        except Exception as error:
            recovery_strategy = "none"
            if isinstance(error, performance_budget.HarnessBudgetExceeded):
                self.repository.append_check(claim=claim, check=HarnessCheckV2(
                    name="pre_execution_budget", status=HarnessCheckStatus.FAILED,
                    code=error.code, message=error.evidence.model_dump_json(),
                ))
            if isinstance(error, HarnessRuntimeGenerationError):
                for check in error.checks:
                    self.repository.append_check(claim=claim, check=check)
                recovery_strategy = error.recovery_strategy
            self._record_attempt(
                claim,
                HarnessAttemptPhase.GENERATE,
                HarnessAttemptStatus.FAILED,
                started_at,
                error_code=_error_code(error),
            )
            return self._terminal_failure(
                claim=claim,
                execution=self._require_execution(execution.trace_id),
                error_code=_error_code(error),
                started_at=started_at,
                recovery_strategy=recovery_strategy,
            )

        repair_count = 0
        while True:
            phase_started = self.clock()
            try:
                decoded = adapter.decode(raw)
                self._record_attempt(
                    claim,
                    HarnessAttemptPhase.DECODE,
                    HarnessAttemptStatus.PASSED,
                    phase_started,
                    output=decoded,
                )
            except Exception as error:
                code = _error_code(error)
                self._record_attempt(
                    claim,
                    HarnessAttemptPhase.DECODE,
                    HarnessAttemptStatus.FAILED,
                    phase_started,
                    error_code=code,
                )
                if adapter.repair is None or repair_count >= manifest.attempt_ceiling.max_repair_attempts:
                    return self._terminal_failure(
                        claim=claim,
                        execution=self._require_execution(execution.trace_id),
                        error_code=code,
                        started_at=started_at,
                        recovery_strategy=(adapter.recovery_strategy if repaired else "none"),
                    )
                repair_count += 1
                raw = self._repair(
                    claim=claim,
                    adapter=adapter,
                    raw=raw,
                    error_code=code,
                    repair_index=repair_count,
                    lease_seconds=lease_seconds,
                    deadline=deadline,
                )
                repaired = True
                continue

            validate_started = self.clock()
            try:
                self._ensure_within_budget(deadline)
                validated = adapter.validate(decoded)
                self._ensure_within_budget(deadline)
                if not isinstance(validated, HarnessRuntimeValidationResult):
                    raise HarnessRuntimeError("harness_runtime_validation_result_invalid")
                validated.validate()
                failed_checks = [
                    item
                    for item in validated.checks
                    if item.status == HarnessCheckStatus.FAILED
                ]
                if failed_checks:
                    if (
                        adapter.repair is None
                        or repair_count >= manifest.attempt_ceiling.max_repair_attempts
                    ):
                        for check in validated.checks:
                            self.repository.append_check(claim=claim, check=check)
                    raise HarnessRuntimeValidationFailure(failed_checks[0].code)
                for check in validated.checks:
                    self.repository.append_check(claim=claim, check=check)
                output_digest = canonical_harness_digest(
                    validated.output.model_dump(mode="json", exclude_none=False)
                )
                if validated.status == HarnessStatus.REPAIRED:
                    self._record_attempt(
                        claim,
                        HarnessAttemptPhase.REPAIR,
                        HarnessAttemptStatus.PASSED,
                        validate_started,
                        output=validated.output,
                    )
                    repaired = True
                self._record_attempt(
                    claim,
                    HarnessAttemptPhase.VALIDATE,
                    HarnessAttemptStatus.PASSED,
                    validate_started,
                    output=validated.output,
                )
            except Exception as error:
                code = _error_code(error)
                if isinstance(error, HarnessRuntimeDomainValidationError):
                    for check in error.checks:
                        self.repository.append_check(claim=claim, check=check)
                self._record_attempt(
                    claim,
                    HarnessAttemptPhase.VALIDATE,
                    HarnessAttemptStatus.FAILED,
                    validate_started,
                    error_code=code,
                )
                if adapter.repair is None or repair_count >= manifest.attempt_ceiling.max_repair_attempts:
                    return self._terminal_failure(
                        claim=claim,
                        execution=self._require_execution(execution.trace_id),
                        error_code=code,
                        started_at=started_at,
                        recovery_strategy=(adapter.recovery_strategy if repaired else "none"),
                    )
                repair_count += 1
                raw = self._repair(
                    claim=claim,
                    adapter=adapter,
                    raw=raw,
                    error_code=code,
                    repair_index=repair_count,
                    lease_seconds=lease_seconds,
                    deadline=deadline,
                )
                repaired = True
                continue
            break

        if _prepare_only:
            current = self._require_execution(execution.trace_id)
            return HarnessRuntimePreparedOutput(
                execution=current,
                claim=claim,
                output=validated.output,
                output_digest=output_digest,
                checks=tuple(current.checks),
                started_at=started_at,
                prepared_at=self.clock(),
                status=HarnessStatus.REPAIRED if repaired else HarnessStatus.PASSED,
                recovery_strategy=(
                    validated.recovery_strategy
                    if validated.status == HarnessStatus.REPAIRED
                    else adapter.recovery_strategy
                    if repaired
                    else "none"
                ),
            )

        commit_evidence = HarnessCommitEvidenceV3(
            status=HarnessCommitStatus.NOT_APPLICABLE,
            rollback_reason_code=""
        )
        if adapter.commit is not None:
            commit_started = self.clock()
            try:
                commit_evidence = self._call_with_heartbeat(
                    claim,
                    lease_seconds,
                    lambda: adapter.commit(validated.output),
                    deadline=deadline,
                )
                if commit_evidence.status != HarnessCommitStatus.COMMITTED:
                    raise HarnessRuntimeError("harness_runtime_commit_not_terminal")
                self._record_attempt(
                    claim,
                    HarnessAttemptPhase.COMMIT,
                    HarnessAttemptStatus.PASSED,
                    commit_started,
                    output_digest=commit_evidence.payload_digest,
                )
            except Exception as error:
                code = _error_code(error)
                # A failed commit needs domain-owned attempted-resource evidence.
                # The runtime therefore leaves the claimed row for authoritative
                # read-back instead of fabricating a not-committed projection.
                self._record_attempt(
                    claim,
                    HarnessAttemptPhase.COMMIT,
                    HarnessAttemptStatus.FAILED,
                    commit_started,
                    error_code=code,
                )
                if adapter.rollback is not None:
                    rollback_started = self.clock()
                    try:
                        rollback_evidence = adapter.rollback(validated.output, code)
                        if rollback_evidence.status != HarnessCommitStatus.ROLLED_BACK:
                            raise HarnessRuntimeError("harness_runtime_rollback_not_terminal")
                        self._record_attempt(
                            claim,
                            HarnessAttemptPhase.ROLLBACK,
                            HarnessAttemptStatus.PASSED,
                            rollback_started,
                            output_digest=rollback_evidence.payload_digest,
                        )
                        current = self._require_execution(execution.trace_id)
                        completed_at = self.clock()
                        trace = HarnessTraceV3(
                            trace_schema_version="harness-trace-v3",
                            trace_id=current.trace_id,
                            operation_id=current.harness_operation_id,
                            parent_trace_id=current.parent_trace_id,
                            workflow=current.workflow,
                            stage=current.stage,
                            status=HarnessStatus.FAILED,
                            contract=current.trace_contract,
                            context=current.context,
                            output_digest=output_digest,
                            checks=current.checks,
                            attempt_records=current.attempt_records,
                            recovery_strategy=adapter.recovery_strategy,
                            error_code=code,
                            duration_ms=_duration_ms(started_at, completed_at),
                            commit_evidence=rollback_evidence,
                            started_at=started_at,
                            completed_at=completed_at,
                        )
                        return self.repository.terminalize(claim=claim, trace=trace)
                    except Exception as rollback_error:
                        raise HarnessRuntimeCommitOutcomeUnknown(
                            _error_code(rollback_error)
                        ) from rollback_error
                raise HarnessRuntimeCommitOutcomeUnknown(code) from error

        current = self._require_execution(execution.trace_id)
        completed_at = self.clock()
        status = HarnessStatus.REPAIRED if repaired else HarnessStatus.PASSED
        trace = HarnessTraceV3(
            trace_schema_version="harness-trace-v3",
            trace_id=current.trace_id,
            operation_id=current.harness_operation_id,
            parent_trace_id=current.parent_trace_id,
            workflow=current.workflow,
            stage=current.stage,
            status=status,
            contract=current.trace_contract,
            context=current.context,
            output_digest=output_digest,
            checks=current.checks,
            attempt_records=current.attempt_records,
            recovery_strategy=adapter.recovery_strategy if repaired else "none",
            error_code="",
            duration_ms=_duration_ms(started_at, completed_at),
            commit_evidence=commit_evidence,
            started_at=started_at,
            completed_at=completed_at,
        )
        return self.repository.terminalize(claim=claim, trace=trace)

    def prepare_output(
        self,
        *,
        request: HarnessRuntimeRequest,
        adapter: HarnessRuntimeStageAdapter,
        claim_owner: str,
    ) -> HarnessRuntimePreparedOutput:
        """Run through validation and leave commit to the caller's transaction."""
        result = self.execute(
            request=request,
            adapter=adapter,
            claim_owner=claim_owner,
            _prepare_only=True,
        )
        if not isinstance(result, HarnessRuntimePreparedOutput):
            raise HarnessRuntimeError("harness_runtime_prepare_output_invalid")
        return result

    def inspect_recovery(self, trace_id: str) -> HarnessRuntimeRecoveryDecisionV1:
        return self.repository.inspect_recovery(trace_id)

    def get_execution_in_session(self, session: Session, trace_id: str) -> HarnessRuntimeExecutionV1 | None:
        return self.repository.get_in_session(session, trace_id)

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
        """Commit a validated output and its Harness terminal trace atomically.

        The caller owns ``session`` and may apply domain effects before this
        method. Any exception rolls back the caller's transaction.
        """
        if commit_evidence.status != HarnessCommitStatus.COMMITTED:
            raise HarnessRuntimeError("harness_runtime_finalize_requires_committed_evidence")
        self.repository.append_attempt_in_session(
            session,
            claim=prepared.claim,
            phase=HarnessAttemptPhase.COMMIT,
            status=HarnessAttemptStatus.PASSED,
            duration_ms=max(0, int((self.clock() - prepared.prepared_at).total_seconds() * 1000)),
            output_digest=commit_evidence.payload_digest,
        )
        current = self.repository.get_in_session(session, prepared.execution.trace_id)
        if current is None:
            raise HarnessRuntimeError("harness_runtime_trace_not_found")
        completed_at = self.clock()
        trace = HarnessTraceV3(
            trace_schema_version="harness-trace-v3",
            trace_id=current.trace_id,
            operation_id=current.harness_operation_id,
            parent_trace_id=current.parent_trace_id,
            workflow=current.workflow,
            stage=current.stage,
            status=status or prepared.status,
            contract=current.trace_contract,
            context=current.context,
            output_digest=prepared.output_digest,
            checks=current.checks,
            attempt_records=current.attempt_records,
            recovery_strategy=recovery_strategy if recovery_strategy != "none" else prepared.recovery_strategy,
            error_code=error_code,
            duration_ms=_duration_ms(prepared.started_at, completed_at),
            commit_evidence=commit_evidence,
            started_at=prepared.started_at,
            completed_at=completed_at,
        )
        execution = self.repository.terminalize_in_session(
            session, claim=prepared.claim, trace=trace
        )
        return HarnessRuntimeFinalizeResult(execution=execution, trace=trace)

    def fail_prepared_in_session(
        self,
        session: Session,
        *,
        prepared: HarnessRuntimePreparedOutput,
        commit_evidence: HarnessCommitEvidenceV3,
        error_code: str,
    ) -> HarnessRuntimeFinalizeResult:
        """Record a known transaction non-commit with the domain failure."""

        if commit_evidence.status != HarnessCommitStatus.NOT_COMMITTED:
            raise HarnessRuntimeError(
                "harness_runtime_failure_requires_not_committed_evidence"
            )
        code = error_code.strip()[:160]
        if not code:
            raise HarnessRuntimeError("harness_runtime_failure_error_required")
        self.repository.append_attempt_in_session(
            session,
            claim=prepared.claim,
            phase=HarnessAttemptPhase.COMMIT,
            status=HarnessAttemptStatus.FAILED,
            duration_ms=max(
                0,
                int((self.clock() - prepared.prepared_at).total_seconds() * 1000),
            ),
            error_code=code,
        )
        current = self.repository.get_in_session(
            session,
            prepared.execution.trace_id,
        )
        if current is None:
            raise HarnessRuntimeError("harness_runtime_trace_not_found")
        completed_at = self.clock()
        trace = HarnessTraceV3(
            trace_schema_version="harness-trace-v3",
            trace_id=current.trace_id,
            operation_id=current.harness_operation_id,
            parent_trace_id=current.parent_trace_id,
            workflow=current.workflow,
            stage=current.stage,
            status=HarnessStatus.FAILED,
            contract=current.trace_contract,
            context=current.context,
            output_digest=prepared.output_digest,
            checks=current.checks,
            attempt_records=current.attempt_records,
            recovery_strategy=prepared.recovery_strategy,
            error_code=code,
            duration_ms=_duration_ms(prepared.started_at, completed_at),
            commit_evidence=commit_evidence,
            started_at=prepared.started_at,
            completed_at=completed_at,
        )
        execution = self.repository.terminalize_in_session(
            session,
            claim=prepared.claim,
            trace=trace,
        )
        return HarnessRuntimeFinalizeResult(execution=execution, trace=trace)

    def fail_prepared(
        self,
        *,
        prepared: HarnessRuntimePreparedOutput,
        commit_evidence: HarnessCommitEvidenceV3,
        error_code: str,
    ) -> HarnessRuntimeFinalizeResult:
        with self.repository.database.session() as session:
            return self.fail_prepared_in_session(
                session,
                prepared=prepared,
                commit_evidence=commit_evidence,
                error_code=error_code,
            )

    def _recover_with_read_back(
        self,
        *,
        execution: HarnessRuntimeExecutionV1,
        adapter: HarnessRuntimeStageAdapter,
        claim_owner: str,
    ) -> HarnessRuntimeExecutionV1:
        if adapter.read_back is None:
            raise HarnessRuntimeCommitOutcomeUnknown(
                "harness_runtime_authoritative_read_back_unavailable"
            )
        claim = self.repository.claim(
            trace_id=execution.trace_id,
            claim_owner=claim_owner,
            recovery=True,
        )
        if claim is None:
            raise HarnessRuntimeError("harness_runtime_recovery_claim_unavailable")
        recovered = adapter.read_back(self._require_execution(execution.trace_id))
        if recovered is None:
            raise HarnessRuntimeCommitOutcomeUnknown(
                "harness_runtime_authoritative_read_back_inconclusive"
            )
        return self.repository.terminalize(claim=claim, trace=recovered)

    def _resolve_artifacts(
        self,
        request: HarnessRuntimeRequest,
    ) -> Mapping[str, object]:
        refs = request.context.snapshot_refs
        if not refs:
            return {}
        if self.artifact_resolver is None:
            raise HarnessRuntimeError("harness_runtime_artifact_resolver_required")
        resolved = self.artifact_resolver.resolve(
            operation_binding=request.operation_binding,
            context=request.context,
        )
        by_id = {item.artifact_id: item for item in resolved}
        if len(by_id) != len(resolved) or set(by_id) != {
            item.artifact_id for item in refs
        }:
            raise HarnessRuntimeError("harness_runtime_artifact_set_mismatch")
        for ref in refs:
            item = by_id[ref.artifact_id]
            if item.payload_digest != ref.payload_digest:
                raise HarnessRuntimeError("harness_runtime_artifact_digest_mismatch")
        total = 0
        for item in resolved:
            size = performance_budget.canonical_byte_count(item.payload)
            performance_budget.enforce_budget("snapshot_bytes", size, performance_budget.SNAPSHOT_MAX_BYTES)
            total += size
            performance_budget.enforce_budget("resolved_bytes", total, performance_budget.RESOLVED_MAX_BYTES)
        return {artifact_id: item.payload for artifact_id, item in by_id.items()}

    def _repair(
        self,
        *,
        claim: HarnessRuntimeClaimV1,
        adapter: HarnessRuntimeStageAdapter,
        raw: object,
        error_code: str,
        repair_index: int,
        lease_seconds: int,
        deadline: datetime,
    ) -> object:
        started = self.clock()
        assert adapter.repair is not None
        try:
            repaired = self._call_with_heartbeat(
                claim,
                lease_seconds,
                lambda: adapter.repair(raw, error_code, repair_index),
                deadline=deadline,
            )
            self._record_attempt(
                claim,
                HarnessAttemptPhase.REPAIR,
                HarnessAttemptStatus.PASSED,
                started,
                output=repaired,
            )
            return repaired
        except Exception as error:
            self._record_attempt(
                claim,
                HarnessAttemptPhase.REPAIR,
                HarnessAttemptStatus.FAILED,
                started,
                error_code=_error_code(error),
            )
            raise

    def _call_with_heartbeat(
        self,
        claim: HarnessRuntimeClaimV1,
        lease_seconds: int,
        callback: Callable[[], object],
        deadline: datetime | None = None,
    ) -> object:
        # A previous phase may consume the remaining deadline. Never start a
        # provider/worker/commit callback after that deadline has already passed.
        if deadline is not None:
            self._ensure_within_budget(deadline)
        current = self._require_execution(claim.trace_id)
        performance_budget.enforce_budget(
            "attempt_count", len(current.attempt_records), performance_budget.RUNTIME_MAX_ATTEMPTS,
        )
        performance_budget.enforce_budget(
            "runtime_evidence_bytes",
            performance_budget.canonical_byte_count({
                "attempts": [a.model_dump(mode="json") for a in current.attempt_records],
                "checks": [c.model_dump(mode="json") for c in current.checks],
            }), performance_budget.RUNTIME_MAX_EVIDENCE_BYTES,
        )
        with _HarnessLeaseHeartbeat(self.repository, claim, lease_seconds) as heartbeat:
            result = callback()
        heartbeat.raise_if_failed()
        if deadline is not None:
            self._ensure_within_budget(deadline)
        return result

    def _ensure_within_budget(self, deadline: datetime) -> None:
        if self.clock() > deadline:
            raise HarnessRuntimeError("harness_runtime_wall_time_budget_exceeded")

    def _record_attempt(
        self,
        claim: HarnessRuntimeClaimV1,
        phase: HarnessAttemptPhase,
        status: HarnessAttemptStatus,
        started_at: datetime,
        *,
        output: object | None = None,
        output_digest: str | None = None,
        error_code: str = "",
    ) -> None:
        completed = self.clock()
        digest = output_digest
        if digest is None and output is not None:
            value = (
                output.model_dump(mode="json", exclude_none=False)
                if isinstance(output, BaseModel)
                else output
            )
            digest = canonical_harness_digest(value)
        self.repository.append_attempt(
            claim=claim,
            phase=phase,
            status=status,
            duration_ms=_duration_ms(started_at, completed),
            output_digest=digest,
            error_code=error_code,
        )

    def _terminal_failure(
        self,
        *,
        claim: HarnessRuntimeClaimV1,
        execution: HarnessRuntimeExecutionV1,
        error_code: str,
        started_at: datetime,
        recovery_strategy: str,
    ) -> HarnessRuntimeExecutionV1:
        completed = self.clock()
        commit_evidence = HarnessCommitEvidenceV3(
            status=HarnessCommitStatus.NOT_COMMITTED,
            rollback_reason_code="",
        )
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
            attempt_records=execution.attempt_records,
            recovery_strategy=recovery_strategy,
            error_code=error_code,
            duration_ms=_duration_ms(started_at, completed),
            commit_evidence=commit_evidence,
            started_at=started_at,
            completed_at=completed,
        )
        return self.repository.terminalize(claim=claim, trace=trace)

    def _require_execution(self, trace_id: str) -> HarnessRuntimeExecutionV1:
        execution = self.repository.get(trace_id)
        if execution is None:
            raise HarnessRuntimeError("harness_runtime_trace_not_found")
        return execution


class HarnessRuntimeValidationFailure(HarnessRuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code or "harness_runtime_validation_failed")


class HarnessRuntimeDomainValidationError(HarnessRuntimeValidationFailure):
    """Domain validator failure with content-free checks safe for the trace."""

    def __init__(self, code: str, checks: tuple[HarnessCheckV2, ...]) -> None:
        super().__init__(code)
        self.checks = checks


class HarnessRuntimeGenerationError(HarnessRuntimeError):
    """Generate/preflight failure with content-free nested recovery evidence."""

    def __init__(
        self,
        code: str,
        checks: tuple[HarnessCheckV2, ...],
        recovery_strategy: str = "none",
    ) -> None:
        super().__init__(code or "harness_runtime_generation_failed")
        self.checks = checks
        self.recovery_strategy = recovery_strategy or "none"


class HarnessRuntimeCommitOutcomeUnknown(HarnessRuntimeError):
    pass


def _lease_seconds(max_wall_time_ms: int) -> int:
    return max(1, min(300, (max_wall_time_ms + 999) // 1000))


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def _error_code(error: Exception) -> str:
    code = str(error).strip() or type(error).__name__
    return code[:160]
