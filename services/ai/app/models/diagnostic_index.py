"""Reviewed content-free Harness index DTO; never a commit receipt."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.harness import HarnessWorkflow, HarnessStage, HarnessStatus, HarnessCommitStatus, HarnessAttemptPhase, HarnessAttemptStatus, HarnessContractRef, HarnessResourceType
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN


class DiagnosticAttemptMetricV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: str = Field(pattern=r"^[A-Za-z0-9:._-]{1,160}$")
    attempt_index: int = Field(ge=1)
    phase: HarnessAttemptPhase
    status: HarnessAttemptStatus
    duration_ms: int = Field(ge=0)


class DiagnosticResourceSubjectV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_type: HarnessResourceType
    resource_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    revision: int | None = Field(default=None, ge=0)


class DiagnosticCommittedResourceV1(BaseModel):
    """Historical canonical output identity; excludes content/digests and receipts."""
    model_config = ConfigDict(extra="forbid")
    resource_type: HarnessResourceType
    resource_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    expected_revision: int | None = Field(default=None, ge=0)
    committed_revision: int | None = Field(default=None, ge=0)
    first_sequence: int | None = Field(default=None, ge=1)
    last_sequence: int | None = Field(default=None, ge=1)


class DiagnosticCanonicalResourcesV1(BaseModel):
    model_config = ConfigDict(extra="forbid")
    context_subjects: list[DiagnosticResourceSubjectV1] = Field(default_factory=list, max_length=64)
    attempted_outputs: list[DiagnosticResourceSubjectV1] = Field(default_factory=list, max_length=64)
    committed_outputs: list[DiagnosticCommittedResourceV1] = Field(default_factory=list, max_length=64)
    scope: Literal["historical_canonical_projection_requires_read_back"] = "historical_canonical_projection_requires_read_back"


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
    resources: DiagnosticCanonicalResourcesV1 | None = None
    resources_gap: Literal["not_backfilled", "source_removed", "source_invalid_or_unavailable"] | None = "not_backfilled"
    components: list[HarnessContractRef] = Field(default_factory=list, max_length=64)
    attempts: list[DiagnosticAttemptMetricV1] = Field(default_factory=list, max_length=128)
    provider: None = None
    model: None = None
    tokens: None = None
    cost: None = None
    usage_gap: Literal["not_recorded_in_canonical_trace"] = "not_recorded_in_canonical_trace"
    correlation_gap: Literal["resolve_request_links_separately"] = "resolve_request_links_separately"
