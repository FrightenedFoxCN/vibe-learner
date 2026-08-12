from __future__ import annotations

import hashlib
import json


def tavern_payload_digest(payload: object) -> str:
    """Return the canonical legacy Tavern payload digest."""

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def persona_prompt_hash(persona_payload: object) -> str:
    """Bind a room participant to its immutable Persona snapshot."""

    return tavern_payload_digest(persona_payload)
