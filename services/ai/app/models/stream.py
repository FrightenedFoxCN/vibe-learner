from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from app.models.harness import canonical_harness_digest

STREAM_EVENT_SCHEMA_VERSION = "stream-event-v1"
STREAM_REPORT_SCHEMA_VERSION = "stream-report-v1"

DOCUMENT_PROCESS_STREAM_PAYLOAD_CONTRACT = "document-process-stream-payload-v1"
LEARNING_PLAN_STREAM_PAYLOAD_CONTRACT = "learning-plan-stream-payload-v1"
DOCUMENT_STREAM_PROJECTION_CONTRACT = "document-record-v1"
LEARNING_PLAN_STREAM_PROJECTION_CONTRACT = "learning-plan-record-v1"

StreamKind = Literal["document_process", "learning_plan"]
StreamSubjectType = Literal["document", "learning_plan_request"]
StreamReportStatus = Literal["idle", "running", "completed", "error", "cancelled"]
StreamCommitStatus = Literal["committed", "not_committed", "uncertain"]
StreamResourceType = Literal["document", "learning_plan"]

DOCUMENT_PROCESS_STREAM_STAGES = frozenset(
    {
        "document_processing_started",
        "parser_started",
        "page_parsed",
        "margin_patterns_detected",
        "sections_built",
        "chunks_built",
        "study_units_built",
        "document_processing_completed",
        "stream_completed",
        "stream_error",
        "stream_cancelled",
    }
)
LEARNING_PLAN_STREAM_STAGES = frozenset(
    {
        "learning_plan_started",
        "study_units_ready",
        "heuristic_plan_built",
        "model_round_started",
        "planning_question_asked",
        "model_tool_call",
        "model_round_completed",
        "model_round_failed",
        "model_recovery_attempt",
        "model_fallback_started",
        "model_fallback_succeeded",
        "model_plan_applied",
        "learning_plan_completed",
        "stream_completed",
        "stream_error",
        "stream_cancelled",
    }
)
TERMINAL_STREAM_STAGES = frozenset(
    {"stream_completed", "stream_error", "stream_cancelled"}
)


class StreamSubjectRefV1(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject_type: StreamSubjectType
    subject_id: str = Field(min_length=1, max_length=80)


class StreamTerminalEvidenceV1(BaseModel):
    """Transport terminal evidence; this is not Harness v3 commit evidence."""

    model_config = ConfigDict(extra="forbid")

    commit_status: StreamCommitStatus
    domain_operation_id: str = Field(default="", max_length=96)
    domain_operation_status: str = Field(default="", max_length=32)
    evidence_scope: Literal["primary_output_only"] = "primary_output_only"
    resource_type: StreamResourceType | None = None
    resource_id: str | None = Field(default=None, max_length=80)
    commit_contract_version: str | None = Field(default=None, max_length=80)
    projection_contract_version: str | None = Field(default=None, max_length=80)
    projection_digest: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_evidence_shape(self) -> "StreamTerminalEvidenceV1":
        projection_fields = (
            self.resource_type,
            self.resource_id,
            self.commit_contract_version,
            self.projection_contract_version,
            self.projection_digest,
        )
        if self.commit_status == "committed":
            if not self.domain_operation_id or not self.domain_operation_status:
                raise ValueError("committed_stream_domain_operation_evidence_required")
            if self.domain_operation_status != "committed":
                raise ValueError("committed_stream_domain_status_mismatch")
            if any(value is None or value == "" for value in projection_fields):
                raise ValueError("committed_stream_projection_evidence_required")
        elif any(value is not None for value in projection_fields):
            raise ValueError("uncommitted_stream_has_projection_evidence")
        return self


class StreamEventRecord(BaseModel):
    """Strict v1 event plus an explicit no-version legacy compatibility shape."""

    model_config = ConfigDict(extra="forbid")

    event_schema_version: Literal["stream-event-v1"] | None = None
    operation_id: str | None = Field(default=None, max_length=80)
    event_id: str | None = Field(default=None, max_length=128)
    event_sequence: int | None = Field(default=None, ge=1, le=9_007_199_254_740_991)
    stream_kind: StreamKind | None = None
    subject: StreamSubjectRefV1 | None = None
    stage: str = Field(min_length=1, max_length=64)
    payload_contract_version: str | None = Field(default=None, max_length=80)
    payload_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    terminal_evidence: StreamTerminalEvidenceV1 | None = None
    committed_projection: dict[str, JsonValue] | None = None
    created_at: str = Field(min_length=1, max_length=64)

    @model_validator(mode="before")
    @classmethod
    def reject_partial_legacy_upgrade(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("event_schema_version") is not None:
            return value
        v1_only_fields = {
            "operation_id",
            "event_id",
            "event_sequence",
            "stream_kind",
            "subject",
            "payload_contract_version",
            "payload_digest",
            "terminal_evidence",
            "committed_projection",
        }
        if any(value.get(field) is not None for field in v1_only_fields):
            raise ValueError("legacy_stream_event_has_v1_evidence")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "StreamEventRecord":
        if self.event_schema_version is None:
            return self
        required = (
            self.operation_id,
            self.event_id,
            self.event_sequence,
            self.stream_kind,
            self.subject,
            self.payload_contract_version,
            self.payload_digest,
        )
        if any(value is None or value == "" for value in required):
            raise ValueError("versioned_stream_event_evidence_incomplete")
        assert self.operation_id is not None
        assert self.event_sequence is not None
        assert self.stream_kind is not None
        assert self.subject is not None
        expected_event_id = f"{self.operation_id}:event:{self.event_sequence}"
        if self.event_id != expected_event_id:
            raise ValueError("stream_event_identity_mismatch")
        allowed_stages = (
            DOCUMENT_PROCESS_STREAM_STAGES
            if self.stream_kind == "document_process"
            else LEARNING_PLAN_STREAM_STAGES
        )
        if self.stage not in allowed_stages:
            raise ValueError("stream_event_stage_unregistered")
        expected_subject_type = (
            "document"
            if self.stream_kind == "document_process"
            else {"document", "learning_plan_request"}
        )
        if isinstance(expected_subject_type, str):
            if self.subject.subject_type != expected_subject_type:
                raise ValueError("stream_subject_type_mismatch")
        elif self.subject.subject_type not in expected_subject_type:
            raise ValueError("stream_subject_type_mismatch")
        expected_payload_contract = (
            DOCUMENT_PROCESS_STREAM_PAYLOAD_CONTRACT
            if self.stream_kind == "document_process"
            else LEARNING_PLAN_STREAM_PAYLOAD_CONTRACT
        )
        if self.payload_contract_version != expected_payload_contract:
            raise ValueError("stream_payload_contract_mismatch")
        if canonical_harness_digest(self.payload) != self.payload_digest:
            raise ValueError("stream_payload_digest_mismatch")
        payload_document_id = self.payload.get("document_id")
        if (
            self.subject.subject_type == "document"
            and payload_document_id is not None
            and payload_document_id != self.subject.subject_id
        ):
            raise ValueError("stream_payload_subject_mismatch")
        is_terminal = self.stage in TERMINAL_STREAM_STAGES
        if is_terminal != (self.terminal_evidence is not None):
            raise ValueError("stream_terminal_evidence_mismatch")
        if not is_terminal and self.committed_projection is not None:
            raise ValueError("nonterminal_stream_has_committed_projection")
        if self.stage == "stream_completed":
            if (
                self.terminal_evidence is None
                or self.terminal_evidence.commit_status != "committed"
                or self.committed_projection is None
            ):
                raise ValueError("completed_stream_commit_evidence_required")
            expected_resource_type = (
                "document" if self.stream_kind == "document_process" else "learning_plan"
            )
            expected_projection_contract = (
                DOCUMENT_STREAM_PROJECTION_CONTRACT
                if self.stream_kind == "document_process"
                else LEARNING_PLAN_STREAM_PROJECTION_CONTRACT
            )
            if self.terminal_evidence.resource_type != expected_resource_type:
                raise ValueError("stream_committed_resource_type_mismatch")
            if (
                self.terminal_evidence.projection_contract_version
                != expected_projection_contract
            ):
                raise ValueError("stream_projection_contract_mismatch")
            projection_id = self.committed_projection.get("id")
            if projection_id != self.terminal_evidence.resource_id:
                raise ValueError("stream_projection_resource_identity_mismatch")
            if (
                self.stream_kind == "document_process"
                and projection_id != self.subject.subject_id
            ):
                raise ValueError("stream_projection_subject_identity_mismatch")
            if (
                canonical_harness_digest(self.committed_projection)
                != self.terminal_evidence.projection_digest
            ):
                raise ValueError("stream_projection_digest_mismatch")
        elif self.stage in {"stream_error", "stream_cancelled"}:
            if (
                self.terminal_evidence is None
                or self.terminal_evidence.commit_status == "committed"
                or self.committed_projection is not None
            ):
                raise ValueError("failed_stream_must_not_claim_commit")
        return self

    @property
    def is_versioned(self) -> bool:
        return self.event_schema_version == STREAM_EVENT_SCHEMA_VERSION


class StreamReportRecord(BaseModel):
    """Persisted replay report with strict v1 and read-only legacy compatibility."""

    model_config = ConfigDict(extra="forbid")

    report_schema_version: Literal["stream-report-v1"] | None = None
    operation_id: str | None = Field(default=None, max_length=80)
    subject: StreamSubjectRefV1 | None = None
    document_id: str = Field(min_length=1, max_length=80)
    stream_kind: str = Field(min_length=1, max_length=64)
    status: StreamReportStatus = "idle"
    last_event_sequence: int | None = Field(
        default=None,
        ge=0,
        le=9_007_199_254_740_991,
    )
    created_at: str = Field(max_length=64)
    updated_at: str = Field(max_length=64)
    events: list[StreamEventRecord] = Field(default_factory=list, max_length=120)

    @model_validator(mode="before")
    @classmethod
    def reject_partial_legacy_upgrade(cls, value: Any) -> Any:
        if not isinstance(value, dict) or value.get("report_schema_version") is not None:
            return value
        for field in ("operation_id", "subject", "last_event_sequence"):
            if value.get(field) is not None:
                raise ValueError("legacy_stream_report_has_v1_evidence")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> "StreamReportRecord":
        if self.report_schema_version is None:
            if any(event.is_versioned for event in self.events):
                raise ValueError("legacy_stream_report_has_versioned_event")
            return self
        if self.stream_kind not in {"document_process", "learning_plan"}:
            raise ValueError("stream_report_kind_unregistered")
        if self.operation_id is None or self.subject is None or self.last_event_sequence is None:
            raise ValueError("versioned_stream_report_evidence_incomplete")
        expected_sequence = self.last_event_sequence - len(self.events) + 1
        for event in self.events:
            if not event.is_versioned:
                raise ValueError("versioned_stream_report_has_legacy_event")
            if (
                event.operation_id != self.operation_id
                or event.stream_kind != self.stream_kind
                or event.subject != self.subject
            ):
                raise ValueError("stream_report_event_scope_mismatch")
            if event.event_sequence != expected_sequence:
                raise ValueError("stream_report_event_sequence_gap")
            expected_sequence += 1
        terminal_stage = self.events[-1].stage if self.events else ""
        expected_status = {
            "stream_completed": "completed",
            "stream_error": "error",
            "stream_cancelled": "cancelled",
        }.get(terminal_stage, "running")
        if self.status != expected_status:
            raise ValueError("stream_report_status_mismatch")
        if any(event.stage in TERMINAL_STREAM_STAGES for event in self.events[:-1]):
            raise ValueError("stream_report_event_after_terminal")
        return self
