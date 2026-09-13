"""Strictly aggregate two independent absolute-blind Persona/Scene reviews."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from examples.export_persona_scene_full_call_blind import (
    KEY_VERSION, PACKET_VERSION, REVIEW_SEED, UNAVAILABLE, build_packet,
    canonical_bytes, file_sha256, sha256, _committed_preregistration,
)


REVIEW_VERSION = "persona-scene-production-full-call-absolute-blind-review-v1"
AGGREGATE_VERSION = "persona-scene-production-full-call-absolute-blind-aggregate-v1"
PERSONA_AXES = (
    "relationship_fidelity", "permission_fidelity", "profession_fidelity",
    "shared_history_fidelity", "epistemic_fidelity", "format_adherence",
)
PERSONA_CRITICAL = PERSONA_AXES[:5]
SCENE_AXES = (
    "topology_fidelity", "object_fidelity", "permission_fidelity",
    "source_fidelity", "format_adherence",
)
SCENE_CRITICAL = SCENE_AXES[:3]
GRADES = {"pass", "minor", "major", "not_evaluable"}


def _validate_domain_review(item: object, *, axes: tuple[str, ...], available: bool) -> dict[str, str]:
    if not isinstance(item, dict) or set(item) != {"axes", "rationale"}:
        raise ValueError("full_call_review_domain_schema_invalid")
    grades = item.get("axes")
    rationale = item.get("rationale")
    if (
        not isinstance(grades, dict)
        or set(grades) != set(axes)
        or any(value not in GRADES for value in grades.values())
        or not isinstance(rationale, str)
        or len(rationale.strip()) < 12
    ):
        raise ValueError("full_call_review_domain_content_invalid")
    values = set(grades.values())
    if available and "not_evaluable" in values:
        raise ValueError("full_call_available_proposal_not_graded")
    if not available and values != {"not_evaluable"}:
        raise ValueError("full_call_unavailable_proposal_was_graded")
    return grades


def aggregate(*, packet_path: Path, key_path: Path, review_paths: list[Path], run_root: Path, prereg_git_commit: str) -> dict[str, object]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    prereg, _, _ = _committed_preregistration(prereg_git_commit)
    if file_sha256(Path(__file__)) != prereg["source_bindings"]["strict_two_reviewer_aggregator"]:
        raise ValueError("full_call_aggregator_worktree_drift")
    expected_packet, expected_key = build_packet(run_root, prereg_git_commit=prereg_git_commit, seed=REVIEW_SEED)
    if packet != expected_packet or key != expected_key:
        raise ValueError("full_call_packet_or_key_not_rebuilt_from_frozen_run")
    if packet.get("version") != PACKET_VERSION or key.get("version") != KEY_VERSION:
        raise ValueError("full_call_packet_or_key_version_invalid")
    if key.get("packet_canonical_sha256") != sha256(packet):
        raise ValueError("full_call_packet_key_binding_invalid")
    packet_cases = packet.get("cases")
    key_cases = key.get("cases")
    if not isinstance(packet_cases, list) or not isinstance(key_cases, list) or len(packet_cases) != 8 or len(key_cases) != 8:
        raise ValueError("full_call_denominator_invalid")
    packet_by_token = {row.get("anonymous_token"): row for row in packet_cases if isinstance(row, dict)}
    key_by_token = {row.get("anonymous_token"): row for row in key_cases if isinstance(row, dict)}
    if len(packet_by_token) != 8 or set(packet_by_token) != set(key_by_token):
        raise ValueError("full_call_anonymous_token_set_invalid")
    if len(review_paths) != 2:
        raise ValueError("full_call_exactly_two_reviews_required")
    packet_bytes_sha = file_sha256(packet_path)
    reviewers = []
    reviewer_ids: set[str] = set()
    body_hashes: set[str] = set()
    persona_major_any: set[str] = set()
    scene_major_any: set[str] = set()
    for path in review_paths:
        review = json.loads(path.read_text(encoding="utf-8"))
        reviewer_id = review.get("reviewer_id")
        rows = review.get("cases")
        if (
            review.get("version") != REVIEW_VERSION
            or review.get("packet_file_sha256") != packet_bytes_sha
            or not isinstance(reviewer_id, str)
            or not reviewer_id.strip()
            or reviewer_id in reviewer_ids
            or not isinstance(rows, list)
            or len(rows) != 8
        ):
            raise ValueError("full_call_review_envelope_invalid")
        body_hash = hashlib.sha256(canonical_bytes(rows)).hexdigest()
        if body_hash in body_hashes:
            raise ValueError("full_call_duplicate_review_body")
        reviewer_ids.add(reviewer_id)
        body_hashes.add(body_hash)
        by_token = {row.get("anonymous_token"): row for row in rows if isinstance(row, dict)}
        if len(by_token) != 8 or set(by_token) != set(packet_by_token):
            raise ValueError("full_call_review_token_set_invalid")
        reviewer_persona_major = set()
        reviewer_scene_major = set()
        for token, packet_row in packet_by_token.items():
            row = by_token[token]
            if set(row) != {"anonymous_token", "persona", "scene"}:
                raise ValueError("full_call_review_case_schema_invalid")
            persona_available = packet_row["anonymous_persona_proposal"] != UNAVAILABLE
            scene_available = packet_row["anonymous_scene_proposal"] != UNAVAILABLE
            persona_grades = _validate_domain_review(row["persona"], axes=PERSONA_AXES, available=persona_available)
            scene_grades = _validate_domain_review(row["scene"], axes=SCENE_AXES, available=scene_available)
            reviewer_persona_major.update(f"{token}:{axis}" for axis in PERSONA_CRITICAL if persona_grades[axis] == "major")
            reviewer_scene_major.update(f"{token}:{axis}" for axis in SCENE_CRITICAL if scene_grades[axis] == "major")
        persona_major_any.update(reviewer_persona_major)
        scene_major_any.update(reviewer_scene_major)
        reviewers.append({
            "reviewer_id": reviewer_id,
            "review_file_sha256": file_sha256(path),
            "persona_critical_majors": sorted(reviewer_persona_major),
            "scene_critical_majors": sorted(reviewer_scene_major),
        })
    persona_strict = sum(row.get("persona_strict_lifecycle") is True for row in key_cases)
    scene_strict = sum(row.get("scene_strict_lifecycle") is True for row in key_cases)
    joint_strict = sum(row.get("joint_strict_lifecycle") is True for row in key_cases)
    lifecycle_failures = [{
        "family_id": row["family_id"],
        "sample_status": row["sample_status"],
        "persona_status": row["persona_status"],
        "scene_status": row["scene_status"],
    } for row in key_cases if not row.get("joint_strict_lifecycle")]
    promotion_passed = (
        persona_strict >= 7
        and scene_strict >= 7
        and joint_strict >= 7
        and not persona_major_any
        and not scene_major_any
    )
    return {
        "version": AGGREGATE_VERSION,
        "campaign_id": key["campaign_id"],
        "packet_file_sha256": packet_bytes_sha,
        "key_file_sha256": file_sha256(key_path),
        "denominators": {"persona": 8, "scene": 8, "joint": 8},
        "strict_lifecycle_success": {"persona": persona_strict, "scene": scene_strict, "joint": joint_strict},
        "reviewers": reviewers,
        "persona_critical_majors_worst_of_two": sorted(persona_major_any),
        "scene_critical_majors_worst_of_two": sorted(scene_major_any),
        "lifecycle_failures": lifecycle_failures,
        "gate": {
            "persona": "at_least_7_of_8_strict_and_no_reviewer_major_on_relationship_permission_profession_shared_history_epistemic",
            "scene": "at_least_7_of_8_strict_and_no_reviewer_major_on_topology_object_permission",
            "joint": "at_least_7_of_8_both_domains_strict",
        },
        "semantic_review_is_not_harness_commit_evidence": True,
        "failure_policy": "no_rerun_no_replacement",
        "promotion_passed": promotion_passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--prereg-git-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(packet_path=args.packet, key_path=args.key, review_paths=args.review, run_root=args.run, prereg_git_commit=args.prereg_git_commit)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
