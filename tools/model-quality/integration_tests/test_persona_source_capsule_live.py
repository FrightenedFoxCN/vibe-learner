from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from examples.prepare_persona_source_capsule_live import (
    FIXTURE,
    PREREGISTERED_GATE,
    build_manifest,
)
from model_quality.ledger import GateClosed
from model_quality.protocol import Campaign, digest
from model_quality.transport import WireFailure
from app.services.provider_settings import (
    PERSONA_CARD_GENERATION_SCHEMA,
    _render_persona_card_count_hint,
    _setting_prompt_sections,
)
from vibe_learner.persona_source_capsule import PersonaSourceIssueCode
from vibe_learner.persona_source_capsule_live import (
    BASELINE_VARIANT,
    CANDIDATE_VARIANT,
    EVIDENCE_NAME,
    LIVE_CAMPAIGN_CANONICAL_SHA256,
    build_payload,
    build_prompt_projection,
    run_sample,
)


BUDGET = {
    "token_limit": 500000,
    "wire_limit": 100,
    "rpm": 60,
    "tpm": 200000,
    "max_inflight": 2,
    "expires_at": 9999999999,
    "stop_buffer_seconds": 1,
}


def _fixture_rows():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]


def _wire(proposal, *, finish_reason="stop", content_marker="content"):
    message = {content_marker: json.dumps(proposal, ensure_ascii=False)}
    return {
        "model": "MiniMax-M3",
        "choices": [{"message": message, "finish_reason": finish_reason}],
        "usage": {
            "prompt_tokens": 101,
            "completion_tokens": 53,
            "total_tokens": 154,
        },
    }


def _campaign_and_case(case_index=0):
    manifest = build_manifest(budget_document={"budget": BUDGET}, transport="fake")
    campaign = Campaign.model_validate(manifest, strict=True)
    return campaign, campaign.cases[case_index]


def _invoke(*, variant_id=BASELINE_VARIANT, raw=None, side_effect=None, mutate_case=None):
    campaign, case = _campaign_and_case()
    if mutate_case is not None:
        case = mutate_case(case)
    request = Mock(side_effect=side_effect) if side_effect is not None else Mock(return_value=raw)
    context = SimpleNamespace(transport=SimpleNamespace(campaign=campaign, request=request))
    variant = SimpleNamespace(id=variant_id)
    with TemporaryDirectory() as directory:
        context.storage = Path(directory) / "storage"
        context.storage.mkdir()
        result = run_sample(context, case, variant)
        evidence_path = context.storage / EVIDENCE_NAME
        evidence_bytes = evidence_path.read_bytes() if evidence_path.exists() else None
        evidence = json.loads(evidence_bytes) if evidence_bytes is not None else None
    return result, request, evidence, evidence_bytes


class PersonaSourceCapsuleLiveTests(unittest.TestCase):
    def test_frozen_live_manifest_matches_adapter_digest(self):
        path = (
            Path(__file__).resolve().parents[3]
            / "docs"
            / "quality"
            / "evidence"
            / "m3-persona-source-capsule-live-manifest-2026-09-13.json"
        )
        campaign = Campaign.model_validate_json(path.read_bytes(), strict=True)
        self.assertEqual(
            digest(campaign.model_dump(mode="json")),
            LIVE_CAMPAIGN_CANONICAL_SHA256,
        )

    def test_manifest_is_one_randomized_fresh_campaign_with_sixteen_wires(self):
        manifest = build_manifest(budget_document={"budget": BUDGET}, transport="fake")
        campaign = Campaign.model_validate(manifest, strict=True)
        self.assertEqual(len(campaign.cases), 8)
        self.assertEqual(len(campaign.variants), 2)
        self.assertEqual(len(list(campaign.samples())), 16)
        self.assertEqual(campaign.sample_wire_limit, 1)
        self.assertEqual(campaign.model, "MiniMax-M3")
        self.assertEqual(campaign.thinking, "adaptive")
        self.assertEqual(campaign.temperature, 0.2)
        self.assertEqual(campaign.max_output_tokens, 4096)
        self.assertEqual(campaign.input_reservation_tokens, 100000)
        orders = []
        samples = list(campaign.samples())
        for index in range(0, len(samples), 2):
            first, second = samples[index], samples[index + 1]
            self.assertEqual(first[2].id, second[2].id)
            orders.append((first[3].id, second[3].id))
        self.assertIn((BASELINE_VARIANT, CANDIDATE_VARIANT), orders)
        self.assertIn((CANDIDATE_VARIANT, BASELINE_VARIANT), orders)
        self.assertEqual(PREREGISTERED_GATE["paired_strict_candidates_min"], 7)
        self.assertEqual(PREREGISTERED_GATE["shared_major_reductions_min"], 4)
        self.assertEqual(PREREGISTERED_GATE["candidate_only_major_max"], 0)
        self.assertEqual(PREREGISTERED_GATE["capsule_relationship_major_max"], 0)
        self.assertEqual(PREREGISTERED_GATE["capsule_permission_major_max"], 0)
        self.assertEqual(PREREGISTERED_GATE["blind_reviewers"], 2)
        self.assertFalse(PREREGISTERED_GATE["production_registry_change"])
        self.assertFalse(PREREGISTERED_GATE["persona_save"])

    def test_fake_matrix_sends_exactly_sixteen_independent_single_wires(self):
        campaign, _ = _campaign_and_case()
        calls = []
        for _, _, case, variant in campaign.samples():
            raw = _wire(json.loads(case.gold)["fake_proposal"])
            request = Mock(return_value=raw)
            context = SimpleNamespace(transport=SimpleNamespace(campaign=campaign, request=request))
            with TemporaryDirectory() as directory:
                context.storage = Path(directory)
                result = run_sample(context, case, variant)
            self.assertEqual(result["status"], "completed")
            request.assert_called_once()
            calls.append((case.id, variant.id, request.call_args.args[0]))
        self.assertEqual(len(calls), 16)
        by_case = {}
        for case_id, variant_id, payload in calls:
            by_case.setdefault(case_id, {})[variant_id] = payload
        self.assertEqual(len(by_case), 8)
        for pair in by_case.values():
            self.assertEqual(set(pair), {BASELINE_VARIANT, CANDIDATE_VARIANT})
            baseline = deepcopy(pair[BASELINE_VARIANT])
            candidate = deepcopy(pair[CANDIDATE_VARIANT])
            appendix = candidate["messages"][0]["content"].split(
                "\n\n[persona_source_constraint_appendix_v1]\n", 1
            )
            self.assertEqual(len(appendix), 2)
            candidate["messages"][0]["content"] = appendix[0]
            self.assertEqual(candidate, baseline)

    def test_baseline_payload_is_the_current_production_long_text_prompt(self):
        campaign, case = _campaign_and_case()
        payload = build_payload(campaign=campaign, source=case.source, projection=None)
        sections = _setting_prompt_sections()
        count_hint = _render_persona_card_count_hint(1)
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertEqual(
            payload["messages"],
            [
                {
                    "role": "system",
                    "content": sections["generate_long_text_system"]
                    .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA)
                    .replace("{{CARD_COUNT}}", count_hint),
                },
                {
                    "role": "user",
                    "content": sections["generate_long_text_user"]
                    .replace("{{SOURCE_TEXT}}", case.source.strip())
                    .replace("{{CARD_COUNT}}", count_hint)
                    .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA),
                },
            ],
        )

    def test_capsule_projection_has_only_source_claims_and_no_grading_leakage(self):
        for row in _fixture_rows():
            capsule = row["capsule"]
            campaign, _ = _campaign_and_case()
            from vibe_learner.persona_source_capsule import PersonaSourceConstraintCapsuleV1
            decoded = PersonaSourceConstraintCapsuleV1.model_validate(capsule, strict=True)
            projection = build_prompt_projection(decoded)
            self.assertEqual(set(projection), {"version", "address", "claims", "rules"})
            self.assertTrue(all(
                set(claim)
                == {"claim_id", "kind", "key", "polarity", "source_char_start", "source_char_end"}
                for claim in projection["claims"]
            ))
            for projected_claim, source_claim in zip(projection["claims"], capsule["claims"]):
                self.assertEqual(projected_claim["source_char_start"], source_claim["source_span"]["char_start"])
                self.assertEqual(projected_claim["source_char_end"], source_claim["source_span"]["char_end"])
            projected = json.dumps(projection, ensure_ascii=False, sort_keys=True)
            self.assertNotIn("forbidden_transformations", projected)
            self.assertNotIn("markers", projected)
            for code in PersonaSourceIssueCode.__args__:
                self.assertNotIn(code, projected)
            self.assertNotIn(
                json.dumps(row["valid_minimal_persona_card_batch_proposal"], ensure_ascii=False),
                projected,
            )
            payload = build_payload(campaign=campaign, source=row["source_text"], projection=projection)
            baseline = build_payload(campaign=campaign, source=row["source_text"], projection=None)
            baseline_text = json.dumps(baseline, ensure_ascii=False)
            candidate_text = json.dumps(payload, ensure_ascii=False)
            for mutation in row["single_point_mutations"]:
                marker = mutation["value"]
                self.assertEqual(candidate_text.count(marker), baseline_text.count(marker))
            self.assertNotIn("tools", payload)
            self.assertNotIn("web_search", json.dumps(payload, ensure_ascii=False))

    def test_strict_success_evidence_is_safe_and_digest_bound(self):
        row = _fixture_rows()[0]
        result, request, evidence, evidence_bytes = _invoke(raw=_wire(row["valid_minimal_persona_card_batch_proposal"]))
        self.assertEqual(result["status"], "completed")
        request.assert_called_once()
        self.assertTrue(evidence["strict_candidate"])
        self.assertEqual(len(evidence["proposal"]["cards"]), 1)
        self.assertEqual(evidence["commit_evidence"], {"status": "not_applicable"})
        self.assertEqual(evidence["exact_marker_policy"], "deterministic_exact_match_non_semantic")
        self.assertEqual(evidence["safe_wire"]["finish_reason"], "stop")
        self.assertEqual(evidence["safe_wire"]["final_channel"], "message.content")
        self.assertNotIn("raw", evidence)
        self.assertNotIn("reasoning", json.dumps(evidence))
        self.assertEqual(result["evidence"][0]["sha256"], hashlib.sha256(evidence_bytes).hexdigest())
        self.assertRegex(evidence["provider_payload_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(evidence["campaign_config_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(result["scope"], "provider-proposal-only; no domain admission, commit or read-back")

    def test_length_and_schema_failure_are_candidate_owned(self):
        row = _fixture_rows()[0]
        two_cards = deepcopy(row["valid_minimal_persona_card_batch_proposal"])
        two_cards["cards"].append(deepcopy(two_cards["cards"][0]))
        for raw in (
            _wire(row["valid_minimal_persona_card_batch_proposal"], finish_reason="length"),
            _wire({"summary": "missing fields"}),
            _wire(two_cards),
        ):
            result, request, evidence, _ = _invoke(raw=raw)
            self.assertEqual(result["status"], "candidate_failed")
            self.assertEqual(result["failure_owner"], "candidate")
            self.assertFalse(evidence["strict_candidate"])
            request.assert_called_once()

    def test_reasoning_content_is_not_a_final_channel_fallback(self):
        row = _fixture_rows()[0]
        raw = _wire(row["valid_minimal_persona_card_batch_proposal"])
        raw["choices"][0]["message"] = {
            "content": None,
            "reasoning_content": json.dumps(row["valid_minimal_persona_card_batch_proposal"]),
        }
        result, _, evidence, _ = _invoke(raw=raw)
        self.assertEqual(result["status"], "candidate_failed")
        self.assertFalse(evidence["safe_wire"]["final_content_present"])
        self.assertNotIn("reasoning_content", json.dumps(evidence))

    def test_unknown_finish_is_infrastructure_owned(self):
        row = _fixture_rows()[0]
        result, _, evidence, _ = _invoke(
            raw=_wire(row["valid_minimal_persona_card_batch_proposal"], finish_reason="future")
        )
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(result["failure_owner"], "infrastructure")
        self.assertEqual(evidence["safe_wire"]["finish_reason"], "unknown")

    def test_gate_closed_is_infrastructure_but_ambiguous_transport_is_uncertain(self):
        result, request, evidence, _ = _invoke(side_effect=GateClosed("budget_closed"))
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(evidence["safe_wire"], {"dispatch": "gate_closed"})
        request.assert_called_once()
        result, request, evidence, _ = _invoke(side_effect=TimeoutError("after dispatch unknown"))
        self.assertEqual(result["status"], "uncertain")
        self.assertEqual(result["failure_owner"], "infrastructure")
        self.assertEqual(evidence["safe_wire"], {"dispatch": "ambiguous_after_request"})
        request.assert_called_once()
        result, request, evidence, _ = _invoke(
            side_effect=WireFailure("known_http_failure", uncertain=False)
        )
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(evidence["safe_wire"], {"dispatch": "known_transport_failure"})
        request.assert_called_once()

    def test_fixture_binding_failure_is_data_owned_and_pre_wire(self):
        def mutate(case):
            payload = case.model_dump(mode="json")
            payload["source"] += "tamper"
            return type(case).model_validate(payload, strict=True)

        result, request, evidence, _ = _invoke(mutate_case=mutate)
        self.assertEqual(result["status"], "data_failed")
        self.assertEqual(result["failure_owner"], "data")
        request.assert_not_called()
        self.assertIsNone(evidence)

    def test_preregistered_gate_tamper_is_data_owned_and_pre_wire(self):
        def mutate(case):
            payload = case.model_dump(mode="json")
            gold = json.loads(payload["gold"])
            gold["preregistered_gate"]["paired_strict_candidates_min"] = 1
            payload["gold"] = json.dumps(gold, ensure_ascii=False)
            return type(case).model_validate(payload, strict=True)

        result, request, evidence, _ = _invoke(mutate_case=mutate)
        self.assertEqual(result["status"], "data_failed")
        request.assert_not_called()
        self.assertIsNone(evidence)

    def test_campaign_shape_tamper_is_pre_wire_infrastructure_failure(self):
        campaign, case = _campaign_and_case()
        payload = campaign.model_dump(mode="json")
        payload["seed"] = 1
        payload["cases"] = payload["cases"][:1]
        tampered = Campaign.model_validate(payload, strict=True)
        request = Mock(return_value=_wire(json.loads(case.gold)["fake_proposal"]))
        context = SimpleNamespace(transport=SimpleNamespace(campaign=tampered, request=request))
        with TemporaryDirectory() as directory:
            context.storage = Path(directory)
            result = run_sample(context, tampered.cases[0], SimpleNamespace(id=BASELINE_VARIANT))
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(result["error_code"], "persona_source_capsule_campaign_invalid")
        request.assert_not_called()

    def test_evidence_digest_changes_when_production_prompt_changes(self):
        row = _fixture_rows()[0]
        _, _, original, _ = _invoke(raw=_wire(row["valid_minimal_persona_card_batch_proposal"]))
        sections = _setting_prompt_sections()
        changed = dict(sections)
        changed["generate_long_text_system"] += "\nchanged-for-test"
        with patch(
            "vibe_learner.persona_source_capsule_live._setting_prompt_sections",
            return_value=changed,
        ):
            _, _, modified, _ = _invoke(raw=_wire(row["valid_minimal_persona_card_batch_proposal"]))
        self.assertNotEqual(original["provider_payload_sha256"], modified["provider_payload_sha256"])
        self.assertEqual(original["campaign_config_sha256"], modified["campaign_config_sha256"])


if __name__ == "__main__":
    unittest.main()
