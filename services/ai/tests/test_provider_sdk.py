"""SDK adapter protocol tests do not import LiteLLM or initialize the application."""
import subprocess
import sys
import unittest
from unittest.mock import Mock

from app.services.provider_sdk import ProviderRequestAdapter
from app.services.provider_transport import ProviderTransport


class ProviderSDKTests(unittest.TestCase):
    def adapter(self, **overrides):
        config = dict(api_key="base-key", base_url="https://base.invalid/v1",
            plan_api_key="plan-key", plan_base_url="https://plan.invalid/v1",
            setting_api_key="setting-key", setting_base_url="https://setting.invalid/v1",
            chat_api_key="chat-key", chat_base_url="https://chat.invalid/v1",
            timeout_seconds=7, completion=None, responses=None, embedding=None,
            providers=frozenset({"openai", "anthropic"}), transport=ProviderTransport(timeout_seconds=7))
        return ProviderRequestAdapter(**{**config, **overrides})

    def test_adapter_import_does_not_load_sdk_or_provider(self):
        result = subprocess.run([sys.executable, "-c", '''
import sys
from app.services.provider_sdk import ProviderSDK, ProviderRequestAdapter
assert "litellm" not in sys.modules
assert "app.services.model_provider" not in sys.modules
'''], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_completion_routes_endpoint_and_adapts_model_parameters(self):
        for kind in ("plan", "setting", "chat"):
            with self.subTest(kind=kind):
                completion = Mock(return_value={"choices": []})
                payload = {"model": "gpt-5-mini", "messages": [], "temperature": 0.4, "max_tokens": 32}
                self.adapter(completion=completion).request_chat_completion(payload, request_kind=kind, model="gpt-5-mini")
                call = completion.call_args.kwargs
                self.assertEqual(call["api_base"], f"https://{kind}.invalid/v1")
                self.assertEqual(call["api_key"], f"{kind}-key")
                self.assertEqual(call["timeout"], 7)
                self.assertEqual(call["model"], "openai/gpt-5-mini")
                self.assertEqual(call["max_completion_tokens"], 32)
                self.assertNotIn("temperature", call)
                self.assertIn("temperature", payload)

    def test_responses_converts_messages_and_records_response_usage(self):
        usage = Mock()
        response = Mock(return_value={"output_text": "ok", "usage": {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}})
        adapter = self.adapter(responses=response, transport=ProviderTransport(timeout_seconds=7, token_usage_service=usage))
        adapter.request_response({"model": "gpt-4.1", "messages": [{"role": "user", "content": "x"}]}, request_kind="setting", model="gpt-4.1")
        self.assertEqual(response.call_args.kwargs["input"], [{"role": "user", "content": "x"}])
        self.assertNotIn("messages", response.call_args.kwargs)
        usage.record.assert_called_once()
        self.assertEqual(usage.record.call_args.kwargs["prompt_tokens"], 2)
        self.assertEqual(usage.record.call_args.kwargs["completion_tokens"], 3)

    def test_embedding_uses_chat_endpoint_and_preserves_known_provider_prefix(self):
        embedding = Mock(return_value={"data": []})
        self.adapter(embedding=embedding).request_embeddings({"model": "anthropic/test", "input": ["x"]}, model="anthropic/test")
        call = embedding.call_args.kwargs
        self.assertEqual(call["api_base"], "https://chat.invalid/v1")
        self.assertEqual(call["api_key"], "chat-key")
        self.assertEqual(call["model"], "anthropic/test")

    def test_missing_sdk_fails_without_attempt_or_usage(self):
        transport = Mock()
        with self.assertRaisesRegex(RuntimeError, "litellm_sdk_not_installed:completion"):
            self.adapter(transport=transport).request_chat_completion({"model": "test"}, request_kind="chat", model="test")
        transport.execute.assert_not_called()
        transport.record_usage.assert_not_called()
