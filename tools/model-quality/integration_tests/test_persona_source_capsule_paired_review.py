from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from examples.aggregate_persona_source_capsule_paired_review import AXES, aggregate
from examples.export_persona_source_capsule_paired_review import (
    REVIEW_SEED,
    UNAVAILABLE,
    _digest,
    build_packet,
    build_run_anchor,
)
from examples.prepare_persona_source_capsule_live import build_manifest
from model_quality.protocol import Campaign, digest
from vibe_learner.persona_source_capsule import PersonaSourceConstraintCapsuleV1
from vibe_learner.persona_source_capsule_live import (
    BASELINE_VARIANT,
    CANDIDATE_VARIANT,
    EVIDENCE_CONTRACT,
    EVIDENCE_NAME,
    FIXTURE,
    SCOPE,
    build_payload,
    build_prompt_projection,
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
ANCHOR_COMMIT = "a" * 40
TEST_REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_frozen_run(root: Path, *, failed_case: str | None = None) -> None:
    config = build_manifest(
        budget_document={"budget": BUDGET},
        transport="minimax",
    )
    campaign = Campaign.model_validate(config, strict=True)
    (root / "manifest.json").write_text(
        json.dumps(
            {
                "config": campaign.model_dump(mode="json"),
                "config_digest": digest(campaign.model_dump(mode="json")),
                "source": {"test_fixture": True},
                "scope": "standalone research campaign",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fixture = {
        row["case_id"]: row
        for row in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    }
    rows = []
    wires = []
    pairs: dict[str, dict[str, str]] = {}
    for index, (sample_id, identity, case, variant) in enumerate(campaign.samples()):
        should_fail = case.id == failed_case and variant.id == CANDIDATE_VARIANT
        state = "data_failed" if should_fail else "completed"
        references = []
        if not should_fail:
            fixture_capsule = PersonaSourceConstraintCapsuleV1.model_validate(
                fixture[case.id]["capsule"], strict=True
            )
            projection = (
                build_prompt_projection(fixture_capsule)
                if variant.id == CANDIDATE_VARIANT
                else {"version": "production-prompt-no-capsule-projection-v1"}
            )
            evidence = {
                "version": EVIDENCE_CONTRACT,
                "case_id": case.id,
                "variant": variant.id,
                "scope": SCOPE,
                "commit_evidence": {"status": "not_applicable"},
                "source_sha256": fixture[case.id]["capsule"]["source_sha256"],
                "capsule_sha256": fixture[case.id]["capsule_sha256"],
                "prompt_projection_sha256": _digest(projection),
                "provider_payload_sha256": _digest(build_payload(
                    campaign=campaign,
                    source=case.source,
                    projection=(
                        projection if variant.id == CANDIDATE_VARIANT else None
                    ),
                )),
                "campaign_config_sha256": _digest(
                    campaign.model_dump(mode="json")
                ),
                "strict_candidate": True,
                "exact_marker_policy": "deterministic_exact_match_non_semantic",
                "exact_marker_issues": [],
                "proposal": fixture[case.id][
                    "valid_minimal_persona_card_batch_proposal"
                ],
                "safe_wire": {
                    "finish_reason": "stop",
                    "prompt_tokens": 10,
                    "completion_tokens": 10,
                    "total_tokens": 20,
                    "final_channel": "message.content",
                    "final_content_present": True,
                },
            }
            evidence_path = (
                root
                / case.id
                / variant.id
                / "0"
                / "storage"
                / EVIDENCE_NAME
            )
            evidence_path.parent.mkdir(parents=True)
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            references = [{
                "path": EVIDENCE_NAME,
                "contract": EVIDENCE_CONTRACT,
                "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            }]
            wires.append({
                "id": f"wire-{index}",
                "campaign": campaign.id,
                "sample": sample_id,
                "started": float(index),
                "finished": float(index + 1),
                "state": "finished",
                "reserved": 100,
                "charged": 20,
                "metadata": {
                    "call_kind": "generation",
                    "http_status": 200,
                    "total_tokens": 20,
                },
            })
        result = {
            "status": state,
            "failure_owner": "data" if should_fail else None,
            "scope": SCOPE,
            "evidence": references,
        }
        rows.append({
            **identity,
            "sample_id": sample_id,
            "family": case.family,
            "state": state,
            "result": result,
            "elapsed_seconds": 1.0,
        })
        pairs.setdefault(f"{case.id}:0", {})[variant.id] = state
    states = dict(Counter(row["state"] for row in rows))
    usage = {
        "wire_count": len(wires),
        "charged_or_reserved_tokens": sum(wire["charged"] for wire in wires),
        "unknown_usage_requests": 0,
        "stopped": None,
        "wires": wires,
    }
    (root / "report.json").write_text(
        json.dumps(
            {
                "version": "quality-report-v1",
                "campaign": campaign.id,
                "transport": "minimax",
                "scope": "research infrastructure; not Harness evidence or independent quality certification",
                "expected_samples": 16,
                "independent_families": 8,
                "states": states,
                "pairs": pairs,
                "failure_owners": {
                    "data": 1,
                }
                if failed_case is not None
                else {},
                "samples": rows,
                "campaign_usage": usage,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_packet_and_reviews(root: Path, *, failed_case: str | None = None):
    run_root = root / "run"
    run_root.mkdir()
    _write_frozen_run(run_root, failed_case=failed_case)
    anchor = build_run_anchor(run_root)
    packet, key = build_packet(
        run_root=run_root,
        seed=REVIEW_SEED,
        run_anchor=anchor,
        anchor_git_commit=ANCHOR_COMMIT,
    )
    packet_path = root / "packet.json"
    key_path = root / "key.json"
    packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
    key_path.write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")
    packet_sha = hashlib.sha256(packet_path.read_bytes()).hexdigest()
    key_by_case = {row["case_id"]: row for row in key["cases"]}
    review_paths = []
    for reviewer_index, reviewer_id in enumerate(("reviewer-g", "reviewer-h")):
        review_rows = []
        for case_index, packet_row in enumerate(packet["cases"]):
            labels = key_by_case[packet_row["case_id"]]["labels"]
            unavailable = packet_row["candidate_a"] == UNAVAILABLE
            candidate_reviews = {}
            for candidate_name in ("candidate_a", "candidate_b"):
                if unavailable:
                    grades = {axis: "not_evaluable" for axis in AXES}
                else:
                    grades = {axis: "pass" for axis in AXES}
                    if (
                        case_index < 4
                        and labels[candidate_name] == BASELINE_VARIANT
                    ):
                        grades["relationship_fidelity"] = "major"
                candidate_reviews[candidate_name] = {
                    "axes": grades,
                    "rationale": (
                        f"manual semantic comparison {reviewer_index} for "
                        f"{packet_row['case_id']} {candidate_name}"
                    ),
                }
            review_rows.append({
                "case_id": packet_row["case_id"],
                **candidate_reviews,
            })
        review = {
            "version": "m3-persona-source-capsule-blind-review-v1",
            "reviewer_id": reviewer_id,
            "packet_file_sha256": packet_sha,
            "cases": review_rows,
        }
        review_path = root / f"{reviewer_id}.json"
        review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        review_paths.append(review_path)
    return run_root, packet_path, key_path, review_paths, anchor


class PersonaSourceCapsulePairedReviewTests(unittest.TestCase):
    def test_runner_level_uncertain_without_scope_or_evidence_stays_in_denominator(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            run_root = Path(directory) / "run"
            run_root.mkdir()
            _write_frozen_run(run_root)
            report_path = run_root / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            sample = next(
                row
                for row in report["samples"]
                if row["variant"] == CANDIDATE_VARIANT
            )
            sample["state"] = "uncertain"
            sample["result"] = {
                "status": "uncertain",
                "failure_owner": "infrastructure",
                "error_code": "worker_exit_no_replay",
            }
            report["states"] = {"completed": 15, "uncertain": 1}
            report["failure_owners"] = {"infrastructure": 1}
            report["pairs"][f"{sample['case']}:0"][CANDIDATE_VARIANT] = "uncertain"
            wire = next(
                row
                for row in report["campaign_usage"]["wires"]
                if row["sample"] == sample["sample_id"]
            )
            wire["state"] = "uncertain"
            wire["metadata"] = None
            wire["charged"] = wire["reserved"]
            report["campaign_usage"]["unknown_usage_requests"] = 1
            report["campaign_usage"]["charged_or_reserved_tokens"] = sum(
                row["charged"] for row in report["campaign_usage"]["wires"]
            )
            report_path.write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            anchor = build_run_anchor(run_root)
            packet, key = build_packet(
                run_root=run_root,
                seed=REVIEW_SEED,
                run_anchor=anchor,
                anchor_git_commit=ANCHOR_COMMIT,
            )
        packet_row = next(row for row in packet["cases"] if row["case_id"] == sample["case"])
        key_row = next(row for row in key["cases"] if row["case_id"] == sample["case"])
        self.assertEqual(packet_row["candidate_a"], UNAVAILABLE)
        self.assertEqual(packet_row["candidate_b"], UNAVAILABLE)
        self.assertFalse(key_row["pair_strict_candidate"])

    def test_exporter_rebuilds_eight_pairs_and_hides_which_arm_failed(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            failed_case = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"][-1][
                "case_id"
            ]
            run_root = root / "run"
            run_root.mkdir()
            _write_frozen_run(run_root, failed_case=failed_case)
            anchor = build_run_anchor(run_root)
            packet, key = build_packet(
                run_root=run_root,
                seed=REVIEW_SEED,
                run_anchor=anchor,
                anchor_git_commit=ANCHOR_COMMIT,
            )
        self.assertEqual(len(packet["cases"]), 8)
        self.assertEqual(len(key["cases"]), 8)
        self.assertNotEqual(key["seed"], 91317)  # independent from campaign order seed
        self.assertEqual(
            Counter(row["labels"]["candidate_a"] for row in key["cases"]),
            Counter({BASELINE_VARIANT: 4, CANDIDATE_VARIANT: 4}),
        )
        self.assertEqual(
            sum(row["pair_strict_candidate"] for row in key["cases"]), 7
        )
        failed = next(row for row in packet["cases"] if row["case_id"] == failed_case)
        self.assertEqual(failed["candidate_a"], UNAVAILABLE)
        self.assertEqual(failed["candidate_a"], failed["candidate_b"])
        packet_text = json.dumps(packet, ensure_ascii=False)
        for forbidden in (
            BASELINE_VARIANT,
            CANDIDATE_VARIANT,
            "preregistered_gate",
            "exact_marker",
            "run_status",
        ):
            self.assertNotIn(forbidden, packet_text)

    def test_worst_of_two_preregistered_gate_can_pass_with_seven_strict_pairs(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            failed_case = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"][-1][
                "case_id"
            ]
            run_root, packet, key, reviews, anchor = _write_packet_and_reviews(
                root, failed_case=failed_case
            )
            result = aggregate(
                packet_path=packet,
                key_path=key,
                review_paths=reviews,
                run_root=run_root,
                run_anchor=anchor,
                anchor_git_commit=ANCHOR_COMMIT,
            )
        self.assertEqual(result["denominator_pairs"], 8)
        self.assertEqual(result["strict_paired_candidates_over_eight"], 7)
        self.assertEqual(len(result["shared_major_reductions"]), 4)
        self.assertFalse(result["exact_marker_success_credit"])
        self.assertEqual(result["proposal_commit"], "not_applicable")
        self.assertTrue(result["promotion_passed"])

    def test_one_reviewer_candidate_only_major_blocks_worst_of_two_gate(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            run_root, packet_path, key_path, reviews, anchor = _write_packet_and_reviews(root)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            key = json.loads(key_path.read_text(encoding="utf-8"))
            labels = {row["case_id"]: row["labels"] for row in key["cases"]}
            review = json.loads(reviews[1].read_text(encoding="utf-8"))
            row = review["cases"][-1]
            capsule_name = next(
                name
                for name, label in labels[row["case_id"]].items()
                if label == CANDIDATE_VARIANT
            )
            row[capsule_name]["axes"]["task_format_adherence"] = "major"
            reviews[1].write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            result = aggregate(
                packet_path=packet_path,
                key_path=key_path,
                review_paths=reviews,
                run_root=run_root,
                run_anchor=anchor,
                anchor_git_commit=ANCHOR_COMMIT,
            )
        self.assertEqual(len(result["any_candidate_only_majors"]), 1)
        self.assertFalse(result["promotion_passed"])

    def test_joint_packet_key_forgery_is_rejected_by_frozen_run_rebuild(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            run_root, packet_path, key_path, reviews, anchor = _write_packet_and_reviews(root)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            key = json.loads(key_path.read_text(encoding="utf-8"))
            packet["cases"][0]["authoritative_source"] = "forged source"
            key["cases"][0]["source_sha256"] = _digest("forged source")
            key["packet_canonical_sha256"] = _digest(packet)
            packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
            key_path.write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "packet_key_run_binding_mismatch"):
                aggregate(
                    packet_path=packet_path,
                    key_path=key_path,
                    review_paths=reviews,
                    run_root=run_root,
                    run_anchor=anchor,
                    anchor_git_commit=ANCHOR_COMMIT,
                )

    def test_forged_unavailable_pair_is_rejected_by_frozen_run_rebuild(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            run_root, packet_path, key_path, reviews, anchor = _write_packet_and_reviews(root)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            key = json.loads(key_path.read_text(encoding="utf-8"))
            packet["cases"][0]["candidate_a"] = deepcopy(UNAVAILABLE)
            packet["cases"][0]["candidate_b"] = deepcopy(UNAVAILABLE)
            key["cases"][0]["candidate_a_sha256"] = _digest(UNAVAILABLE)
            key["cases"][0]["candidate_b_sha256"] = _digest(UNAVAILABLE)
            key["cases"][0]["pair_strict_candidate"] = False
            key["packet_canonical_sha256"] = _digest(packet)
            packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
            key_path.write_text(json.dumps(key, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "packet_key_run_binding_mismatch"):
                aggregate(
                    packet_path=packet_path,
                    key_path=key_path,
                    review_paths=reviews,
                    run_root=run_root,
                    run_anchor=anchor,
                    anchor_git_commit=ANCHOR_COMMIT,
                )

    def test_prompt_digest_tamper_is_rejected_before_blind_export(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            run_root = Path(directory) / "run"
            run_root.mkdir()
            _write_frozen_run(run_root)
            evidence_path = next(run_root.glob(f"*/*/0/storage/{EVIDENCE_NAME}"))
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["provider_payload_sha256"] = "0" * 64
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
            )
            report_path = run_root / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            case_id = evidence_path.parents[3].name
            variant_id = evidence_path.parents[2].name
            row = next(
                item
                for item in report["samples"]
                if item["case"] == case_id and item["variant"] == variant_id
            )
            row["result"]["evidence"][0]["sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            report_path.write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(
                ValueError, "persona_capsule_review_evidence_binding_invalid"
            ):
                build_packet(
                    run_root=run_root,
                    seed=REVIEW_SEED,
                    run_anchor=build_run_anchor(run_root),
                    anchor_git_commit=ANCHOR_COMMIT,
                )

    def test_post_anchor_run_rewrite_is_rejected(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            run_root = Path(directory) / "run"
            run_root.mkdir()
            _write_frozen_run(run_root)
            anchor = build_run_anchor(run_root)
            evidence_path = next(run_root.glob(f"*/*/0/storage/{EVIDENCE_NAME}"))
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["proposal"]["summary"] = "jointly forged after anchor"
            evidence_path.write_text(
                json.dumps(evidence, ensure_ascii=False), encoding="utf-8"
            )
            report_path = run_root / "report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            case_id = evidence_path.parents[3].name
            variant_id = evidence_path.parents[2].name
            row = next(
                item
                for item in report["samples"]
                if item["case"] == case_id and item["variant"] == variant_id
            )
            row["result"]["evidence"][0]["sha256"] = hashlib.sha256(
                evidence_path.read_bytes()
            ).hexdigest()
            report_path.write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "run_anchor_mismatch"):
                build_packet(
                    run_root=run_root,
                    seed=REVIEW_SEED,
                    run_anchor=anchor,
                    anchor_git_commit=ANCHOR_COMMIT,
                )

    def test_duplicate_case_and_non_independent_reviews_are_rejected(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            run_root, packet_path, key_path, reviews, anchor = _write_packet_and_reviews(root)
            packet = json.loads(packet_path.read_text(encoding="utf-8"))
            packet["cases"][-1] = deepcopy(packet["cases"][0])
            packet_path.write_text(json.dumps(packet, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "packet_key_case_set_mismatch"):
                aggregate(
                    packet_path=packet_path,
                    key_path=key_path,
                    review_paths=reviews,
                    run_root=run_root,
                    run_anchor=anchor,
                    anchor_git_commit=ANCHOR_COMMIT,
                )

        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            run_root, packet_path, key_path, reviews, anchor = _write_packet_and_reviews(root)
            first = json.loads(reviews[0].read_text(encoding="utf-8"))
            second = deepcopy(first)
            second["reviewer_id"] = "different-id-same-body"
            second["cases"].reverse()
            reviews[1].write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate_reviewer_content"):
                aggregate(
                    packet_path=packet_path,
                    key_path=key_path,
                    review_paths=reviews,
                    run_root=run_root,
                    run_anchor=anchor,
                    anchor_git_commit=ANCHOR_COMMIT,
                )

    def test_review_metadata_and_candidate_extras_are_rejected(self):
        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            run_root, packet_path, key_path, reviews, anchor = _write_packet_and_reviews(root)
            review = json.loads(reviews[0].read_text(encoding="utf-8"))
            review["revealed_variant"] = CANDIDATE_VARIANT
            reviews[0].write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "review_version_invalid"):
                aggregate(
                    packet_path=packet_path,
                    key_path=key_path,
                    review_paths=reviews,
                    run_root=run_root,
                    run_anchor=anchor,
                    anchor_git_commit=ANCHOR_COMMIT,
                )

        with TemporaryDirectory(dir=TEST_REPO_ROOT) as directory:
            root = Path(directory)
            run_root, packet_path, key_path, reviews, anchor = _write_packet_and_reviews(root)
            review = json.loads(reviews[0].read_text(encoding="utf-8"))
            review["cases"][0]["candidate_a"]["variant"] = CANDIDATE_VARIANT
            reviews[0].write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "review_axes_invalid"):
                aggregate(
                    packet_path=packet_path,
                    key_path=key_path,
                    review_paths=reviews,
                    run_root=run_root,
                    run_anchor=anchor,
                    anchor_git_commit=ANCHOR_COMMIT,
                )


if __name__ == "__main__":
    unittest.main()
