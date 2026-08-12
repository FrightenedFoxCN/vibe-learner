from __future__ import annotations

import json

from app.models.domain import PersonaProfile, SceneProfileRecord
from app.models.tavern import TavernMessageRecord, TavernParticipantRecord
from app.services.persona_runtime import render_tavern_persona_instruction
from app.services.prompt_loader import load_prompt_template


TAVERN_ACTOR_PROMPT_VERSION = "tavern-actor-v1"


def build_tavern_actor_messages(
    *,
    persona: PersonaProfile,
    participants: list[TavernParticipantRecord],
    scene_profile: SceneProfileRecord | None,
    recent_messages: list[TavernMessageRecord],
    user_message: str,
    guidance: str,
    allowed_target_ids: list[str],
    actor_reply_schema: str,
    turn_kind: str = "user_message",
    required_target_id: str = "",
) -> list[dict[str, str]]:
    template = load_prompt_template("tavern_actor_prompt.txt")
    system = template.require("system").replace("{{ACTOR_REPLY_SCHEMA}}", actor_reply_schema)
    cast_payload = [
        {
            "persona_id": item.persona_id,
            "display_name": item.display_name,
            "summary": item.persona_snapshot.summary,
            "relationship": item.persona_snapshot.relationship,
        }
        for item in participants
    ]
    transcript_payload = [
        {
            "sequence": item.sequence,
            "author_kind": item.author_kind.value,
            "persona_id": item.persona_id,
            "persona_name": item.persona_name,
            "content": item.content,
            "addressed_participant_ids": item.addressed_participant_ids,
        }
        for item in recent_messages
    ]
    scene_payload = (
        scene_profile.model_dump(mode="json")
        if scene_profile is not None
        else {"scene": None, "rule": "保持空间中性，不虚构固定设施或世界规则。"}
    )
    user = (
        template.require("user")
        .replace(
            "{{PERSONA_INSTRUCTION_JSON}}",
            _json(render_tavern_persona_instruction(persona)),
        )
        .replace("{{CAST_JSON}}", _json(cast_payload))
        .replace("{{SCENE_JSON}}", _json(scene_payload))
        .replace("{{TRANSCRIPT_JSON}}", _json(transcript_payload))
        .replace("{{TURN_KIND_JSON}}", _json(turn_kind))
        .replace("{{USER_MESSAGE_JSON}}", _json(user_message))
        .replace("{{GUIDANCE_JSON}}", _json(guidance))
        .replace("{{ALLOWED_TARGET_IDS_JSON}}", _json(allowed_target_ids))
        .replace("{{REQUIRED_TARGET_ID_JSON}}", _json(required_target_id))
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_tavern_actor_recovery_message(actor_reply_schema: str) -> str:
    return load_prompt_template("tavern_actor_prompt.txt").require("recovery").replace(
        "{{ACTOR_REPLY_SCHEMA}}",
        actor_reply_schema,
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
