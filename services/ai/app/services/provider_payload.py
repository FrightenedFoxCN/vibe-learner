"""Shared compatible response envelope decoding; domain schemas stay with capabilities."""
from __future__ import annotations

import json
from typing import Any
from app.services.provider_transport import _coerce_int

from app.core.logging import get_logger

logger = get_logger("vibe_learner.model_provider")


def _extract_json_payload(
    content: str,
    *,
    invalid_json_code: str = "plan_model_invalid_json",
    invalid_payload_code: str = "plan_model_invalid_payload",
) -> dict[str, object]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        # Some upstream models emit invalid string escapes like "\("; normalize and retry once.
        sanitized = _escape_invalid_backslashes_in_json_strings(content)
        if sanitized != content:
            try:
                payload = json.loads(sanitized)
            except json.JSONDecodeError:
                payload = None
        else:
            payload = None
        if payload is not None:
            if not isinstance(payload, dict):
                raise RuntimeError(invalid_payload_code)
            return payload
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError(invalid_json_code)
        sliced = content[start : end + 1]
        try:
            payload = json.loads(sliced)
        except json.JSONDecodeError:
            sanitized_sliced = _escape_invalid_backslashes_in_json_strings(sliced)
            try:
                payload = json.loads(sanitized_sliced)
            except json.JSONDecodeError as exc:
                raise RuntimeError(invalid_json_code) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(invalid_payload_code)
    return payload



def _escape_invalid_backslashes_in_json_strings(raw: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    i = 0
    valid_escape = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}

    while i < len(raw):
        ch = raw[i]
        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if escaped:
            result.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\":
            next_char = raw[i + 1] if i + 1 < len(raw) else ""
            if next_char and next_char in valid_escape:
                result.append(ch)
            else:
                # Double invalid backslashes so the payload remains literal text.
                result.append("\\\\")
            escaped = True
            i += 1
            continue

        result.append(ch)
        if ch == '"':
            in_string = False
        i += 1

    return "".join(result)



def _extract_choice_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("chat_model_invalid_payload")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("chat_model_invalid_payload")

    # Some OpenAI-compatible providers return assistant text in non-standard shapes.
    # Keep extraction tolerant before treating the payload as invalid.
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "value", "content"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                nested = value.get("value")
                if isinstance(nested, str) and nested.strip():
                    return nested
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type not in {"text", "output_text", "message"}:
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                texts.append(text_value)
                continue
            if isinstance(text_value, dict):
                nested_value = text_value.get("value")
                if isinstance(nested_value, str) and nested_value.strip():
                    texts.append(nested_value)
                    continue
            value_field = item.get("value")
            if isinstance(value_field, str) and value_field.strip():
                texts.append(value_field)
        merged = "".join(texts).strip()
        if merged:
            return merged

    alt_text = choices[0].get("text") if isinstance(choices[0], dict) else None
    if isinstance(alt_text, str) and alt_text.strip():
        return alt_text

    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        logger.warning("model.chat.extract_content fallback=reasoning_content")
        return reasoning_content

    logger.warning(
        "model.chat.extract_content failed message_keys=%s content_type=%s",
        sorted(message.keys()),
        type(content).__name__,
    )
    raise RuntimeError("chat_model_invalid_payload")


def _extract_choice_diagnostics(payload: dict[str, Any]) -> tuple[str, int, int]:
    choices = payload.get("choices")
    finish_reason = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = str(choices[0].get("finish_reason") or "")

    usage = payload.get("usage") if isinstance(payload, dict) else None
    completion_tokens = 0
    reasoning_tokens = 0
    if isinstance(usage, dict):
        completion_tokens = _coerce_int(usage.get("completion_tokens"), default=0)
        details = usage.get("completion_tokens_details")
        if isinstance(details, dict):
            reasoning_tokens = _coerce_int(details.get("reasoning_tokens"), default=0)
    return finish_reason, reasoning_tokens, completion_tokens

