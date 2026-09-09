"""Tavern actor generation and its bounded transport/semantic recovery."""
from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Protocol

from app.core.logging import get_logger
from app.models.domain import PersonaProfile, SceneProfileRecord
from app.models.tavern import TavernActorReply, TavernMessageRecord, TavernParticipantRecord
from app.services.model_recovery import record_model_recovery
from app.services.provider_capabilities import TavernModelCapability
from app.services.provider_payload import _extract_choice_content, _extract_json_payload
from app.services.provider_transport import ModelRequestError
from app.services.tavern_prompt import build_tavern_actor_messages, build_tavern_actor_recovery_message

logger = get_logger("vibe_learner.model_provider")


class TavernRequest(Protocol):
    def __call__(self, payload: dict[str, Any], *, request_kind: str, model: str) -> tuple[dict[str, Any], int]: ...


@dataclass(frozen=True)
class RemoteTavernProvider(TavernModelCapability):
    chat_model: str
    chat_temperature: float
    chat_max_tokens: int
    request: TavernRequest

    def generate_tavern_actor_reply(
        self,
        *,
        persona: PersonaProfile,
        participants: list[TavernParticipantRecord],
        scene_profile: SceneProfileRecord | None,
        recent_messages: list[TavernMessageRecord],
        user_message: str,
        guidance: str,
        allowed_target_ids: list[str],
        turn_kind: str = "user_message",
        required_target_id: str = "",
        should_continue: Callable[[], bool] | None = None,
    ) -> TavernActorReply:
        if should_continue is not None and not should_continue():
            raise RuntimeError("tavern_actor_generation_canceled")
        actor_schema = TavernActorReply.transport_json_schema()
        actor_schema_text = json.dumps(actor_schema, ensure_ascii=False, sort_keys=True)
        messages = build_tavern_actor_messages(
            persona=persona,
            participants=participants,
            scene_profile=scene_profile,
            recent_messages=recent_messages,
            user_message=user_message,
            guidance=guidance,
            allowed_target_ids=allowed_target_ids,
            actor_reply_schema=actor_schema_text,
            turn_kind=turn_kind,
            required_target_id=required_target_id,
        )
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "tavern_actor_reply",
                "strict": True,
                "schema": actor_schema,
            },
        }
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "temperature": self.chat_temperature,
            "max_tokens": self.chat_max_tokens,
            "messages": messages,
            "response_format": response_format,
        }
        active_response_format = response_format
        try:
            raw_payload, _ = self.request(
                payload,
                request_kind="chat",
                model=self.chat_model,
            )
        except ModelRequestError as exc:
            if not _should_fallback_tavern_schema_transport(exc):
                raise
            if should_continue is not None and not should_continue():
                raise RuntimeError("tavern_actor_generation_canceled") from exc
            logger.warning(
                "model.tavern.schema_transport_fallback status=%s upstream_code=%s",
                exc.status_code,
                exc.upstream_code,
            )
            record_model_recovery(
                category="transport_compatibility",
                reason="tavern_json_schema_unsupported",
                strategy="retry_json_object",
                attempts=2,
            )
            active_response_format = {"type": "json_object"}
            fallback_payload = {**payload, "response_format": active_response_format}
            raw_payload, _ = self.request(
                fallback_payload,
                request_kind="chat",
                model=self.chat_model,
            )

        try:
            return _parse_tavern_actor_reply(raw_payload)
        except RuntimeError as exc:
            recovery_reason = str(exc)
            if should_continue is not None and not should_continue():
                raise RuntimeError("tavern_actor_generation_canceled") from exc
            logger.warning("model.tavern.recovery reason=%s", recovery_reason)
            record_model_recovery(
                category="semantic_retry",
                reason=recovery_reason,
                strategy="retry_strict_actor_reply",
                attempts=2,
            )
            recovery_payload: dict[str, Any] = {
                "model": self.chat_model,
                "temperature": min(self.chat_temperature, 0.2),
                "max_tokens": max(self.chat_max_tokens, 900),
                "messages": [
                    *messages,
                    {
                        "role": "user",
                        "content": build_tavern_actor_recovery_message(actor_schema_text),
                    },
                ],
                "response_format": active_response_format,
            }
            recovery_raw_payload, _ = self.request(
                recovery_payload,
                request_kind="chat",
                model=self.chat_model,
            )
            recovered = _parse_tavern_actor_reply(recovery_raw_payload)
            return recovered



def _parse_tavern_actor_reply(raw_payload: dict[str, Any]) -> TavernActorReply:
    try:
        content = _extract_choice_content(raw_payload)
        parsed = _extract_json_payload(
            content,
            invalid_json_code="tavern_actor_invalid_payload",
            invalid_payload_code="tavern_actor_invalid_payload",
        )
        return TavernActorReply.model_validate(parsed)
    except Exception as exc:
        if isinstance(exc, ModelRequestError):
            raise
        raise RuntimeError("tavern_actor_invalid_payload") from exc



def _should_fallback_tavern_schema_transport(exc: ModelRequestError) -> bool:
    return (
        exc.status_code in {"400", "422"}
        or exc.upstream_code == "unsupported_params"
        or str(exc) == "openai_chat_request_unsupported_params"
    )

