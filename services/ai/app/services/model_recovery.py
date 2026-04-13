from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import uuid4

from app.models.domain import ModelRecoveryRecord

_MODEL_RECOVERY_STATE: ContextVar[list[ModelRecoveryRecord] | None] = ContextVar(
    "vibe_learner_model_recovery_state",
    default=None,
)


def reset_model_recovery_state() -> None:
    _MODEL_RECOVERY_STATE.set([])


def record_model_recovery(
    *,
    category: str,
    reason: str,
    strategy: str,
    attempts: int = 1,
    note: str = "",
) -> ModelRecoveryRecord:
    current = list(_MODEL_RECOVERY_STATE.get() or [])
    record = ModelRecoveryRecord(
        recovery_id=f"recovery-{uuid4().hex[:10]}",
        category=category.strip() or "unknown",
        reason=reason.strip() or "unknown",
        strategy=strategy.strip() or "unknown",
        attempts=max(1, attempts),
        note=note.strip(),
        created_at=_now(),
    )
    current.append(record)
    _MODEL_RECOVERY_STATE.set(current)
    return record


def get_model_recovery_state() -> list[ModelRecoveryRecord]:
    return list(_MODEL_RECOVERY_STATE.get() or [])


def consume_model_recovery_state() -> list[ModelRecoveryRecord]:
    current = get_model_recovery_state()
    _MODEL_RECOVERY_STATE.set([])
    return current


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
