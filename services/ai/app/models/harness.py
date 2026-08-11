from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HarnessStatus(StrEnum):
    PASSED = "passed"
    REPAIRED = "repaired"
    FAILED = "failed"
    SKIPPED = "skipped"


class HarnessCheckStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    SKIPPED = "skipped"


class HarnessCheckRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: HarnessCheckStatus
    code: str = ""
    message: str = ""


class HarnessTraceRecord(BaseModel):
    """Workflow-neutral evidence emitted by a validate/repair/commit harness."""

    model_config = ConfigDict(extra="forbid")

    version: str
    workflow: str
    stage: str
    status: HarnessStatus
    schema_name: str
    input_digest: str = ""
    context_digest: str = ""
    checks: list[HarnessCheckRecord] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=1, le=3)
    recovery_strategy: str = "none"
    duration_ms: int = Field(default=0, ge=0)
