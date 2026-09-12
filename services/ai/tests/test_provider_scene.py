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
        self.assertEqual(chat.call_count, 2)

    def test_strict_scene_payload_failure_is_repaired_before_projection(self):
        invalid = scene_proposal_payload()
        invalid["scene_layers"][0]["reuse_hint"] = None
        repaired = scene_proposal_payload()
        chat = Mock(side_effect=[setting_wire_reply(invalid), setting_wire_reply(repaired)])

        result = self.provider(request_chat=chat).generate_scene_tree_from_text(
            text="room", layer_count=1
        )

        self.assertEqual(chat.call_count, 2)
        self.assertTrue(result["scene_layers"][0]["reuse_hint"])
        retry_messages = chat.call_args_list[1].args[0]["messages"]
        self.assertIn("严格只输出一个 JSON 对象", retry_messages[-1]["content"])

    def test_projection_value_error_is_repaired_for_chat_and_responses(self):
        invalid = scene_proposal_payload()
        invalid["scene_layers"][0]["reusable_node_ref"] = "unresolved-node"
        repaired = scene_proposal_payload()

        with self.subTest(transport="chat"):
            chat = Mock(side_effect=[setting_wire_reply(invalid), setting_wire_reply(repaired)])
            result = self.provider(request_chat=chat).generate_scene_tree_from_text(
                text="room", layer_count=1
            )
            self.assertEqual(chat.call_count, 2)
            self.assertTrue(result["scene_layers"][0]["id"])

        with self.subTest(transport="responses"):
            responses = Mock(side_effect=[
                setting_wire_reply(invalid, responses=True),
                setting_wire_reply(repaired, responses=True),
            ])
            result = self.provider(request_response=responses).generate_scene_tree_from_keywords(
                keywords="room", layer_count=1
            )
            self.assertEqual(responses.call_count, 2)
            self.assertTrue(result["used_web_search"])
