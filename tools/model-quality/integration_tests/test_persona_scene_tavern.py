import json
import unittest

from vibe_learner.persona_scene_tavern import (
    _contains_all,
    _contains_none,
    _fake_response,
    _http_failure_status,
    _persona_save_payload,
    _scene_save_payload,
    _trace_is_proposal,
    _verified_candidate_tavern_run_id,
)
from types import SimpleNamespace


class PersonaSceneTavernShadowTests(unittest.TestCase):
    def test_semantic_checks_are_case_insensitive_and_fail_closed(self):
        self.assertTrue(_contains_all("齐女士 First MEETING", ["齐女士", "first meeting"]))
        self.assertFalse(_contains_all("齐女士", ["齐女士", "首次见面"]))
        self.assertTrue(_contains_none("只有北库", ["地下室", "旧友"]))
        self.assertFalse(_contains_none("这是旧友", ["旧友"]))

    def test_trace_requires_successful_not_applicable_proposal(self):
        self.assertTrue(_trace_is_proposal({"status": "repaired", "commit_evidence": {"status": "not_applicable"}}))
        self.assertFalse(_trace_is_proposal({"status": "passed", "commit_evidence": {"status": "committed"}}))
        self.assertFalse(_trace_is_proposal({"status": "failed", "commit_evidence": {"status": "not_applicable"}}))

    def test_projection_payloads_keep_generation_and_save_boundaries_separate(self):
        persona = _persona_save_payload("顾砚", {
            "summary": "谨慎", "relationship": "首次见面", "learner_address": "齐女士",
            "items": [{"kind": "relationship", "label": "关系", "content": "不编造", "ignored": "not copied"}],
        })
        self.assertEqual(persona["name"], "顾砚")
        self.assertNotIn("id", persona)
        self.assertEqual(persona["slots"][0]["content"], "不编造")
        scene = _scene_save_payload({
            "scene_name": "档案室", "scene_summary": "封闭", "scene_layers": [], "selected_layer_id": "layer-1",
        })
        self.assertEqual(scene["expected_revision"], 0)
        self.assertEqual(scene["contract_version"], "scene-committed-save-v1")

    def test_fake_responses_follow_three_stage_wire_order(self):
        spec = {"fake_persona": {"summary": "p"}, "fake_scene": {"scene_name": "s"}, "fake_tavern": {"text": "t"}}
        values = [json.loads(_fake_response(spec, index)["choices"][0]["message"]["content"]) for index in (1, 2, 3)]
        self.assertEqual(values, [spec["fake_persona"], spec["fake_scene"], spec["fake_tavern"]])

    def test_http_failure_ownership_does_not_treat_internal_errors_as_candidates(self):
        class Response:
            def __init__(self, status, detail):
                self.status_code = status
                self._detail = detail

            def json(self):
                return {"detail": self._detail}

        bridge = SimpleNamespace(failure=None)
        self.assertEqual(_http_failure_status(Response(502, "setting_model_invalid_json"), bridge), "candidate_failed")
        valid_tavern_error = Response(502, {
            "code": "tavern_run_failed",
            "run_id": "run-1",
            "recovery_action": "replay_same_request",
        })
        self.assertEqual(_http_failure_status(valid_tavern_error, bridge), "infrastructure_failed")
        self.assertEqual(_http_failure_status(
            valid_tavern_error,
            bridge,
            verified_candidate_tavern_run_id="run-1",
        ), "candidate_failed")
        self.assertEqual(_http_failure_status(
            valid_tavern_error,
            bridge,
            verified_candidate_tavern_run_id="forged-run",
        ), "infrastructure_failed")
        self.assertEqual(_http_failure_status(Response(502, {
            "code": "tavern_run_failed",
            "run_id": "",
            "recovery_action": "none",
        }), bridge), "infrastructure_failed")
        self.assertEqual(_http_failure_status(Response(500, "setting_generation_failed"), bridge), "infrastructure_failed")
        self.assertEqual(_http_failure_status(Response(422, "bad fixture"), bridge), "data_failed")
        bridge.failure = RuntimeError("transport")
        self.assertEqual(_http_failure_status(Response(502, "setting_model_invalid_json"), bridge), "uncertain")

    def test_candidate_tavern_failure_requires_authoritative_terminal_readback(self):
        failed_run = SimpleNamespace(
            id="run-1",
            status=SimpleNamespace(value="failed"),
            speaker_steps=[SimpleNamespace(
                status=SimpleNamespace(value="failed"),
                error_code="tavern_actor_invalid_payload",
            )],
        )
        repository = SimpleNamespace(
            get_run_by_idempotency_key=lambda **kwargs: failed_run,
            require_harness_operation=lambda run_id: SimpleNamespace(
                harness_operation_id="operation-1"
            ),
        )
        runtime_repository = SimpleNamespace(
            list_operation_traces=lambda operation_id: [SimpleNamespace(
                terminal_trace=SimpleNamespace(status="failed")
            )]
        )
        container = SimpleNamespace(tavern_service=SimpleNamespace(
            repository=repository,
            harness_runtime_repository=runtime_repository,
        ))

        self.assertEqual(_verified_candidate_tavern_run_id(
            container,
            room_id="room-1",
            idempotency_key="turn-1",
        ), "run-1")
        failed_run.speaker_steps[0].error_code = "unexpected_internal_error"
        self.assertIsNone(_verified_candidate_tavern_run_id(
            container,
            room_id="room-1",
            idempotency_key="turn-1",
        ))
        failed_run.speaker_steps[0].error_code = "tavern_actor_transport_payload_invalid"
        self.assertIsNone(_verified_candidate_tavern_run_id(
            container,
            room_id="room-1",
            idempotency_key="turn-1",
        ))


if __name__ == "__main__":
    unittest.main()
