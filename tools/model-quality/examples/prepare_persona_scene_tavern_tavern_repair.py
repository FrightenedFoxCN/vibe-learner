"""Freeze the confirmation baseline into a conditional Tavern repair replay."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def build_case(
    fixture_row: dict[str, object],
    source_case: dict[str, object],
    evidence: dict[str, object],
) -> dict[str, object]:
    case_id = fixture_row["id"]
    if source_case.get("id") != case_id or evidence.get("case_id") != case_id:
        raise ValueError("repair_case_identity_mismatch")
    generated = evidence.get("generated")
    if not isinstance(generated, dict):
        raise ValueError("repair_generated_output_missing")
    messages = generated.get("tavern_messages")
    if not isinstance(messages, list) or len(messages) != 1:
        raise ValueError("repair_tavern_message_count_invalid")
    message = messages[0]
    frozen_message = {
        key: message.get(key)
        for key in (
            "content",
            "emotion",
            "action",
            "speech_style",
            "addressed_participant_ids",
        )
    }
    gold = {
        "canonical_source": source_case["source"],
        "source_fidelity_constraints": fixture_row["source_fidelity_constraints"],
        "generated": {
            "persona": generated["persona"],
            "scene": generated["scene"],
        },
        "initial_tavern_message": frozen_message,
    }
    return {
        "id": case_id,
        "family": case_id,
        "lane": "tavern-exact-repair",
        "split": "confirmation",
        "provenance": "synthetic-authored",
        "source": source_case["source"],
        "request": fixture_row["user_message"],
        "gold": json.dumps(gold, ensure_ascii=False),
        "rubric": "persona-scene-tavern-exact-repair-v1",
    }


def build_manifest(
    *,
    fixture: dict[str, object],
    baseline_manifest: dict[str, object],
    baseline_run: Path,
    budget_document: dict[str, object],
    transport: str,
) -> dict[str, object]:
    rows = fixture.get("cases")
    source_cases = baseline_manifest.get("config", {}).get("cases")
    if not isinstance(rows, list) or not isinstance(source_cases, list) or len(rows) != 6:
        raise ValueError("repair_baseline_manifest_invalid")
    source_by_id = {row["id"]: row for row in source_cases}
    cases = []
    for row in rows:
        case_id = row["id"]
        evidence_path = (
            baseline_run / case_id / "shadow-chain" / "0" / "storage" / "domain-evidence.json"
        )
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        cases.append(build_case(row, source_by_id[case_id], evidence))
    budget = budget_document.get("budget") or budget_document.get("config", {}).get("budget")
    if not isinstance(budget, dict):
        raise ValueError("repair_budget_missing")
    return {
        "version": "quality-campaign-v1",
        "id": "m3-persona-scene-tavern-exact-repair-20260913-v1",
        "purpose": (
            "Conditional one-wire exact Tavern repair over all six frozen confirmation outputs. "
            "The committed baseline Messages remain immutable. Exact checks are narrow research "
            "triggers with known Scene-semantic recall gaps; independent manual review is required."
        ),
        "transport": transport,
        "adapter": "vibe_learner.persona_scene_tavern_tavern_repair:run_sample",
        "concurrency": 2,
        "seed": 1310,
        "repetitions": 1,
        "timeout_seconds": 90,
        "sample_deadline_seconds": 300,
        "sample_wire_limit": 1,
        "max_output_tokens": 2048,
        "input_reservation_tokens": 100000,
        "thinking": "adaptive",
        "temperature": 0.1,
        "budget": budget,
        "cases": cases,
        "variants": [{
            "id": "conditional-exact-repair",
            "instruction": "Repair only pre-registered failed exact Tavern constraints once.",
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--budget-from", type=Path, required=True)
    parser.add_argument("--transport", choices=("fake", "minimax"), default="minimax")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        fixture=json.loads(args.fixture.read_text(encoding="utf-8")),
        baseline_manifest=json.loads((args.baseline_run / "manifest.json").read_text(encoding="utf-8")),
        baseline_run=args.baseline_run,
        budget_document=json.loads(args.budget_from.read_text(encoding="utf-8")),
        transport=args.transport,
    )
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
