"""Null-safe text coercion for the data-flow boundaries.

Layer contract (the long form lives in ``docs/data-flow-layers.md``):

1. **Untrusted shapes** — external JSON, legacy rows, model output. A missing
   key, an explicit ``null`` and a wrong scalar type all mean "no text". These
   are the only places allowed to turn absence into a value.
2. **Domain models** — trusted shapes. A required field never passes through
   this module; its absence must fail validation instead of becoming ``""``.
3. **API DTOs and the frontend** — already-trusted shapes. They validate shape
   and must not re-invent semantic defaults; only presentation code may fall
   back for display.

``text_or_empty`` deliberately mirrors the historical ``x or ""`` idiom,
including its treatment of falsy non-strings (``0``, ``False``, ``[]``). It is
the behaviour-preserving step of the consolidation, not the final semantics:
call sites that need "0 stays 0" should migrate to :func:`optional_text_at`
and decide the default explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

__all__ = ["optional_text", "optional_text_at", "text_or_empty", "text_at"]


def text_or_empty(value: Any) -> str:
    """Return ``str(value)`` for truthy values and ``""`` otherwise.

    This is the exact behaviour of ``value or ""`` wrapped in ``str()``, which
    it replaces across untrusted-shape boundaries.
    """
    if not value:
        return ""
    return value if isinstance(value, str) else str(value)


def text_at(mapping: Mapping[str, Any], key: str) -> str:
    """Return :func:`text_or_empty` for one mapping field."""
    return text_or_empty(mapping.get(key))


def optional_text(value: Any) -> str | None:
    """Preserve ``None`` instead of collapsing it to ``""``.

    Use when "absent" and "empty" are different states for the caller.
    """
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def optional_text_at(mapping: Mapping[str, Any], key: str) -> str | None:
    """Return :func:`optional_text` for one mapping field."""
    return optional_text(mapping.get(key))
