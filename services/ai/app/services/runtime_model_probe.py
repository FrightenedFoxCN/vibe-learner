from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any


_IMAGE_MODALITY_TOKENS = {
    "image",
    "images",
    "vision",
    "input_image",
    "image_input",
    "image_url",
    "image_urls",
}

_WEB_SEARCH_TOOL_TOKENS = {
    "web_search",
    "web_search_preview",
    "web-browse",
    "browser",
    "search",
}

_MULTIMODAL_NAME_HINTS = (
    re.compile(r"gpt-4o", re.IGNORECASE),
    re.compile(r"gpt-4\.1", re.IGNORECASE),
    re.compile(r"gpt-4\.5", re.IGNORECASE),
    re.compile(r"gpt-5", re.IGNORECASE),
    re.compile(r"(?:^|[-_])omni(?:[-_]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[-_])vision(?:[-_]|$)", re.IGNORECASE),
    re.compile(r"(?:^|[-_])vl(?:[-_]|$)", re.IGNORECASE),
    re.compile(r"llava", re.IGNORECASE),
    re.compile(r"gemini", re.IGNORECASE),
    re.compile(r"claude-3", re.IGNORECASE),
    re.compile(r"claude-(?:sonnet|opus|haiku)-4", re.IGNORECASE),
)


def probe_openai_models(*, api_key: str, base_url: str, timeout_seconds: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url=f"{base_url.rstrip('/')}/models",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_payload = json.loads(response.read().decode("utf-8"))
        return parse_model_probe_payload(raw_payload)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        return {
            "available": False,
            "models": [],
            "capabilities": {},
            "error": f"http_{exc.code}:{body[:180]}",
        }
    except urllib.error.URLError as exc:
        return {
            "available": False,
            "models": [],
            "capabilities": {},
            "error": f"network_error:{exc.reason}",
        }
    except (TimeoutError, socket.timeout):
        return {
            "available": False,
            "models": [],
            "capabilities": {},
            "error": "timeout",
        }
    except json.JSONDecodeError:
        return {
            "available": False,
            "models": [],
            "capabilities": {},
            "error": "invalid_json_response",
        }


def parse_model_probe_payload(raw_payload: Any) -> dict[str, Any]:
    models_raw = raw_payload.get("data") if isinstance(raw_payload, dict) else []
    capabilities: dict[str, Any] = {}
    model_ids: list[str] = []
    if isinstance(models_raw, list):
        for item in models_raw:
            if not isinstance(item, dict):
                continue
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            model_ids.append(model_id)
            capabilities[model_id] = describe_model_capabilities(item)
    sorted_ids = sorted(set(model_ids))
    return {
        "available": True,
        "models": sorted_ids,
        "capabilities": {model_id: capabilities[model_id] for model_id in sorted_ids},
        "error": "",
    }


def describe_model_capabilities(model_payload: dict[str, Any]) -> dict[str, Any]:
    model_id = str(model_payload.get("id") or "").strip()
    input_modalities = _collect_modalities(model_payload, prefix="input")
    output_modalities = _collect_modalities(model_payload, prefix="output")
    tool_types = _collect_tool_types(model_payload)

    multimodal = _detect_multimodal_signal(model_id, model_payload, input_modalities)
    web_search = _detect_web_search_signal(model_payload, tool_types)

    return {
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "tool_types": tool_types,
        "multimodal": multimodal,
        "web_search": web_search,
    }


def _detect_multimodal_signal(
    model_id: str,
    model_payload: dict[str, Any],
    input_modalities: list[str],
) -> dict[str, str]:
    explicit_flag = _read_bool_signal(
        model_payload,
        (
            ("supports_image_input",),
            ("image_input",),
            ("vision",),
            ("multimodal",),
            ("capabilities", "image_input"),
            ("capabilities", "supports_image_input"),
            ("capabilities", "vision"),
            ("capabilities", "multimodal"),
        ),
    )
    if explicit_flag is not None:
        return _capability_signal(
            explicit_flag,
            source="metadata",
            note="上游模型元数据直接给出了图像输入能力开关。",
        )

    if input_modalities:
        has_image_input = any(token in _IMAGE_MODALITY_TOKENS for token in input_modalities)
        return _capability_signal(
            has_image_input,
            source="metadata",
            note=f"根据 input_modalities={','.join(input_modalities)} 推断。",
        )

    if _matches_multimodal_name_hint(model_id):
        return _capability_signal(
            True,
            source="model_name",
            note="上游未返回明确模态字段，当前结果基于模型名规则推断。",
        )

    return _unknown_signal("未从上游模型元数据中读取到图像输入能力。")


def _detect_web_search_signal(model_payload: dict[str, Any], tool_types: list[str]) -> dict[str, str]:
    explicit_flag = _read_bool_signal(
        model_payload,
        (
            ("supports_web_search",),
            ("web_search",),
            ("capabilities", "web_search"),
            ("capabilities", "supports_web_search"),
            ("capabilities", "built_in_tools", "web_search"),
        ),
    )
    if explicit_flag is not None:
        return _capability_signal(
            explicit_flag,
            source="metadata",
            note="上游模型元数据直接给出了网络访问能力开关。",
        )

    if any(token in _WEB_SEARCH_TOOL_TOKENS for token in tool_types):
        return _capability_signal(
            True,
            source="metadata",
            note=f"根据 tool_types={','.join(tool_types)} 推断。",
        )

    return _unknown_signal("当前 `/models` 返回中没有明确的网络访问能力字段。")


def _collect_modalities(model_payload: dict[str, Any], *, prefix: str) -> list[str]:
    if prefix == "input":
        keys = ("input_modalities", "supported_input_modalities")
    else:
        keys = ("output_modalities", "supported_output_modalities")

    collected: list[str] = []
    for key in keys:
        collected.extend(_flatten_string_values(model_payload.get(key)))

    modalities = model_payload.get("modalities")
    if isinstance(modalities, dict):
        collected.extend(_flatten_string_values(modalities.get(prefix)))
        collected.extend(_flatten_string_values(modalities.get(f"{prefix}_modalities")))
    elif prefix == "input":
        collected.extend(_flatten_string_values(modalities))

    capabilities = model_payload.get("capabilities")
    if isinstance(capabilities, dict):
        for key in keys:
            collected.extend(_flatten_string_values(capabilities.get(key)))
        if prefix == "input":
            collected.extend(_flatten_string_values(capabilities.get("modalities")))

    return _unique_strings(collected)


def _collect_tool_types(model_payload: dict[str, Any]) -> list[str]:
    collected: list[str] = []
    for key in ("tool_types", "supported_tool_types", "supported_tools", "tools"):
        collected.extend(_flatten_tool_values(model_payload.get(key)))

    capabilities = model_payload.get("capabilities")
    if isinstance(capabilities, dict):
        for key in ("tool_types", "supported_tool_types", "supported_tools", "tools"):
            collected.extend(_flatten_tool_values(capabilities.get(key)))
        built_in_tools = capabilities.get("built_in_tools")
        if isinstance(built_in_tools, dict):
            for key, enabled in built_in_tools.items():
                if _coerce_bool(enabled):
                    collected.append(str(key))

    return _unique_strings(collected)


def _read_bool_signal(model_payload: dict[str, Any], paths: tuple[tuple[str, ...], ...]) -> bool | None:
    for path in paths:
        current: Any = model_payload
        for segment in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(segment)
        normalized = _coerce_bool(current)
        if normalized is not None:
            return normalized
    return None


def _flatten_string_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip().lower()
        return [normalized] if normalized else []
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_flatten_string_values(item))
        return items
    if isinstance(value, dict):
        items: list[str] = []
        for key in ("type", "name", "id", "modality"):
            items.extend(_flatten_string_values(value.get(key)))
        return items
    return []


def _flatten_tool_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        normalized = value.strip().lower()
        return [normalized] if normalized else []
    if isinstance(value, dict):
        items: list[str] = []
        for key in ("type", "name", "id"):
            items.extend(_flatten_string_values(value.get(key)))
        return items
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(_flatten_tool_values(item))
        return items
    return []


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "enabled", "available", "supported"}:
            return True
        if normalized in {"false", "0", "no", "disabled", "unavailable", "unsupported"}:
            return False
    return None


def _matches_multimodal_name_hint(model_id: str) -> bool:
    if not model_id:
        return False
    return any(pattern.search(model_id) for pattern in _MULTIMODAL_NAME_HINTS)


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _capability_signal(supported: bool, *, source: str, note: str) -> dict[str, str]:
    return {
        "status": "supported" if supported else "unsupported",
        "source": source,
        "note": note,
    }


def _unknown_signal(note: str) -> dict[str, str]:
    return {
        "status": "unknown",
        "source": "unavailable",
        "note": note,
    }
