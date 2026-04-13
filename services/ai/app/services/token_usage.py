from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.models.domain import TokenUsageRecord
from app.persistence.database import Database
from app.persistence.models import TokenUsageRow


class TokenUsageService:
    """Stores per-request token usage records in the primary database."""

    def __init__(self, db: Database) -> None:
        self._db = db

    def record(
        self,
        *,
        feature: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        entry = TokenUsageRecord(
            id=uuid4().hex,
            feature=feature,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            created_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        self.record_entry(entry)

    def record_entry(self, entry: TokenUsageRecord) -> None:
        payload = entry.model_dump(mode="json")
        with self._db.session() as session:
            session.add(
                TokenUsageRow(
                    id=entry.id,
                    feature=entry.feature,
                    model=entry.model,
                    prompt_tokens=entry.prompt_tokens,
                    completion_tokens=entry.completion_tokens,
                    total_tokens=entry.total_tokens,
                    created_at=entry.created_at,
                    payload=payload,
                )
            )

    def load_all(self) -> list[TokenUsageRecord]:
        with self._db.session() as session:
            rows = (
                session.query(TokenUsageRow)
                .order_by(TokenUsageRow.created_at.desc(), TokenUsageRow.id.desc())
                .all()
            )
            return [TokenUsageRecord.model_validate(row.payload or {}) for row in rows]

    def clear(self) -> int:
        with self._db.session() as session:
            rows = session.query(TokenUsageRow).all()
            for row in rows:
                session.delete(row)
            return len(rows)
