from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Event, Lock
from uuid import uuid4

from fastapi import HTTPException


class StreamInterruptedError(Exception):
    pass


@dataclass
class StreamInterruptHandle:
    stream_id: str
    stream_kind: str
    target_id: str
    created_at: str = field(default_factory=lambda: _now())
    cancel_reason: str = ""
    cancelled_at: str = ""
    completed_at: str = ""
    _cancel_event: Event = field(default_factory=Event, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def cancel(self, *, reason: str = "user_requested") -> bool:
        with self._lock:
            if self._cancel_event.is_set():
                return False
            self.cancel_reason = reason.strip() or "user_requested"
            self.cancelled_at = _now()
            self._cancel_event.set()
            return True

    def mark_completed(self) -> None:
        with self._lock:
            if self.completed_at:
                return
            self.completed_at = _now()

    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._cancel_event.is_set():
            raise StreamInterruptedError("stream_interrupted")


class StreamInterruptRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._handles: dict[str, StreamInterruptHandle] = {}

    def create(self, *, stream_kind: str, target_id: str) -> StreamInterruptHandle:
        handle = StreamInterruptHandle(
            stream_id=f"stream-{uuid4().hex[:12]}",
            stream_kind=stream_kind.strip() or "unknown",
            target_id=target_id.strip(),
        )
        with self._lock:
            self._handles[handle.stream_id] = handle
        return handle

    def require(self, stream_id: str) -> StreamInterruptHandle:
        normalized_id = stream_id.strip()
        with self._lock:
            handle = self._handles.get(normalized_id)
        if handle is None:
            raise HTTPException(status_code=404, detail="stream_not_found")
        return handle

    def cancel(self, *, stream_id: str, reason: str = "user_requested") -> StreamInterruptHandle:
        handle = self.require(stream_id)
        handle.cancel(reason=reason)
        return handle


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
