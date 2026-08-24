from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from app.models.harness import canonical_harness_digest
from app.models.stream import (
    DOCUMENT_PROCESS_STREAM_PAYLOAD_CONTRACT,
    LEARNING_PLAN_STREAM_PAYLOAD_CONTRACT,
    STREAM_EVENT_SCHEMA_VERSION,
    STREAM_REPORT_SCHEMA_VERSION,
    StreamEventRecord,
    StreamReportRecord,
    StreamSubjectRefV1,
    StreamTerminalEvidenceV1,
)
from app.services.local_store import LocalJsonStore

DOCUMENT_PROCESS_STREAM_CATEGORY = "document_process_stream"
LEARNING_PLAN_STREAM_CATEGORY = "learning_plan_stream"
MAX_STREAM_EVENTS = 120


class StreamReportRecorder:
    def __init__(
        self,
        *,
        store: LocalJsonStore,
        category: str,
        document_id: str,
        stream_kind: Literal["document_process", "learning_plan"],
        subject: StreamSubjectRefV1,
        operation_id: str | None = None,
        max_events: int = MAX_STREAM_EVENTS,
    ) -> None:
        self.store = store
        self.category = category
        self.document_id = document_id
        self.stream_kind = stream_kind
        self.subject = subject
        self.operation_id = operation_id or f"stream-{uuid4().hex[:12]}"
        if max_events < 1 or max_events > MAX_STREAM_EVENTS:
            raise ValueError("stream_report_max_events_out_of_range")
        self.max_events = max_events
        now = _now()
        self.report = StreamReportRecord(
            report_schema_version=STREAM_REPORT_SCHEMA_VERSION,
            operation_id=self.operation_id,
            subject=subject,
            document_id=document_id,
            stream_kind=stream_kind,
            status="running",
            last_event_sequence=0,
            created_at=now,
            updated_at=now,
            events=[],
        )
        self._persist()

    def callback(self, stage: str, payload: dict[str, object]) -> None:
        self.emit(stage, payload)

    def emit(
        self,
        stage: str,
        payload: dict[str, object] | None = None,
        *,
        terminal_evidence: StreamTerminalEvidenceV1 | None = None,
        committed_projection: dict[str, object] | None = None,
    ) -> StreamEventRecord:
        if self.report.status != "running":
            raise ValueError("stream_event_after_terminal")
        now = _now()
        normalized_payload = payload or {}
        sequence = (self.report.last_event_sequence or 0) + 1
        next_event = StreamEventRecord(
            event_schema_version=STREAM_EVENT_SCHEMA_VERSION,
            operation_id=self.operation_id,
            event_id=f"{self.operation_id}:event:{sequence}",
            event_sequence=sequence,
            stream_kind=self.stream_kind,
            subject=self.subject,
            stage=stage,
            payload_contract_version=(
                DOCUMENT_PROCESS_STREAM_PAYLOAD_CONTRACT
                if self.stream_kind == "document_process"
                else LEARNING_PLAN_STREAM_PAYLOAD_CONTRACT
            ),
            payload_digest=canonical_harness_digest(normalized_payload),
            payload=normalized_payload,
            terminal_evidence=terminal_evidence,
            committed_projection=committed_projection,
            created_at=now,
        )
        retained_events = (
            self.report.events[-(self.max_events - 1) :]
            if self.max_events > 1
            else []
        )
        next_events = [*retained_events, next_event]
        status: Literal["running", "completed", "error", "cancelled"] = "running"
        if stage == "stream_completed":
            status = "completed"
        elif stage == "stream_error":
            status = "error"
        elif stage == "stream_cancelled":
            status = "cancelled"
        self.report = StreamReportRecord(
            report_schema_version=STREAM_REPORT_SCHEMA_VERSION,
            operation_id=self.operation_id,
            subject=self.subject,
            document_id=self.document_id,
            stream_kind=self.stream_kind,
            status=status,
            last_event_sequence=sequence,
            created_at=self.report.created_at,
            updated_at=now,
            events=next_events,
        )
        self._persist()
        return next_event

    @classmethod
    def load(
        cls,
        *,
        store: LocalJsonStore,
        category: str,
        document_id: str,
        stream_kind: str,
    ) -> StreamReportRecord:
        report = store.load_item(category, document_id, StreamReportRecord)
        if report is not None:
            return report
        return StreamReportRecord(
            document_id=document_id,
            stream_kind=stream_kind,
            status="idle",
            created_at="",
            updated_at="",
            events=[],
        )

    def _persist(self) -> None:
        self.store.save_item(self.category, self.document_id, self.report)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
