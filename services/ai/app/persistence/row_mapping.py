"""Shared helpers for ORM-row → domain-record mapping.

Every repository stores the model-owned part of a record in a JSON ``payload``
column and the application-owned columns beside it. These helpers keep the
"payload may be NULL" and "list field may be absent" handling in one place so
`_from_row` functions stay a flat field list.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.coerce import text_or_empty
from app.models.harness import HarnessTraceRecord, validate_harness_trace

__all__ = [
    "harness_traces",
    "optional_id",
    "payload_of",
    "text_list",
]


def payload_of(row: Any) -> dict[str, Any]:
    """Return the row's JSON payload, or an empty mapping when it is NULL."""
    payload = getattr(row, "payload", None)
    return payload if isinstance(payload, Mapping) else {}


def text_list(values: Sequence[Any] | None) -> list[str]:
    """Coerce an optional sequence of identifiers into a list of strings."""
    return [str(item) for item in (values or [])]


def optional_id(value: Any) -> str | None:
    """Return the identifier as ``str``, keeping "absent" distinct from ``""``."""
    if value is None:
        return None
    return text_or_empty(value)


def harness_traces(
    payload: Mapping[str, Any], key: str = "harness_trace"
) -> list[HarnessTraceRecord]:
    """Decode the validated Harness trace list stored under ``key``."""
    return [validate_harness_trace(item) for item in (payload.get(key) or [])]
