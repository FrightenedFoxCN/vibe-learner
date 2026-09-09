import unittest
from unittest.mock import patch

from app.models.domain import PersonaSlot
from app.services.model_provider import OpenAIModelProvider


class PersonaSlotRewriteTests(unittest.TestCase):
    def test_rewrite_preserves_user_slot_controls_when_model_omits_or_changes_them(self):
        provider = OpenAIModelProvider(
            api_key="test-key", base_url="https://example.test/v1",
            plan_model="test", setting_model="test", timeout_seconds=3,
        )
        original = PersonaSlot(
            kind="teaching_method", label="Method", content="Ask one question.",
            weight=73, locked=False, sort_order=20,
        )
        for controls in ({}, {"weight": 1.0, "locked": True, "sort_order": 0}):
            with self.subTest(controls=controls), patch.object(
                provider, "_request_setting_json_chat", return_value={"slot": {
                    "kind": "unexpected_kind", "label": "Evidence method",
                    "content": "Ask one question and check the observation.", **controls,
                }},
            ):
                result = provider.assist_persona_slot(
                    name="Mira", summary="Astronomy tutor", slot=original,
                    rewrite_strength=0.3,
                )["slot"]
                self.assertEqual(result["content"], "Ask one question and check the observation.")
                self.assertEqual(result["label"], "Evidence method")
                for field in ("kind", "weight", "locked", "sort_order"):
                    self.assertEqual(result[field], getattr(original, field))

