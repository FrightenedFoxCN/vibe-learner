"""Predictable actor calls with per-call failure injection."""
from app.models.tavern import TavernActorReply
from app.services.model_provider import MockModelProvider

class SequencedTavernProvider(MockModelProvider):
    def __init__(self, *, fail_calls: set[int] | None = None) -> None:
        self.fail_calls = set(fail_calls or set())
        self.calls: list[dict[str, object]] = []

    def generate_tavern_actor_reply(self, **kwargs) -> TavernActorReply:
        call_number = len(self.calls) + 1
        self.calls.append(
            {
                "call_number": call_number,
                "persona_id": kwargs["persona"].id,
                "recent_message_ids": [item.id for item in kwargs["recent_messages"]],
                "recent_persona_ids": [
                    item.persona_id
                    for item in kwargs["recent_messages"]
                    if item.persona_id
                ],
                "user_message": kwargs["user_message"],
                "turn_kind": kwargs["turn_kind"],
                "required_target_id": kwargs["required_target_id"],
            }
        )
        if call_number in self.fail_calls:
            raise RuntimeError(f"planned_actor_failure:{call_number}")
        return TavernActorReply(
            text=f"{kwargs['persona'].name} 完成第 {call_number} 次回应。",
            mood="calm",
            action="微微颔首，望向上一位说话者",
            speech_style="克制",
            delivery_cue="停顿后自然接话",
            state_commentary="按服务端安排推进多人互动",
            addressed_participant_ids=[],
        )

