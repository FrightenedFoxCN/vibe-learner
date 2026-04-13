from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.settings import Settings
from app.models.domain import RuntimeSettingsRecord
from app.services.local_store import LocalJsonStore


class RuntimeSettingsService:
    def __init__(self, store: LocalJsonStore, base_settings: Settings) -> None:
        self._store = store
        self._base_settings = base_settings
        self._record = self._load_or_default()

    def describe(self) -> dict[str, Any]:
        return {
            "updated_at": self._record.updated_at,
            "plan_provider": self._record.plan_provider,
            "openai_api_key": self._record.openai_api_key,
            "openai_base_url": self._record.openai_base_url,
            "openai_plan_api_key": self._record.openai_plan_api_key,
            "openai_plan_base_url": self._record.openai_plan_base_url,
            "openai_plan_model": self._record.openai_plan_model,
            "openai_setting_api_key": self._record.openai_setting_api_key,
            "openai_setting_base_url": self._record.openai_setting_base_url,
            "openai_setting_model": self._record.openai_setting_model,
            "openai_setting_web_search_enabled": self._record.openai_setting_web_search_enabled,
            "openai_chat_api_key": self._record.openai_chat_api_key,
            "openai_chat_base_url": self._record.openai_chat_base_url,
            "openai_chat_model": self._record.openai_chat_model,
            "openai_chat_temperature": self._record.openai_chat_temperature,
            "openai_setting_temperature": self._record.openai_setting_temperature,
            "openai_setting_max_tokens": self._record.openai_setting_max_tokens,
            "openai_chat_max_tokens": self._record.openai_chat_max_tokens,
            "openai_chat_history_messages": self._record.openai_chat_history_messages,
            "openai_chat_tool_max_rounds": self._record.openai_chat_tool_max_rounds,
            "openai_embedding_model": self._record.openai_embedding_model,
            "openai_chat_model_multimodal": self._record.openai_chat_model_multimodal,
            "openai_timeout_seconds": self._record.openai_timeout_seconds,
            "openai_plan_model_multimodal": self._record.openai_plan_model_multimodal,
            "openai_plan_fallback_model": self._record.openai_plan_fallback_model,
            "openai_plan_fallback_disable_tools": self._record.openai_plan_fallback_disable_tools,
            "show_debug_info": self._record.show_debug_info,
        }

    def effective_settings(self) -> Settings:
        record = self._record
        return Settings(
            plan_provider=record.plan_provider,
            openai_api_key=record.openai_api_key,
            openai_base_url=record.openai_base_url,
            openai_plan_api_key=record.openai_plan_api_key,
            openai_plan_base_url=record.openai_plan_base_url,
            openai_plan_model=record.openai_plan_model,
            openai_setting_api_key=record.openai_setting_api_key,
            openai_setting_base_url=record.openai_setting_base_url,
            openai_setting_model=record.openai_setting_model,
            openai_setting_web_search_enabled=record.openai_setting_web_search_enabled,
            openai_chat_api_key=record.openai_chat_api_key,
            openai_chat_base_url=record.openai_chat_base_url,
            openai_chat_model=record.openai_chat_model,
            openai_chat_temperature=record.openai_chat_temperature,
            openai_setting_temperature=record.openai_setting_temperature,
            openai_setting_max_tokens=record.openai_setting_max_tokens,
            openai_chat_max_tokens=record.openai_chat_max_tokens,
            openai_chat_history_messages=record.openai_chat_history_messages,
            openai_chat_tool_max_rounds=record.openai_chat_tool_max_rounds,
            openai_embedding_model=record.openai_embedding_model,
            openai_chat_model_multimodal=record.openai_chat_model_multimodal,
            openai_timeout_seconds=record.openai_timeout_seconds,
            openai_plan_model_multimodal=record.openai_plan_model_multimodal,
            openai_plan_fallback_model=record.openai_plan_fallback_model,
            openai_plan_fallback_disable_tools=record.openai_plan_fallback_disable_tools,
        )

    def update(self, updates: dict[str, Any]) -> RuntimeSettingsRecord:
        plan_provider = _normalize_plan_provider(updates.get("plan_provider", self._record.plan_provider))

        openai_api_key = str(updates.get("openai_api_key", self._record.openai_api_key)).strip()
        openai_base_url = _normalize_base_url(
            updates.get("openai_base_url", self._record.openai_base_url)
        )

        raw_plan_api_key = updates.get("openai_plan_api_key", self._record.openai_plan_api_key)
        raw_plan_base_url = updates.get("openai_plan_base_url", self._record.openai_plan_base_url)
        raw_setting_api_key = updates.get("openai_setting_api_key", self._record.openai_setting_api_key)
        raw_setting_base_url = updates.get("openai_setting_base_url", self._record.openai_setting_base_url)
        raw_chat_api_key = updates.get("openai_chat_api_key", self._record.openai_chat_api_key)
        raw_chat_base_url = updates.get("openai_chat_base_url", self._record.openai_chat_base_url)

        openai_plan_api_key = str(raw_plan_api_key).strip() or openai_api_key
        openai_plan_base_url = _normalize_optional_base_url(raw_plan_base_url)
        openai_setting_api_key = str(raw_setting_api_key).strip() or openai_api_key
        openai_setting_base_url = _normalize_optional_base_url(raw_setting_base_url)
        openai_chat_api_key = str(raw_chat_api_key).strip() or openai_api_key
        openai_chat_base_url = _normalize_optional_base_url(raw_chat_base_url)

        openai_plan_model = str(
            updates.get("openai_plan_model", self._record.openai_plan_model)
        ).strip() or "gpt-4.1-mini"
        openai_setting_model = str(
            updates.get("openai_setting_model", self._record.openai_setting_model)
        ).strip() or "gpt-4.1-mini"
        openai_setting_web_search_enabled = _normalize_bool(
            updates.get(
                "openai_setting_web_search_enabled",
                self._record.openai_setting_web_search_enabled,
            ),
            code="invalid_openai_setting_web_search_enabled",
        )
        openai_chat_model = str(
            updates.get("openai_chat_model", self._record.openai_chat_model)
        ).strip() or "gpt-4.1-mini"
        openai_embedding_model = str(
            updates.get("openai_embedding_model", self._record.openai_embedding_model)
        ).strip() or "text-embedding-3-small"

        openai_chat_temperature = _normalize_float(
            updates.get("openai_chat_temperature", self._record.openai_chat_temperature),
            code="invalid_openai_chat_temperature",
            min_value=0.0,
            max_value=2.0,
        )
        openai_setting_temperature = _normalize_float(
            updates.get("openai_setting_temperature", self._record.openai_setting_temperature),
            code="invalid_openai_setting_temperature",
            min_value=0.0,
            max_value=2.0,
        )
        openai_setting_max_tokens = _normalize_int(
            updates.get("openai_setting_max_tokens", self._record.openai_setting_max_tokens),
            code="invalid_openai_setting_max_tokens",
            min_value=64,
            max_value=16384,
        )
        openai_chat_max_tokens = _normalize_int(
            updates.get("openai_chat_max_tokens", self._record.openai_chat_max_tokens),
            code="invalid_openai_chat_max_tokens",
            min_value=64,
            max_value=16384,
        )
        openai_chat_history_messages = _normalize_int(
            updates.get("openai_chat_history_messages", self._record.openai_chat_history_messages),
            code="invalid_openai_chat_history_messages",
            min_value=1,
            max_value=40,
        )
        openai_chat_tool_max_rounds = _normalize_int(
            updates.get("openai_chat_tool_max_rounds", self._record.openai_chat_tool_max_rounds),
            code="invalid_openai_chat_tool_max_rounds",
            min_value=1,
            max_value=12,
        )
        openai_chat_model_multimodal = _normalize_bool(
            updates.get("openai_chat_model_multimodal", self._record.openai_chat_model_multimodal),
            code="invalid_openai_chat_model_multimodal",
        )
        openai_plan_model_multimodal = _normalize_bool(
            updates.get("openai_plan_model_multimodal", self._record.openai_plan_model_multimodal),
            code="invalid_openai_plan_model_multimodal",
        )
        openai_plan_fallback_disable_tools = _normalize_bool(
            updates.get("openai_plan_fallback_disable_tools", self._record.openai_plan_fallback_disable_tools),
            code="invalid_openai_plan_fallback_disable_tools",
        )
        openai_plan_fallback_model = str(
            updates.get("openai_plan_fallback_model", self._record.openai_plan_fallback_model)
        ).strip()

        timeout_value = updates.get("openai_timeout_seconds", self._record.openai_timeout_seconds)
        try:
            openai_timeout_seconds = int(timeout_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_openai_timeout_seconds") from exc
        if openai_timeout_seconds < 5 or openai_timeout_seconds > 300:
            raise ValueError("invalid_openai_timeout_seconds")

        show_debug_info = updates.get("show_debug_info", self._record.show_debug_info)
        if not isinstance(show_debug_info, bool):
            raise ValueError("invalid_show_debug_info")

        self._record = RuntimeSettingsRecord(
            config_id="default",
            updated_at=_now_iso(),
            plan_provider=plan_provider,
            openai_api_key=openai_api_key,
            openai_base_url=openai_base_url,
            openai_plan_api_key=openai_plan_api_key,
            openai_plan_base_url=openai_plan_base_url,
            openai_plan_model=openai_plan_model,
            openai_setting_api_key=openai_setting_api_key,
            openai_setting_base_url=openai_setting_base_url,
            openai_setting_model=openai_setting_model,
            openai_setting_web_search_enabled=openai_setting_web_search_enabled,
            openai_chat_api_key=openai_chat_api_key,
            openai_chat_base_url=openai_chat_base_url,
            openai_chat_model=openai_chat_model,
            openai_chat_temperature=openai_chat_temperature,
            openai_setting_temperature=openai_setting_temperature,
            openai_setting_max_tokens=openai_setting_max_tokens,
            openai_chat_max_tokens=openai_chat_max_tokens,
            openai_chat_history_messages=openai_chat_history_messages,
            openai_chat_tool_max_rounds=openai_chat_tool_max_rounds,
            openai_embedding_model=openai_embedding_model,
            openai_chat_model_multimodal=openai_chat_model_multimodal,
            openai_timeout_seconds=openai_timeout_seconds,
            openai_plan_model_multimodal=openai_plan_model_multimodal,
            openai_plan_fallback_model=openai_plan_fallback_model,
            openai_plan_fallback_disable_tools=openai_plan_fallback_disable_tools,
            show_debug_info=show_debug_info,
        )
        self._store.save_item("runtime_settings", "default", self._record)
        return self._record

    def _load_or_default(self) -> RuntimeSettingsRecord:
        existing = self._store.load_item("runtime_settings", "default", RuntimeSettingsRecord)
        if existing is not None:
            migrated = self._migrate_existing_record(existing)
            if migrated != existing:
                self._store.save_item("runtime_settings", "default", migrated)
            return migrated
        record = RuntimeSettingsRecord(
            config_id="default",
            updated_at=_now_iso(),
            plan_provider=self._base_settings.plan_provider,
            openai_api_key=self._base_settings.openai_api_key,
            openai_base_url=self._base_settings.openai_base_url,
            openai_plan_api_key=self._base_settings.openai_plan_api_key,
            openai_plan_base_url=self._base_settings.openai_plan_base_url,
            openai_plan_model=self._base_settings.openai_plan_model,
            openai_setting_api_key=self._base_settings.openai_setting_api_key,
            openai_setting_base_url=self._base_settings.openai_setting_base_url,
            openai_setting_model=self._base_settings.openai_setting_model,
            openai_setting_web_search_enabled=self._base_settings.openai_setting_web_search_enabled,
            openai_chat_api_key=self._base_settings.openai_chat_api_key,
            openai_chat_base_url=self._base_settings.openai_chat_base_url,
            openai_chat_model=self._base_settings.openai_chat_model,
            openai_chat_temperature=self._base_settings.openai_chat_temperature,
            openai_setting_temperature=self._base_settings.openai_setting_temperature,
            openai_setting_max_tokens=self._base_settings.openai_setting_max_tokens,
            openai_chat_max_tokens=self._base_settings.openai_chat_max_tokens,
            openai_chat_history_messages=self._base_settings.openai_chat_history_messages,
            openai_chat_tool_max_rounds=self._base_settings.openai_chat_tool_max_rounds,
            openai_embedding_model=self._base_settings.openai_embedding_model,
            openai_chat_model_multimodal=self._base_settings.openai_chat_model_multimodal,
            openai_timeout_seconds=self._base_settings.openai_timeout_seconds,
            openai_plan_model_multimodal=self._base_settings.openai_plan_model_multimodal,
            openai_plan_fallback_model=self._base_settings.openai_plan_fallback_model,
            openai_plan_fallback_disable_tools=self._base_settings.openai_plan_fallback_disable_tools,
            show_debug_info=True,
        )
        self._store.save_item("runtime_settings", "default", record)
        return record

    def _migrate_existing_record(self, existing: RuntimeSettingsRecord) -> RuntimeSettingsRecord:
        fields_set = set(existing.model_fields_set)
        updates: dict[str, Any] = {}

        field_to_base_value = {
            "plan_provider": self._base_settings.plan_provider,
            "openai_api_key": self._base_settings.openai_api_key,
            "openai_base_url": self._base_settings.openai_base_url,
            "openai_plan_api_key": self._base_settings.openai_plan_api_key,
            "openai_plan_base_url": self._base_settings.openai_plan_base_url,
            "openai_plan_model": self._base_settings.openai_plan_model,
            "openai_setting_api_key": self._base_settings.openai_setting_api_key,
            "openai_setting_base_url": self._base_settings.openai_setting_base_url,
            "openai_setting_model": self._base_settings.openai_setting_model,
            "openai_setting_web_search_enabled": self._base_settings.openai_setting_web_search_enabled,
            "openai_chat_api_key": self._base_settings.openai_chat_api_key,
            "openai_chat_base_url": self._base_settings.openai_chat_base_url,
            "openai_chat_model": self._base_settings.openai_chat_model,
            "openai_chat_temperature": self._base_settings.openai_chat_temperature,
            "openai_setting_temperature": self._base_settings.openai_setting_temperature,
            "openai_setting_max_tokens": self._base_settings.openai_setting_max_tokens,
            "openai_chat_max_tokens": self._base_settings.openai_chat_max_tokens,
            "openai_chat_history_messages": self._base_settings.openai_chat_history_messages,
            "openai_chat_tool_max_rounds": self._base_settings.openai_chat_tool_max_rounds,
            "openai_embedding_model": self._base_settings.openai_embedding_model,
            "openai_chat_model_multimodal": self._base_settings.openai_chat_model_multimodal,
            "openai_timeout_seconds": self._base_settings.openai_timeout_seconds,
            "openai_plan_model_multimodal": self._base_settings.openai_plan_model_multimodal,
            "openai_plan_fallback_model": self._base_settings.openai_plan_fallback_model,
            "openai_plan_fallback_disable_tools": self._base_settings.openai_plan_fallback_disable_tools,
        }

        for field_name, base_value in field_to_base_value.items():
            if field_name not in fields_set:
                updates[field_name] = base_value

        if not updates:
            return existing

        updates["updated_at"] = _now_iso()
        return existing.model_copy(update=updates)


def _normalize_plan_provider(value: Any) -> str:
    provider = str(value or "").strip().lower() or "mock"
    if provider == "openai":
        return "litellm"
    if provider not in {"mock", "litellm"}:
        raise ValueError("invalid_plan_provider")
    return provider


def _normalize_base_url(value: Any, fallback: str = "https://api.openai.com/v1") -> str:
    return str(value or "").strip().rstrip("/") or fallback


def _normalize_optional_base_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def _normalize_int(value: Any, *, code: str, min_value: int, max_value: int) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(code) from exc
    if normalized < min_value or normalized > max_value:
        raise ValueError(code)
    return normalized


def _normalize_float(value: Any, *, code: str, min_value: float, max_value: float) -> float:
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(code) from exc
    if normalized < min_value or normalized > max_value:
        raise ValueError(code)
    return normalized


def _normalize_bool(value: Any, *, code: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(code)
    return value


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
