"""Content-free diagnostic hints; never authorization or commit evidence."""
from typing import Annotated, Literal
from app.models.diagnostic_tool import DiagnosticToolMetricV1
from app.models.diagnostic_provider import DiagnosticProviderMetricV1
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.models.harness import HarnessStage, HarnessWorkflow, HarnessAttemptPhase, HarnessAttemptStatus
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN

Identity = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,96}$")]


DIAGNOSTIC_EVENT_CATALOG = {
    "request_started": ("transport", "info", "started", None),
    "response_headers": ("transport", "info", "headers_received", None),
    "request_finished": ("transport", "info", "completed", None),
    "request_failed": ("transport", "error", "failed", "transport_failure"),
    "request_cancelled": ("transport", "warning", "cancelled", "cancelled"),
    "lifecycle_started": ("lifecycle", "info", "started", None),
    "lifecycle_stopped": ("lifecycle", "info", "completed", None),
    "harness_reference": ("harness", "info", "observed", None),
    "resource_reference": ("resource", "info", "observed", None),
    "provider_started": ("provider", "info", "started", None),
    "provider_finished": ("provider", "info", "completed", None),
    "provider_failed": ("provider", "error", "failed", "provider_failure"),
    "provider_attempt_started": ("provider", "info", "started", None),
    "provider_attempt_finished": ("provider", "info", "completed", None),
    "provider_attempt_failed": ("provider", "error", "failed", "provider_failure"),
    "tool_started": ("tool", "info", "started", None),
    "tool_finished": ("tool", "info", "completed", None),
    "tool_failed": ("tool", "error", "failed", "tool_failure"),
    "tool_unknown": ("tool", "warning", "unknown", None),
}


def classify_diagnostic(name, status_code=None):
    category, severity, outcome, error_code = DIAGNOSTIC_EVENT_CATALOG[name]
    if name in {"response_headers", "request_finished"} and isinstance(status_code, int) and status_code >= 400:
        severity, error_code = "error" if status_code >= 500 else "warning", "http_error"
        if name == "request_finished":
            outcome = "failed"
    return dict(category=category, severity=severity, outcome=outcome, error_code=error_code)



class DiagnosticHarnessReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    operation_id: Annotated[str, Field(pattern=HARNESS_OPERATION_ID_PATTERN)]
    workflow: HarnessWorkflow
    stage: HarnessStage
    trace_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9:._-]{1,160}$")] | None = None
    attempt_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9:._-]{1,160}$")] | None = None
    attempt_index: Annotated[int, Field(ge=1)] | None = None
    phase: HarnessAttemptPhase | None = None
    attempt_status: HarnessAttemptStatus | None = None

    @model_validator(mode="after")
    def coherent_attempt(self):
        fields = (self.attempt_id, self.attempt_index, self.phase, self.attempt_status)
        if any(value is not None for value in fields) and (self.trace_id is None or any(value is None for value in fields)):
            raise ValueError("diagnostic_attempt_reference_incomplete")
        return self

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
    name: Literal["request_started", "response_headers", "request_finished", "request_failed", "request_cancelled", "lifecycle_started", "lifecycle_stopped", "harness_reference", "resource_reference", "provider_started", "provider_finished", "provider_failed", "provider_attempt_started", "provider_attempt_finished", "provider_attempt_failed", "tool_started", "tool_finished", "tool_failed", "tool_unknown"]
    span_id: Identity | None = None
    parent_span_id: Identity | None = None
    tool_metric: DiagnosticToolMetricV1 | None = None
    provider_metric: DiagnosticProviderMetricV1 | None = None
    harness: DiagnosticHarnessReferenceV1 | None = None
    resource: DiagnosticResourceReferenceV1 | None = None
    category: Literal["transport", "lifecycle", "harness", "resource", "provider", "tool"]
    severity: Literal["info", "warning", "error"]
    outcome: Literal["started", "headers_received", "completed", "failed", "cancelled", "observed", "unknown"]
    error_code: Literal["transport_failure", "http_error", "cancelled", "provider_failure", "tool_failure"] | None

    @model_validator(mode="before")
    @classmethod
    def reviewed_classification(cls, value):
        if isinstance(value, dict) and isinstance(value.get("name"), str) and value.get("name") in DIAGNOSTIC_EVENT_CATALOG:
            expected = classify_diagnostic(value["name"], value.get("status_code"))
            if any(key in value and value[key] != item for key, item in expected.items()):
                raise ValueError("diagnostic_classification_mismatch")
            value = {**value, **expected}
        return value

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
