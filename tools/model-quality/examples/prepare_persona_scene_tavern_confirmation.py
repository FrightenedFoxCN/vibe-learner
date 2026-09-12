"""Prepare the frozen M3 Persona/Scene -> Tavern confirmation baseline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.prepare_persona_scene_tavern import _fake_values


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "persona-scene-tavern-confirmation-v2.json"
)


def _canonical_source(row: dict[str, object]) -> str:
    return json.dumps(
        {
            "persona_input": row["persona_input"],
            "scene_input": row["scene_input"],
            "user_message": row["user_message"],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def build_manifest(*, budget_document: dict[str, object], transport: str) -> dict[str, object]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if fixture.get("version") != "persona-scene-tavern-confirmation-v2":
        raise ValueError("unexpected_confirmation_fixture_version")
    rows = fixture.get("cases")
    if not isinstance(rows, list) or len(rows) != 6:
        raise ValueError("confirmation_fixture_must_have_six_cases")
    ids = [row.get("id") for row in rows if isinstance(row, dict)]
    if len(ids) != len(set(ids)) or any(not isinstance(value, str) for value in ids):
        raise ValueError("confirmation_case_ids_invalid")
    budget = budget_document.get("budget") or budget_document.get("config", {}).get("budget")
    if not isinstance(budget, dict):
        raise ValueError("budget_document_missing_budget")
    cases = []
    for row in rows:
        frozen = row | _fake_values(row)
        cases.append(
            {
                "id": row["id"],
                "family": row["id"],
                "lane": "persona-scene-tavern-confirmation",
                "split": "confirmation",
                "provenance": "synthetic-authored",
                "source": _canonical_source(row),
                "request": row["user_message"],
                "gold": json.dumps(frozen, ensure_ascii=False),
                "rubric": "persona-scene-tavern-shadow-v1",
            }
        )
    return {
        "version": "quality-campaign-v1",
        "id": "m3-persona-scene-tavern-confirmation-20260913-v1",
        "purpose": (
            "Frozen confirmation baseline over six independently authored families. "
            "Operational v3 evidence and semantic review remain separate; this run captures "
            "all initial outputs before any source-fidelity repair strategy is implemented."
        ),
        "transport": transport,
        "adapter": "vibe_learner.persona_scene_tavern:run_confirmation_sample",
        "concurrency": 2,
        "seed": 1309,
        "repetitions": 1,
        "timeout_seconds": 90,
        "sample_deadline_seconds": 900,
        "sample_wire_limit": 9,
        "max_output_tokens": 6400,
        "input_reservation_tokens": 100000,
        "thinking": "adaptive",
        "temperature": 0.2,
        "budget": budget,
        "cases": cases,
        "variants": [
            {
                "id": "shadow-chain",
                "instruction": "Capture the current production-shaped baseline before repair experiments.",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-from", type=Path, required=True)
    parser.add_argument("--transport", choices=("fake", "minimax"), default="minimax")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        budget_document=json.loads(args.budget_from.read_text(encoding="utf-8")),
        transport=args.transport,
    )
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
