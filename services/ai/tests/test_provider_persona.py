"""Persona generation contracts run without API, database, or SDK setup."""
import unittest
from unittest.mock import Mock

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
