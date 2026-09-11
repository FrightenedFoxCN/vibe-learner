from __future__ import annotations

from dataclasses import dataclass
import json
import math
import re

from app.core.harness_component_versions import TAVERN_ACTOR_PROMPT_CONTRACT_VERSION
from app.models.domain import PersonaProfile, SceneLayerStateRecord, SceneProfileRecord
from app.models.tavern import TavernMessageRecord, TavernParticipantRecord
from app.services.persona_runtime import render_tavern_persona_instruction
from app.services.prompt_loader import load_prompt_template


TAVERN_ACTOR_PROMPT_VERSION = TAVERN_ACTOR_PROMPT_CONTRACT_VERSION

# This budget is deliberately independent from the legacy v1 Harness trace schema.
# It versions deterministic prompt construction and pre-provider fail-closed limits.
TAVERN_PROMPT_BUDGET_VERSION = "tavern-prompt-budget-v1"
TAVERN_PROMPT_MAX_CANONICAL_BYTES = 256 * 1024
TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE = 48_000
TAVERN_PROMPT_MAX_SCENE_BYTES = 64 * 1024
TAVERN_PROMPT_MAX_SCENE_DEPTH = 8
TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES = 128 * 1024
TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES = 64 * 1024
TAVERN_PROMPT_MAX_CAST_BYTES = 64 * 1024

_ASCII_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class TavernPromptBudgetReport:
    version: str
    original_prompt_bytes: int
    final_prompt_bytes: int
    input_token_estimate: int
    original_transcript_bytes: int
    final_transcript_bytes: int
    removed_message_count: int
    scene_bytes: int
    scene_depth: int
    persona_instruction_bytes: int
    cast_bytes: int


@dataclass(frozen=True)
class TavernPromptPreflightResult:
    messages: list[dict[str, str]]
    recent_messages: list[TavernMessageRecord]
    report: TavernPromptBudgetReport


class TavernPromptBudgetError(RuntimeError):
    """Stable typed failure raised before any Tavern provider request."""

    def __init__(
        self,
        code: str,
        *,
        partition: str,
        actual: int,
        limit: int,
    ) -> None:
        self.code = code
        self.partition = partition
        self.actual = max(0, actual)
        self.limit = max(0, limit)
        super().__init__(code)


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
    return preflight_tavern_actor_prompt(
        persona=persona,
        participants=participants,
        scene_profile=scene_profile,
        recent_messages=recent_messages,
        user_message=user_message,
        guidance=guidance,
        allowed_target_ids=allowed_target_ids,
        actor_reply_schema=actor_reply_schema,
        turn_kind=turn_kind,
        required_target_id=required_target_id,
    ).messages


def preflight_tavern_actor_prompt(
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
) -> TavernPromptPreflightResult:
    """Build one bounded canonical actor prompt without provider side effects.

    Transcript pressure is the only recoverable over-budget partition. Messages
    are ordered by their committed sequence and removed oldest-first. Scene,
    Persona, cast, and the final total fail closed because silently trimming
    those inputs would alter identity or world rules.
    """

    template = load_prompt_template("tavern_actor_prompt.txt")
    system = template.require("system").replace(
        "{{ACTOR_REPLY_SCHEMA}}", actor_reply_schema
    )
    recovery_message = template.require("recovery").replace(
        "{{ACTOR_REPLY_SCHEMA}}", actor_reply_schema
    )
    persona_instruction = render_tavern_persona_instruction(persona)
    cast_payload = [
        {
            "persona_id": item.persona_id,
            "display_name": item.display_name,
            "summary": item.persona_snapshot.summary,
            "relationship": item.persona_snapshot.relationship,
        }
        for item in sorted(participants, key=lambda item: item.display_order)
    ]
    scene_depth = (
        _scene_layer_depth(scene_profile.scene_tree) if scene_profile is not None else 0
    )
    if scene_depth > TAVERN_PROMPT_MAX_SCENE_DEPTH:
        raise TavernPromptBudgetError(
            "tavern_prompt_scene_depth_exceeded",
            partition="scene_depth",
            actual=scene_depth,
            limit=TAVERN_PROMPT_MAX_SCENE_DEPTH,
        )
    scene_payload = (
        scene_profile.model_dump(mode="json")
        if scene_profile is not None
        else {"scene": None, "rule": "保持空间中性，不虚构固定设施或世界规则。"}
    )

    persona_instruction_bytes = _require_partition_bytes(
        persona_instruction,
        limit=TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES,
        error_code="tavern_prompt_persona_instruction_bytes_exceeded",
        partition="persona_instruction_bytes",
    )
    cast_bytes = _require_partition_bytes(
        _canonical_json(cast_payload),
        limit=TAVERN_PROMPT_MAX_CAST_BYTES,
        error_code="tavern_prompt_cast_bytes_exceeded",
        partition="cast_bytes",
    )
    scene_bytes = _require_partition_bytes(
        _canonical_json(scene_payload),
        limit=TAVERN_PROMPT_MAX_SCENE_BYTES,
        error_code="tavern_prompt_scene_bytes_exceeded",
        partition="scene_bytes",
    )

    retained_messages = sorted(
        recent_messages,
        key=lambda item: (item.sequence, item.id),
    )
    original_transcript_bytes = _utf8_bytes(
        _canonical_json(_transcript_payload(retained_messages))
    )
    original_prompt = _render_messages(
        system=system,
        user_template=template.require("user"),
        persona_instruction=persona_instruction,
        cast_payload=cast_payload,
        scene_payload=scene_payload,
        recent_messages=retained_messages,
        turn_kind=turn_kind,
        user_message=user_message,
        guidance=guidance,
        allowed_target_ids=allowed_target_ids,
        required_target_id=required_target_id,
    )
    original_prompt_bytes = max(
        _canonical_prompt_bytes(original_prompt),
        _canonical_prompt_bytes(
            [
                *original_prompt,
                {"role": "user", "content": recovery_message},
            ]
        ),
    )
    removed_message_count = 0
    all_messages = retained_messages
    # Removing an oldest prefix monotonically reduces every budget dimension.
    # Search the smallest removed prefix instead of re-rendering every suffix.
    # Keep the initial full-history fast path and the empty-history error order.
    search_lower = 0
    search_upper = len(all_messages)

    while True:
        messages = _render_messages(
            system=system,
            user_template=template.require("user"),
            persona_instruction=persona_instruction,
            cast_payload=cast_payload,
            scene_payload=scene_payload,
            recent_messages=retained_messages,
            turn_kind=turn_kind,
            user_message=user_message,
            guidance=guidance,
            allowed_target_ids=allowed_target_ids,
            required_target_id=required_target_id,
        )
        transcript_bytes = _utf8_bytes(
            _canonical_json(_transcript_payload(retained_messages))
        )
        recovery_messages = [
            *messages,
            {"role": "user", "content": recovery_message},
        ]
        prompt_bytes = max(
            _canonical_prompt_bytes(messages),
            _canonical_prompt_bytes(recovery_messages),
        )
        # Byte failures already require dropping the oldest message. Avoid scanning
        # those oversized prompts; retain the empty-transcript error precedence.
        if retained_messages and (
            transcript_bytes > TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES
            or prompt_bytes > TAVERN_PROMPT_MAX_CANONICAL_BYTES
        ):
            search_lower = removed_message_count + 1
            removed_message_count = (search_lower + search_upper) // 2
            retained_messages = all_messages[removed_message_count:]
            continue
        # The estimator is additive per message, so recovery always dominates.
        token_estimate = estimate_tavern_prompt_input_tokens(recovery_messages)
        if (
            transcript_bytes <= TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES
            and prompt_bytes <= TAVERN_PROMPT_MAX_CANONICAL_BYTES
            and token_estimate <= TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE
        ):
            if removed_message_count == search_lower:
                break
            search_upper = removed_message_count
            removed_message_count = (search_lower + search_upper) // 2
            retained_messages = all_messages[removed_message_count:]
            continue
        if retained_messages:
            search_lower = removed_message_count + 1
            removed_message_count = (search_lower + search_upper) // 2
            retained_messages = all_messages[removed_message_count:]
            continue
        if prompt_bytes > TAVERN_PROMPT_MAX_CANONICAL_BYTES:
            raise TavernPromptBudgetError(
                "tavern_prompt_canonical_bytes_exceeded",
                partition="canonical_prompt_bytes",
                actual=prompt_bytes,
                limit=TAVERN_PROMPT_MAX_CANONICAL_BYTES,
            )
        if token_estimate > TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE:
            raise TavernPromptBudgetError(
                "tavern_prompt_input_tokens_exceeded",
                partition="input_token_estimate",
                actual=token_estimate,
                limit=TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE,
            )
        raise TavernPromptBudgetError(
            "tavern_prompt_transcript_bytes_exceeded",
            partition="transcript_bytes",
            actual=transcript_bytes,
            limit=TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES,
        )

    return TavernPromptPreflightResult(
        messages=messages,
        recent_messages=retained_messages,
        report=TavernPromptBudgetReport(
            version=TAVERN_PROMPT_BUDGET_VERSION,
            original_prompt_bytes=original_prompt_bytes,
            final_prompt_bytes=prompt_bytes,
            input_token_estimate=token_estimate,
            original_transcript_bytes=original_transcript_bytes,
            final_transcript_bytes=transcript_bytes,
            removed_message_count=removed_message_count,
            scene_bytes=scene_bytes,
            scene_depth=scene_depth,
            persona_instruction_bytes=persona_instruction_bytes,
            cast_bytes=cast_bytes,
        ),
    )


def estimate_tavern_prompt_input_tokens(messages: list[dict[str, str]]) -> int:
    """Return a deterministic, deliberately conservative tokenizer-free bound."""

    estimate = 2
    for message in messages:
        content = message["content"]
        estimate += 6
        cursor = 0
        while cursor < len(content):
            match = _ASCII_WORD_RE.match(content, cursor)
            if match is not None:
                estimate += math.ceil(len(match.group(0)) / 3)
                cursor = match.end()
                continue
            character = content[cursor]
            if character.isascii():
                if character.isspace():
                    whitespace_end = cursor + 1
                    while (
                        whitespace_end < len(content)
                        and content[whitespace_end].isascii()
                        and content[whitespace_end].isspace()
                    ):
                        whitespace_end += 1
                    estimate += math.ceil((whitespace_end - cursor) / 4)
                    cursor = whitespace_end
                    continue
                estimate += 1
            else:
                estimate += max(1, math.ceil(len(character.encode("utf-8")) / 2))
            cursor += 1
    return estimate


def build_tavern_actor_recovery_message(actor_reply_schema: str) -> str:
    recovery = load_prompt_template("tavern_actor_prompt.txt").require("recovery").replace(
        "{{ACTOR_REPLY_SCHEMA}}",
        actor_reply_schema,
    )
    recovery_bytes = _utf8_bytes(recovery)
    if recovery_bytes > TAVERN_PROMPT_MAX_CANONICAL_BYTES:
        raise TavernPromptBudgetError(
            "tavern_prompt_recovery_bytes_exceeded",
            partition="recovery_bytes",
            actual=recovery_bytes,
            limit=TAVERN_PROMPT_MAX_CANONICAL_BYTES,
        )
    recovery_tokens = estimate_tavern_prompt_input_tokens(
        [{"role": "user", "content": recovery}]
    )
    if recovery_tokens > TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE:
        raise TavernPromptBudgetError(
            "tavern_prompt_recovery_tokens_exceeded",
            partition="recovery_token_estimate",
            actual=recovery_tokens,
            limit=TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE,
        )
    return recovery


def _render_messages(
    *,
    system: str,
    user_template: str,
    persona_instruction: str,
    cast_payload: list[dict[str, object]],
    scene_payload: object,
    recent_messages: list[TavernMessageRecord],
    turn_kind: str,
    user_message: str,
    guidance: str,
    allowed_target_ids: list[str],
    required_target_id: str,
) -> list[dict[str, str]]:
    user = (
        user_template.replace("{{PERSONA_INSTRUCTION_JSON}}", _json(persona_instruction))
        .replace("{{CAST_JSON}}", _json(cast_payload))
        .replace("{{SCENE_JSON}}", _json(scene_payload))
        .replace("{{TRANSCRIPT_JSON}}", _json(_transcript_payload(recent_messages)))
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


def _transcript_payload(
    recent_messages: list[TavernMessageRecord],
) -> list[dict[str, object]]:
    return [
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


def _scene_layer_depth(layers: list[SceneLayerStateRecord]) -> int:
    max_depth = 0
    pending = [(item, 1) for item in reversed(layers)]
    while pending:
        layer, depth = pending.pop()
        max_depth = max(max_depth, depth)
        if max_depth > TAVERN_PROMPT_MAX_SCENE_DEPTH:
            return max_depth
        pending.extend((child, depth + 1) for child in reversed(layer.children))
    return max_depth


def _require_partition_bytes(
    value: str,
    *,
    limit: int,
    error_code: str,
    partition: str = "partition_bytes",
) -> int:
    size = _utf8_bytes(value)
    if size > limit:
        raise TavernPromptBudgetError(
            error_code,
            partition=partition,
            actual=size,
            limit=limit,
        )
    return size


def _canonical_prompt_bytes(messages: list[dict[str, str]]) -> int:
    return _utf8_bytes(_canonical_json(messages))


def _utf8_bytes(value: str) -> int:
    return len(value.encode("utf-8"))


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)
