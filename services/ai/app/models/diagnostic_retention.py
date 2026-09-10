from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class DiagnosticRecordRetentionV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["diagnostic-record-retention-v1"] = "diagnostic-record-retention-v1"
    table: Literal["operation_links", "projections"]
    retained_rows: int = Field(ge=0)
    retained_payload_bytes: int = Field(ge=0)
    removed_rows: int = Field(ge=0)
    legacy_timestamp_rows: int = Field(ge=0)
    max_rows: int = Field(ge=1)
    max_payload_bytes: int = Field(ge=1)
    max_age_seconds: int = Field(ge=1)
    age_basis: Literal["first_local_observation", "canonical_update_or_first_local_observation"]
    removed_count_scope: Literal["deletions_not_unique_identities"] = "deletions_not_unique_identities"
    source_age_exclusions_possible: bool
    complete_history_claim: Literal[False] = False
    disk_size_limit_certified: Literal[False] = False
