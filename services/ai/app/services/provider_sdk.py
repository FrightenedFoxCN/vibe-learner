"""Injected LiteLLM request adaptation with immutable operation endpoints."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Callable

from app.core.logging import get_logger
from app.services.provider_transport import ProviderTransport

REASONING_CHAT_MODEL_RE = re.compile(
    r"^(?:gpt-5(?:[.-]|$)|o[134](?:[.-]|$))",
    re.IGNORECASE,
)


logger = get_logger("vibe_learner.model_provider")


@dataclass
class ProviderSDK:
    """Instance-owned SDK dependencies; callable references are captured per operation."""

    completion: Callable[..., Any] | None = None
    responses: Callable[..., Any] | None = None
    embedding: Callable[..., Any] | None = None
    error_types: Any = None

    @classmethod
    def load(cls) -> ProviderSDK:
        try:
            import litellm
            from litellm import completion, responses, embedding
        except ImportError:
            return cls()
        return cls(completion, responses, embedding, litellm)


@dataclass(frozen=True)
class ProviderRequestAdapter:
    api_key: str = field(repr=False)
    base_url: str
    plan_api_key: str = field(repr=False)
    plan_base_url: str
    setting_api_key: str = field(repr=False)
    setting_base_url: str
    chat_api_key: str = field(repr=False)
    chat_base_url: str
    timeout_seconds: int
    completion: Callable[..., Any] | None
    responses: Callable[..., Any] | None
    embedding: Callable[..., Any] | None
    providers: frozenset[str]
    transport: ProviderTransport

    def request_chat_completion(
        self,
        payload: dict[str, Any],
        *,
        request_kind: str,
        model: str,
    ) -> tuple[dict[str, Any], int]:
        request_base_url, request_api_key = self._resolve_request_endpoint(request_kind)
        resolved_payload = self._normalize_litellm_payload_model(
            payload,
            api_base=request_base_url,
        )
        tools_enabled = "tools" in payload
        tool_round = len(
            [message for message in resolved_payload.get("messages", []) if message.get("role") == "tool"]
        )
        logger.info(
            "model.%s.request provider=litellm model=%s tool_round=%s tools_enabled=%s",
            request_kind,
            str(resolved_payload.get("model") or model),
            tool_round,
            tools_enabled,
        )
        self._require_litellm_sdk(self.completion, feature="completion")
        raw_payload, elapsed_ms = self._execute_litellm_request(
            request_kind=request_kind,
            model=model,
            invoke=lambda: self.completion(
                **resolved_payload,
                **self._build_litellm_request_kwargs(
                    api_base=request_base_url,
                    api_key=request_api_key,
                    model=str(resolved_payload.get("model") or model),
                ),
            ),
        )
        self._record_token_usage(raw_payload, feature=request_kind, model=model)
        return raw_payload, elapsed_ms


    def request_response(
        self,
        payload: dict[str, Any],
        *,
        request_kind: str,
        model: str,
    ) -> tuple[dict[str, Any], int]:
        request_base_url, request_api_key = self._resolve_request_endpoint(request_kind)
        resolved_payload = self._normalize_litellm_payload_model(
            payload,
            api_base=request_base_url,
        )
        if "input" not in resolved_payload and "messages" in resolved_payload:
            resolved_payload["input"] = resolved_payload.pop("messages")
        logger.info(
            "model.%s.responses.request provider=litellm model=%s tools_enabled=%s",
            request_kind,
            str(resolved_payload.get("model") or model),
            bool(resolved_payload.get("tools")),
        )
        self._require_litellm_sdk(self.responses, feature="responses")
        raw_payload, elapsed_ms = self._execute_litellm_request(
            request_kind=request_kind,
            model=model,
            invoke=lambda: self.responses(
                **resolved_payload,
                **self._build_litellm_request_kwargs(
                    api_base=request_base_url,
                    api_key=request_api_key,
                    model=str(resolved_payload.get("model") or model),
                ),
            ),
        )
        self._record_token_usage_responses(raw_payload, feature=request_kind, model=model)
        return raw_payload, elapsed_ms


    def request_embeddings(
        self,
        payload: dict[str, Any],
        *,
        model: str,
    ) -> tuple[dict[str, Any], int]:
        request_base_url, request_api_key = self._resolve_request_endpoint("chat")
        resolved_payload = self._normalize_litellm_payload_model(
            payload,
            api_base=request_base_url,
        )
        self._require_litellm_sdk(self.embedding, feature="embedding")
        raw_payload, elapsed_ms = self._execute_litellm_request(
            request_kind="embedding",
            model=model,
            invoke=lambda: self.embedding(
                **resolved_payload,
                **self._build_litellm_request_kwargs(
                    api_base=request_base_url,
                    api_key=request_api_key,
                    model=str(resolved_payload.get("model") or model),
                ),
            ),
        )
        logger.info("model.embedding.request provider=litellm model=%s elapsed_ms=%s", model, elapsed_ms)
        self._record_token_usage(raw_payload, feature="embedding", model=model)
        return raw_payload, elapsed_ms


    def _record_token_usage(
        self,
        raw_payload: dict[str, Any],
        *,
        feature: str,
        model: str,
        prompt_key: str = "prompt_tokens",
        completion_key: str = "completion_tokens",
    ) -> None:
        return self.transport.record_usage(raw_payload, feature=feature, model=model, prompt_key=prompt_key, completion_key=completion_key)


    def _record_token_usage_responses(self, raw_payload: dict[str, Any], *, feature: str, model: str) -> None:
        self._record_token_usage(
            raw_payload,
            feature=feature,
            model=model,
            prompt_key="input_tokens",
            completion_key="output_tokens",
        )


    def _resolve_request_endpoint(self, request_kind: str) -> tuple[str, str]:
        if request_kind == "plan":
            return self.plan_base_url, self.plan_api_key
        if request_kind == "setting":
            return self.setting_base_url, self.setting_api_key
        if request_kind == "chat":
            return self.chat_base_url, self.chat_api_key
        return self.base_url, self.api_key


    def _require_litellm_sdk(self, client: Any, *, feature: str) -> None:
        if client is None:
            raise RuntimeError(f"litellm_sdk_not_installed:{feature}")


    def _build_litellm_request_kwargs(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "timeout": self.timeout_seconds,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key
        forced_provider = _infer_openai_compatible_provider(model=model, api_base=api_base, providers=self.providers)
        if forced_provider:
            kwargs["custom_llm_provider"] = forced_provider
        return kwargs


    def _normalize_litellm_payload_model(
        self,
        payload: dict[str, Any],
        *,
        api_base: str,
    ) -> dict[str, Any]:
        resolved_payload = dict(payload)
        raw_model = str(resolved_payload.get("model") or "").strip()
        resolved_payload["model"] = _normalize_litellm_model_name(
            model=raw_model,
            api_base=api_base,
            providers=self.providers,
        )
        adapted_payload, adjustments = adapt_openai_compatible_payload(
            resolved_payload,
            model=str(resolved_payload["model"]),
        )
        if adjustments:
            logger.info(
                "model.request.compatibility model=%s adjustments=%s",
                raw_model,
                ",".join(adjustments),
            )
        return adapted_payload


    def _map_litellm_request_error(self, exc: Exception, *, request_kind: str) -> RuntimeError:
        return self.transport.map_error(exc, request_kind=request_kind)


    def _execute_litellm_request(
        self,
        *,
        request_kind: str,
        model: str,
        invoke: Callable[[], Any],
    ) -> tuple[dict[str, Any], int]:
        return self.transport.execute(request_kind=request_kind, model=model, invoke=invoke)



def adapt_openai_compatible_payload(
    payload: dict[str, Any],
    *,
    model: str,
) -> tuple[dict[str, Any], list[str]]:
    """Apply explicit model-family request rules without global parameter dropping."""
    adapted = dict(payload)
    adjustments: list[str] = []
    model_id = _bare_model_id(model)
    if REASONING_CHAT_MODEL_RE.match(model_id):
        if "temperature" in adapted:
            adapted.pop("temperature", None)
            adjustments.append("temperature_omitted")
        if "max_tokens" in adapted and "max_completion_tokens" not in adapted:
            adapted["max_completion_tokens"] = adapted.pop("max_tokens")
            adjustments.append("max_tokens_to_max_completion_tokens")
    return adapted, adjustments



def _bare_model_id(model: str) -> str:
    normalized = model.strip()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized



def _normalize_litellm_model_name(*, model: str, api_base: str, providers: frozenset[str]) -> str:
    normalized = model.strip()
    if not normalized:
        return normalized
    if _litellm_model_has_provider_prefix(normalized, providers):
        return normalized
    if _infer_openai_compatible_provider(model=normalized, api_base=api_base, providers=providers):
        return f"openai/{normalized}"
    return normalized



def _infer_openai_compatible_provider(*, model: str, api_base: str, providers: frozenset[str]) -> str | None:
    if not model.strip():
        return None
    if _litellm_model_has_provider_prefix(model, providers):
        return None
    normalized_base = api_base.rstrip("/")
    if not normalized_base:
        return None
    if normalized_base == "https://api.openai.com/v1":
        return None
    return "openai"



def _litellm_model_has_provider_prefix(model: str, providers: frozenset[str]) -> bool:
    if "/" not in model:
        return False
    provider = model.split("/", 1)[0].strip().lower()
    if not provider:
        return False
    return provider in providers



def _known_litellm_providers(sdk: Any) -> set[str]:
    if sdk is not None:
        providers = getattr(sdk, "provider_list", None)
        if providers:
            normalized = {
                str(getattr(provider, "value", provider)).strip().lower()
                for provider in providers
            }
            return {provider for provider in normalized if provider}
    return {
        "openai",
        "azure",
        "anthropic",
        "gemini",
        "vertex_ai",
        "vertex_ai_beta",
        "openrouter",
        "ollama",
        "huggingface",
        "bedrock",
        "xai",
        "custom_openai",
        "openai_like",
        "text-completion-openai",
    }

