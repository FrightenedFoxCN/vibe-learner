"""Database-clock leases for document processing and plan generation.

Every mutation first takes the same conditional write lock on the active
operation row. This is a row lock on PostgreSQL and a writer fence on SQLite
(where FOR UPDATE alone is ignored). Only then may it examine/change the
lease or write domain effects. Once a lease expires, it cannot be revived.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.persistence.database import Database
from app.persistence.models import (
    DocumentProcessLeaseRow,
    DocumentProcessOperationRow,
    LearningPlanLeaseRow,
    LearningPlanOperationRow,
)


class DomainOperationLease:
    def __init__(
        self,
        database: Database,
        operation_row: type[DocumentProcessOperationRow]
        | type[LearningPlanOperationRow],
        lease_row: type[DocumentProcessLeaseRow] | type[LearningPlanLeaseRow],
        *,
        lease_seconds: float = 60,
    ) -> None:
        self.database = database
        self.operation_row = operation_row
        self.lease_row = lease_row
        self.lease_seconds = lease_seconds
        self.owner_id = uuid4().hex

    def admit_in_session(self, session: Session, operation_id: str) -> None:
        session.add(
            self.lease_row(
                operation_id=operation_id,
                owner_id=self.owner_id,
                expires_at=self._expires_at(_database_utc_now(session)),
            )
        )

    def fence_owner_in_session(self, session: Session, operation_id: str) -> bool:
        if not self._lock_running(session, operation_id):
            return False
        lease = session.get(self.lease_row, operation_id, populate_existing=True)
        return (
            lease is not None
            and lease.owner_id == self.owner_id
            and lease.expires_at > _wire(_database_utc_now(session))
        )

    def heartbeat(self, operation_id: str) -> bool:
        with self.database.session() as session:
            if not self._lock_running(session, operation_id):
                return False
            now = _database_utc_now(session)
            result = session.execute(
                update(self.lease_row)
                .where(
                    self.lease_row.operation_id == operation_id,
                    self.lease_row.owner_id == self.owner_id,
                    self.lease_row.expires_at > _wire(now),
                )
                .values(expires_at=self._expires_at(now))
            )
            return result.rowcount == 1

    def recovery_candidates(self) -> list[str]:
        operation, lease = self.operation_row, self.lease_row
        with self.database.session() as session:
            return list(
                session.scalars(
                    select(operation.operation_id)
                    .outerjoin(lease, lease.operation_id == operation.operation_id)
                    .where(
                        operation.status == "running",
                        operation.active_slot == 1,
                        or_(
                            lease.operation_id.is_(None),
                            lease.expires_at <= _wire(_database_utc_now(session)),
                        ),
                    )
                )
            )

    def fence_recovery_in_session(self, session: Session, operation_id: str) -> bool:
        if not self._lock_running(session, operation_id):
            return False
        # The candidate scan is only a hint. Recheck with current DB time after
        # serialization against renewal, provider start, and terminal writes.
        lease = session.get(self.lease_row, operation_id, populate_existing=True)
        return lease is None or lease.expires_at <= _wire(_database_utc_now(session))

    def release_in_session(self, session: Session, operation_id: str) -> None:
        # Call only after acquiring the owner/recovery fence in this transaction.
        session.execute(
            delete(self.lease_row).where(self.lease_row.operation_id == operation_id)
        )

    def _expires_at(self, now: datetime) -> str:
        return _wire(now + timedelta(seconds=self.lease_seconds))

    def _lock_running(self, session: Session, operation_id: str) -> bool:
        row = self.operation_row
        result = session.execute(
            update(row)
            .where(
                row.operation_id == operation_id,
                row.status == "running",
                row.active_slot == 1,
            )
            .values(updated_at=row.updated_at)
            .execution_options(synchronize_session=False)
        )
        return result.rowcount == 1


def _database_utc_now(session: Session) -> datetime:
    dialect = session.get_bind().dialect.name
    if dialect == "sqlite":
        value = session.scalar(select(func.strftime("%Y-%m-%dT%H:%M:%f", "now")))
    elif dialect == "postgresql":
        value = session.scalar(select(func.clock_timestamp()))
    else:
        value = session.scalar(select(func.current_timestamp()))
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise RuntimeError("domain_operation_lease_database_clock_unavailable")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _wire(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")
