"""Reviewed provider telemetry whitelist; no URLs, prompts, credentials or SDK error text."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DiagnosticProviderMetricV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    adapter: Literal["litellm"] = "litellm"
    adapter_contract: Literal["diagnostic-provider-transport-v1"] = "diagnostic-provider-transport-v1"
    request_kind: Literal["plan", "chat", "setting", "embedding", "other"]
    model: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")
    model_gap: Literal["model_label_unreviewed"] | None = None
    timeout_seconds: int = Field(ge=0)
    max_attempts: Literal[3] = 3
    attempt_index: int | None = Field(default=None, ge=1, le=3)
    attempts_used: int = Field(ge=0, le=3)
    recovered: bool = False
    input_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    output_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    total_tokens: int | None = Field(default=None, ge=0, le=1_000_000_000_000)
    usage_source: Literal["provider_reported", "unavailable"]
    usage_gap: Literal["not_returned", "partial_or_invalid", "aggregate_not_additive"] | None = None
    cost: None = None
    cost_gap: Literal["provider_cost_evidence_unavailable"] = "provider_cost_evidence_unavailable"
    configuration_gap: Literal["endpoint_configuration_not_recorded"] = "endpoint_configuration_not_recorded"
