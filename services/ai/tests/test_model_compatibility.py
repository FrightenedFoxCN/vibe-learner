from __future__ import annotations

import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.models.api import RuntimeSettingsProbeRequest
from app.services.model_provider import (
    ModelRequestError,
    OpenAIModelProvider,
    adapt_openai_compatible_payload,
)


class UnsupportedParamsError(Exception):
    pass


class ModelCompatibilityTests(unittest.TestCase):
    def build_provider(self, *, model: str = "gpt-5-mini") -> OpenAIModelProvider:
        return OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model=model,
            setting_model=model,
            chat_model=model,
            setting_web_search_enabled=False,
            timeout_seconds=3,
        )

    def test_reasoning_family_uses_explicit_parameter_adapter(self) -> None:
        original = {
            "model": "gpt-5-mini",
            "temperature": 0.4,
            "max_tokens": 96,
            "messages": [],
        }

        adapted, adjustments = adapt_openai_compatible_payload(
            original,
            model="openai/gpt-5-mini",
        )

        self.assertNotIn("temperature", adapted)
        self.assertNotIn("max_tokens", adapted)
        self.assertEqual(adapted["max_completion_tokens"], 96)
        self.assertEqual(
            adjustments,
            ["temperature_omitted", "max_tokens_to_max_completion_tokens"],
        )
        self.assertIn("temperature", original)
        self.assertIn("max_tokens", original)

    def test_non_reasoning_model_payload_is_unchanged(self) -> None:
        original = {
            "model": "gpt-4.1-mini",
            "temperature": 0.4,
            "max_tokens": 96,
        }

        adapted, adjustments = adapt_openai_compatible_payload(
            original,
            model="gpt-4.1-mini",
        )

        self.assertEqual(adapted, original)
        self.assertEqual(adjustments, [])

    def test_litellm_path_receives_adapted_reasoning_payload(self) -> None:
        provider = self.build_provider()
        with patch(
            "app.services.model_provider.litellm_completion",
            return_value={"choices": [{"message": {"content": "ok"}}]},
        ) as completion:
            provider._request_openai_chat_completion(
                {
                    "model": "gpt-5-mini",
                    "temperature": 0.4,
                    "max_tokens": 32,
                    "messages": [{"role": "user", "content": "probe"}],
                },
                request_kind="setting",
                model="gpt-5-mini",
            )

        request = completion.call_args.kwargs
        self.assertEqual(request["model"], "openai/gpt-5-mini")
        self.assertNotIn("temperature", request)
        self.assertNotIn("max_tokens", request)
        self.assertEqual(request["max_completion_tokens"], 32)

    def test_unsupported_parameters_get_typed_non_retryable_reason(self) -> None:
        provider = self.build_provider(model="gpt-4.1-mini")
        with patch(
            "app.services.model_provider.litellm_completion",
            side_effect=UnsupportedParamsError("Unsupported parameter: temperature"),
        ) as completion:
            with self.assertRaises(ModelRequestError) as caught:
                provider._request_openai_chat_completion(
                    {
                        "model": "gpt-4.1-mini",
                        "temperature": 0.4,
                        "messages": [{"role": "user", "content": "probe"}],
                    },
                    request_kind="setting",
                    model="gpt-4.1-mini",
                )

        self.assertEqual(str(caught.exception), "openai_setting_request_unsupported_params")
        self.assertEqual(caught.exception.upstream_code, "unsupported_params")
        self.assertEqual(caught.exception.attempts, 1)
        self.assertEqual(completion.call_count, 1)

    def test_feature_readiness_probes_current_paths_and_tavern_fallback(self) -> None:
        provider = self.build_provider()

        def fake_request(payload, *, request_kind, model):
            response_format = payload.get("response_format") or {}
            if response_format.get("type") == "json_schema":
                raise ModelRequestError(
                    "openai_chat_request_unsupported_params",
                    upstream_code="unsupported_params",
                )
            return ({"choices": [{"message": {"content": "ok"}}]}, 1)

        with patch.object(
            provider,
            "_request_openai_chat_completion",
            side_effect=fake_request,
        ) as request:
            result = provider.probe_feature_readiness(
                ["plan", "study", "persona", "scene", "tavern"]
            )

        self.assertEqual(request.call_count, 5)
        self.assertTrue(all(item["status"] == "ready" for item in result.values()))
        self.assertEqual(result["persona"], result["scene"])
        self.assertIn("temperature_omitted", result["plan"]["parameter_adjustments"])
        self.assertIn(
            "json_schema_to_json_object",
            result["tavern"]["parameter_adjustments"],
        )
        self.assertIn("回退路径可调用", result["tavern"]["note"])

    def test_feature_readiness_reports_shared_setting_failure(self) -> None:
        provider = self.build_provider(model="gpt-4.1-mini")
        error = ModelRequestError("openai_setting_request_unsupported_params")
        with patch.object(
            provider,
            "_request_openai_chat_completion",
            side_effect=error,
        ):
            result = provider.probe_feature_readiness(["persona", "scene"])

        self.assertEqual(result["persona"]["status"], "unsupported")
        self.assertEqual(result["persona"]["code"], "openai_setting_request_unsupported_params")
        self.assertEqual(result["persona"], result["scene"])

    def test_feature_probe_requires_a_model(self) -> None:
        with self.assertRaises(ValidationError):
            RuntimeSettingsProbeRequest.model_validate(
                {
                    "api_key": "test-key",
                    "base_url": "https://api.openai.test/v1",
                    "features": ["persona"],
                }
            )


if __name__ == "__main__":
    unittest.main()
