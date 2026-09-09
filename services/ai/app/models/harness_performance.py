"""Versioned pre-execution limits and content-free budget evidence."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


HARNESS_PERFORMANCE_BUDGET_VERSION = "harness-performance-budget-v1"
# These bound one admitted stage, not the size of an entire installation.
CONTEXT_MAX_BYTES = 256 * 1024
CONTEXT_MAX_REFERENCES = 64
SNAPSHOT_MAX_BYTES = 64 * 1024 * 1024
RESOLVED_MAX_BYTES = 128 * 1024 * 1024
RUNTIME_MAX_ATTEMPTS = 64
RUNTIME_MAX_EVIDENCE_BYTES = 1024 * 1024


class HarnessBudgetViolationV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    budget_version: Literal["harness-performance-budget-v1"] = HARNESS_PERFORMANCE_BUDGET_VERSION
    dimension: Literal[
        "context_bytes", "reference_count", "snapshot_bytes", "resolved_bytes",
        "attempt_count", "runtime_evidence_bytes",
    ]
    actual: int = Field(ge=0)
    limit: int = Field(ge=0)


class HarnessBudgetExceeded(RuntimeError):
    def __init__(self, dimension: str, actual: int, limit: int):
        self.evidence = HarnessBudgetViolationV1(dimension=dimension, actual=actual, limit=limit)
        self.code = f"harness_budget_{dimension}_exceeded"
        super().__init__(self.code)


def canonical_byte_count(payload: object) -> int:
    """Count canonical UTF-8 bytes without retaining a second full JSON string.

    This is a size measurement, never a trace digest of protected content.
    Match canonical_harness_digest's JSON settings.
    """
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(mode="json", exclude_none=False)
    if isinstance(payload, bytes):
        return len(payload)
    encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sum(len(part.encode("utf-8")) for part in encoder.iterencode(payload))


def enforce_budget(dimension: str, actual: int, limit: int) -> None:
    if actual > limit:
        raise HarnessBudgetExceeded(dimension, actual, limit)
