from __future__ import annotations

import unittest
from unittest.mock import patch

from app.models.domain import PersonaSlot
from app.services.model_provider import OpenAIModelProvider


class ModelProviderAuditTests(unittest.TestCase):
    def _provider(self) -> OpenAIModelProvider:
        return OpenAIModelProvider(
            api_key="test-key",
            base_url="http://127.0.0.1:9/v1",
            plan_model="plan-model",
            setting_model="setting-model",
        )

    def test_card_batch_top_level_types_fail_before_normalization(self) -> None:
        valid = {
            "summary": " Summary ", "relationship": " Friend ",
            "learner_address": " You ",
            "cards": [{"title": "Card", "kind": "custom", "label": "Label", "content": "Content"}],
        }
        for mode in ("text", "keywords", "web"):
            provider = self._provider()
            provider.setting_web_search_enabled = mode == "web"
            method = "_request_setting_json_response" if mode == "web" else "_request_setting_json_chat"
            def generate():
                if mode == "text":
                    return provider.generate_persona_cards_from_text(text="input", count=1)
                return provider.generate_persona_cards_from_keywords(keywords="input", count=1)
            for field in ("summary", "relationship", "learner_address"):
                for wrong in ({"bad": True}, ["bad"], 77, False, None):
                    with self.subTest(mode=mode, field=field, wrong=wrong):
                        with patch.object(provider, method, return_value={**valid, field: wrong}):
                            with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_payload"):
                                generate()
            with patch.object(provider, method, return_value=valid):
                self.assertEqual(generate()["summary"], "Summary")
            for invalid in ({k: v for k, v in valid.items() if k != "summary"}, {**valid, "used_model": "forged"}):
                with patch.object(provider, method, return_value=invalid):
                    with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_payload"):
                        generate()

    def test_persona_slot_model_types_are_rejected_before_domain_coercion(self) -> None:
        provider = self._provider()
        slot = PersonaSlot(
            kind="custom",
            label="语气",
            content="保持清晰",
            weight=50,
            locked=False,
            sort_order=0,
        )
        with patch.object(
            provider,
            "_request_setting_json_chat",
            return_value={
                "slot": {
                    "kind": "custom",
                    "label": "语气",
                    "content": "更清晰",
                    "weight": "90",
                    "locked": False,
                    "sort_order": 0,
                }
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_payload"):
                provider.assist_persona_slot(
                    name="导师",
                    summary="结构化教学",
                    slot=slot,
                    rewrite_strength=0.5,
                )

    def test_persona_cards_do_not_drop_malformed_items_and_continue(self) -> None:
        provider = self._provider()
        with patch.object(
            provider,
            "_request_setting_json_chat",
            return_value={
                "summary": "摘要",
                "relationship": "导师",
                "learner_address": "同学",
                "cards": [
                    {
                        "title": "卡片",
                        "kind": "custom",
                        "label": "标签",
                        "content": "内容",
                        "tags": ["有效"],
                    },
                    {
                        "title": 12,
                        "kind": "custom",
                        "label": "标签",
                        "content": "错误类型",
                    },
                ],
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_payload"):
                provider.generate_persona_cards_from_text(
                    text="输入文本",
                    count=None,
                )


if __name__ == "__main__":
    unittest.main()
