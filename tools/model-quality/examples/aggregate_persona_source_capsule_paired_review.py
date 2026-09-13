"""Validate and aggregate two independent blinded Persona capsule reviews."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from examples.export_persona_source_capsule_paired_review import (
    BASELINE_VARIANT,
    CANDIDATE_VARIANT,
    REVIEW_SEED,
    UNAVAILABLE,
    build_packet,
    load_committed_run_anchor,
)


AXES = (
    "relationship_fidelity",
    "permission_fidelity",
    "profession_uncertainty",
    "shared_history_invention",
    "epistemic_provenance",
    "task_format_adherence",
)
GRADES = {"pass", "minor", "major", "not_evaluable"}
REPO_ROOT = Path(__file__).resolve().parents[3]


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def _unavailable(value: object) -> bool:
    return value == UNAVAILABLE


def _review_by_case(review: dict[str, object], expected_ids: set[str]):
    if (
        not isinstance(review, dict)
        or set(review) != {"version", "reviewer_id", "packet_file_sha256", "cases"}
        or review.get("version") != "m3-persona-source-capsule-blind-review-v1"
    ):
        raise ValueError("persona_capsule_review_version_invalid")
    reviewer_id = review.get("reviewer_id")
    rows = review.get("cases")
    if (
        not isinstance(reviewer_id, str)
        or re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}", reviewer_id) is None
        or not isinstance(rows, list)
    ):
        raise ValueError("persona_capsule_reviewer_or_cases_invalid")
    by_id = {
        row.get("case_id"): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("case_id"), str)
    }
    if set(by_id) != expected_ids or len(rows) != len(expected_ids):
        raise ValueError(f"persona_capsule_review_case_set_invalid:{reviewer_id}")
    for case_id, row in by_id.items():
        if set(row) != {"case_id", "candidate_a", "candidate_b"}:
            raise ValueError(
                f"persona_capsule_review_row_metadata_invalid:{reviewer_id}:{case_id}"
            )
        for candidate_name in ("candidate_a", "candidate_b"):
            candidate = row.get(candidate_name)
            axes = candidate.get("axes") if isinstance(candidate, dict) else None
            rationale = candidate.get("rationale") if isinstance(candidate, dict) else None
            if (
                not isinstance(candidate, dict)
                or set(candidate) != {"axes", "rationale"}
                or not isinstance(axes, dict)
                or set(axes) != set(AXES)
                or not isinstance(rationale, str)
                or not rationale.strip()
            ):
                raise ValueError(
                    f"persona_capsule_review_axes_invalid:{reviewer_id}:{case_id}:{candidate_name}"
                )
            if any(grade not in GRADES for grade in axes.values()):
                raise ValueError(
                    f"persona_capsule_review_grade_invalid:{reviewer_id}:{case_id}:{candidate_name}"
                )
    return reviewer_id, by_id


def aggregate(
    *,
    packet_path: Path,
    key_path: Path,
    review_paths: list[Path],
    run_root: Path,
    run_anchor: dict[str, object],
    anchor_git_commit: str,
) -> dict[str, object]:
    if len(review_paths) != 2:
        raise ValueError("persona_capsule_review_requires_exactly_two_reviewers")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    if (
        not isinstance(packet, dict)
        or not isinstance(key, dict)
        or packet.get("version")
        != "m3-persona-source-capsule-blinded-paired-review-v1"
        or key.get("version")
        != "m3-persona-source-capsule-blinded-paired-review-key-v2"
        or packet.get("review_axes") != list(AXES)
        or packet.get("grading") != ["pass", "minor", "major", "not_evaluable"]
        or key.get("seed") != REVIEW_SEED
        or key.get("proposal_commit") != "not_applicable"
        or key.get("persona_save") is not False
        or key.get("run_anchor_sha256") != _digest(run_anchor)
        or key.get("run_anchor_git_commit") != anchor_git_commit
    ):
        raise ValueError("persona_capsule_packet_or_key_version_invalid")
    packet_rows = packet.get("cases")
    key_rows = key.get("cases")
    if not isinstance(packet_rows, list) or not isinstance(key_rows, list):
        raise ValueError("persona_capsule_packet_or_key_invalid")
    if any(
        not isinstance(row, dict)
        or set(row)
        != {"case_id", "authoritative_source", "candidate_a", "candidate_b"}
        for row in packet_rows
    ):
        raise ValueError("persona_capsule_packet_metadata_leak")
    packet_by_id = {
        row.get("case_id"): row for row in packet_rows if isinstance(row, dict)
    }
    key_by_id = {
        row.get("case_id"): row for row in key_rows if isinstance(row, dict)
    }
    expected_ids = set(packet_by_id)
    if (
        len(packet_rows) != 8
        or len(packet_by_id) != 8
        or len(key_rows) != 8
        or len(key_by_id) != 8
        or set(key_by_id) != expected_ids
    ):
        raise ValueError("persona_capsule_packet_key_case_set_mismatch")

    expected_packet, expected_key = build_packet(
        run_root=run_root,
        seed=REVIEW_SEED,
        run_anchor=run_anchor,
        anchor_git_commit=anchor_git_commit,
    )
    if packet != expected_packet or key != expected_key:
        raise ValueError("persona_capsule_packet_key_run_binding_mismatch")
    if (
        key.get("packet_canonical_sha256") != _digest(packet)
        or key.get("manifest_file_sha256") != _file_digest(run_root / "manifest.json")
        or key.get("report_file_sha256") != _file_digest(run_root / "report.json")
    ):
        raise ValueError("persona_capsule_packet_key_digest_mismatch")
    for case_id, packet_row in packet_by_id.items():
        key_row = key_by_id[case_id]
        if key_row.get("source_sha256") != _digest(packet_row["authoritative_source"]):
            raise ValueError(f"persona_capsule_source_digest_mismatch:{case_id}")
        labels = key_row.get("labels")
        if (
            not isinstance(labels, dict)
            or set(labels) != {"candidate_a", "candidate_b"}
            or set(labels.values()) != {BASELINE_VARIANT, CANDIDATE_VARIANT}
        ):
            raise ValueError(f"persona_capsule_labels_invalid:{case_id}")
        for candidate_name in ("candidate_a", "candidate_b"):
            if key_row.get(f"{candidate_name}_sha256") != _digest(
                packet_row[candidate_name]
            ):
                raise ValueError(
                    f"persona_capsule_candidate_digest_mismatch:{case_id}:{candidate_name}"
                )
        unavailable_a = _unavailable(packet_row["candidate_a"])
        unavailable_b = _unavailable(packet_row["candidate_b"])
        declared_strict = key_row.get("pair_strict_candidate")
        if (
            not isinstance(declared_strict, bool)
            or declared_strict != (not unavailable_a and not unavailable_b)
        ):
            raise ValueError(f"persona_capsule_pair_availability_mismatch:{case_id}")
        if unavailable_a != unavailable_b:
            raise ValueError(f"persona_capsule_one_sided_unavailable_leak:{case_id}")

    packet_file_sha256 = _file_digest(packet_path)
    strict_pairs = sum(
        row.get("pair_strict_candidate") is True for row in key_by_id.values()
    )
    reviewers: list[dict[str, object]] = []
    seen_reviewer_ids: set[str] = set()
    seen_review_bodies: set[str] = set()
    reviewer_reductions: list[set[str]] = []
    reviewer_candidate_majors: list[set[str]] = []
    reviewer_capsule_relationship_majors: list[set[str]] = []
    reviewer_capsule_permission_majors: list[set[str]] = []
    for review_path in review_paths:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review.get("packet_file_sha256") != packet_file_sha256:
            raise ValueError("persona_capsule_review_packet_file_digest_mismatch")
        reviewer_id, by_id = _review_by_case(review, expected_ids)
        if reviewer_id in seen_reviewer_ids:
            raise ValueError("persona_capsule_duplicate_reviewer_id")
        seen_reviewer_ids.add(reviewer_id)
        normalized_review_body = [by_id[case_id] for case_id in sorted(by_id)]
        body_digest = _digest(normalized_review_body)
        if body_digest in seen_review_bodies:
            raise ValueError("persona_capsule_duplicate_reviewer_content")
        seen_review_bodies.add(body_digest)
        baseline_counts: Counter[str] = Counter()
        capsule_counts: Counter[str] = Counter()
        reductions: set[str] = set()
        candidate_majors: set[str] = set()
        capsule_relationship_majors: set[str] = set()
        capsule_permission_majors: set[str] = set()
        evaluable_pairs = 0
        not_evaluable_pairs = 0
        for case_id in sorted(expected_ids):
            labels = key_by_id[case_id]["labels"]
            inverse = {label: candidate for candidate, label in labels.items()}
            baseline_name = inverse[BASELINE_VARIANT]
            capsule_name = inverse[CANDIDATE_VARIANT]
            baseline_axes = by_id[case_id][baseline_name]["axes"]
            capsule_axes = by_id[case_id][capsule_name]["axes"]
            packet_baseline = packet_by_id[case_id][baseline_name]
            packet_capsule = packet_by_id[case_id][capsule_name]
            if _unavailable(packet_baseline) or _unavailable(packet_capsule):
                if (
                    set(baseline_axes.values()) != {"not_evaluable"}
                    or set(capsule_axes.values()) != {"not_evaluable"}
                ):
                    raise ValueError(
                        f"persona_capsule_unavailable_pair_was_graded:{reviewer_id}:{case_id}"
                    )
                not_evaluable_pairs += 1
                continue
            if (
                "not_evaluable" in baseline_axes.values()
                or "not_evaluable" in capsule_axes.values()
            ):
                raise ValueError(
                    f"persona_capsule_evaluable_pair_missing_grade:{reviewer_id}:{case_id}"
                )
            evaluable_pairs += 1
            baseline_counts.update(baseline_axes.values())
            capsule_counts.update(capsule_axes.values())
            for axis in AXES:
                item = f"{case_id}:{axis}"
                if baseline_axes[axis] == "major" and capsule_axes[axis] != "major":
                    reductions.add(item)
                if baseline_axes[axis] != "major" and capsule_axes[axis] == "major":
                    candidate_majors.add(item)
            if capsule_axes["relationship_fidelity"] == "major":
                capsule_relationship_majors.add(case_id)
            if capsule_axes["permission_fidelity"] == "major":
                capsule_permission_majors.add(case_id)
        reviewer_reductions.append(reductions)
        reviewer_candidate_majors.append(candidate_majors)
        reviewer_capsule_relationship_majors.append(capsule_relationship_majors)
        reviewer_capsule_permission_majors.append(capsule_permission_majors)
        reviewers.append({
            "reviewer_id": reviewer_id,
            "review_file": _display_path(review_path),
            "review_file_sha256": _file_digest(review_path),
            "evaluable_pairs": evaluable_pairs,
            "not_evaluable_pairs": not_evaluable_pairs,
            "baseline_axes": dict(sorted(baseline_counts.items())),
            "capsule_axes": dict(sorted(capsule_counts.items())),
            "major_reductions": sorted(reductions),
            "candidate_only_majors": sorted(candidate_majors),
            "capsule_relationship_majors": sorted(capsule_relationship_majors),
            "capsule_permission_majors": sorted(capsule_permission_majors),
        })
    shared_reductions = set.intersection(*reviewer_reductions)
    any_candidate_majors = set.union(*reviewer_candidate_majors)
    any_capsule_relationship_majors = set.union(
        *reviewer_capsule_relationship_majors
    )
    any_capsule_permission_majors = set.union(*reviewer_capsule_permission_majors)
    promotion_passed = (
        strict_pairs >= 7
        and len(shared_reductions) >= 4
        and not any_candidate_majors
        and not any_capsule_relationship_majors
        and not any_capsule_permission_majors
    )
    return {
        "version": "m3-persona-source-capsule-paired-review-aggregate-v1",
        "packet_file": _display_path(packet_path),
        "packet_file_sha256": packet_file_sha256,
        "packet_canonical_sha256": _digest(packet),
        "key_file": _display_path(key_path),
        "key_file_sha256": _file_digest(key_path),
        "manifest_file_sha256": key["manifest_file_sha256"],
        "report_file_sha256": key["report_file_sha256"],
        "denominator_pairs": 8,
        "strict_paired_candidates_over_eight": strict_pairs,
        "reviewers": reviewers,
        "shared_major_reductions": sorted(shared_reductions),
        "any_candidate_only_majors": sorted(any_candidate_majors),
        "capsule_relationship_majors_worst_of_two": sorted(
            any_capsule_relationship_majors
        ),
        "capsule_permission_majors_worst_of_two": sorted(
            any_capsule_permission_majors
        ),
        "semantic_scoring_only": True,
        "exact_marker_success_credit": False,
        "decision_rule_status": "preregistered",
        "reviewer_independence_evidence": (
            "external isolated-agent orchestration; duplicate reviewer ids and "
            "identical review bodies rejected here"
        ),
        "proposal_commit": "not_applicable",
        "persona_save": False,
        "promotion_passed": promotion_passed,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--run-anchor", type=Path, required=True)
    parser.add_argument("--run-anchor-git-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_anchor = load_committed_run_anchor(
        args.run_anchor, args.run_anchor_git_commit
    )
    result = aggregate(
        packet_path=args.packet,
        key_path=args.key,
        review_paths=args.review,
        run_root=args.run,
        run_anchor=run_anchor,
        anchor_git_commit=args.run_anchor_git_commit,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
