from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DiagnosticWriterEpochV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    sequence: int = Field(ge=1)
    epoch_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    started_at: int = Field(ge=0)
    observed_at: int = Field(ge=0)
    closed_at: int | None = Field(ge=0)
    observed_dropped: int = Field(ge=0)
    observed_write_failures: int = Field(ge=0)
    observed_read_failures: int = Field(ge=0)


class DiagnosticWriterTotalsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    retired_epochs: int = Field(ge=0)
    retired_unclosed: int = Field(ge=0)
    retained_epochs: int = Field(ge=0)
    unclosed_epochs: int = Field(ge=0)
    observed_dropped: int = Field(ge=0)
    observed_write_failures: int = Field(ge=0)
    observed_read_failures: int = Field(ge=0)


class DiagnosticWriterCoverageV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["diagnostic-writer-coverage-v1"]
    items: list[DiagnosticWriterEpochV1] = Field(max_length=100)
    next_cursor: int = Field(ge=0)
    has_more: bool
    totals: DiagnosticWriterTotalsV1
    counts_are_lower_bounds: Literal[True]
    unpersisted_queue_gap: Literal[True]
    startup_before_epoch_gap: Literal[True]
    unclosed_meaning: Literal["active_or_interrupted"]
    complete_collection_claim: Literal[False]
