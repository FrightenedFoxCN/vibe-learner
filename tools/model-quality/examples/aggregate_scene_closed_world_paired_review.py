"""Validate and aggregate two independently authored blinded Scene reviews."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from examples.export_scene_closed_world_paired_review import REVIEW_SEED, build_packet


AXES = (
    "topology_fidelity",
    "object_fidelity",
    "supported_detail_deletion",
    "relationship_and_permission_invention",
    "epistemic_and_temporal_invention",
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


def _unavailable(candidate: object) -> bool:
    return (
        isinstance(candidate, dict)
        and candidate.get("not_evaluable") is True
        and candidate.get("reason") == "strict_candidate_unavailable"
    )


def _review_by_case(review: dict[str, object], expected_ids: set[str]):
    if review.get("version") != "m3-scene-closed-world-blind-review-v1":
        raise ValueError("scene_review_version_invalid")
    reviewer_id = review.get("reviewer_id")
    rows = review.get("cases")
    if not isinstance(reviewer_id, str) or not reviewer_id or not isinstance(rows, list):
        raise ValueError("scene_reviewer_or_cases_invalid")
    by_id = {row.get("case_id"): row for row in rows if isinstance(row, dict)}
    if set(by_id) != expected_ids or len(rows) != len(expected_ids):
        raise ValueError(f"scene_review_case_set_invalid:{reviewer_id}")
    for case_id, row in by_id.items():
        for candidate_name in ("candidate_a", "candidate_b"):
            candidate = row.get(candidate_name)
            axes = candidate.get("axes") if isinstance(candidate, dict) else None
            if not isinstance(axes, dict) or set(axes) != set(AXES):
                raise ValueError(
                    f"scene_review_axes_invalid:{reviewer_id}:{case_id}:{candidate_name}"
                )
            if any(grade not in GRADES for grade in axes.values()):
                raise ValueError(
                    f"scene_review_grade_invalid:{reviewer_id}:{case_id}:{candidate_name}"
                )
    return reviewer_id, by_id


def aggregate(
    *,
    packet_path: Path,
    key_path: Path,
    review_paths: list[Path],
    baseline_run: Path,
    repair_run: Path,
) -> dict[str, object]:
    if len(review_paths) != 2:
        raise ValueError("scene_review_requires_exactly_two_reviewers")
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    key = json.loads(key_path.read_text(encoding="utf-8"))
    if (
        packet.get("version") != "m3-scene-closed-world-blinded-paired-review-v1"
        or key.get("version")
        != "m3-scene-closed-world-blinded-paired-review-key-v2"
        or packet.get("review_axes") != list(AXES)
    ):
        raise ValueError("scene_packet_or_key_version_invalid")
    packet_rows = packet.get("cases")
    key_rows = key.get("cases")
    if not isinstance(packet_rows, list) or not isinstance(key_rows, list):
        raise ValueError("scene_packet_or_key_invalid")
    packet_by_id = {row["case_id"]: row for row in packet_rows}
    key_by_id = {row["case_id"]: row for row in key_rows}
    expected_ids = set(packet_by_id)
    if (
        set(key_by_id) != expected_ids
        or len(packet_rows) != 6
        or len(packet_by_id) != 6
        or len(key_rows) != 6
        or len(key_by_id) != 6
    ):
        raise ValueError("scene_packet_key_case_set_mismatch")
    expected_packet, expected_key = build_packet(
        baseline_run=baseline_run,
        repair_run=repair_run,
        seed=REVIEW_SEED,
    )
    if packet != expected_packet or key != expected_key:
        raise ValueError("scene_packet_key_run_binding_mismatch")
    if key.get("packet_canonical_sha256") != _digest(packet):
        raise ValueError("scene_packet_canonical_digest_mismatch")
    for case_id, packet_row in packet_by_id.items():
        key_row = key_by_id[case_id]
        if key_row.get("source_sha256") != _digest(packet_row["authoritative_source"]):
            raise ValueError(f"scene_source_digest_mismatch:{case_id}")
        for candidate_name in ("candidate_a", "candidate_b"):
            if key_row.get(f"{candidate_name}_sha256") != _digest(
                packet_row[candidate_name]
            ):
                raise ValueError(
                    f"scene_candidate_digest_mismatch:{case_id}:{candidate_name}"
                )

    packet_file_sha256 = _file_digest(packet_path)
    reviewers: list[dict[str, object]] = []
    all_reductions: list[set[str]] = []
    all_regressions: list[set[str]] = []
    seen_ids: set[str] = set()
    strict_repaired_candidates = sum(
        row.get("repair_candidate_available") is True for row in key_by_id.values()
    )
    review_case_digests: set[str] = set()
    for review_path in review_paths:
        review = json.loads(review_path.read_text(encoding="utf-8"))
        if review.get("packet_file_sha256") != packet_file_sha256:
            raise ValueError("scene_review_packet_file_digest_mismatch")
        reviewer_id, by_id = _review_by_case(review, expected_ids)
        if reviewer_id in seen_ids:
            raise ValueError("scene_duplicate_reviewer_id")
        seen_ids.add(reviewer_id)
        review_case_digest = _digest(review["cases"])
        if review_case_digest in review_case_digests:
            raise ValueError("scene_duplicate_reviewer_content")
        review_case_digests.add(review_case_digest)
        initial_counts: Counter[str] = Counter()
        repair_counts: Counter[str] = Counter()
        reductions: set[str] = set()
        regressions: set[str] = set()
        evaluable_pairs = 0
        not_evaluable_pairs = 0
        for case_id in sorted(expected_ids):
            labels = key_by_id[case_id].get("labels")
            if not isinstance(labels, dict) or set(labels) != {"candidate_a", "candidate_b"}:
                raise ValueError(f"scene_labels_invalid:{case_id}")
            inverse = {label: candidate for candidate, label in labels.items()}
            if "initial" not in inverse or len(set(inverse) - {"initial"}) != 1:
                raise ValueError(f"scene_labels_invalid:{case_id}")
            repair_label = next(iter(set(inverse) - {"initial"}))
            initial_name = inverse["initial"]
            repair_name = inverse[repair_label]
            initial_axes = by_id[case_id][initial_name]["axes"]
            repair_axes = by_id[case_id][repair_name]["axes"]
            packet_initial = packet_by_id[case_id][initial_name]
            packet_repair = packet_by_id[case_id][repair_name]
            declared_available = key_by_id[case_id].get("repair_candidate_available")
            if (
                declared_available is True
                and (repair_label != "final" or _unavailable(packet_initial) or _unavailable(packet_repair))
            ) or (
                declared_available is False
                and (
                    repair_label != "repair_failed"
                    or not _unavailable(packet_initial)
                    or not _unavailable(packet_repair)
                )
            ):
                raise ValueError(f"scene_repair_availability_mismatch:{case_id}")
            unavailable = _unavailable(packet_initial) or _unavailable(packet_repair)
            if unavailable:
                for candidate_name, candidate in (
                    (initial_name, packet_initial),
                    (repair_name, packet_repair),
                ):
                    if _unavailable(candidate) and set(
                        by_id[case_id][candidate_name]["axes"].values()
                    ) != {"not_evaluable"}:
                        raise ValueError(
                            f"scene_unavailable_candidate_was_graded:{reviewer_id}:{case_id}"
                        )
                not_evaluable_pairs += 1
                continue
            if "not_evaluable" in initial_axes.values() or "not_evaluable" in repair_axes.values():
                raise ValueError(f"scene_evaluable_pair_missing_grade:{reviewer_id}:{case_id}")
            evaluable_pairs += 1
            initial_counts.update(initial_axes.values())
            repair_counts.update(repair_axes.values())
            for axis in AXES:
                pair_axis = f"{case_id}:{axis}"
                if initial_axes[axis] == "major" and repair_axes[axis] != "major":
                    reductions.add(pair_axis)
                if initial_axes[axis] != "major" and repair_axes[axis] == "major":
                    regressions.add(pair_axis)
        all_reductions.append(reductions)
        all_regressions.append(regressions)
        reviewers.append({
            "reviewer_id": reviewer_id,
            "review_file": _display_path(review_path),
            "review_file_sha256": _file_digest(review_path),
            "evaluable_pairs": evaluable_pairs,
            "not_evaluable_pairs": not_evaluable_pairs,
            "initial_axes": dict(sorted(initial_counts.items())),
            "repair_axes": dict(sorted(repair_counts.items())),
            "major_reductions": sorted(reductions),
            "new_major_regressions": sorted(regressions),
        })
    shared_reductions = set.intersection(*all_reductions)
    any_regressions = set.union(*all_regressions)
    return {
        "version": "m3-scene-closed-world-paired-review-aggregate-v1",
        "packet_file": _display_path(packet_path),
        "packet_file_sha256": packet_file_sha256,
        "packet_canonical_sha256": _digest(packet),
        "key_file": _display_path(key_path),
        "key_file_sha256": _file_digest(key_path),
        "strict_repaired_candidates_over_six": strict_repaired_candidates,
        "reviewers": reviewers,
        "shared_major_reductions": sorted(shared_reductions),
        "any_new_major_regressions": sorted(any_regressions),
        "decision_rule_status": "preregistered",
        "reviewer_independence_evidence": "external isolated-agent orchestration; duplicate reviewer ids and identical review bodies rejected here",
        "promotion_passed": (
            strict_repaired_candidates >= 5
            and len(shared_reductions) >= 3
            and not any_regressions
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", required=True)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--repair-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = aggregate(
        packet_path=args.packet,
        key_path=args.key,
        review_paths=args.review,
        baseline_run=args.baseline_run,
        repair_run=args.repair_run,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
