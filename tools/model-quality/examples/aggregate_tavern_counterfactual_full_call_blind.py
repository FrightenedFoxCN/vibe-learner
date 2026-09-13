"""Fail-closed aggregation for two isolated Tavern full-call blind reviews."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from examples.export_tavern_counterfactual_full_call_blind import (
    AXES, KEY_VERSION, PACKET_VERSION, REVIEW_SEED, UNAVAILABLE,
    PREREG_PATH, build_packet, file_sha, value_sha,
)
from vibe_learner.tavern_counterfactual_full_call_blind import CAMPAIGN_ID, GATE


CANDIDATE_AXES = AXES[:-1]
GRADES = {"pass", "minor", "major", "not_evaluable"}
REVIEW_VERSION = "m3-tavern-counterfactual-production-full-call-blind-review-v1"


def _validate_review(review: object, *, pair_ids: set[str], packet_file_sha256: str):
    if not isinstance(review, dict) or set(review) != {"version", "reviewer_id", "packet_file_sha256", "cases"}:
        raise ValueError("tavern_full_call_review_schema_invalid")
    reviewer_id = review.get("reviewer_id")
    rows = review.get("cases")
    if (
        review.get("version") != REVIEW_VERSION
        or not isinstance(reviewer_id, str)
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", reviewer_id) is None
        or review.get("packet_file_sha256") != packet_file_sha256
        or not isinstance(rows, list)
    ):
        raise ValueError("tavern_full_call_review_header_invalid")
    by_id = {row.get("pair_id"): row for row in rows if isinstance(row, dict)}
    if len(rows) != 10 or set(by_id) != pair_ids:
        raise ValueError("tavern_full_call_review_pair_set_invalid")
    for pair_id, row in by_id.items():
        if set(row) != {"pair_id", "candidate_a", "candidate_b", "counterfactual_sensitivity"}:
            raise ValueError(f"tavern_full_call_review_row_schema_invalid:{pair_id}")
        for label in ("candidate_a", "candidate_b"):
            candidate = row.get(label)
            if (
                not isinstance(candidate, dict) or set(candidate) != {"axes", "rationale"}
                or not isinstance(candidate.get("axes"), dict)
                or set(candidate["axes"]) != set(CANDIDATE_AXES)
                or any(value not in GRADES for value in candidate["axes"].values())
                or not isinstance(candidate.get("rationale"), str) or not candidate["rationale"].strip()
            ):
                raise ValueError(f"tavern_full_call_review_candidate_invalid:{pair_id}:{label}")
        sensitivity = row.get("counterfactual_sensitivity")
        if (
            not isinstance(sensitivity, dict) or set(sensitivity) != {"grade", "rationale"}
            or sensitivity.get("grade") not in GRADES
            or not isinstance(sensitivity.get("rationale"), str) or not sensitivity["rationale"].strip()
        ):
            raise ValueError(f"tavern_full_call_review_sensitivity_invalid:{pair_id}")
    return reviewer_id, by_id


def aggregate(
    *, packet_path: Path, key_path: Path, review_paths: list[Path],
    run_root: Path, prereg_git_commit: str, prereg_path: Path = PREREG_PATH,
) -> dict[str, object]:
    if len(review_paths) != 2:
        raise ValueError("tavern_full_call_requires_exactly_two_reviewers")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    rebuilt_packet, rebuilt_key = build_packet(
        run_root=run_root, prereg_git_commit=prereg_git_commit,
        prereg_path=prereg_path, seed=REVIEW_SEED,
    )
    if packet != rebuilt_packet or key != rebuilt_key:
        raise ValueError("tavern_full_call_packet_key_run_binding_mismatch")
    if (
        packet.get("version") != PACKET_VERSION or key.get("version") != KEY_VERSION
        or key.get("campaign_id") != CAMPAIGN_ID or key.get("gate") != GATE
        or key.get("packet_canonical_sha256") != value_sha(packet)
    ):
        raise ValueError("tavern_full_call_packet_key_invalid")
    packet_rows = packet.get("cases")
    key_rows = key.get("cases")
    if not isinstance(packet_rows, list) or not isinstance(key_rows, list):
        raise ValueError("tavern_full_call_packet_key_cases_invalid")
    if set(packet) != {"version", "scope", "review_axes", "grading", "rubric", "cases"}:
        raise ValueError("tavern_full_call_packet_metadata_leak")
    if any(not isinstance(row, dict) or set(row) != {"pair_id", "candidate_a", "candidate_b"} for row in packet_rows):
        raise ValueError("tavern_full_call_packet_metadata_leak")
    packet_by_id = {row["pair_id"]: row for row in packet_rows}
    key_by_id = {row.get("pair_id"): row for row in key_rows if isinstance(row, dict)}
    if len(packet_rows) != 10 or len(packet_by_id) != 10 or len(key_rows) != 10 or set(key_by_id) != set(packet_by_id):
        raise ValueError("tavern_full_call_packet_key_pair_set_invalid")
    for pair_id, row in packet_by_id.items():
        key_row = key_by_id[pair_id]
        if (
            key_row.get("candidate_a_sha256") != value_sha(row["candidate_a"])
            or key_row.get("candidate_b_sha256") != value_sha(row["candidate_b"])
        ):
            raise ValueError(f"tavern_full_call_candidate_digest_invalid:{pair_id}")
        unavailable = row["candidate_a"] == UNAVAILABLE
        if unavailable != (row["candidate_b"] == UNAVAILABLE) or key_row.get("strict_pair") != (not unavailable):
            raise ValueError(f"tavern_full_call_asymmetric_sentinel:{pair_id}")

    packet_file_sha256 = file_sha(packet_path)
    seen_ids: set[str] = set()
    seen_bodies: set[str] = set()
    reviewer_rows: list[dict[str, object]] = []
    confirmation_sets: list[set[str]] = []
    any_new_major: set[str] = set()
    for review_path in review_paths:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        reviewer_id, rows = _validate_review(
            review, pair_ids=set(packet_by_id), packet_file_sha256=packet_file_sha256,
        )
        body_sha = value_sha([rows[key] for key in sorted(rows)])
        if reviewer_id in seen_ids or body_sha in seen_bodies:
            raise ValueError("tavern_full_call_duplicate_reviewer_or_body")
        seen_ids.add(reviewer_id)
        seen_bodies.add(body_sha)
        confirmations: set[str] = set()
        reviewer_majors: set[str] = set()
        evaluable = 0
        for pair_id, packet_row in packet_by_id.items():
            unavailable = packet_row["candidate_a"] == UNAVAILABLE
            row = rows[pair_id]
            candidate_grades = [
                grade for label in ("candidate_a", "candidate_b")
                for grade in row[label]["axes"].values()
            ]
            sensitivity = row["counterfactual_sensitivity"]["grade"]
            all_grades = candidate_grades + [sensitivity]
            if unavailable:
                if set(all_grades) != {"not_evaluable"}:
                    raise ValueError(f"tavern_full_call_unavailable_was_graded:{reviewer_id}:{pair_id}")
                continue
            if "not_evaluable" in all_grades:
                raise ValueError(f"tavern_full_call_evaluable_missing_grade:{reviewer_id}:{pair_id}")
            evaluable += 1
            for label in ("candidate_a", "candidate_b"):
                for axis, grade in row[label]["axes"].items():
                    if grade == "major":
                        reviewer_majors.add(f"{pair_id}:{label}:{axis}")
            if sensitivity == "major":
                reviewer_majors.add(f"{pair_id}:counterfactual_sensitivity")
            if (
                row["candidate_a"]["axes"]["authority_fidelity"] == "pass"
                and row["candidate_b"]["axes"]["authority_fidelity"] == "pass"
                and sensitivity == "pass"
            ):
                confirmations.add(pair_id)
        any_new_major |= reviewer_majors
        confirmation_sets.append(confirmations)
        reviewer_rows.append({
            "reviewer_id": reviewer_id, "review_file_sha256": file_sha(review_path),
            "evaluable_families": evaluable,
            "authority_and_sensitivity_confirmed": sorted(confirmations),
            "new_majors": sorted(reviewer_majors),
        })
    shared_confirmed = set.intersection(*confirmation_sets)
    strict_count = sum(row.get("strict_pair") is True for row in key_by_id.values())
    denied_evaluable = sum(row.get("strict_pair") is True and row.get("second_polarity") == "denied" for row in key_by_id.values())
    unknown_evaluable = sum(row.get("strict_pair") is True and row.get("second_polarity") == "explicitly_unknown" for row in key_by_id.values())
    passed = (
        strict_count >= GATE["double_strict_min"]
        and denied_evaluable >= GATE["denied_evaluable_min"]
        and unknown_evaluable >= GATE["explicitly_unknown_evaluable_min"]
        and len(shared_confirmed) >= GATE["shared_authority_and_sensitivity_min"]
        and len(any_new_major) <= GATE["reviewer_new_major_max"]
    )
    return {
        "version": "m3-tavern-counterfactual-production-full-call-blind-aggregate-v1",
        "campaign_id": CAMPAIGN_ID, "denominator_families": 10,
        "strict_pairs": strict_count, "denied_evaluable": denied_evaluable,
        "explicitly_unknown_evaluable": unknown_evaluable,
        "shared_authority_and_sensitivity": sorted(shared_confirmed),
        "any_reviewer_new_majors": sorted(any_new_major),
        "reviewers": reviewer_rows, "gate": GATE,
        "packet_file_sha256": packet_file_sha256,
        "key_file_sha256": file_sha(key_path),
        "prereg_git_commit": prereg_git_commit,
        "message_commit_scope": "primary_output_only",
        "promotion_passed": passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--review", action="append", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--prereg-git-commit", required=True)
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(packet_path=args.packet, key_path=args.key, review_paths=args.review,
                       run_root=args.run, prereg_git_commit=args.prereg_git_commit,
                       prereg_path=args.prereg)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
