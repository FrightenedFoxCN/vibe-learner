from __future__ import annotations

from dataclasses import replace
from typing import Any

from app.core.clock import utc_now_iso as _now_iso
from app.core.model_runtime_limits import DEFAULT_EMBEDDING_MODEL, DEFAULT_MODEL_NAME
from app.core.runtime_settings_validation import (
    NUMERIC_FIELDS,
    repair_legacy_runtime_numbers,
    validate_runtime_number,
)
from app.core.settings import Settings
from app.models.domain import RuntimeSettingsRecord
from app.services.local_store import LocalJsonStore

SECRET_FIELDS = (
    "openai_api_key",
    "openai_plan_api_key",
    "openai_setting_api_key",
    "openai_chat_api_key",
)
_RUNTIME_FIELDS = tuple(
    name
    for name in RuntimeSettingsRecord.model_fields
    if name in Settings.__dataclass_fields__
)
_TEXT_DEFAULTS = {
    "openai_plan_model": DEFAULT_MODEL_NAME,
    "openai_setting_model": DEFAULT_MODEL_NAME,
    "openai_chat_model": DEFAULT_MODEL_NAME,
    "openai_embedding_model": DEFAULT_EMBEDDING_MODEL,
    "openai_base_url": "https://api.openai.com/v1",
}
_BOOL_FIELDS = {
    "openai_setting_web_search_enabled",
    "openai_chat_model_multimodal",
    "openai_plan_model_multimodal",
    "openai_plan_fallback_disable_tools",
    "show_debug_info",
}


class RuntimeSettingsService:
    def __init__(self, store: LocalJsonStore, base_settings: Settings) -> None:
        self._store = store
        self._base_settings = base_settings
        self._record = self._load_or_default()
        self._session_secrets = {
            name: getattr(base_settings, name).strip()
            if base_settings.desktop_mode
            else ""
            for name in SECRET_FIELDS
        }

    def describe(self) -> dict[str, Any]:
        record = self._record
        secrets = self._effective_secret_values(record)
        result = record.model_dump(exclude={"config_id"})
        for name in SECRET_FIELDS:
            result[f"{name}_configured"] = bool(secrets[name])
            if self._base_settings.desktop_mode:
                result[name] = ""
        return result

    def effective_settings(self) -> Settings:
        record = self._record
        return replace(
            self._base_settings,
            **(
                {name: getattr(record, name) for name in _RUNTIME_FIELDS}
                | self._effective_secret_values(record)
            ),
        )

    def update(self, updates: dict[str, Any]) -> RuntimeSettingsRecord:
        normalized = {
            name: _normalize_update(name, value) for name, value in updates.items()
        }
        payload = self._record.model_dump() | normalized
        if self._base_settings.desktop_mode:
            payload.update(dict.fromkeys(SECRET_FIELDS, ""))
        else:
            for field in SECRET_FIELDS[1:]:
                payload[field] = payload[field] or payload["openai_api_key"]
        next_record = RuntimeSettingsRecord.model_validate(
            payload | {"updated_at": _now_iso()}
        )
        self._store.save_item("runtime_settings", "default", next_record)
        self._record = next_record
        return next_record

    def apply_session_secrets(self, updates: dict[str, Any]) -> None:
        self._session_secrets = self._session_secrets | {
            name: _normalize_update(name, updates[name])
            for name in SECRET_FIELDS
            if name in updates
        }

    def clear_session_secrets(self) -> None:
        self._session_secrets = dict.fromkeys(SECRET_FIELDS, "")

    def _load_or_default(self) -> RuntimeSettingsRecord:
        base = {name: getattr(self._base_settings, name) for name in _RUNTIME_FIELDS}
        raw = self._store.load_runtime_settings_payload()
        payload = base | repair_legacy_runtime_numbers(raw or {})
        if self._base_settings.desktop_mode:
            payload.update(dict.fromkeys(SECRET_FIELDS, ""))
        if raw is not None and all(
            raw.get(name) == value for name, value in payload.items()
        ):
            return RuntimeSettingsRecord.model_validate(payload)
        record = RuntimeSettingsRecord.model_validate(
            payload | {"updated_at": _now_iso()}
        )
        self._store.save_item("runtime_settings", "default", record)
        return record

    def _effective_secret_values(self, record: RuntimeSettingsRecord) -> dict[str, str]:
        session = self._session_secrets
        effective = {
            name: session[name] or getattr(record, name).strip()
            for name in SECRET_FIELDS
        }
        global_key = effective["openai_api_key"]
        return {name: value or global_key for name, value in effective.items()}


def _normalize_update(name: str, value: object) -> object:
    if name in NUMERIC_FIELDS:
        return validate_runtime_number(name, value)
    if name in _BOOL_FIELDS:
        if type(value) is not bool:
            raise ValueError(f"invalid_{name}")
        return value
    if name not in _RUNTIME_FIELDS or not isinstance(value, str):
        raise ValueError(f"invalid_{name}")
    text = value.strip()
    if name == "plan_provider":
        provider = text.lower() or "mock"
        if provider == "openai":
            return "litellm"
        if provider not in {"mock", "litellm"}:
            raise ValueError("invalid_plan_provider")
        return provider
    if name.endswith("_base_url"):
        text = text.rstrip("/")
    return text or _TEXT_DEFAULTS.get(name, "")
