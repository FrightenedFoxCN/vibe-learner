from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.harness import (
    HarnessAttemptRecord,
    HarnessCheckV2,
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
    canonical_harness_digest,
)
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN


HARNESS_RUNTIME_EXECUTION_SCHEMA_VERSION = "harness-runtime-execution-v1"
HARNESS_RUNTIME_CLAIM_SCHEMA_VERSION = "harness-runtime-claim-v1"
HARNESS_RUNTIME_RECOVERY_SCHEMA_VERSION = "harness-runtime-recovery-v1"

_TRACE_ID_PATTERN = r"^harness-trace-[0-9a-f]{32}$"
_CLAIM_TOKEN_PATTERN = r"^harness-runtime-claim-[0-9a-f]{32}$"


class HarnessRuntimeState(StrEnum):
    PREPARED = "prepared"
    CLAIMED = "claimed"
    TERMINAL = "terminal"


class HarnessRuntimeRecoveryDisposition(StrEnum):
    ALREADY_TERMINAL = "already_terminal"
    BUSY = "busy"
    SAFE_TO_RESUME = "safe_to_resume"
    READ_BACK_REQUIRED = "read_back_required"
    ATTEMPTS_EXHAUSTED = "attempts_exhausted"


class _RuntimeModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        revalidate_instances="always",
    )


class HarnessRuntimeExecutionV1(_RuntimeModel):
    schema_name: Literal["HarnessRuntimeExecution"] = "HarnessRuntimeExecution"
    schema_version: Literal["harness-runtime-execution-v1"] = (
        HARNESS_RUNTIME_EXECUTION_SCHEMA_VERSION
    )
    trace_id: str = Field(pattern=_TRACE_ID_PATTERN)
    trace_slot: int = Field(ge=0, le=127)
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    parent_trace_id: str | None = Field(default=None, pattern=_TRACE_ID_PATTERN)
    workflow: HarnessWorkflow
    stage: HarnessStage
    adapter_contract: HarnessContractRef
    trace_contract: HarnessContractRef
    context: HarnessContextEnvelopeV3
    state: HarnessRuntimeState
    claim_owner: str = Field(max_length=160)
    claim_token: str = Field(max_length=64)
    claim_count: int = Field(ge=0, le=3)
    lease_expires_at: AwareDatetime | None
    execution_started_at: AwareDatetime | None
    attempt_records: list[HarnessAttemptRecord] = Field(default_factory=list, max_length=128)
    checks: list[HarnessCheckV2] = Field(default_factory=list, max_length=256)
    terminal_trace: HarnessTraceV3 | None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_execution(self) -> "HarnessRuntimeExecutionV1":
        if self.trace_id != expected_harness_runtime_trace_id(
            harness_operation_id=self.harness_operation_id,
            stage=self.stage,
            trace_slot=self.trace_slot,
        ):
            raise ValueError("harness_runtime_trace_id_mismatch")
        if (
            self.context.operation_id != self.harness_operation_id
            or self.context.workflow != self.workflow
            or self.context.stage != self.stage
        ):
            raise ValueError("harness_runtime_context_identity_mismatch")
        if self.parent_trace_id == self.trace_id:
            raise ValueError("harness_runtime_parent_trace_self_reference")
        indexes = [item.attempt_index for item in self.attempt_records]
        if indexes != list(range(1, len(indexes) + 1)):
            raise ValueError("harness_runtime_attempt_indexes_not_contiguous")
        attempt_ids = [item.attempt_id for item in self.attempt_records]
        expected_attempt_ids = [
            expected_harness_runtime_attempt_id(self.trace_id, index)
            for index in indexes
        ]
        if attempt_ids != expected_attempt_ids:
            raise ValueError("harness_runtime_attempt_id_mismatch")
        for value in (
            self.lease_expires_at,
            self.execution_started_at,
            self.created_at,
            self.updated_at,
        ):
            if value is not None and value.utcoffset() != timedelta(0):
                raise ValueError("harness_runtime_timestamp_must_be_utc")
        if self.updated_at < self.created_at:
            raise ValueError("harness_runtime_time_range_invalid")
        if self.state == HarnessRuntimeState.PREPARED:
            if (
                self.claim_owner
                or self.claim_token
                or self.lease_expires_at is not None
                or self.terminal_trace is not None
            ):
                raise ValueError("harness_runtime_prepared_state_invalid")
        elif self.state == HarnessRuntimeState.CLAIMED:
            if (
                not self.claim_owner
                or not self.claim_token
                or self.lease_expires_at is None
                or self.claim_count < 1
                or self.terminal_trace is not None
            ):
                raise ValueError("harness_runtime_claimed_state_invalid")
        else:
            if (
                self.claim_owner
                or self.claim_token
                or self.lease_expires_at is not None
                or self.terminal_trace is None
            ):
                raise ValueError("harness_runtime_terminal_state_invalid")
            trace = self.terminal_trace
            if (
                trace.trace_id != self.trace_id
                or trace.operation_id != self.harness_operation_id
                or trace.parent_trace_id != self.parent_trace_id
                or trace.workflow != self.workflow
                or trace.stage != self.stage
                or trace.contract != self.trace_contract
                or trace.context != self.context
                or trace.attempt_records != self.attempt_records
                or trace.checks != self.checks
            ):
                raise ValueError("harness_runtime_terminal_trace_mismatch")
        return self


class HarnessRuntimeClaimV1(_RuntimeModel):
    schema_name: Literal["HarnessRuntimeClaim"] = "HarnessRuntimeClaim"
    schema_version: Literal["harness-runtime-claim-v1"] = (
        HARNESS_RUNTIME_CLAIM_SCHEMA_VERSION
    )
    trace_id: str = Field(pattern=_TRACE_ID_PATTERN)
    claim_owner: str = Field(min_length=1, max_length=160)
    claim_token: str = Field(pattern=_CLAIM_TOKEN_PATTERN)
    claim_count: int = Field(ge=1, le=3)
    lease_expires_at: AwareDatetime


class HarnessRuntimeRecoveryDecisionV1(_RuntimeModel):
    schema_name: Literal["HarnessRuntimeRecoveryDecision"] = (
        "HarnessRuntimeRecoveryDecision"
    )
    schema_version: Literal["harness-runtime-recovery-v1"] = (
        HARNESS_RUNTIME_RECOVERY_SCHEMA_VERSION
    )
    trace_id: str = Field(pattern=_TRACE_ID_PATTERN)
    disposition: HarnessRuntimeRecoveryDisposition
    reason_code: str = Field(min_length=1, max_length=160)
    claim_count: int = Field(ge=0, le=3)
    execution_started: bool
    terminal_trace_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_decision(self) -> "HarnessRuntimeRecoveryDecisionV1":
        if (
            self.disposition == HarnessRuntimeRecoveryDisposition.ALREADY_TERMINAL
        ) != (self.terminal_trace_digest is not None):
            raise ValueError("harness_runtime_recovery_terminal_digest_mismatch")
        return self


def expected_harness_runtime_trace_id(
    *,
    harness_operation_id: str,
    stage: HarnessStage,
    trace_slot: int,
) -> str:
    digest = hashlib.sha256(
        (
            "harness-runtime-trace-v1\0"
            f"{harness_operation_id}\0{stage.value}\0{trace_slot}"
        ).encode("utf-8")
    ).hexdigest()
    return f"harness-trace-{digest[:32]}"


def expected_harness_runtime_attempt_id(trace_id: str, attempt_index: int) -> str:
    digest = hashlib.sha256(
        f"harness-runtime-attempt-v1\0{trace_id}\0{attempt_index}".encode("utf-8")
    ).hexdigest()
    return f"harness-attempt-{digest[:32]}"


def harness_runtime_terminal_trace_digest(trace: HarnessTraceV3) -> str:
    return canonical_harness_digest(
        trace.model_dump(mode="json", exclude_none=False)
    )
