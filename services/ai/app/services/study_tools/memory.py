from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.study_chat_effect import (
    StudyMemoryUpsertEffectProposalV1,
)
from app.models.study_chat_tool_contracts import WriteSessionMemoryArgumentsV1
from app.services.study_tools.context import StudyToolContext
from fastapi import HTTPException


@dataclass
class SessionMemoryTools:
    context: StudyToolContext

    def read_session_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = self.context.sessions.require_session(self.context.session_id)
        requested_key = str(arguments.get("key") or "").strip()
        limit = max(1, min(int(arguments.get("limit") or 6), 12))
        items = (
            self.context.effects.preview_session_memory(session.session_memory)
            if self.context.effects is not None
            else [item.model_dump(mode="json") for item in session.session_memory]
        )
        if requested_key:
            items = [item for item in items if item.get("key") == requested_key]
        return {
            "ok": True,
            "tool_name": "read_session_memory",
            "memory_items": items[-limit:],
        }

    def write_session_memory(self, arguments: dict[str, Any]) -> dict[str, Any]:
        validated = WriteSessionMemoryArgumentsV1.model_validate(arguments)
        key = validated.key.strip()
        content = validated.content.strip()
        if self.context.verbatim_memory_source is not None:
            if validated.key != self.context.verbatim_memory_source.key:
                raise HTTPException(
                    status_code=422, detail="verbatim_memory_key_mismatch"
                )
            content = self.context.verbatim_memory_source.content
        if not key or not content:
            raise HTTPException(status_code=422, detail="session_memory_invalid")
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyMemoryUpsertEffectProposalV1(key=key, content=content)
        effect = self.context.effects.prepare_memory_upsert(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        predicted = next(
            item
            for item in reversed(
                self.context.effects.preview_session_memory(session.session_memory)
            )
            if item.get("key") == key
        )
        return {
            "ok": True,
            "tool_name": "write_session_memory",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": {
                "memory": predicted,
                "memory_count": len(
                    self.context.effects.preview_session_memory(session.session_memory)
                ),
            },
        }
