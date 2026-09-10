"""Content-free diagnostic hints; never authorization or commit evidence."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN

Identity = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,96}$")]


class DiagnosticHarnessReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: Annotated[str, Field(pattern=HARNESS_OPERATION_ID_PATTERN)]
    workflow: HarnessWorkflow
    stage: HarnessStage
    trace_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9:._-]{1,160}$")] | None = None
    # A reference is an index hint; clients must resolve canonical records for truth.


class DiagnosticResourceReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    resource_type: Literal["persona"]
    resource_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9:._-]{1,160}$")]
    revision: Annotated[int, Field(ge=0)] | None = None


class DiagnosticEventV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal["diagnostic-event-v1"] = "diagnostic-event-v1"
    event_id: Identity
    source: Literal["server", "browser", "desktop"]
    name: Literal["request_started", "response_headers", "request_finished", "request_failed", "request_cancelled", "lifecycle_started", "lifecycle_stopped", "harness_reference", "resource_reference"]
    harness: DiagnosticHarnessReferenceV1 | None = None
    resource: DiagnosticResourceReferenceV1 | None = None
    timestamp: Annotated[str, Field(max_length=40)]
    request_id: Identity | None = None
    client_instance_id: Identity | None = None
    page_view_id: Identity | None = None
    flow_id: Identity | None = None
    action_id: Identity | None = None
    duration_ms: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    status_code: Annotated[int, Field(ge=100, le=599)] | None = None
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"] | None = None
    # Reviewed route templates only; raw paths, query strings and bodies are excluded.
    route: Annotated[str, Field(max_length=160, pattern=r"^/[a-zA-Z0-9_/{\}-]*$")] | None = None
