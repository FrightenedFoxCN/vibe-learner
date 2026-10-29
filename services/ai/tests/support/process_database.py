"""Process-crash storage selection; PostgreSQL requires an owned schema marker."""

from __future__ import annotations

import os
import re
from pathlib import Path

from sqlalchemy.engine import make_url

from app.persistence.database import Database
from app.persistence.storage import StorageManager
from app.services.local_store import LocalJsonStore

POSTGRES_ENV = "VIBE_PROCESS_RECOVERY_POSTGRES_URL"
SCHEMA_FILE = "postgres-schema.txt"


def process_database_url(root: Path) -> str | None:
    selected = os.environ.get(POSTGRES_ENV)
    if selected is None:
        return None
    url = make_url(selected)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("process recovery requires PostgreSQL")
    schema = (root / SCHEMA_FILE).read_text().strip()
    if not re.fullmatch(r"vibe_pg_accept_[0-9a-f]{32}", schema):
        raise ValueError("process recovery schema is not owned by the probe")
    return url.update_query_dict(
        {"options": f"-csearch_path={schema}"}
    ).render_as_string(hide_password=False)


def open_process_store(root: Path) -> LocalJsonStore:
    url = process_database_url(root)
    if url is None:
        return LocalJsonStore(root)
    # The probe applies real Alembic migrations before spawning a worker.
    # Never silently create an SQLite fallback or bypass PG migration guards.
    return LocalJsonStore(Database(url), StorageManager(root))
