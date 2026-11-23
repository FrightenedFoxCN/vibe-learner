from __future__ import annotations

from app.persistence.database import Database
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.tavern_errors import (
    TavernRoomCursorInvalid,
    TavernRevisionConflict,
    TavernRunInProgress,
    TavernParticipantHistoryConflict,
    TavernIdempotencyConflict,
    TavernRetryAlreadyCreated,
    TavernStepClaimConflict,
    TavernRunTerminalConflict,
    TavernStepClaimsExhausted,
)
from app.persistence.tavern_msg_ops import TavernMessageOps
from app.persistence.tavern_room_ops import TavernRoomOps
from app.persistence.tavern_run_ops import TavernRunOps

__all__ = [
    "TavernRepository",
    "TavernIdempotencyConflict",
    "TavernParticipantHistoryConflict",
    "TavernRetryAlreadyCreated",
    "TavernRevisionConflict",
    "TavernRoomCursorInvalid",
    "TavernRunInProgress",
    "TavernRunTerminalConflict",
    "TavernStepClaimConflict",
    "TavernStepClaimsExhausted",
]


class TavernRepository(TavernRoomOps, TavernRunOps, TavernMessageOps):
    def __init__(self, database: Database) -> None:
        self.database = database
        self.harness_operations = HarnessOperationBindingRepository(database)
