from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from examples.aggregate_tavern_counterfactual_full_call_blind import AXES, aggregate
from examples.export_tavern_counterfactual_full_call_blind import (
    KEY_VERSION, PACKET_VERSION, UNAVAILABLE, public_rubric, value_sha,
)
from examples.prepare_tavern_counterfactual_full_call_blind import build_manifest
from vibe_learner.tavern_counterfactual_full_call_blind import CAMPAIGN_ID, GATE


def _budget() -> dict[str, object]:
    return {"token_limit": 999999, "wire_limit": 60, "rpm": 10, "tpm": 999999,
            "max_inflight": 2, "expires_at": 9999999999, "stop_buffer_seconds": 1}


class TavernCounterfactualFullCallBlindTests(unittest.TestCase):
    def test_manifest_is_exact_twenty_arm_full_call_campaign(self):
        manifest = build_manifest(budget_document={"budget": _budget()}, transport="minimax")
        self.assertEqual(manifest["id"], CAMPAIGN_ID)
        self.assertEqual(manifest["sample_wire_limit"], 3)
        self.assertEqual(len(manifest["cases"]), 20)
        self.assertEqual(len({row["family"] for row in manifest["cases"]}), 10)
        self.assertTrue(all(sum(row["family"] == other["family"] for other in manifest["cases"]) == 2 for row in manifest["cases"]))
        self.assertTrue(all("oracle" not in row["source"] and "polarity" not in row["source"] for row in manifest["cases"]))

    def _files(self, root: Path, *, strict: int = 10):
        packet_rows = []
        key_rows = []
        for index in range(10):
            available = index < strict
            values = (
                [{"authoritative_source": f"source-a-{index}", "request": "correct opposite; inventory paper, seal, lamp", "guidance": "use authority", "response": f"reply-a-{index}"},
                 {"authoritative_source": f"source-b-{index}", "request": "correct opposite; inventory paper, seal, lamp", "guidance": "use authority", "response": f"reply-b-{index}"}]
                if available else [UNAVAILABLE.copy(), UNAVAILABLE.copy()]
            )
            pair_id = f"pair-{index + 1:02}"
            packet_rows.append({"pair_id": pair_id, "candidate_a": values[0], "candidate_b": values[1]})
            key_rows.append({
                "pair_id": pair_id, "family_id": f"hidden-family-{index}",
                "axis": "permission_fidelity",
                "second_polarity": "denied" if index < 5 else "explicitly_unknown",
                "strict_pair": available,
                "labels": {
                    "candidate_a": {"case_id": f"hidden-{index}-a", "family_id": f"hidden-family-{index}", "arm": "x", "polarity": "supported", "source": "hidden", "source_sha256": "0" * 64},
                    "candidate_b": {"case_id": f"hidden-{index}-b", "family_id": f"hidden-family-{index}", "arm": "y", "polarity": "denied", "source": "hidden", "source_sha256": "1" * 64},
                },
                "candidate_a_sha256": value_sha(values[0]),
                "candidate_b_sha256": value_sha(values[1]),
            })
        packet = {"version": PACKET_VERSION, "scope": "anonymous committed authority plus final Tavern response only",
                  "review_axes": list(AXES), "grading": ["pass", "minor", "major", "not_evaluable"],
                  "rubric": public_rubric(), "cases": packet_rows}
        key = {"version": KEY_VERSION, "campaign_id": CAMPAIGN_ID, "seed": 913413,
               "prereg_git_commit": "a" * 40, "fixture_sha256": "f" * 64,
               "prereg_canonical_sha256": "e" * 64,
               "manifest_file_sha256": "1" * 64, "report_file_sha256": "2" * 64,
               "rubric_file_sha256": "3" * 64,
               "packet_canonical_sha256": value_sha(packet), "gate": GATE, "cases": key_rows}
        packet_path, key_path = root / "packet.json", root / "key.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        key_path.write_text(json.dumps(key), encoding="utf-8")
        packet_file_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        reviews = []
        for reviewer_id in ("isolated-one", "isolated-two"):
            cases = []
            for index, packet_row in enumerate(packet_rows):
                available = index < strict
                grade = "pass" if available else "not_evaluable"
                cases.append({
                    "pair_id": packet_row["pair_id"],
                    "candidate_a": {"axes": {axis: grade for axis in AXES[:-1]}, "rationale": reviewer_id + " independent A"},
                    "candidate_b": {"axes": {axis: grade for axis in AXES[:-1]}, "rationale": reviewer_id + " independent B"},
                    "counterfactual_sensitivity": {"grade": grade, "rationale": reviewer_id + " independent pair"},
                })
            review = {"version": "m3-tavern-counterfactual-production-full-call-blind-review-v1",
                      "reviewer_id": reviewer_id, "packet_file_sha256": packet_file_sha, "cases": cases}
            path = root / f"{reviewer_id}.json"
            path.write_text(json.dumps(review), encoding="utf-8")
            reviews.append(path)
        return packet_path, key_path, reviews, packet, key

    def test_two_independent_all_pass_reviews_meet_gate(self):
        with TemporaryDirectory() as directory:
            packet_path, key_path, reviews, packet, key = self._files(Path(directory))
            with patch("examples.aggregate_tavern_counterfactual_full_call_blind.build_packet", return_value=(packet, key)):
                result = aggregate(packet_path=packet_path, key_path=key_path, review_paths=reviews,
                                   run_root=Path(directory), prereg_git_commit="a" * 40)
        self.assertTrue(result["promotion_passed"])
        self.assertEqual(result["strict_pairs"], 10)
        self.assertEqual(len(result["shared_authority_and_sensitivity"]), 10)

    def test_eight_strict_pairs_stay_in_ten_denominator_and_fail(self):
        with TemporaryDirectory() as directory:
            packet_path, key_path, reviews, packet, key = self._files(Path(directory), strict=8)
            with patch("examples.aggregate_tavern_counterfactual_full_call_blind.build_packet", return_value=(packet, key)):
                result = aggregate(packet_path=packet_path, key_path=key_path, review_paths=reviews,
                                   run_root=Path(directory), prereg_git_commit="a" * 40)
        self.assertEqual(result["denominator_families"], 10)
        self.assertEqual(result["strict_pairs"], 8)
        self.assertFalse(result["promotion_passed"])

    def test_one_sided_sentinel_is_rejected(self):
        with TemporaryDirectory() as directory:
            packet_path, key_path, reviews, packet, key = self._files(Path(directory))
            packet["cases"][0]["candidate_a"] = UNAVAILABLE.copy()
            key["cases"][0]["candidate_a_sha256"] = value_sha(UNAVAILABLE)
            key["packet_canonical_sha256"] = value_sha(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            key_path.write_text(json.dumps(key), encoding="utf-8")
            with patch("examples.aggregate_tavern_counterfactual_full_call_blind.build_packet", return_value=(packet, key)):
                with self.assertRaisesRegex(ValueError, "asymmetric_sentinel"):
                    aggregate(packet_path=packet_path, key_path=key_path, review_paths=reviews,
                              run_root=Path(directory), prereg_git_commit="a" * 40)

    def test_packet_shape_contains_no_identity_or_runtime_metadata(self):
        with TemporaryDirectory() as directory:
            _, _, _, packet, _ = self._files(Path(directory))
        forbidden = {"family_id", "axis", "polarity", "status", "trace", "repair", "provider_reasoning", "resource_id"}
        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(item) for item in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(item) for item in value)) if value else set()
            return set()
        self.assertFalse(keys(packet) & forbidden)


if __name__ == "__main__":
    unittest.main()
