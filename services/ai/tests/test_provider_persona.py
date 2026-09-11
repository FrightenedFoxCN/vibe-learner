"""Persona generation contracts run without API, database, or SDK setup."""
import unittest
from unittest.mock import Mock, patch

from app.services.provider_settings import RemoteSettingsProvider
from tests.support.provider_payloads import setting_wire_reply


class PersonaProviderTests(unittest.TestCase):
    def provider(self, **overrides):
        config = dict(setting_model="setting", setting_temperature=0.4, setting_max_tokens=900,
                      setting_web_search_enabled=False, request_chat=Mock(), request_response=Mock())
        return RemoteSettingsProvider(**{**config, **overrides})

    def test_openai_persona_card_count_invariant_accepts_exact_count(self) -> None:
        parsed = {'summary': '结构化导师', 'relationship': '导师', 'learner_address': '同学', 'cards': [{'title': f'卡片 {index + 1}', 'kind': 'thinking_style', 'label': '思维风格', 'content': f'内容 {index + 1}'} for index in range(2)]}
        request = Mock(return_value=setting_wire_reply(parsed, responses=False))
        provider = self.provider(request_chat=request)
        result = provider.generate_persona_cards_from_keywords(keywords='结构化导师', count=2)
        self.assertEqual(len(result['cards']), 2)
        prompt_payload = request.call_args.args[0]
        prompt_text = '\n'.join((str(message['content']) for message in prompt_payload['messages']))
        self.assertIn('card_count_hint: 2', prompt_text)
        self.assertIn('`cards` 必须恰好生成该数量', prompt_text)

    def test_openai_persona_card_count_invariant_rejects_under_and_over_generation(self) -> None:
        for actual_count in (1, 3):
            parsed = {'summary': '结构化导师', 'relationship': '导师', 'learner_address': '同学', 'cards': [{'title': f'卡片 {index + 1}', 'kind': 'thinking_style', 'label': '思维风格', 'content': f'内容 {index + 1}'} for index in range(actual_count)]}
            with self.subTest(actual_count=actual_count):
                request = Mock(return_value=setting_wire_reply(parsed, responses=False))
                provider = self.provider(request_chat=request)
                with self.assertRaisesRegex(RuntimeError, '^setting_persona_card_count_mismatch$'):
                    provider.generate_persona_cards_from_keywords(keywords='结构化导师', count=2)

    def test_invalid_json_is_retried_only_once(self):
        request = Mock(return_value=({"choices": [{"message": {"content": "{"}}]}, 1))
        with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_json"):
            self.provider(request_chat=request).generate_persona_cards_from_text(text="mentor", count=1)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args.args[0]["temperature"], 0.2)
        self.assertLessEqual(request.call_args.args[0]["max_tokens"], 6400)

    def test_missing_nested_kind_repairs_within_the_existing_chat_budget(self):
        # MiniMax live samples stopped normally but omitted kind on every card.
        invalid = {"summary": "同行者", "relationship": "朋友", "learner_address": "阿岚",
                   "cards": [{"title": "思维", "label": "思维方式", "content": "先核对事实"}]}
        valid = {**invalid, "cards": [{**invalid["cards"][0], "kind": "thinking_style"}]}
        for mode in ("keywords", "long_text"):
            with self.subTest(mode=mode):
                request = Mock(side_effect=[setting_wire_reply(invalid), setting_wire_reply(valid)])
                with patch("app.services.provider_settings.record_model_recovery") as recovery:
                    provider = self.provider(request_chat=request)
                    result = (provider.generate_persona_cards_from_keywords(keywords="朋友", count=1)
                              if mode == "keywords" else provider.generate_persona_cards_from_text(text="朋友", count=1))
                self.assertEqual(result["cards"][0]["kind"], "thinking_style")
                self.assertEqual(request.call_count, 2)
                self.assertIn("kind", request.call_args.args[0]["messages"][-1]["content"])
                recovery.assert_called_once()
                self.assertEqual(recovery.call_args.kwargs["reason"], "setting_model_invalid_payload")

    def test_schema_failure_after_json_retry_does_not_get_a_third_attempt(self):
        invalid = {"summary": "同行者", "relationship": "朋友", "learner_address": "阿岚",
                   "cards": [{"title": "思维", "label": "思维方式", "content": "先核对事实"}]}
        request = Mock(side_effect=[({"choices": [{"message": {"content": "{"}}]}, 1), setting_wire_reply(invalid)])
        with patch("app.services.provider_settings.record_model_recovery") as recovery:
            with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_payload"):
                self.provider(request_chat=request).generate_persona_cards_from_text(text="朋友", count=1)
        self.assertEqual(request.call_count, 2)
        recovery.assert_not_called()

    def test_responses_repairs_nested_schema_and_retains_web_search(self):
        invalid = {"summary": "同行者", "relationship": "朋友", "learner_address": "阿岚",
                   "cards": [{"title": "思维", "label": "思维方式", "content": "先核对事实"}]}
        valid = {**invalid, "cards": [{**invalid["cards"][0], "kind": "thinking_style"}]}
        request = Mock(side_effect=[setting_wire_reply(invalid, responses=True), setting_wire_reply(valid, responses=True)])
        chat = Mock(side_effect=AssertionError("schema failure must not switch transport"))
        result = self.provider(request_response=request, request_chat=chat, setting_web_search_enabled=True).generate_persona_cards_from_keywords(keywords="朋友", count=1)
        self.assertEqual(request.call_count, 2)
        self.assertTrue(result["used_web_search"])
        chat.assert_not_called()

    def test_repeated_schema_failure_remains_fail_closed_in_both_transports(self):
        invalid = {"summary": "同行者", "relationship": "朋友", "learner_address": "阿岚",
                   "cards": [{"title": "思维", "kind": "thinking_style", "label": "思维方式", "content": "核对事实", "id": "model-forged"}]}
        for responses in (False, True):
            with self.subTest(responses=responses):
                request = Mock(return_value=setting_wire_reply(invalid, responses=responses))
                provider = self.provider(request_chat=request, request_response=request, setting_web_search_enabled=responses)
                with patch("app.services.provider_settings.record_model_recovery") as recovery:
                    with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_payload"):
                        provider.generate_persona_cards_from_keywords(keywords="朋友", count=1)
                self.assertEqual(request.call_count, 2)
                recovery.assert_not_called()
