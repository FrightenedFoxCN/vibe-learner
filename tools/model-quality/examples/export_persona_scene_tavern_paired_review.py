"""Build a blinded paired-review packet for the frozen Tavern repair campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=913502)
    args = parser.parse_args()

    manifest = json.loads((args.run / "manifest.json").read_text())
    cases = manifest["config"]["cases"]
    rng = random.Random(args.seed)
    shuffled_ids = [case["id"] for case in cases]
    rng.shuffle(shuffled_ids)
    intervention_on_a = set(shuffled_ids[: len(shuffled_ids) // 2])
    packet_cases: list[dict[str, object]] = []
    key_cases: list[dict[str, object]] = []
    for case in sorted(cases, key=lambda item: item["id"]):
        evidence_path = (
            args.run
            / case["id"]
            / "conditional-exact-repair"
            / "0"
            / "storage"
            / "tavern-exact-repair-evidence.json"
        )
        evidence = json.loads(evidence_path.read_text())
        initial = evidence["initial_reply"]
        final = evidence.get("final_reply")
        intervention_label = "final" if final is not None else "repair_failed"
        intervention = final or {"not_evaluable": True, "reason": "strict_repair_unavailable"}
        order = (
            [intervention_label, "initial"]
            if case["id"] in intervention_on_a
            else ["initial", intervention_label]
        )
        values = {"initial": initial, intervention_label: intervention}
        labels = {"candidate_a": order[0], "candidate_b": order[1]}
        candidates: dict[str, object] = {
            "candidate_a": values[order[0]],
            "candidate_b": values[order[1]],
        }
        source = json.loads(case["source"])
        packet_cases.append({
            "case_id": case["id"],
            "authoritative_source": source,
            **candidates,
        })
        key_cases.append({
            "case_id": case["id"],
            "labels": labels,
            "source_sha256": digest(source),
            "candidate_a_sha256": digest(candidates["candidate_a"]),
            "candidate_b_sha256": digest(candidates["candidate_b"]),
        })

    packet = {
        "version": "persona-scene-tavern-blinded-paired-review-v1",
        "scope": "authoritative source plus blinded Tavern replies only",
        "review_axes": [
            "false_premise_correction",
            "relationship_and_permission_fidelity",
            "epistemic_and_temporal_invention",
            "task_adherence",
        ],
        "grading": ["pass", "minor", "major", "not_evaluable"],
        "cases": packet_cases,
    }
    key = {
        "version": "persona-scene-tavern-blinded-paired-review-key-v1",
        "packet_sha256": digest(packet),
        "seed": args.seed,
        "cases": key_cases,
    }
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    args.key_output.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
