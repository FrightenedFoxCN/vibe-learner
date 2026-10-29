from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.study_chat_effect import (
    StudyAffinityDeltaEffectProposalV1,
)
from app.services.study_tools.context import StudyToolContext
from fastapi import HTTPException


@dataclass
class AffinityTools:
    context: StudyToolContext

    def read_affinity_state(self, arguments: dict[str, Any]) -> dict[str, Any]:
        session = self.context.sessions.require_session(self.context.session_id)
        affinity = (
            self.context.effects.preview_affinity_state(session.affinity_state)
            if self.context.effects is not None
            else session.affinity_state.model_dump(mode="json")
        )
        return {
            "ok": True,
            "tool_name": "read_affinity_state",
            "score": affinity["score"],
            "level": affinity["level"],
            "summary": affinity["summary"],
            "updated_at": affinity["updated_at"],
            "effect_state": affinity.get("effect_state", "committed"),
            "committed": affinity.get("committed", True),
            "recent_events": list(affinity.get("events") or [])[-6:],
        }

    def update_affinity_state(self, arguments: dict[str, Any]) -> dict[str, Any]:
        delta = int(arguments.get("delta") or 0)
        if delta < -20 or delta > 20:
            raise HTTPException(status_code=422, detail="affinity_delta_invalid")
        reason = str(arguments.get("reason") or "").strip()
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyAffinityDeltaEffectProposalV1(
            delta=delta,
            reason=reason,
        )
        effect = self.context.effects.prepare_affinity_delta(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        affinity = self.context.effects.preview_affinity_state(session.affinity_state)
        return {
            "ok": True,
            "tool_name": "update_affinity_state",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": {
                "score": affinity["score"],
                "level": affinity["level"],
                "summary": affinity["summary"],
            },
        }
