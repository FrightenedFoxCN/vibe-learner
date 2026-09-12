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

    def invoke(self, initial_text, repaired_text):
        source, spec = self.spec(initial_text)
        request = Mock(return_value=actor_wire(repaired_text))
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
        return result, request

    def test_exact_pass_reuses_frozen_reply_without_wire(self):
        result, request = self.invoke(
            "这里没有第四个区域。原回复。",
            "不应调用",
        )
        self.assertEqual(result["status"], "completed")
        request.assert_not_called()

    def test_failed_exact_prefix_gets_exactly_one_strict_repair_wire(self):
        result, request = self.invoke(
            "这里不存在多余区域。",
            "这里没有第四个区域。已核对。",
        )
        self.assertEqual(result["status"], "completed")
        request.assert_called_once()
        payload = request.call_args.args[0]
        self.assertEqual(request.call_args.kwargs["call_kind"], "repair")
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_repair_that_still_misses_prefix_is_candidate_failure(self):
        result, request = self.invoke("未按要求。", "仍未按要求。")
        self.assertEqual(result["status"], "candidate_failed")
        self.assertEqual(result["failure_owner"], "candidate")
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
