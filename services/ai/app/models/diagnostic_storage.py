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


class DiagnosticStorageDatabaseV1(StorageModel):
    name: Literal["events", "index"]
    max_bytes: int | None = Field(ge=0)
    files: DiagnosticStorageFilesV1 | None
    counters: DiagnosticStorageCountersV1 | None
    status: Literal["within_observed_limit", "over_observed_limit", "unavailable"]
    gap: Literal["not_configured", "database_absent", "filesystem_unavailable"] | None


class DiagnosticStorageV1(StorageModel):
    schema_version: Literal["diagnostic-storage-v1"] = "diagnostic-storage-v1"
    observed_at: datetime
    databases: list[DiagnosticStorageDatabaseV1] = Field(min_length=2, max_length=2)
    observation_scope: Literal["independent_live_file_lengths_and_process_counters"] = "independent_live_file_lengths_and_process_counters"
    sizes_are_atomic: Literal[False] = False
    counters_are_process_local: Literal[True] = True
    admission_guarantee: Literal[False] = False
    installation_disk_limit_certified: Literal[False] = False
    unmeasured: list[Literal["desktop_spool", "filesystem_allocation_and_metadata", "external_writers", "vacuum_temporary_files"]] = Field(min_length=4, max_length=4)
