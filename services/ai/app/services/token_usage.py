from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.models.domain import TokenUsageRecord


class TokenUsageService:
    """Appends and reads per-request token usage records stored in a JSONL file."""

    def __init__(self, data_root: Path) -> None:
        self._path = data_root / "token_usage.jsonl"
        data_root.mkdir(parents=True, exist_ok=True)

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
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def load_all(self) -> list[TokenUsageRecord]:
        if not self._path.exists():
            return []
        records: list[TokenUsageRecord] = []
        with self._path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(TokenUsageRecord.model_validate(json.loads(line)))
                except Exception:
                    pass
        return records
