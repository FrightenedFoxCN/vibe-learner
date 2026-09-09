"""Aggregate provider wiring captures capability configuration at operation entry."""
import json
import unittest
from unittest.mock import Mock, patch

from app.services.model_provider import OpenAIModelProvider
from tests.support.study_chat_samples import study_persona, raw_chat_reply


class ProviderConfigurationTests(unittest.TestCase):
    def test_study_tool_policy_and_model_stay_stable_across_rounds(self):
        disabled = {"ask_fill_blank_question"}
        read_disabled = Mock(side_effect=lambda: disabled)
        provider = OpenAIModelProvider(api_key="test", base_url="https://example.invalid/v1",
            plan_model="initial-model", chat_disabled_tools_provider=read_disabled)
        calls = []

        def request(payload, **kwargs):
            calls.append((payload, kwargs))
            if len(calls) == 1:
                disabled.clear()
                provider.chat_model = "changed-model"
                provider.chat_max_tokens = 9999
                return {"choices": [{"finish_reason": "tool_calls", "message": {
                    "content": "", "tool_calls": [{"id": "call-question", "type": "function",
                        "function": {"name": "ask_multiple_choice_question", "arguments": json.dumps({
                            "topic": "basis", "difficulty": "easy", "option_count": 3,
                        })}}],
                }}]}, 1
            return raw_chat_reply(json.dumps({"text": "请回答题目。", "mood": "calm", "action": "point"})), 1

        with patch.object(provider, "_request_openai_chat_completion", side_effect=request):
            result = provider.generate_chat(persona=study_persona(), section_id="unit-1", message="quiz")
        self.assertIsNotNone(result.interactive_question)
        self.assertEqual(len(calls), 2)
        read_disabled.assert_called_once()
        for payload, kwargs in calls:
            self.assertEqual(payload["model"], "initial-model")
            self.assertEqual(kwargs["model"], "initial-model")
            self.assertEqual(payload["max_tokens"], 800)
            self.assertNotIn("ask_fill_blank_question", [tool["function"]["name"] for tool in payload["tools"]])

    def test_repair_captures_endpoint_credentials_timeout_and_sdk_callable(self):
        from app.services.provider_sdk import ProviderSDK
        calls = []
        provider = None

        def completion(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                provider.chat_base_url = "https://changed.invalid/v1"
                provider.chat_api_key = "changed-key"
                provider.timeout_seconds = 99
                provider.chat_model = "changed-model"
                provider.sdk.completion = Mock(side_effect=AssertionError("new SDK used during old operation"))
                return raw_chat_reply('{"mood":"calm"}')
            return raw_chat_reply('{"text":"完成","mood":"calm","action":"point"}')

        provider = OpenAIModelProvider(api_key="initial-key", base_url="https://initial.invalid/v1",
            plan_model="initial-model", timeout_seconds=3, chat_tools_enabled=False,
            sdk=ProviderSDK(completion=completion))
        reply = provider.generate_chat(persona=study_persona(), section_id="unit-1", message="explain")
        self.assertEqual(reply.text, "完成")
        self.assertEqual(len(calls), 2)
        for call in calls:
            self.assertEqual(call["api_key"], "initial-key")
            self.assertEqual(call["api_base"], "https://initial.invalid/v1")
            self.assertEqual(call["model"], "openai/initial-model")
            self.assertEqual(call["timeout"], 3)
        # A later operation adopts the new configuration rather than caching it forever.
        with self.assertRaisesRegex(RuntimeError, "openai_chat_request_failed"):
            provider.generate_chat(persona=study_persona(), section_id="unit-1", message="next")
        provider.sdk.completion.assert_called_once()
