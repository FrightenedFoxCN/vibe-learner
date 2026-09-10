"""Reviewed content-free Harness index DTO; never a commit receipt."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.harness import HarnessWorkflow, HarnessStage, HarnessStatus, HarnessCommitStatus, HarnessAttemptPhase, HarnessAttemptStatus, HarnessContractRef
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN


class DiagnosticAttemptMetricV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str = Field(pattern=r"^[A-Za-z0-9:._-]{1,160}$")
    attempt_index: int = Field(ge=1)
    phase: HarnessAttemptPhase
    status: HarnessAttemptStatus
    duration_ms: int = Field(ge=0)


class DiagnosticHarnessIndexV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["diagnostic-harness-index-v1"] = "diagnostic-harness-index-v1"
    trace_id: str = Field(pattern=r"^[A-Za-z0-9:._-]{1,160}$")
    parent_trace_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:._-]{1,160}$")
    operation_id: str | None = Field(default=None, pattern=HARNESS_OPERATION_ID_PATTERN)
    workflow: HarnessWorkflow | None = None
    stage: HarnessStage | None = None
    state: Literal["prepared", "claimed", "terminal"] | None = None
    status: HarnessStatus | None = None
    commit_status: HarnessCommitStatus | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    started_at: str | None = None
    completed_at: str | None = None
    source_updated_at: str | None = None
    gap: Literal["source_removed", "source_invalid_or_unavailable", "terminal_trace_not_available"] | None = None
    components: list[HarnessContractRef] = Field(default_factory=list, max_length=64)
    attempts: list[DiagnosticAttemptMetricV1] = Field(default_factory=list, max_length=128)
    provider: None = None
    model: None = None
    tokens: None = None
    cost: None = None
    usage_gap: Literal["not_recorded_in_canonical_trace"] = "not_recorded_in_canonical_trace"
    correlation_gap: Literal["resolve_request_links_separately"] = "resolve_request_links_separately"
