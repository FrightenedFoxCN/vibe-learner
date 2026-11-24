"""Shared numeric contract for persisted settings, DTOs and env input."""

import logging
from typing import Annotated

from pydantic import BeforeValidator, Field, TypeAdapter, ValidationError

from app.core.model_runtime_limits import (
    CHAT_HISTORY_MESSAGES_MAX,
    CHAT_HISTORY_MESSAGES_MIN,
    CHAT_TOOL_MAX_ROUNDS_MAX,
    CHAT_TOOL_MAX_ROUNDS_MIN,
    DEFAULT_CHAT_HISTORY_MESSAGES,
    DEFAULT_CHAT_MAX_TOKENS,
    DEFAULT_CHAT_TEMPERATURE,
    DEFAULT_CHAT_TOOL_MAX_ROUNDS,
    DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    DEFAULT_SETTING_MAX_TOKENS,
    DEFAULT_SETTING_TEMPERATURE,
    MODEL_MAX_TOKENS_MAX,
    MODEL_MAX_TOKENS_MIN,
    MODEL_TEMPERATURE_MAX,
    MODEL_TEMPERATURE_MIN,
    PROVIDER_TIMEOUT_SECONDS_MAX,
    PROVIDER_TIMEOUT_SECONDS_MIN,
)


def _real_number(value: object) -> object:
    # Temperature accepts JSON integers and floats, not other values with a
    # __float__ implementation. Check bounds before converting even a huge int.
    if type(value) not in (int, float) or not (
        MODEL_TEMPERATURE_MIN <= value <= MODEL_TEMPERATURE_MAX
    ):
        raise ValueError("expected a finite temperature in range")
    return value


RuntimeTemperature = Annotated[
    float,
    Field(
        strict=True,
        ge=MODEL_TEMPERATURE_MIN,
        le=MODEL_TEMPERATURE_MAX,
        allow_inf_nan=False,
    ),
    BeforeValidator(_real_number),
]
RuntimeMaxTokens = Annotated[
    int, Field(strict=True, ge=MODEL_MAX_TOKENS_MIN, le=MODEL_MAX_TOKENS_MAX)
]
RuntimeHistoryMessages = Annotated[
    int, Field(strict=True, ge=CHAT_HISTORY_MESSAGES_MIN, le=CHAT_HISTORY_MESSAGES_MAX)
]
RuntimeToolMaxRounds = Annotated[
    int, Field(strict=True, ge=CHAT_TOOL_MAX_ROUNDS_MIN, le=CHAT_TOOL_MAX_ROUNDS_MAX)
]
RuntimeTimeoutSeconds = Annotated[
    int,
    Field(
        strict=True, ge=PROVIDER_TIMEOUT_SECONDS_MIN, le=PROVIDER_TIMEOUT_SECONDS_MAX
    ),
]

logger = logging.getLogger(__name__)

_TEMPERATURE = TypeAdapter(RuntimeTemperature)
_MAX_TOKENS = TypeAdapter(RuntimeMaxTokens)
NUMERIC_FIELDS = {
    "openai_chat_temperature": (_TEMPERATURE, DEFAULT_CHAT_TEMPERATURE),
    "openai_setting_temperature": (_TEMPERATURE, DEFAULT_SETTING_TEMPERATURE),
    "openai_setting_max_tokens": (_MAX_TOKENS, DEFAULT_SETTING_MAX_TOKENS),
    "openai_chat_max_tokens": (_MAX_TOKENS, DEFAULT_CHAT_MAX_TOKENS),
    "openai_chat_history_messages": (
        TypeAdapter(RuntimeHistoryMessages),
        DEFAULT_CHAT_HISTORY_MESSAGES,
    ),
    "openai_chat_tool_max_rounds": (
        TypeAdapter(RuntimeToolMaxRounds),
        DEFAULT_CHAT_TOOL_MAX_ROUNDS,
    ),
    "openai_timeout_seconds": (
        TypeAdapter(RuntimeTimeoutSeconds),
        DEFAULT_PROVIDER_TIMEOUT_SECONDS,
    ),
}


def validate_runtime_number(field: str, value: object) -> int | float:
    adapter, _ = NUMERIC_FIELDS[field]
    try:
        return adapter.validate_python(value)
    except ValidationError:
        # Never include inputs in logs or user-facing errors.
        raise ValueError(f"invalid_{field}") from None


def repair_legacy_runtime_numbers(payload: dict[str, object]) -> dict[str, object]:
    """Reset only invalid numeric fields to safe canonical defaults, never clamp.

    Missing fields are left for the existing startup-default migration. Log only
    field names: an invalid value could itself contain a credential.
    """
    repaired = dict(payload)
    for field, (_, default) in NUMERIC_FIELDS.items():
        if field not in payload:
            continue
        try:
            validate_runtime_number(field, payload[field])
        except ValueError:
            repaired[field] = default
            logger.warning("runtime_settings.legacy_number_reset field=%s", field)
    return repaired
