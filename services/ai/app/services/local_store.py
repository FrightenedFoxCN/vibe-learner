from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LocalJsonStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.upload_root = self.root / "uploads"
        self.root.mkdir(parents=True, exist_ok=True)
        self.upload_root.mkdir(parents=True, exist_ok=True)

    def load_list(self, name: str, model: type[T]) -> list[T]:
        path = self.root / f"{name}.json"
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [model.model_validate(item) for item in payload]

    def save_list(self, name: str, items: list[BaseModel]) -> None:
        path = self.root / f"{name}.json"
        payload = [item.model_dump(mode="json") for item in items]
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
