"""Bridge a blocking domain workflow and its report to an NDJSON response."""

from collections.abc import Callable, Iterator
from contextvars import copy_context
import json
from queue import Queue
from threading import Thread

from fastapi.responses import StreamingResponse

from app.models.stream import StreamTerminalEvidenceV1
from app.services.stream_interrupts import StreamInterruptHandle, StreamInterruptedError
from app.services.stream_reports import StreamReportRecorder


class NdjsonWorkflow:
    """Own stream transport and interruption, not the domain's terminal evidence."""

    def __init__(
        self, handle: StreamInterruptHandle, recorder: StreamReportRecorder
    ) -> None:
        self.handle = handle
        self._recorder = recorder
        self._events: Queue[dict[str, object] | None] = Queue()

    def before_commit(self) -> None:
        if self.handle.claim_terminal():
            raise StreamInterruptedError("stream_interrupted")

    def report(self, stage: str, payload: dict[str, object]) -> None:
        self.handle.raise_if_cancelled()
        self.emit(stage, payload)

    def emit(
        self,
        stage: str,
        payload: dict[str, object],
        *,
        terminal_evidence: StreamTerminalEvidenceV1 | None = None,
        committed_projection: dict[str, object] | None = None,
    ) -> None:
        event = self._recorder.emit(
            stage,
            payload,
            terminal_evidence=terminal_evidence,
            committed_projection=committed_projection,
        )
        self._events.put(event.model_dump(mode="json"))

    def start(self, run: Callable[[], None]) -> StreamingResponse:
        def worker() -> None:
            try:
                run()
            finally:
                self.handle.mark_completed()
                self._events.put(None)

        Thread(target=copy_context().run, args=(worker,), daemon=True).start()
        return StreamingResponse(self._generate(), media_type="application/x-ndjson")

    def _generate(self) -> Iterator[str]:
        while (event := self._events.get()) is not None:
            yield json.dumps(event, ensure_ascii=False) + "\n"
