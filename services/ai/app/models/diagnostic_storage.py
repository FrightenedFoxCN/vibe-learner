"""Live file/counter observations, not an atomic disk or admission proof."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StorageModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class DiagnosticStorageFilesV1(StorageModel):
    database: int = Field(ge=0)
    wal: int = Field(ge=0)
    shm: int = Field(ge=0)
    journal: int = Field(ge=0)
    lock: int = Field(ge=0)
    total_bytes: int = Field(ge=0)


class DiagnosticStorageCountersV1(StorageModel):
    quota_refusals: int = Field(ge=0)
    quota_unavailable: int = Field(ge=0)
    maintenance_busy: int = Field(ge=0)
    maintenance_failures: int = Field(ge=0)
    maintenance_completed: int = Field(ge=0)
    legacy_migrations: int = Field(ge=0)


class DiagnosticStorageRecoveryV1(StorageModel):
    attempts: int = Field(ge=0)
    completed: int = Field(ge=0)
    deferred: int = Field(ge=0)
    failures: int = Field(ge=0)
    workspace_bytes: int = Field(ge=0)
    temporary_overage_possible: Literal[True] = True


class DiagnosticStorageDatabaseV1(StorageModel):
    name: Literal["events", "index"]
    max_bytes: int | None = Field(ge=0)
    files: DiagnosticStorageFilesV1 | None
    counters: DiagnosticStorageCountersV1 | None
    recovery: DiagnosticStorageRecoveryV1 | None
    status: Literal["within_observed_limit", "over_observed_limit", "unavailable"]
    gap: Literal["not_configured", "database_absent", "filesystem_unavailable"] | None


class DiagnosticSpoolStorageV1(StorageModel):
    status: Literal["observed", "absent", "incomplete", "unavailable"]
    gap: Literal["not_configured", "filesystem_unavailable", "scan_limit", "unsupported_entry"] | None
    event_files: int = Field(ge=0, le=1024)
    event_bytes: int = Field(ge=0)
    metadata_bytes: int = Field(ge=0)
    other_files: int = Field(ge=0, le=1024)
    other_bytes: int = Field(ge=0)
    skipped_entries: int = Field(ge=0, le=1024)
    total_bytes: int = Field(ge=0)
    max_event_files: Literal[256] = 256
    max_event_bytes: Literal[4194304] = 4194304
    scan_limit: Literal[1024] = 1024


class DiagnosticDirectoryStorageV1(StorageModel):
    scope: Literal["diagnostics_directory_regular_file_lengths"]
    status: Literal["observed", "absent", "incomplete", "unavailable"]
    gaps: list[Literal["not_configured", "filesystem_unavailable", "configured_database_outside_directory", "scan_limit", "depth_limit", "time_limit", "unsupported_entry"]] = Field(max_length=7)
    budget_state: Literal["within_observed_limit", "over_observed_limit", "unknown"]
    database_bytes: int = Field(ge=0)
    spool_bytes: int = Field(ge=0)
    other_bytes: int = Field(ge=0)
    total_bytes: int = Field(ge=0)
    database_files: int = Field(ge=0, le=4096)
    spool_files: int = Field(ge=0, le=4096)
    other_files: int = Field(ge=0, le=4096)
    scanned_entries: int = Field(ge=0, le=4096)
    visited_directories: int = Field(ge=0, le=4097)
    skipped_entries: int = Field(ge=0, le=4096)
    max_bytes: Literal[209715200] = 209715200
    scan_limit: Literal[4096] = 4096
    max_depth: Literal[4] = 4
    scan_budget_ms: Literal[100] = 100


class DiagnosticStorageV1(StorageModel):
    schema_version: Literal["diagnostic-storage-v1"] = "diagnostic-storage-v1"
    observed_at: datetime
    databases: list[DiagnosticStorageDatabaseV1] = Field(min_length=2, max_length=2)
    desktop_spool: DiagnosticSpoolStorageV1
    directory: DiagnosticDirectoryStorageV1
    observation_scope: Literal["independent_live_file_lengths_and_process_counters"] = "independent_live_file_lengths_and_process_counters"
    sizes_are_atomic: Literal[False] = False
    counters_are_process_local: Literal[True] = True
    admission_guarantee: Literal[False] = False
    installation_disk_limit_certified: Literal[False] = False
    unmeasured: list[Literal["filesystem_allocation_and_metadata", "external_writers", "vacuum_temporary_files"]] = Field(min_length=3, max_length=3)
