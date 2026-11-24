from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from app.api.routers.system import check_openai_models
from app.models.api import RuntimeSettingsProbeRequest
from app.services.model_provider import OpenAIModelProvider
from app.services.provider_sdk import ProviderSDK

from app.services.runtime_model_probe import (
    parse_model_probe_payload,
    probe_openai_models,
)


class RuntimeProbeTest(TestCase):
    def test_invalid_directory_cannot_report_authentication_success(self):
        for payload in [None, {}, {"data": {}}, {"data": [{"id": 42}]}]:
            with self.subTest(payload=payload):
                result = parse_model_probe_payload(payload)
                self.assertFalse(result["available"])
                self.assertEqual(result["error"], "invalid_model_list_response")

    def test_empty_directory_is_valid_and_duplicate_model_ids_are_collapsed(self):
        self.assertTrue(parse_model_probe_payload({"data": []})["available"])
        result = parse_model_probe_payload({"data": [{"id": "synth"}, {"id": "synth"}]})
        self.assertEqual(result["models"], ["synth"])

    @patch("app.services.runtime_model_probe.urllib.request.urlopen")
    def test_invalid_encoding_and_then_valid_empty_directory(self, urlopen):
        reply = urlopen.return_value.__enter__.return_value
        reply.read.side_effect = [b"\xff", b'{"data": []}']
        args = {
            "api_key": "synthetic",
            "base_url": "https://example.invalid/v1",
            "timeout_seconds": 5,
        }
        self.assertFalse(probe_openai_models(**args)["available"])
        self.assertTrue(probe_openai_models(**args)["available"])
        self.assertEqual(urlopen.call_count, 2)


class RuntimeFeatureProbeTest(TestCase):
    def test_endpoint_keeps_directory_and_feature_evidence_independent(self):
        completion = Mock(return_value={"choices": []})
        responses = Mock(side_effect=AssertionError("probe must not execute Responses"))
        container = SimpleNamespace(
            runtime_settings_service=SimpleNamespace(
                effective_settings=lambda: SimpleNamespace(openai_timeout_seconds=5),
            )
        )
        payload = RuntimeSettingsProbeRequest(
            api_key="synthetic",
            base_url="https://example.invalid/v1",
            model="gpt-5-mini",
            features=["plan", "study", "persona", "scene"],
        )
        with (
            patch(
                "app.api.routers.system.probe_openai_models",
                return_value={
                    "available": False,
                    "models": [],
                    "capabilities": {},
                    "error": "http_404",
                },
            ),
            patch.object(
                ProviderSDK,
                "load",
                return_value=ProviderSDK(
                    completion=completion,
                    responses=responses,
                ),
            ),
        ):
            result = check_openai_models(payload, container=container)
        self.assertFalse(result.available)
        self.assertEqual(completion.call_count, 3)
        responses.assert_not_called()
        for call in completion.call_args_list[:2]:
            self.assertEqual(call.kwargs["tool_choice"], "auto")
            self.assertEqual(call.kwargs["tools"][0]["type"], "function")
        setting = completion.call_args_list[-1].kwargs
        self.assertNotIn("tools", setting)
        self.assertNotIn("temperature", setting)
        self.assertIn("max_completion_tokens", setting)
        self.assertEqual(setting["response_format"], {"type": "json_object"})
        persona = result.feature_readiness["persona"]
        self.assertEqual(persona, result.feature_readiness["scene"])
        self.assertEqual(persona.status, "ready")
        self.assertIn("JSON Object 参数（不联网）", persona.note)
        self.assertIn("未校验输出内容", persona.note)
        self.assertEqual(
            persona.parameter_adjustments,
            [
                "temperature_omitted",
                "max_tokens_to_max_completion_tokens",
            ],
        )

    def test_tavern_uses_owned_http_adapter_for_both_schema_attempts(self):
        class SchemaRejected(Exception):
            status_code = 422

        owned_chat = Mock(side_effect=[SchemaRejected(), {"choices": []}])
        completion = Mock(side_effect=AssertionError("wrong adapter"))
        provider = OpenAIModelProvider(
            api_key="synthetic",
            base_url="https://example.invalid/v1",
            plan_model="gpt-5-mini",
            sdk=ProviderSDK(completion=completion, cancellable_chat=owned_chat),
        )
        evidence = provider.probe_feature_readiness(["tavern"])["tavern"]
        self.assertEqual(evidence["status"], "ready")
        self.assertIn("兼容 HTTP Chat Completions", evidence["note"])
        self.assertIn("严格 JSON Schema 请求未通过", evidence["note"])
        self.assertIn("json_schema_to_json_object", evidence["parameter_adjustments"])
        self.assertEqual(owned_chat.call_count, 2)
        strict, fallback = [call.kwargs for call in owned_chat.call_args_list]
        self.assertEqual(strict["payload"]["response_format"]["type"], "json_schema")
        self.assertEqual(
            fallback["payload"]["response_format"], {"type": "json_object"}
        )
        self.assertIsNone(strict["should_continue"])
        self.assertIsNone(fallback["should_continue"])
        completion.assert_not_called()

    def test_tavern_reports_failure_after_schema_fallback_is_rate_limited(self):
        class SchemaRejected(Exception):
            status_code = 422

        class RateLimited(Exception):
            status_code = 429

        owned_chat = Mock(side_effect=[SchemaRejected(), RateLimited()])
        provider = OpenAIModelProvider(
            api_key="synthetic",
            base_url="https://example.invalid/v1",
            plan_model="test-model",
            sdk=ProviderSDK(cancellable_chat=owned_chat),
        )
        evidence = provider.probe_feature_readiness(["tavern"])["tavern"]
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(evidence["code"], "openai_chat_request_rate_limit")
        self.assertIn("已尝试 JSON Object 回退", evidence["note"])
        self.assertEqual(owned_chat.call_count, 2)

    def test_tavern_explicit_non_compatible_route_uses_litellm(self):
        completion = Mock(return_value={"choices": []})
        owned_chat = Mock(side_effect=AssertionError("wrong adapter"))
        provider = OpenAIModelProvider(
            api_key="synthetic",
            base_url="https://example.invalid/v1",
            plan_model="anthropic/test-model",
            sdk=ProviderSDK(completion=completion, cancellable_chat=owned_chat),
        )
        evidence = provider.probe_feature_readiness(["tavern"])["tavern"]
        completion.assert_called_once()
        owned_chat.assert_not_called()
        self.assertIn("LiteLLM Chat Completions", evidence["note"])
