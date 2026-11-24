"""Maintain a domain lease even while its synchronous provider is blocked."""

from threading import Event, Thread

from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger
from app.persistence.domain_operation_lease import DomainOperationLease

logger = get_logger("vibe_learner.domain_operation_heartbeat")


class DomainOperationHeartbeat:
    def __init__(self, lease: DomainOperationLease, operation_id: str) -> None:
        self._lease = lease
        self._operation_id = operation_id
        self._stop = Event()
        self._thread = Thread(
            target=self._run, name="domain-operation-heartbeat", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread.ident is not None:
            self._thread.join()

    def _run(self) -> None:
        interval = self._lease.lease_seconds / 3
        while not self._stop.wait(interval):
            try:
                if not self._lease.heartbeat(self._operation_id):
                    return
            except SQLAlchemyError:
                # A transient lock/connection error need not lose ownership.
                # The database fence rejects writes if the lease does expire.
                logger.warning(
                    "domain_operation.heartbeat_failed id=%s",
                    self._operation_id,
                    exc_info=True,
                )
