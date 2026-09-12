"""Audit frozen confirmation outputs with research-only exact constraints."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from model_quality.runner import atomic_json
from vibe_learner.persona_scene_tavern_fidelity import (
    SourceFidelityConstraintsV1,
    evaluate_source_fidelity,
    failed_domains,
)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def audit(*, fixture_path: Path, run_path: Path) -> dict[str, object]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    rows = fixture.get("cases")
    if fixture.get("version") != "persona-scene-tavern-confirmation-v2" or not isinstance(rows, list):
        raise ValueError("invalid_confirmation_fixture")
    results = []
    for row in rows:
        case_id = row["id"]
        evidence_path = run_path / case_id / "shadow-chain" / "0" / "storage" / "domain-evidence.json"
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("case_id") != case_id:
            raise ValueError("confirmation_case_evidence_mismatch")
        generated = evidence["generated"]
        tavern_messages = generated["tavern_messages"]
        if not isinstance(tavern_messages, list) or len(tavern_messages) != 1:
            raise ValueError("confirmation_tavern_message_count_invalid")
        checks = evaluate_source_fidelity(
            SourceFidelityConstraintsV1.model_validate(row["source_fidelity_constraints"]),
            persona=generated["persona"],
            scene=generated["scene"],
            tavern_text=tavern_messages[0]["content"],
        )
        results.append(
            {
                "case_id": case_id,
                "source_sha256": _digest({
                    "persona_input": row["persona_input"],
                    "scene_input": row["scene_input"],
                    "user_message": row["user_message"],
                }),
                "generated_sha256": _digest(generated),
                "checks": [check.model_dump(mode="json") for check in checks],
                "failed_domains": failed_domains(checks),
                "repair_triggered": bool(failed_domains(checks)),
            }
        )
    check_counts = Counter(
        "passed" if check["passed"] else "failed"
        for result in results
        for check in result["checks"]
    )
    return {
        "version": "persona-scene-tavern-source-fidelity-audit-v1",
        "scope": (
            "Research-only pre-registered exact checks. Not production Harness evidence "
            "and not a semantic-quality verdict."
        ),
        "fixture_sha256": hashlib.sha256(fixture_path.read_bytes()).hexdigest(),
        "run_manifest_sha256": hashlib.sha256((run_path / "manifest.json").read_bytes()).hexdigest(),
        "cases": results,
        "summary": {
            "cases": len(results),
            "repair_triggered": sum(result["repair_triggered"] for result in results),
            "checks": dict(check_counts),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    atomic_json(args.output, audit(fixture_path=args.fixture, run_path=args.run))


if __name__ == "__main__":
    main()
