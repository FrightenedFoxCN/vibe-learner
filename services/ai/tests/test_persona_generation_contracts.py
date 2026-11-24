"""Persona generation contracts and offline Persona/Scene transport policy."""

import json
import unittest
from unittest.mock import Mock, patch

from app.models import persona_generation
from app.services.provider_settings import RemoteSettingsProvider
from app.services.provider_transport import ModelRequestError
from tests.support.harness_contracts import assert_domain_contracts


class PersonaGenerationContractTests(unittest.TestCase):
    def test_schema_and_contract_identity_match_pre_refactor_baseline(self):
        assert_domain_contracts(
            self,
            persona_generation,
            reviewed_contracts={
                "PERSONA_POLICY_CONTRACT": {
                    "name": "PersonaGenerationHarnessPolicy",
                    "version": "persona-generation-harness-v2",
                },
            },
        )


class SettingWebSearchFallbackTests(unittest.TestCase):
    persona = {
        "summary": "Mentor",
        "relationship": "Tutor",
        "learner_address": "Learner",
        "cards": [
            {"title": "Role", "kind": "role", "label": "Role", "content": "Tutor"}
        ],
    }
    scene = {
        "schema_name": "scene-tree-proposal",
        "schema_version": "scene-tree-proposal-v1",
        "scene_name": "Library",
        "scene_summary": "Quiet room",
        "selected_path": [0],
        "scene_layers": [
            {
                "title": "Library",
                "scope_label": "Room",
                "summary": "Quiet room",
                "atmosphere": "Quiet",
                "rules": "Speak softly",
                "entrance": "Door",
            }
        ],
    }

    def test_only_explicit_compatibility_rejection_switches_to_chat_once(self):
        for status, code in (
            ("unknown", "unsupported_params"),
            ("400", "unsupported_params"),
            ("422", "failed:422:unsupported_params"),
        ):
            error = ModelRequestError(
                f"openai_setting_request_{code}",
                status_code=status,
                upstream_code="unsupported_params",
            )
            for feature, proposal in (("persona", self.persona), ("scene", self.scene)):
                with self.subTest(feature=feature, status=status):
                    chat = Mock(
                        return_value=(
                            {
                                "choices": [
                                    {"message": {"content": json.dumps(proposal)}}
                                ]
                            },
                            0,
                        )
                    )
                    with patch(
                        "app.services.provider_settings.record_model_recovery"
                    ) as recovery:
                        result = self.generate(feature, error, chat)
                    self.assertFalse(result["used_web_search"])
                    chat.assert_called_once()
                    payload = chat.call_args.args[0]
                    self.assertNotIn("tools", payload)
                    self.assertEqual(
                        payload["response_format"], {"type": "json_object"}
                    )
                    recovery.assert_called_once_with(
                        category="feature_fallback",
                        reason=str(error),
                        strategy="disable_web_search",
                        attempts=1,
                    )

    def test_non_compatibility_failures_propagate_without_chat(self):
        for code, status in (
            ("failed:401:invalid_api_key", "401"),
            ("failed:403:forbidden", "403"),
            ("rate_limit", "429"),
            ("timeout", ""),
            ("network_error", ""),
            ("failed:400:invalid_request_error", "400"),
            ("failed:422:validation_error", "422"),
            ("failed:500:server_error", "500"),
            # Upstream message heuristics can misclassify these as unsupported.
            ("unsupported_params", "401"),
            ("unsupported_params", "429"),
            ("unsupported_params", "500"),
        ):
            error = ModelRequestError(
                f"openai_setting_request_{code}", status_code=status
            )
            for feature in ("persona", "scene"):
                with self.subTest(feature=feature, code=code, status=status):
                    chat = Mock(side_effect=AssertionError("must not fall back"))
                    with self.assertRaises(ModelRequestError) as caught:
                        self.generate(feature, error, chat)
                    self.assertIs(caught.exception, error)
                    chat.assert_not_called()

    def test_a_failed_offline_request_does_not_repeat_the_feature_switch(self):
        rejected = ModelRequestError("openai_setting_request_unsupported_params")
        for feature in ("persona", "scene"):
            with self.subTest(feature=feature):
                chat = Mock(side_effect=rejected)
                with self.assertRaises(ModelRequestError) as caught:
                    self.generate(feature, rejected, chat)
                self.assertIs(caught.exception, rejected)
                chat.assert_called_once()

    def generate(self, feature, error, chat):
        response = Mock(side_effect=error)
        provider = RemoteSettingsProvider(
            setting_model="test-model",
            setting_temperature=0.2,
            setting_max_tokens=128,
            setting_web_search_enabled=True,
            request_chat=chat,
            request_response=response,
        )
        try:
            if feature == "persona":
                return provider.generate_persona_cards_from_keywords(
                    keywords="mentor", count=1
                )
            return provider.generate_scene_tree_from_keywords(
                keywords="library", layer_count=1
            )
        finally:
            response.assert_called_once()
            self.assertEqual(
                response.call_args.args[0]["tools"], [{"type": "web_search"}]
            )
