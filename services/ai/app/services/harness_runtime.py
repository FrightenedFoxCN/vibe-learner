from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import time
from typing import Callable, Mapping, Protocol

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

    def validate(self) -> None:
        if self.output.model_config.get("extra") != "forbid":
            raise HarnessRuntimeError("harness_runtime_output_extra_forbid_required")
        if not self.checks:
            raise HarnessRuntimeError("harness_runtime_validation_checks_required")


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
    ) -> HarnessRuntimeExecutionV1:
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
        claim = self.repository.claim(
            trace_id=execution.trace_id,
            claim_owner=claim_owner,
        )
        if claim is None:
            raise HarnessRuntimeError("harness_runtime_claim_unavailable")
        self.repository.mark_execution_started(claim)
        started_at = self.clock()
        repaired = False
        raw: object | None = None
        artifacts: Mapping[str, object] = {}
        try:
            artifacts = self._resolve_artifacts(request)
            raw = adapter.generate(request.context, artifacts)
            self._record_attempt(
                claim,
                HarnessAttemptPhase.GENERATE,
                HarnessAttemptStatus.PASSED,
                started_at,
                output=raw,
            )
        except Exception as error:
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
                recovery_strategy="none",
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
                )
                repaired = True
                continue

            validate_started = self.clock()
            try:
                validated = adapter.validate(decoded)
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
                self._record_attempt(
                    claim,
                    HarnessAttemptPhase.VALIDATE,
                    HarnessAttemptStatus.PASSED,
                    validate_started,
                    output=validated.output,
                )
            except Exception as error:
                code = _error_code(error)
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
                )
                repaired = True
                continue
            break

        commit_evidence = HarnessCommitEvidenceV3(
            status=HarnessCommitStatus.NOT_APPLICABLE,
            rollback_reason_code=""
        )
        if adapter.commit is not None:
            commit_started = self.clock()
            try:
                commit_evidence = adapter.commit(validated.output)
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

    def inspect_recovery(self, trace_id: str) -> HarnessRuntimeRecoveryDecisionV1:
        return self.repository.inspect_recovery(trace_id)

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
        return {artifact_id: item.payload for artifact_id, item in by_id.items()}

    def _repair(
        self,
        *,
        claim: HarnessRuntimeClaimV1,
        adapter: HarnessRuntimeStageAdapter,
        raw: object,
        error_code: str,
        repair_index: int,
    ) -> object:
        started = self.clock()
        assert adapter.repair is not None
        try:
            repaired = adapter.repair(raw, error_code, repair_index)
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
            commit_evidence=HarnessCommitEvidenceV3(
                status=HarnessCommitStatus.NOT_COMMITTED,
                rollback_reason_code=""
            ),
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


class HarnessRuntimeCommitOutcomeUnknown(HarnessRuntimeError):
    pass


def _duration_ms(started_at: datetime, completed_at: datetime) -> int:
    return max(0, int((completed_at - started_at).total_seconds() * 1000))


def _error_code(error: Exception) -> str:
    code = str(error).strip() or type(error).__name__
    return code[:160]
