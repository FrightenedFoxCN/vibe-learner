"""Tavern model contract and bounded recovery, with no database/API fixture."""
import unittest
from unittest.mock import Mock

from app.services.provider_tavern import RemoteTavernProvider
from app.services.provider_transport import ModelRequestError
from tests.support.study_chat_samples import study_persona


def actor_payload(text="你好。"):
    import json
    return {"choices": [{"message": {"content": json.dumps({
        "text": text, "mood": "calm", "action": "点头", "speech_style": "warm",
        "delivery_cue": "自然回应", "state_commentary": "保持身份",
        "addressed_participant_ids": [],
    }, ensure_ascii=False)}}]}


class TavernProviderTests(unittest.TestCase):
    def generate(self, request, **kwargs):
        return RemoteTavernProvider("test-model", 0.35, 800, request).generate_tavern_actor_reply(
            persona=study_persona(), participants=[], scene_profile=None,
            recent_messages=[], user_message="你好", guidance="", allowed_target_ids=[], **kwargs,
        )

    def test_strict_json_schema_transport(self):
        request = Mock(return_value=(actor_payload(), 1))
        self.assertEqual(self.generate(request).text, "你好。")
        request.assert_called_once()
        response_format = request.call_args.args[0]["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        schema = response_format["json_schema"]["schema"]
        self.assertEqual(set(schema["required"]), set(schema["properties"]))

    def test_schema_rejection_falls_back_once_to_json_object(self):
        request = Mock(side_effect=[ModelRequestError(
            "openai_chat_request_unsupported_params", upstream_code="unsupported_params",
        ), (actor_payload("回退成功。"), 1)])
        self.assertEqual(self.generate(request).text, "回退成功。")
        self.assertEqual(request.call_count, 2)
        self.assertEqual([c.args[0]["response_format"]["type"] for c in request.call_args_list],
                         ["json_schema", "json_object"])

    def test_schema_fallback_and_semantic_repair_have_three_call_ceiling(self):
        request = Mock(side_effect=[
            ModelRequestError("unsupported", status_code="422"),
            ({"choices": []}, 1), ({"choices": []}, 1),
        ])
        with self.assertRaisesRegex(RuntimeError, "tavern_actor_invalid_payload"):
            self.generate(request)
        self.assertEqual(request.call_count, 3)
        final_payload = request.call_args.args[0]
        self.assertEqual(final_payload["response_format"], {"type": "json_object"})
        self.assertEqual(final_payload["temperature"], 0.2)
        self.assertEqual(final_payload["max_tokens"], 900)

    def test_cancellation_fences_initial_call_fallback_and_semantic_repair(self):
        cases = [([], [False], 0),
                 ([ModelRequestError("unsupported", status_code="400")], [True, False], 1),
                 ([({"choices": []}, 1)], [True, False], 1)]
        for responses, allowed, count in cases:
            with self.subTest(count=count, responses=responses):
                request = Mock(side_effect=responses)
                with self.assertRaisesRegex(RuntimeError, "tavern_actor_generation_canceled"):
                    self.generate(request, should_continue=Mock(side_effect=allowed))
                self.assertEqual(request.call_count, count)

    def test_unrelated_transport_failure_is_not_semantically_retried(self):
        request = Mock(side_effect=ModelRequestError("openai_chat_request_timeout"))
        with self.assertRaisesRegex(ModelRequestError, "openai_chat_request_timeout"):
            self.generate(request)
        self.assertEqual(request.call_count, 1)
