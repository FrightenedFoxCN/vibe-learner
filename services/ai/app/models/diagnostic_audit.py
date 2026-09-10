"""Reviewed metric-only audit DTOs. No protected content or business commit claims."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.harness import HarnessWorkflow, HarnessStage, HarnessContractRef

MetricKind = Literal["provider_call", "provider_attempt", "tool_call", "harness_stage", "harness_attempt"]
MetricOutcome = Literal["completed", "failed", "cancelled", "unknown", "skipped"]
MetricGap = Literal["missing_start", "missing_terminal", "missing_span", "conflicting_span_records", "harness_reference_missing", "component_context_unavailable", "endpoint_configuration_not_recorded", "provider_cost_evidence_unavailable", "usage_not_returned", "usage_partial_or_invalid", "usage_not_additive", "source_unavailable", "duration_unavailable", "model_label_unreviewed", "metric_missing"]

class AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

class DiagnosticAuditGroupKeyV1(AuditModel):
    kind: MetricKind
    workflow: HarnessWorkflow | None = None
    stage: HarnessStage | None = None
    phase: Literal["generate", "decode", "validate", "repair", "commit", "rollback"] | None = None
    provider: Literal["litellm"] | None = None
    request_kind: Literal["plan", "chat", "setting", "embedding", "other"] | None = None
    model: str | None = Field(default=None, max_length=160)
    provider_contract: Literal["diagnostic-provider-transport-v1"] | None = None
    timeout_ms: int | None = Field(default=None, ge=0)
    retry_limit: int | None = Field(default=None, ge=1)
    tool_name: str | None = Field(default=None, max_length=80)
    input_contract: str | None = Field(default=None, max_length=160)
    result_contract: str | None = Field(default=None, max_length=160)
    tool_max_calls_operation: int | None = Field(default=None, ge=1)
    tool_max_calls_round: int | None = Field(default=None, ge=1)
    components: list[HarnessContractRef] = Field(default_factory=list, max_length=64)

class DiagnosticAuditObservationV1(AuditModel):
    sample_id: str = Field(max_length=200)
    group: DiagnosticAuditGroupKeyV1
    event_ids: list[str] = Field(default_factory=list, max_length=10000)
    operation_id: str | None = Field(default=None, max_length=96)
    trace_id: str | None = Field(default=None, max_length=160)
    span_id: str | None = Field(default=None, max_length=96)
    parent_span_id: str | None = Field(default=None, max_length=96)
    outcome: MetricOutcome
    duration_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    recovered: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    gaps: list[MetricGap] = Field(default_factory=list, max_length=16)

class DiagnosticAuditGapCountV1(AuditModel):
    gap: MetricGap
    count: int = Field(ge=1)

class DiagnosticAuditGroupV1(AuditModel):
    key: DiagnosticAuditGroupKeyV1
    sample_count: int = Field(ge=1)
    completed_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    cancelled_count: int = Field(ge=0)
    unknown_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    recovered_count: int = Field(ge=0)
    duration_sample_count: int = Field(ge=0)
    p50_ms: float | None = Field(ge=0, allow_inf_nan=False)
    p95_ms: float | None = Field(ge=0, allow_inf_nan=False)
    input_tokens: int | None = Field(ge=0)
    output_tokens: int | None = Field(ge=0)
    total_tokens: int | None = Field(ge=0)
    input_token_sample_count: int = Field(ge=0)
    output_token_sample_count: int = Field(ge=0)
    total_token_sample_count: int = Field(ge=0)
    gaps: list[DiagnosticAuditGapCountV1]

class DiagnosticAuditV1(AuditModel):
    schema_version: Literal["diagnostic-audit-v1"] = "diagnostic-audit-v1"
    observations: list[DiagnosticAuditObservationV1] = Field(max_length=20000)
    groups: list[DiagnosticAuditGroupV1] = Field(max_length=20000)
    input_event_count: int = Field(ge=0)
    input_trace_count: int = Field(ge=0)
    duplicate_event_count: int = Field(ge=0)
    percentile_method: Literal["nearest_rank"] = "nearest_rank"
    duration_aggregation: Literal["per_kind_inclusive_never_additive"] = "per_kind_inclusive_never_additive"
    token_aggregation: Literal["provider_attempts_only"] = "provider_attempts_only"
    commit_claim: Literal["none"] = "none"
    coverage_gap: Literal["bounded_inputs_not_complete_installation"] = "bounded_inputs_not_complete_installation"
