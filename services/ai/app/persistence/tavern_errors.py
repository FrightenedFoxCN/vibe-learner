from __future__ import annotations


from app.models.tavern import (
    TavernRunRecord,
)


_TAVERN_ROOM_CURSOR_VERSION = 1
_TAVERN_ROOM_CURSOR_KEY = b"vibe-learner:tavern-room-list-v1:cursor"


class TavernRoomCursorInvalid(ValueError):
    pass


class TavernRevisionConflict(RuntimeError):
    def __init__(self, current_revision: int) -> None:
        super().__init__(f"tavern_revision_conflict:{current_revision}")
        self.current_revision = current_revision


class TavernRunInProgress(RuntimeError):
    def __init__(self, run_id: str) -> None:
        super().__init__(f"tavern_run_in_progress:{run_id}")
        self.run_id = run_id


class TavernParticipantHistoryConflict(RuntimeError):
    def __init__(self, persona_ids: list[str]) -> None:
        joined = ",".join(persona_ids)
        super().__init__(f"tavern_participant_history_conflict:{joined}")
        self.persona_ids = tuple(persona_ids)


class TavernIdempotencyConflict(RuntimeError):
    def __init__(self, operation: str) -> None:
        super().__init__(f"tavern_idempotency_key_reused:{operation}")
        self.operation = operation


class TavernRetryAlreadyCreated(RuntimeError):
    def __init__(self, child_run_id: str) -> None:
        super().__init__(f"tavern_retry_already_created:{child_run_id}")
        self.child_run_id = child_run_id


class TavernStepClaimConflict(RuntimeError):
    def __init__(self, step_index: int, status: str) -> None:
        super().__init__(f"tavern_step_claim_conflict:{step_index}:{status}")
        self.step_index = step_index
        self.status = status


class TavernRunTerminalConflict(RuntimeError):
    def __init__(self, run_id: str, status: str) -> None:
        super().__init__(f"tavern_run_not_pending:{run_id}:{status}")
        self.run_id = run_id
        self.status = status


class TavernStepClaimsExhausted(RuntimeError):
    def __init__(self, run: TavernRunRecord) -> None:
        super().__init__(f"tavern_step_claims_exhausted:{run.id}")
        self.run = run
