"""Request-scoped, content-free measurements of actual parser work."""
from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter_ns
from typing import Literal

ParserStage = Literal["page_extraction", "section_detection", "chunk_building", "ocr_page"]
_measurements: ContextVar[dict[str, dict[str, int]] | None] = ContextVar("parser_measurements", default=None)


@contextmanager
def collect_parser_measurements(measurements: dict[str, dict[str, int]]):
    token = _measurements.set(measurements)
    try:
        yield
    finally:
        _measurements.reset(token)


@contextmanager
def measure_parser_stage(stage: ParserStage, *, count_attempt: bool = True):
    started = perf_counter_ns()
    try:
        yield
    finally:
        measurements = _measurements.get()
        if measurements is not None:
            entry = measurements.setdefault(stage, {"attempt_count": 0, "duration_ns": 0})
            entry["attempt_count"] += int(count_attempt)
            entry["duration_ns"] += max(0, perf_counter_ns() - started)


def parser_stage_evidence(measurements: dict[str, dict[str, int]], stage: ParserStage) -> dict[str, int]:
    entry = measurements.get(stage)
    if entry is None:
        return {}  # An uninstrumented/skipped producer has no measurement.
    return {"attempt_count": entry["attempt_count"], "duration_ms": entry["duration_ns"] // 1_000_000}
