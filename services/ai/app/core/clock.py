"""Process clock helpers.

One place owns the wall-clock form the application writes into JSON and logs.
Repositories that must fence claims use the database clock instead
(`_database_utc_now` in the harness/tavern repositories); this module is for
plain timestamps, never for lease arbitration.
"""

from __future__ import annotations

from datetime import datetime, timezone

__all__ = ["utc_now", "utc_now_iso", "utc_now_iso_micro"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def utc_now_iso_micro() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")
