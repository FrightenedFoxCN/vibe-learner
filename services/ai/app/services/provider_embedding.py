from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.services.provider_capabilities import EmbeddingModelCapability


class EmbeddingRequest(Protocol):
    def __call__(self, payload: dict[str, Any], *, model: str) -> tuple[dict[str, Any], int]: ...


@dataclass(frozen=True)
class RemoteEmbeddingProvider(EmbeddingModelCapability):
    """One embedding call with a captured model and explicit request dependency."""

    embedding_model: str
    request: EmbeddingRequest

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        clean = [text.strip() for text in texts if text and text.strip()]
        if not clean:
            return []
        payload: dict[str, Any] = {
            "model": self.embedding_model,
            "input": clean,
        }
        raw_payload, _ = self.request(payload, model=self.embedding_model)
        data = raw_payload.get("data") or []
        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if isinstance(embedding, list):
                vectors.append([float(value) for value in embedding])
        return vectors

