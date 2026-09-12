"""Validate and aggregate independently authored blinded Tavern reviews."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


AXES = (
    "false_premise_correction",
    "relationship_and_permission_fidelity",
    "epistemic_and_temporal_invention",
    "task_adherence",
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


def _review_by_case(review: dict[str, object], expected_ids: set[str]):
    if review.get("version") != "m3-tavern-blind-review-v1":
        raise ValueError("review_version_invalid")
    reviewer_id = review.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id:
        raise ValueError("reviewer_id_invalid")
    rows = review.get("cases")
    if not isinstance(rows, list):
        raise ValueError("review_cases_invalid")
    by_id = {row.get("case_id"): row for row in rows if isinstance(row, dict)}
    if set(by_id) != expected_ids or len(rows) != len(expected_ids):
        raise ValueError(f"review_case_set_invalid:{reviewer_id}")
    for case_id, row in by_id.items():
        for candidate_name in ("candidate_a", "candidate_b"):
            candidate = row.get(candidate_name)
            axes = candidate.get("axes") if isinstance(candidate, dict) else None
            if not isinstance(axes, dict) or set(axes) != set(AXES):
                raise ValueError(
                    f"review_axes_invalid:{reviewer_id}:{case_id}:{candidate_name}"
                )
            if any(grade not in GRADES for grade in axes.values()):
                raise ValueError(
                    f"review_grade_invalid:{reviewer_id}:{case_id}:{candidate_name}"
                )
    return reviewer_id, by_id


def aggregate(
    *,
    packet_path: Path,
    key_path: Path,
    review_paths: list[Path],
) -> dict[str, object]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    packet_rows = packet.get("cases")
    key_rows = key.get("cases")
    if not isinstance(packet_rows, list) or not isinstance(key_rows, list):
        raise ValueError("paired_packet_or_key_invalid")
    packet_by_id = {row["case_id"]: row for row in packet_rows}
    key_by_id = {row["case_id"]: row for row in key_rows}
    expected_ids = set(packet_by_id)
    if set(key_by_id) != expected_ids or len(packet_rows) != len(expected_ids):
        raise ValueError("paired_packet_key_case_set_mismatch")
    packet_file_sha256 = _file_digest(packet_path)
    if key.get("packet_sha256") != _digest(packet):
        raise ValueError("paired_packet_canonical_digest_mismatch")
    for case_id, packet_row in packet_by_id.items():
        key_row = key_by_id[case_id]
        if key_row.get("source_sha256") != _digest(packet_row["authoritative_source"]):
            raise ValueError(f"paired_source_digest_mismatch:{case_id}")
        for candidate_name in ("candidate_a", "candidate_b"):
            if key_row.get(f"{candidate_name}_sha256") != _digest(
                packet_row[candidate_name]
            ):
                raise ValueError(f"paired_candidate_digest_mismatch:{case_id}:{candidate_name}")

    reviewer_results: list[dict[str, object]] = []
    all_reductions: list[set[str]] = []
    all_regressions: list[set[str]] = []
    seen_reviewer_ids: set[str] = set()
    for review_path in review_paths:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review.get("packet_file_sha256") != packet_file_sha256:
            raise ValueError("review_packet_file_digest_mismatch")
        reviewer_id, review_by_id = _review_by_case(review, expected_ids)
        if reviewer_id in seen_reviewer_ids:
            raise ValueError("duplicate_reviewer_id")
        seen_reviewer_ids.add(reviewer_id)
        initial_counts: Counter[str] = Counter()
        intervention_counts: Counter[str] = Counter()
        major_reductions: set[str] = set()
        new_major_regressions: set[str] = set()
        evaluable_pairs = 0
        not_evaluable_pairs = 0
        for case_id in sorted(expected_ids):
            labels = key_by_id[case_id].get("labels")
            if not isinstance(labels, dict) or set(labels) != {"candidate_a", "candidate_b"}:
                raise ValueError(f"paired_labels_invalid:{case_id}")
            inverse = {label: candidate for candidate, label in labels.items()}
            if "initial" not in inverse:
                raise ValueError(f"paired_initial_label_missing:{case_id}")
            intervention_labels = set(inverse) - {"initial"}
            if len(intervention_labels) != 1:
                raise ValueError(f"paired_intervention_label_invalid:{case_id}")
            intervention_label = next(iter(intervention_labels))
            initial_axes = review_by_id[case_id][inverse["initial"]]["axes"]
            intervention_axes = review_by_id[case_id][inverse[intervention_label]]["axes"]
            if intervention_label == "repair_failed":
                if set(intervention_axes.values()) != {"not_evaluable"}:
                    raise ValueError(f"failed_repair_was_graded:{reviewer_id}:{case_id}")
                not_evaluable_pairs += 1
                continue
            if "not_evaluable" in initial_axes.values() or "not_evaluable" in intervention_axes.values():
                raise ValueError(f"evaluable_pair_has_missing_grade:{reviewer_id}:{case_id}")
            evaluable_pairs += 1
            initial_counts.update(initial_axes.values())
            intervention_counts.update(intervention_axes.values())
            for axis in AXES:
                pair_axis = f"{case_id}:{axis}"
                if initial_axes[axis] == "major" and intervention_axes[axis] != "major":
                    major_reductions.add(pair_axis)
                if initial_axes[axis] != "major" and intervention_axes[axis] == "major":
                    new_major_regressions.add(pair_axis)
        all_reductions.append(major_reductions)
        all_regressions.append(new_major_regressions)
        reviewer_results.append(
            {
                "reviewer_id": reviewer_id,
                "review_file": _display_path(review_path),
                "review_file_sha256": _file_digest(review_path),
                "evaluable_pairs": evaluable_pairs,
                "not_evaluable_pairs": not_evaluable_pairs,
                "initial_axes": dict(sorted(initial_counts.items())),
                "intervention_axes": dict(sorted(intervention_counts.items())),
                "major_reductions": sorted(major_reductions),
                "new_major_regressions": sorted(new_major_regressions),
            }
        )
    shared_reductions = set.intersection(*all_reductions) if all_reductions else set()
    any_regressions = set.union(*all_regressions) if all_regressions else set()
    all_repairs_evaluable = all(
        result["not_evaluable_pairs"] == 0 for result in reviewer_results
    )
    return {
        "version": "m3-tavern-paired-review-aggregate-v1",
        "packet_file": _display_path(packet_path),
        "packet_file_sha256": packet_file_sha256,
        "packet_canonical_sha256": _digest(packet),
        "key_file": _display_path(key_path),
        "key_file_sha256": _file_digest(key_path),
        "reviewers": reviewer_results,
        "shared_major_reductions": sorted(shared_reductions),
        "any_new_major_regressions": sorted(any_regressions),
        "decision_rule_status": "post_hoc_conservative_not_preregistered",
        "decision_rule": (
            "At least three pair-axis major reductions confirmed by every reviewer, "
            "zero new major regressions from any reviewer, and no unavailable repair candidate."
        ),
        "promotion_passed": (
            len(shared_reductions) >= 3
            and not any_regressions
            and all_repairs_evaluable
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(
        packet_path=args.packet,
        key_path=args.key,
        review_paths=args.review,
    )
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
