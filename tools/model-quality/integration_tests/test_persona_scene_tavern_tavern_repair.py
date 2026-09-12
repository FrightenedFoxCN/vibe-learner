import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from types import SimpleNamespace

from vibe_learner.persona_scene_tavern_tavern_repair import run_sample


def actor_wire(text):
    return {
        "choices": [{"message": {"content": json.dumps({
            "text": text,
            "mood": "calm",
            "action": "idle",
            "speech_style": "简洁",
            "delivery_cue": "",
            "state_commentary": "",
            "addressed_participant_ids": [],
        }, ensure_ascii=False)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


class TavernExactRepairTests(unittest.TestCase):
    def spec(self, initial_text):
        source = json.dumps({
            "persona_input": {"input_text": "称季研究员"},
            "scene_input": {"input_text": "只有接收格"},
            "user_message": "先逐字回答指定句",
        }, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return source, {
            "canonical_source": source,
            "source_fidelity_constraints": {
                "learner_address_exact": "季研究员",
                "scene_direct_children_exact": [],
                "tavern_prefix_exact": "这里没有第四个区域。",
                "credential_like_output_forbidden": False,
            },
            "generated": {
                "persona": {"learner_address": "季研究员"},
                "scene": {"scene_layers": []},
            },
            "initial_tavern_message": {
                "content": initial_text,
                "emotion": "calm",
                "action": "idle",
                "speech_style": "简洁",
                "addressed_participant_ids": [],
            },
        }

    def invoke(self, initial_text, repaired_text, *, raw_response=None):
        source, spec = self.spec(initial_text)
        request = Mock(return_value=raw_response or actor_wire(repaired_text))
        transport = SimpleNamespace(
            campaign=SimpleNamespace(
                model="MiniMax-M3",
                transport="fake",
                max_output_tokens=2048,
            ),
            request=request,
        )
        case = SimpleNamespace(
            id="case-1",
            source=source,
            gold=json.dumps(spec, ensure_ascii=False),
            rubric="persona-scene-tavern-exact-repair-v1",
        )
        variant = SimpleNamespace(id="conditional-exact-repair")
        with TemporaryDirectory() as directory:
            result = run_sample(
                SimpleNamespace(transport=transport, storage=Path(directory)),
                case,
                variant,
            )
            evidence = json.loads(
                (Path(directory) / "tavern-exact-repair-evidence.json").read_text()
            )
        return result, request, evidence

    def test_exact_pass_reuses_frozen_reply_without_wire(self):
        result, request, _ = self.invoke(
            "这里没有第四个区域。原回复。",
            "不应调用",
        )
        self.assertEqual(result["status"], "completed")
        request.assert_not_called()

    def test_failed_exact_prefix_gets_exactly_one_strict_repair_wire(self):
        result, request, evidence = self.invoke(
            "这里不存在多余区域。",
            "这里没有第四个区域。已核对。",
        )
        self.assertEqual(result["status"], "completed")
        request.assert_called_once()
        payload = request.call_args.args[0]
        self.assertEqual(request.call_args.kwargs["call_kind"], "repair")
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(evidence["wire_envelope"]["finish_reason"], "stop")
        self.assertEqual(evidence["wire_envelope"]["final_text_channel"], "message.content")
        self.assertNotIn("content", evidence["wire_envelope"])

    def test_repair_that_still_misses_prefix_is_candidate_failure(self):
        result, request, _ = self.invoke("未按要求。", "仍未按要求。")
        self.assertEqual(result["status"], "candidate_failed")
        self.assertEqual(result["failure_owner"], "candidate")
        request.assert_called_once()

    def test_missing_final_content_is_an_infrastructure_failure_without_reasoning_leak(self):
        raw = {
            "choices": [{
                "message": {"content": None, "reasoning_content": "private"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
        result, request, evidence = self.invoke("未按要求。", "unused", raw_response=raw)
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(result["failure_owner"], "infrastructure")
        self.assertEqual(evidence["error_code"], "tavern_actor_transport_payload_invalid")
        self.assertTrue(evidence["wire_envelope"]["reasoning_present"])
        self.assertEqual(evidence["wire_envelope"]["reasoning_characters"], 7)
        self.assertNotIn("private", json.dumps(evidence, ensure_ascii=False))
        request.assert_called_once()

    def test_length_finish_is_a_candidate_failure_with_safe_envelope_evidence(self):
        raw = actor_wire("截断")
        raw["choices"][0]["finish_reason"] = "length"
        result, request, evidence = self.invoke("未按要求。", "unused", raw_response=raw)
        self.assertEqual(result["status"], "candidate_failed")
        self.assertEqual(result["failure_owner"], "candidate")
        self.assertEqual(evidence["wire_envelope"]["finish_reason"], "length")
        self.assertEqual(evidence["error_code"], "tavern_repair_output_truncated")
        request.assert_called_once()

    def test_unknown_finish_reason_is_redacted_and_owned_by_infrastructure(self):
        raw = actor_wire("完整候选")
        raw["choices"][0]["finish_reason"] = "private-provider-text"
        result, _, evidence = self.invoke("未按要求。", "unused", raw_response=raw)
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(evidence["wire_envelope"]["finish_reason"], "unknown")
        self.assertEqual(evidence["error_code"], "tavern_repair_transport_finish_reason_invalid")
        self.assertNotIn("private-provider-text", json.dumps(evidence, ensure_ascii=False))

    def test_missing_finish_reason_is_owned_by_infrastructure(self):
        raw = actor_wire("完整候选")
        del raw["choices"][0]["finish_reason"]
        result, _, evidence = self.invoke("未按要求。", "unused", raw_response=raw)
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(evidence["wire_envelope"]["finish_reason"], "missing")

    def test_known_non_final_finish_reasons_are_owned_by_candidate(self):
        for finish_reason in ("tool_calls", "content_filter", "function_call"):
            with self.subTest(finish_reason=finish_reason):
                raw = actor_wire("非最终候选")
                raw["choices"][0]["finish_reason"] = finish_reason
                result, _, evidence = self.invoke("未按要求。", "unused", raw_response=raw)
                self.assertEqual(result["status"], "candidate_failed")
                self.assertEqual(result["failure_owner"], "candidate")
                self.assertEqual(evidence["error_code"], "tavern_repair_non_final_candidate")

    def test_nested_content_shape_is_reported_as_extractable_without_text(self):
        raw = actor_wire("unused")
        raw["choices"][0]["message"]["content"] = {
            "text": actor_wire("这里没有第四个区域。已核对。")["choices"][0]["message"]["content"]
        }
        result, _, evidence = self.invoke("未按要求。", "unused", raw_response=raw)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(evidence["wire_envelope"]["final_text_channel"], "message.content.text")
        self.assertGreater(evidence["wire_envelope"]["final_text_characters"], 0)
        self.assertNotIn("这里没有第四个区域", json.dumps(evidence["wire_envelope"], ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
