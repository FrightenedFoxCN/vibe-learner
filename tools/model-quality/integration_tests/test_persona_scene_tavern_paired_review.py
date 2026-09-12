from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from examples.aggregate_persona_scene_tavern_paired_review import aggregate


REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_ROOT = (
    REPO_ROOT
    / "tools"
    / "model-quality"
    / "runs"
    / "m3-persona-scene-tavern-20260913"
)
EVIDENCE_ROOT = REPO_ROOT / "docs" / "quality" / "evidence"


class PersonaSceneTavernPairedReviewTests(unittest.TestCase):
    def test_archived_reviews_recompute_frozen_aggregate(self):
        result = aggregate(
            packet_path=RUN_ROOT / "paired-review-packet-v1.json",
            key_path=RUN_ROOT / "paired-review-key-v1.json",
            review_paths=[
                EVIDENCE_ROOT / "m3-tavern-paired-review-c.json",
                EVIDENCE_ROOT / "m3-tavern-paired-review-d.json",
            ],
        )
        expected = json.loads(
            (EVIDENCE_ROOT / "m3-tavern-paired-review-aggregate-v2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(result, expected)
        self.assertEqual(result["shared_major_reductions"], [
            "mediator-not-aunt-cinema:task_adherence"
        ])
        self.assertEqual(result["any_new_major_regressions"], [])
        self.assertFalse(result["promotion_passed"])

    def test_review_cannot_be_rebound_to_a_different_packet(self):
        review_path = EVIDENCE_ROOT / "m3-tavern-paired-review-c.json"
        review = json.loads(review_path.read_text(encoding="utf-8"))
        review["packet_file_sha256"] = "0" * 64
        with TemporaryDirectory() as directory:
            forged_path = Path(directory) / "forged-review.json"
            forged_path.write_text(json.dumps(review), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "review_packet_file_digest_mismatch"):
                aggregate(
                    packet_path=RUN_ROOT / "paired-review-packet-v1.json",
                    key_path=RUN_ROOT / "paired-review-key-v1.json",
                    review_paths=[forged_path],
                )


if __name__ == "__main__":
    unittest.main()
