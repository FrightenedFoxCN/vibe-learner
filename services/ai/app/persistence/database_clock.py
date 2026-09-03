from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session


class DatabaseClockUnavailable(RuntimeError):
    pass


def database_utc_now(session: Session) -> datetime:
    """Return UTC time from the connected database, with dialect parity."""
    dialect = session.bind.dialect.name if session.bind is not None else ""
    if dialect == "sqlite":
        value = session.scalar(select(func.strftime("%Y-%m-%dT%H:%M:%f", "now")))
    elif dialect == "postgresql":
        value = session.scalar(select(func.clock_timestamp()))
    else:
        value = session.scalar(select(func.current_timestamp()))
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace(" ", "T"))
    if not isinstance(value, datetime):
        raise DatabaseClockUnavailable("database_clock_unavailable")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def database_utc_wire(session: Session) -> str:
    return database_utc_now(session).isoformat(timespec="microseconds")
