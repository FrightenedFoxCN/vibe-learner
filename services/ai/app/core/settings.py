from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    plan_provider: str = "mock"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_plan_model: str = "gpt-4.1-mini"
    openai_setting_model: str = "gpt-4.1-mini"
    openai_chat_model: str = "gpt-4.1-mini"
    openai_chat_temperature: float = 0.35
    openai_setting_temperature: float = 0.4
    openai_setting_max_tokens: int = 900
    openai_chat_max_tokens: int = 800
    openai_chat_history_messages: int = 8
    openai_chat_tool_max_rounds: int = 4
    openai_chat_tools_enabled: bool = True
    openai_chat_memory_tool_enabled: bool = True
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model_multimodal: bool = False
    openai_timeout_seconds: int = 30
    openai_plan_model_multimodal: bool = False
    openai_plan_tools_enabled: bool = True
    openai_plan_fallback_model: str = ""
    openai_plan_fallback_disable_tools: bool = True

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        return cls(
            plan_provider=os.getenv("VIBE_LEARNER_PLAN_PROVIDER", "mock").strip().lower() or "mock",
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_plan_model=os.getenv("OPENAI_PLAN_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            openai_setting_model=os.getenv("OPENAI_SETTING_MODEL", "gpt-4.1-mini").strip()
            or "gpt-4.1-mini",
            openai_chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            openai_chat_temperature=_to_float(
                os.getenv("OPENAI_CHAT_TEMPERATURE", "0.35"),
                default=0.35,
            ),
            openai_setting_temperature=_to_float(
                os.getenv("OPENAI_SETTING_TEMPERATURE", "0.4"),
                default=0.4,
            ),
            openai_setting_max_tokens=_to_int(
                os.getenv("OPENAI_SETTING_MAX_TOKENS", "900"),
                default=900,
            ),
            openai_chat_max_tokens=_to_int(os.getenv("OPENAI_CHAT_MAX_TOKENS", "800"), default=800),
            openai_chat_history_messages=_to_int(
                os.getenv("OPENAI_CHAT_HISTORY_MESSAGES", "8"),
                default=8,
            ),
            openai_chat_tool_max_rounds=_to_int(
                os.getenv("OPENAI_CHAT_TOOL_MAX_ROUNDS", "4"),
                default=4,
            ),
            openai_chat_tools_enabled=_to_bool(
                os.getenv("OPENAI_CHAT_TOOLS_ENABLED", "true"),
                default=True,
            ),
            openai_chat_memory_tool_enabled=_to_bool(
                os.getenv("OPENAI_CHAT_MEMORY_TOOL_ENABLED", "true"),
                default=True,
            ),
            openai_embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small").strip()
            or "text-embedding-3-small",
            openai_chat_model_multimodal=_to_bool(
                os.getenv("OPENAI_CHAT_MODEL_MULTIMODAL", "false"),
                default=False,
            ),
            openai_timeout_seconds=_to_int(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"), default=30),
            openai_plan_model_multimodal=_to_bool(
                os.getenv("OPENAI_PLAN_MODEL_MULTIMODAL", "false"),
                default=False,
            ),
            openai_plan_tools_enabled=_to_bool(
                os.getenv("OPENAI_PLAN_TOOLS_ENABLED", "true"),
                default=True,
            ),
            openai_plan_fallback_model=os.getenv("OPENAI_PLAN_FALLBACK_MODEL", "").strip(),
            openai_plan_fallback_disable_tools=_to_bool(
                os.getenv("OPENAI_PLAN_FALLBACK_DISABLE_TOOLS", "true"),
                default=True,
            ),
        )


def _to_int(value: str, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: str, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: str, *, default: bool) -> bool:
    normalized = (value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _load_dotenv() -> None:
    dotenv_path = Path(__file__).resolve().parents[2] / ".env"
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
