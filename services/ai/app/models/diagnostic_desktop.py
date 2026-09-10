"""Native spool whitelist; filenames, process arguments and error text are excluded."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

DesktopEventName = Literal["desktop_started", "sidecar_spawned", "sidecar_ready", "sidecar_startup_failed", "sidecar_exited", "desktop_shutdown_requested", "sidecar_stopped", "sidecar_shutdown_unknown", "desktop_stopped"]


class DesktopSpoolRecordV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["desktop-diagnostic-v1"]
    event_id: str = Field(pattern=r"^desktop-[a-f0-9-]{1,88}$")
    instance_id: str = Field(pattern=r"^desktop-[a-f0-9-]{1,88}$")
    name: DesktopEventName
    unix_time_ms: int = Field(ge=0, le=253402300799000)
    duration_ms: int | None = Field(default=None, ge=0, le=9007199254740991)
    exit_code: int | None = Field(default=None, ge=-(2**31), le=2**31-1)
    dropped_before: int = Field(ge=0)
    write_failures_before: int = Field(ge=0)


class DiagnosticDesktopMetricV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    instance_id: str = Field(pattern=r"^desktop-[a-f0-9-]{1,88}$")
    exit_code: int | None = Field(default=None, ge=-(2**31), le=2**31-1)
    dropped_before: int = Field(ge=0)
    write_failures_before: int = Field(ge=0)
