from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.models.study_chat_effect import (
    StudyFollowUpEffectAction,
    StudyFollowUpEffectProposalV1,
)
from app.services.study_tools.context import StudyToolContext
from fastapi import HTTPException


@dataclass
class FollowUpTools:
    context: StudyToolContext

    def read_system_time(self, arguments: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now().astimezone()
        return {
            "ok": True,
            "tool_name": "read_system_time",
            "iso_datetime": now.isoformat(),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "timezone": str(now.tzinfo or ""),
            "weekday": now.strftime("%A"),
        }

    def schedule_session_follow_up(self, arguments: dict[str, Any]) -> dict[str, Any]:
        delay_seconds = int(arguments.get("delay_seconds") or 30)
        if delay_seconds < 10 or delay_seconds > 1800:
            raise HTTPException(status_code=422, detail="follow_up_delay_invalid")
        prompt = str(arguments.get("prompt") or "").strip()
        reason = str(arguments.get("reason") or "").strip()
        if not prompt:
            raise HTTPException(status_code=422, detail="follow_up_prompt_required")
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyFollowUpEffectProposalV1(
            action=StudyFollowUpEffectAction.SCHEDULE,
            delay_seconds=delay_seconds,
            hidden_message=prompt,
            reason=reason,
        )
        effect = self.context.effects.prepare_follow_up(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        predicted = self.context.effects.preview_follow_ups(session.pending_follow_ups)[
            -1
        ]
        return {
            "ok": True,
            "tool_name": "schedule_session_follow_up",
            "requires_client_schedule": True,
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": predicted,
        }
