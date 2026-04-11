from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models.api import CreatePersonaCardRequest
from app.models.domain import PersonaCardRecord
from app.services.local_store import LocalJsonStore


class PersonaCardLibraryService:
    def __init__(self, store: LocalJsonStore) -> None:
        self._store = store

    def list_cards(self) -> list[PersonaCardRecord]:
        cards = self._store.load_category_items("persona_cards", PersonaCardRecord)
        return sorted(cards, key=lambda item: (item.updated_at, item.created_at), reverse=True)

    def require_card(self, card_id: str) -> PersonaCardRecord:
        card = self._store.load_item("persona_cards", card_id, PersonaCardRecord)
        if card is None:
            raise HTTPException(status_code=404, detail="persona_card_not_found")
        return card

    def create_card(self, payload: CreatePersonaCardRequest) -> PersonaCardRecord:
        card_id = f"pcard-{uuid4().hex[:10]}"
        record = PersonaCardRecord(
            id=card_id,
            title=payload.title.strip(),
            kind=payload.kind.strip() or "custom",
            label=payload.label.strip() or payload.kind.strip() or "自定义",
            content=payload.content.strip(),
            tags=[tag.strip() for tag in payload.tags if tag.strip()],
            search_keywords=payload.search_keywords.strip() or "自定义",
            source=payload.source.strip() or "manual",
            source_note=payload.source_note.strip(),
            created_at=_now_iso(),
            updated_at=_now_iso(),
        )
        self._store.save_item("persona_cards", card_id, record)
        return record

    def create_many(self, items: list[CreatePersonaCardRequest]) -> list[PersonaCardRecord]:
        return [self.create_card(item) for item in items if item.content.strip() and item.title.strip()]

    def delete_card(self, card_id: str) -> None:
        self.require_card(card_id)
        self._store.delete_item("persona_cards", card_id)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
