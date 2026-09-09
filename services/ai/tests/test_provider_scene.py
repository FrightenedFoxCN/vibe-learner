"""Scene model contracts and truthful web fallback without persistence or SDK."""
import unittest
from unittest.mock import Mock

from app.services.provider_settings import RemoteSettingsProvider
from tests.support.provider_payloads import setting_wire_reply
from tests.support.scene_samples import scene_proposal_payload


class SceneProviderTests(unittest.TestCase):
    def provider(self, **overrides):
        config = dict(setting_model="setting", setting_temperature=0.4, setting_max_tokens=900,
                      setting_web_search_enabled=True, request_chat=Mock(), request_response=Mock())
        return RemoteSettingsProvider(**{**config, **overrides})

    def test_responses_search_projects_server_identity_and_reports_used_transport(self):
        request = Mock(return_value=setting_wire_reply(scene_proposal_payload(), responses=True))
        result = self.provider(request_response=request).generate_scene_tree_from_keywords(keywords="room", layer_count=1)
        self.assertTrue(result["used_web_search"])
        self.assertEqual(result["used_model"], "setting")
        self.assertTrue(result["scene_layers"][0]["id"].startswith("scene-layer-"))
        self.assertEqual(request.call_args.args[0]["tools"], [{"type": "web_search"}])

    def test_unsupported_search_falls_back_and_reports_no_search(self):
        response = Mock(side_effect=RuntimeError("openai_setting_request_failed:400:unsupported"))
        chat = Mock(return_value=setting_wire_reply(scene_proposal_payload()))
        result = self.provider(request_chat=chat, request_response=response).generate_scene_tree_from_keywords(keywords="room", layer_count=1)
        self.assertFalse(result["used_web_search"])
        self.assertEqual(response.call_count, 1)
        self.assertEqual(chat.call_count, 1)

    def test_model_owned_scene_cannot_forge_committed_identity(self):
        proposal = scene_proposal_payload()
        proposal["scene_layers"][0]["id"] = "forged"
        chat = Mock(return_value=setting_wire_reply(proposal))
        with self.assertRaisesRegex(RuntimeError, "extra_forbidden"):
            self.provider(request_chat=chat).generate_scene_tree_from_text(text="room", layer_count=1)
        self.assertEqual(chat.call_count, 1)
