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
    openai_timeout_seconds: int = 30
    openai_plan_model_multimodal: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        return cls(
            plan_provider=os.getenv("GAL_LEARNER_PLAN_PROVIDER", "mock").strip().lower() or "mock",
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/"),
            openai_plan_model=os.getenv("OPENAI_PLAN_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
            openai_timeout_seconds=_to_int(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"), default=30),
            openai_plan_model_multimodal=_to_bool(
                os.getenv("OPENAI_PLAN_MODEL_MULTIMODAL", "false"),
                default=False,
            ),
        )


def _to_int(value: str, *, default: int) -> int:
    try:
        return int(value)
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
