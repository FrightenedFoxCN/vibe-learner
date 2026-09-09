"""Shared, injectable provider transport policy; no model/SDK import required."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from app.core.logging import get_logger
from app.services.model_recovery import record_model_recovery

logger = get_logger("vibe_learner.provider_transport")

LITELLM_TRANSIENT_RETRY_COUNT = 2
LITELLM_TRANSIENT_RETRYABLE_STATUS_CODES = frozenset({"408", "409", "425", "500", "502", "503", "504"})


class ModelRequestError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        attempts: int = 1,
        status_code: str = "",
        upstream_code: str = "",
        upstream_message: str = "",
    ) -> None:
        super().__init__(code)
        self.attempts = max(1, attempts)
        self.status_code = status_code
        self.upstream_code = upstream_code
        self.upstream_message = upstream_message


@dataclass(frozen=True)
class ProviderTransport:
    timeout_seconds: int
    sdk: Any = None
    token_usage_service: Any = None
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.perf_counter
    record_recovery: Callable[..., Any] = record_model_recovery

    def execute(
        self,
        *,
        request_kind: str,
        model: str,
        invoke: Callable[[], Any],
    ) -> tuple[dict[str, Any], int]:
        started_at = self.clock()
        attempt = 0
        while True:
            attempt += 1
            try:
                raw_result = invoke()
                raw_payload = _normalize_litellm_payload(raw_result)
                elapsed_ms = int((self.clock() - started_at) * 1000)
                if attempt > 1:
                    self.record_recovery(
                        category="transport_retry",
                        reason="upstream_transient_error",
                        strategy="retry_same_payload",
                        attempts=attempt,
                    )
                    logger.info(
                        "model.%s.retry_recovered provider=litellm model=%s attempts=%s elapsed_ms=%s",
                        request_kind,
                        model,
                        attempt,
                        elapsed_ms,
                    )
                return raw_payload, elapsed_ms
            except Exception as exc:
                if _is_litellm_retryable_error(exc, sdk=self.sdk) and attempt <= LITELLM_TRANSIENT_RETRY_COUNT:
                    retry_delay_seconds = min(0.4 * attempt, 1.2)
                    status_code, error_code, error_message = _extract_litellm_exception_details(exc)
                    logger.warning(
                        "model.%s.retry provider=litellm model=%s attempt=%s max_retries=%s delay_ms=%s status=%s upstream_code=%s upstream_message=%s",
                        request_kind,
                        model,
                        attempt,
                        LITELLM_TRANSIENT_RETRY_COUNT,
                        int(retry_delay_seconds * 1000),
                        status_code or "unknown",
                        error_code or "unknown",
                        error_message,
                    )
                    self.sleep(retry_delay_seconds)
                    continue
                mapped_error = self.map_error(exc, request_kind=request_kind)
                if isinstance(mapped_error, ModelRequestError):
                    mapped_error.attempts = attempt
                raise mapped_error from exc

    def map_error(self, exc: Exception, *, request_kind: str) -> RuntimeError:
        if _is_litellm_unsupported_params_error(exc):
            status_code, error_code, error_message = _extract_litellm_exception_details(exc)
            logger.warning(
                "model.%s.unsupported_params provider=litellm status=%s upstream_code=%s",
                request_kind,
                status_code or "client_preflight",
                error_code or "unsupported_params",
            )
            return ModelRequestError(
                f"openai_{request_kind}_request_unsupported_params",
                status_code=status_code,
                upstream_code="unsupported_params",
                upstream_message=error_message,
            )
        if _is_litellm_rate_limit_error(exc, sdk=self.sdk):
            logger.exception("model.%s.rate_limit provider=litellm", request_kind)
            return ModelRequestError(f"openai_{request_kind}_request_rate_limit")
        if _is_litellm_timeout_error(exc, sdk=self.sdk):
            logger.exception(
                "model.%s.timeout provider=litellm timeout_seconds=%s",
                request_kind,
                self.timeout_seconds,
            )
            return ModelRequestError(f"openai_{request_kind}_request_timeout")
        if _is_litellm_network_error(exc, sdk=self.sdk):
            logger.exception("model.%s.network_error provider=litellm", request_kind)
            return ModelRequestError(f"openai_{request_kind}_request_network_error")

        status_code, error_code, error_message = _extract_litellm_exception_details(exc)
        logger.exception(
            "model.%s.http_error provider=litellm status=%s upstream_code=%s upstream_message=%s",
            request_kind,
            status_code,
            error_code,
            error_message,
        )
        return ModelRequestError(
            f"openai_{request_kind}_request_failed:{status_code}:{error_code or 'unknown'}",
            status_code=status_code,
            upstream_code=error_code,
            upstream_message=error_message,
        )

    def record_usage(
        self,
        raw_payload: dict[str, Any],
        *,
        feature: str,
        model: str,
        prompt_key: str = "prompt_tokens",
        completion_key: str = "completion_tokens",
    ) -> None:
        if self.token_usage_service is None:
            return
        usage = raw_payload.get("usage") if isinstance(raw_payload, dict) else None
        if not isinstance(usage, dict):
            return
        prompt_tokens = _coerce_int(usage.get(prompt_key) or usage.get("prompt_tokens"), default=0)
        completion_tokens = _coerce_int(usage.get(completion_key) or usage.get("completion_tokens"), default=0)
        total_tokens = _coerce_int(usage.get("total_tokens"), default=prompt_tokens + completion_tokens)
        try:
            self.token_usage_service.record(
                feature=feature,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        except Exception:
            logger.exception("token_usage.record failed feature=%s model=%s", feature, model)

def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_litellm_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result

    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped

    model_dump_json = getattr(result, "model_dump_json", None)
    if callable(model_dump_json):
        dumped_json = model_dump_json()
        if isinstance(dumped_json, str):
            parsed = _try_parse_json_dict(dumped_json)
            if parsed is not None:
                return parsed

    json_method = getattr(result, "json", None)
    if callable(json_method):
        raw_json = json_method()
        if isinstance(raw_json, str):
            parsed = _try_parse_json_dict(raw_json)
            if parsed is not None:
                return parsed

    raise RuntimeError("litellm_invalid_payload")


def _try_parse_json_dict(raw_value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_upstream_error(body: str) -> tuple[str, str]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return "", body[:200]
    if not isinstance(payload, dict):
        return "", body[:200]
    error = payload.get("error")
    if not isinstance(error, dict):
        return "", body[:200]
    return str(error.get("code", "")), str(error.get("message", ""))


def _extract_litellm_exception_details(exc: Exception) -> tuple[str, str, str]:
    status_code = _extract_litellm_status_code(exc)
    error_code = ""
    error_message = str(exc)

    body_candidates = [
        getattr(exc, "body", None),
        getattr(exc, "response_body", None),
    ]
    response = getattr(exc, "response", None)
    if response is not None:
        body_candidates.extend(
            [
                getattr(response, "text", None),
                getattr(response, "content", None),
                getattr(response, "body", None),
            ]
        )

    for candidate in body_candidates:
        error_code, error_message = _extract_litellm_error_from_body(candidate, fallback_message=error_message)
        if error_code:
            break

    if not error_code:
        error_code = str(
            getattr(exc, "code", "")
            or getattr(exc, "type", "")
            or type(exc).__name__
        ).strip()

    return status_code or "unknown", error_code or "unknown", error_message or str(exc)


def _extract_litellm_status_code(exc: Exception) -> str:
    for value in (
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(getattr(exc, "response", None), "status", None),
    ):
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str) and value.isdigit():
            return value
    return ""


def _extract_litellm_error_from_body(
    body: Any,
    *,
    fallback_message: str,
) -> tuple[str, str]:
    if body is None:
        return "", fallback_message
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="ignore")
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return (
                str(error.get("code") or error.get("type") or ""),
                str(error.get("message") or fallback_message),
            )
        return "", fallback_message
    if isinstance(body, str):
        error_code, error_message = _extract_upstream_error(body)
        return error_code, error_message or fallback_message
    return "", fallback_message


def _is_litellm_rate_limit_error(exc: Exception, *, sdk: Any = None) -> bool:
    rate_limit_cls = getattr(sdk, "RateLimitError", None) if sdk is not None else None
    if rate_limit_cls is not None and isinstance(exc, rate_limit_cls):
        return True
    return _extract_litellm_status_code(exc) == "429" or "ratelimit" in type(exc).__name__.lower()


def _is_litellm_unsupported_params_error(exc: Exception) -> bool:
    class_name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "unsupportedparams" in class_name or "unsupported parameter" in message


def _is_litellm_timeout_error(exc: Exception, *, sdk: Any = None) -> bool:
    timeout_cls = getattr(sdk, "Timeout", None) if sdk is not None else None
    if timeout_cls is not None and isinstance(exc, timeout_cls):
        return True
    class_name = type(exc).__name__.lower()
    message = str(exc).lower()
    return isinstance(exc, TimeoutError) or "timeout" in class_name or "timed out" in message


def _is_litellm_network_error(exc: Exception, *, sdk: Any = None) -> bool:
    connection_cls = getattr(sdk, "APIConnectionError", None) if sdk is not None else None
    if connection_cls is not None and isinstance(exc, connection_cls):
        return True
    class_name = type(exc).__name__.lower()
    message = str(exc).lower()
    return any(
        token in class_name or token in message
        for token in (
            "connection",
            "network",
            "dns",
            "refused",
        )
    )


def _is_litellm_retryable_error(exc: Exception, *, sdk: Any = None) -> bool:
    if _is_litellm_timeout_error(exc, sdk=sdk) or _is_litellm_network_error(exc, sdk=sdk):
        return True
    status_code = _extract_litellm_status_code(exc)
    return status_code in LITELLM_TRANSIENT_RETRYABLE_STATUS_CODES
