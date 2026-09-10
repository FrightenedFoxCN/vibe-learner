"""Content-free export contract. Database snapshots do not prove business commits."""
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.models.diagnostic import DiagnosticEventV1, DiagnosticOperationLinkV1, DiagnosticPagePath, Identity
from app.models.diagnostic_audit import AuditModel, DiagnosticAuditV1
from app.models.diagnostic_index import DiagnosticHarnessIndexV1
from app.models.diagnostic_retention import DiagnosticRecordRetentionV1
from app.models.diagnostic_storage import DiagnosticStorageV1
from app.models.diagnostic_writer import DiagnosticWriterCoverageV1
from app.models.harness import HarnessWorkflow, HarnessStage, HarnessResourceType


class DiagnosticExportFiltersV1(AuditModel):
    request_id: Identity | None = None
    action_id: Identity | None = None
    page_view_id: Identity | None = None
    flow_id: Identity | None = None
    source: Literal["browser", "server", "desktop"] | None = None
    page_path: DiagnosticPagePath | None = None
    severity: Literal["info", "warning", "error"] | None = None
    operation_id: Identity | None = None
    workflow: HarnessWorkflow | None = None
    stage: HarnessStage | None = None
    resource_id: str | None = Field(default=None, max_length=160, pattern=r"^[A-Za-z0-9:._-]{1,160}$")
    resource_type: HarnessResourceType | None = None
    since: datetime | None = None
    until: datetime | None = None

    @model_validator(mode="after")
    def time_range(self):
        if any(value is not None and value.utcoffset() is None for value in (self.since, self.until)):
            raise ValueError("diagnostic_time_timezone_required")
        if self.since is not None and self.until is not None and self.since >= self.until:
            raise ValueError("diagnostic_time_range_invalid")
        return self


class DiagnosticExportEventV1(AuditModel):
    sequence: int = Field(ge=1)
    event: DiagnosticEventV1


class DiagnosticExportRetentionV1(AuditModel):
    schema_version: Literal["diagnostic-event-retention-v1"]
    retained_events: int = Field(ge=0)
    retained_payload_bytes: int = Field(ge=0)
    removed_events: int = Field(ge=0)
    removed_through_sequence: int = Field(ge=0)
    legacy_timestamp_rows: int = Field(ge=0)
    cursor_gap: bool
    max_age_seconds: int = Field(ge=1)
    max_rows: int = Field(ge=1)
    max_payload_bytes: int = Field(ge=1)
    storage_scope: Literal["event_payloads"]
    disk_size_limit_certified: Literal[False]


class DiagnosticExportIndexCoverageV1(AuditModel):
    freshness: Literal["eventual", "unavailable"]
    cursor: str | None = Field(default=None, max_length=160)
    completed_sweeps: int | None = Field(default=None, ge=0)
    canonical_read_back_required: Literal[True] = True
    scope: Literal["all_retained", "workflow_stage", "related_operations"]
    missing_operation_count: int = Field(ge=0)
    time_and_event_filters_apply_to_traces: Literal[False] = False


class DiagnosticExportV1(AuditModel):
    schema_version: Literal["diagnostic-export-v1"] = "diagnostic-export-v1"
    storage_observation: DiagnosticStorageV1
    app_version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9.+_-]+$")
    created_at: datetime
    filters: DiagnosticExportFiltersV1
    snapshot_consistency: Literal["events_links_retention_writers_atomic_index_independent"] = "events_links_retention_writers_atomic_index_independent"
    complete_collection_claim: Literal[False] = False
    events: list[DiagnosticExportEventV1] = Field(max_length=10000)
    operation_links: list[DiagnosticOperationLinkV1] = Field(max_length=5000)
    retention: DiagnosticExportRetentionV1
    link_retention: DiagnosticRecordRetentionV1
    index_retention: DiagnosticRecordRetentionV1 | None
    writer_pages: list[DiagnosticWriterCoverageV1] = Field(min_length=1, max_length=3)
    index: list[DiagnosticHarnessIndexV1] = Field(max_length=5000)
    index_coverage: DiagnosticExportIndexCoverageV1
    audit: DiagnosticAuditV1
