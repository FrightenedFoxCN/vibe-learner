from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.domain import StreamEventRecord, StreamReportRecord
from app.services.local_store import LocalJsonStore

DOCUMENT_PROCESS_STREAM_CATEGORY = "document_process_stream"
LEARNING_PLAN_STREAM_CATEGORY = "learning_plan_stream"
MAX_STREAM_EVENTS = 200


class StreamReportRecorder:
    def __init__(
        self,
        *,
        store: LocalJsonStore,
        category: str,
        document_id: str,
        stream_kind: str,
        max_events: int = MAX_STREAM_EVENTS,
    ) -> None:
        self.store = store
        self.category = category
        self.document_id = document_id
        self.stream_kind = stream_kind
        self.max_events = max_events
        now = _now()
        self.report = StreamReportRecord(
            document_id=document_id,
            stream_kind=stream_kind,
            status="running",
            created_at=now,
            updated_at=now,
            events=[],
        )
        self._persist()

    def callback(self, stage: str, payload: dict[str, object]) -> None:
        self.emit(stage, payload)

    def emit(self, stage: str, payload: dict[str, object] | None = None) -> None:
        now = _now()
        next_event = StreamEventRecord(
            stage=stage,
            payload=payload or {},
            created_at=now,
        )
        self.report.events = [
            *self.report.events[-(self.max_events - 1) :],
            next_event,
        ]
        self.report.updated_at = now
        if stage == "stream_completed":
            self.report.status = "completed"
        elif stage == "stream_error":
            self.report.status = "error"
        else:
            self.report.status = "running"
        self._persist()

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
