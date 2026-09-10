"""Manifest-only tool metadata; results and arguments never enter diagnostics."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.harness import HarnessWorkflow, HarnessStage


class DiagnosticToolMetricV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    workflow: HarnessWorkflow
    offered_in_stage: HarnessStage
    execution_stage: HarnessStage | None = None
    manifest_key: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$")
    canonical_name: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{0,79}$")
    input_contract_version: str | None = Field(default=None, max_length=160)
    result_contract_version: str | None = Field(default=None, max_length=160)
    provider_tool_call_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,160}$")
    max_calls_per_operation: int | None = Field(default=None, ge=1, le=64)
    max_calls_per_round: int | None = Field(default=None, ge=1, le=8)
    timeout_ms: int | None = Field(default=None, ge=100, le=120_000)
    manifest_gap: Literal["unregistered_tool"] | None = None
    effect_commit_claim: Literal["none"] = "none"
