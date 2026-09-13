from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from examples.aggregate_scene_closed_world_paired_review import (
    AXES,
    _digest,
    aggregate,
)
from examples.export_scene_closed_world_paired_review import _validated_wire_counts


class SceneClosedWorldPairedReviewTests(unittest.TestCase):
    def _fixtures(self, root: Path):
        packet_rows = []
        key_rows = []
        for index in range(6):
            case_id = f"scene-case-{index}"
            available = index < 3
            candidate_a = (
                {"scene": f"initial-{index}"}
                if available
                else {"not_evaluable": True, "reason": "strict_candidate_unavailable"}
            )
            candidate_b = (
                {"scene": f"final-{index}"}
                if available
                else {"not_evaluable": True, "reason": "strict_candidate_unavailable"}
            )
            packet_rows.append({
                "case_id": case_id,
                "authoritative_source": f"source-{index}",
                "candidate_a": candidate_a,
                "candidate_b": candidate_b,
            })
            key_rows.append({
                "case_id": case_id,
                "labels": {
                    "candidate_a": "initial",
                    "candidate_b": "final" if available else "repair_failed",
                },
                "source_sha256": _digest(f"source-{index}"),
                "candidate_a_sha256": _digest(candidate_a),
                "candidate_b_sha256": _digest(candidate_b),
                "repair_candidate_available": available,
            })
        packet = {
            "version": "m3-scene-closed-world-blinded-paired-review-v1",
            "scope": "synthetic authoritative source plus blinded Scene proposals only",
            "review_axes": list(AXES),
            "grading": ["pass", "minor", "major", "not_evaluable"],
            "cases": packet_rows,
        }
        key = {
            "version": "m3-scene-closed-world-blinded-paired-review-key-v2",
            "packet_canonical_sha256": _digest(packet),
            "cases": key_rows,
        }
        packet_path = root / "packet.json"
        key_path = root / "key.json"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        key_path.write_text(json.dumps(key), encoding="utf-8")
        packet_file_sha256 = hashlib.sha256(packet_path.read_bytes()).hexdigest()
        review_paths = []
        for reviewer_id in ("reviewer-e", "reviewer-f"):
            rows = []
            for index, packet_row in enumerate(packet_rows):
                available = index < 3
                rows.append({
                    "case_id": packet_row["case_id"],
                    "candidate_a": {
                        "axes": {
                            axis: "pass" if available else "not_evaluable"
                            for axis in AXES
                        },
                        "rationale": f"independent source comparison by {reviewer_id}",
                    },
                    "candidate_b": {
                        "axes": {
                            axis: "pass" if available else "not_evaluable"
                            for axis in AXES
                        },
                        "rationale": f"independent source comparison by {reviewer_id}",
                    },
                })
            review = {
                "version": "m3-scene-closed-world-blind-review-v1",
                "reviewer_id": reviewer_id,
                "packet_file_sha256": packet_file_sha256,
                "cases": rows,
            }
            path = root / f"{reviewer_id}.json"
            path.write_text(json.dumps(review), encoding="utf-8")
            review_paths.append(path)
        return packet_path, key_path, review_paths

    def test_upstream_http_502_wire_is_rejected(self):
        report = {
            "campaign_usage": {
                "wire_count": 1,
                "charged_or_reserved_tokens": 13,
                "unknown_usage_requests": 0,
                "stopped": None,
                "wires": [{
                    "id": "wire-1",
                    "campaign": "campaign-1",
                    "sample": "sample-1",
                    "started": 1.0,
                    "finished": 2.0,
                    "state": "finished",
                    "reserved": 100,
                    "charged": 13,
                    "metadata": {"call_kind": "repair", "http_status": 502},
                }],
            }
        }
        with self.assertRaisesRegex(ValueError, "scene_review_wire_binding_invalid"):
            _validated_wire_counts(
                report,
                expected_campaign="campaign-1",
                expected_sample_ids={"sample-1"},
                expected_call_kind="repair",
            )

    def test_three_strict_repairs_cannot_pass_five_of_six_gate(self):
        with TemporaryDirectory() as directory:
            packet, key, reviews = self._fixtures(Path(directory))
            expected_packet = json.loads(packet.read_text(encoding="utf-8"))
            expected_key = json.loads(key.read_text(encoding="utf-8"))
            with patch(
                "examples.aggregate_scene_closed_world_paired_review.build_packet",
                return_value=(expected_packet, expected_key),
            ):
                result = aggregate(
                    packet_path=packet,
                    key_path=key,
                    review_paths=reviews,
                    baseline_run=Path(directory),
                    repair_run=Path(directory),
                )
        self.assertEqual(result["strict_repaired_candidates_over_six"], 3)
        self.assertTrue(all(row["not_evaluable_pairs"] == 3 for row in result["reviewers"]))
        self.assertFalse(result["promotion_passed"])

    def test_unavailable_candidate_cannot_be_graded_as_pass(self):
        with TemporaryDirectory() as directory:
            packet, key, reviews = self._fixtures(Path(directory))
            review = json.loads(reviews[0].read_text(encoding="utf-8"))
            review["cases"][3]["candidate_b"]["axes"][AXES[0]] = "pass"
            reviews[0].write_text(json.dumps(review), encoding="utf-8")
            expected_packet = json.loads(packet.read_text(encoding="utf-8"))
            expected_key = json.loads(key.read_text(encoding="utf-8"))
            with patch(
                "examples.aggregate_scene_closed_world_paired_review.build_packet",
                return_value=(expected_packet, expected_key),
            ):
                with self.assertRaisesRegex(ValueError, "unavailable_candidate_was_graded"):
                    aggregate(
                        packet_path=packet,
                        key_path=key,
                        review_paths=reviews,
                        baseline_run=Path(directory),
                        repair_run=Path(directory),
                    )

    def test_duplicate_case_rows_cannot_inflate_strict_count(self):
        with TemporaryDirectory() as directory:
            packet_path, key_path, reviews = self._fixtures(Path(directory))
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            key = json.loads(key_path.read_text(encoding="utf-8"))
            packet["cases"] = packet["cases"][:3] * 2
            key["cases"] = key["cases"][:3] * 2
            key["packet_canonical_sha256"] = _digest(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            key_path.write_text(json.dumps(key), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "packet_key_case_set_mismatch"):
                aggregate(
                    packet_path=packet_path,
                    key_path=key_path,
                    review_paths=reviews,
                    baseline_run=Path(directory),
                    repair_run=Path(directory),
                )

    def test_joint_packet_and_key_rewrite_is_rejected_by_run_rebuild(self):
        with TemporaryDirectory() as directory:
            packet_path, key_path, reviews = self._fixtures(Path(directory))
            original_packet = json.loads(packet_path.read_text(encoding="utf-8"))
            original_key = json.loads(key_path.read_text(encoding="utf-8"))
            packet = json.loads(json.dumps(original_packet))
            key = json.loads(json.dumps(original_key))
            packet["cases"][0]["authoritative_source"] = "forged-source"
            key["cases"][0]["source_sha256"] = _digest("forged-source")
            key["packet_canonical_sha256"] = _digest(packet)
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            key_path.write_text(json.dumps(key), encoding="utf-8")
            with patch(
                "examples.aggregate_scene_closed_world_paired_review.build_packet",
                return_value=(original_packet, original_key),
            ):
                with self.assertRaisesRegex(ValueError, "packet_key_run_binding_mismatch"):
                    aggregate(
                        packet_path=packet_path,
                        key_path=key_path,
                        review_paths=reviews,
                        baseline_run=Path(directory),
                        repair_run=Path(directory),
                    )


if __name__ == "__main__":
    unittest.main()
