"""Canonical model request defaults and bounded-recovery limits.

Keep provider request limits here. Domain schema limits (for example Scene tree
depth) and Harness persistence limits intentionally remain with their owning
models/repositories.
"""

DEFAULT_MODEL_NAME = "gpt-4.1-mini"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"

DEFAULT_CHAT_TEMPERATURE = 0.35
DEFAULT_SETTING_TEMPERATURE = 0.4
DEFAULT_SETTING_MAX_TOKENS = 900
DEFAULT_CHAT_MAX_TOKENS = 800
DEFAULT_CHAT_HISTORY_MESSAGES = 8
DEFAULT_CHAT_TOOL_MAX_ROUNDS = 4
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 30

MODEL_TEMPERATURE_MIN = 0.0
MODEL_TEMPERATURE_MAX = 2.0
MODEL_MAX_TOKENS_MIN = 64
MODEL_MAX_TOKENS_MAX = 16_384
CHAT_HISTORY_MESSAGES_MIN = 1
CHAT_HISTORY_MESSAGES_MAX = 40
CHAT_TOOL_MAX_ROUNDS_MIN = 1
CHAT_TOOL_MAX_ROUNDS_MAX = 12
PROVIDER_TIMEOUT_SECONDS_MIN = 5
PROVIDER_TIMEOUT_SECONDS_MAX = 300

# Large structured generation uses one shared ceiling across Planning, Persona,
# and Scene. Provider adapters may use a smaller user-configured value for
# short setting-assist calls.
STRUCTURED_GENERATION_MAX_TOKENS = 8_192
PLANNING_MAX_TOKENS = STRUCTURED_GENERATION_MAX_TOKENS
SETTING_GENERATION_MAX_TOKENS = STRUCTURED_GENERATION_MAX_TOKENS

STUDY_CHAT_RECOVERY_MIN_TOKENS = 1_600
STUDY_CHAT_EXEMPT_TOOL_EXTRA_ROUNDS = 12
TAVERN_ACTOR_RECOVERY_MIN_TOKENS = 900

PLANNING_MAX_ROUNDS = 24
PLANNING_MAX_TOOL_ROUNDS = 1
PLANNING_MAX_CONTENT_FILTER_RETRIES = 2
PLANNING_MAX_EMPTY_RESPONSE_RETRIES = 1
PLANNING_MAX_TOOL_PROBE_RETRIES = 3
PLANNING_MAX_UNOFFERED_TOOL_RETRIES = 1

SETTING_STRUCTURED_REPAIR_ATTEMPTS = 1
SETTING_REPAIR_TOKEN_INCREMENT = 800
SETTING_REPAIR_TOKEN_MULTIPLIER = 1.5

LITELLM_TRANSIENT_RETRY_COUNT = 2

FEATURE_PROBE_TOOL_MAX_TOKENS = 32
FEATURE_PROBE_JSON_MAX_TOKENS = 48
FEATURE_PROBE_TAVERN_MAX_TOKENS = 48


def browser_model_runtime_config_snapshot() -> dict[str, object]:
    """Return the stable Python side of the browser-visible settings contract."""
    return {
        "schema_version": "model-runtime-config-v1",
        "default_model_name": DEFAULT_MODEL_NAME,
        "default_embedding_model": DEFAULT_EMBEDDING_MODEL,
        "timeout_seconds": {
            "min": PROVIDER_TIMEOUT_SECONDS_MIN,
            "max": PROVIDER_TIMEOUT_SECONDS_MAX,
            "default": DEFAULT_PROVIDER_TIMEOUT_SECONDS,
        },
        "setting_temperature": {
            "min": MODEL_TEMPERATURE_MIN,
            "max": MODEL_TEMPERATURE_MAX,
            "default": DEFAULT_SETTING_TEMPERATURE,
        },
        "chat_temperature": {
            "min": MODEL_TEMPERATURE_MIN,
            "max": MODEL_TEMPERATURE_MAX,
            "default": DEFAULT_CHAT_TEMPERATURE,
        },
        "setting_max_tokens": {
            "min": MODEL_MAX_TOKENS_MIN,
            "max": MODEL_MAX_TOKENS_MAX,
            "default": DEFAULT_SETTING_MAX_TOKENS,
        },
        "chat_max_tokens": {
            "min": MODEL_MAX_TOKENS_MIN,
            "max": MODEL_MAX_TOKENS_MAX,
            "default": DEFAULT_CHAT_MAX_TOKENS,
        },
        "chat_history_messages": {
            "min": CHAT_HISTORY_MESSAGES_MIN,
            "max": CHAT_HISTORY_MESSAGES_MAX,
            "default": DEFAULT_CHAT_HISTORY_MESSAGES,
        },
        "chat_tool_max_rounds": {
            "min": CHAT_TOOL_MAX_ROUNDS_MIN,
            "max": CHAT_TOOL_MAX_ROUNDS_MAX,
            "default": DEFAULT_CHAT_TOOL_MAX_ROUNDS,
        },
    }
