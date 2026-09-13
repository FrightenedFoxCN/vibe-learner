"""Prepare (but never dispatch) the paired fresh Persona capsule campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from vibe_learner.persona_source_capsule import PersonaSourceCapsuleFixtureV1
from vibe_learner.persona_source_capsule_live import (
    CAMPAIGN_CONCURRENCY,
    CAMPAIGN_ID,
    CAMPAIGN_INPUT_RESERVATION_TOKENS,
    CAMPAIGN_MAX_OUTPUT_TOKENS,
    CAMPAIGN_SAMPLE_DEADLINE_SECONDS,
    CAMPAIGN_SEED,
    CAMPAIGN_TIMEOUT_SECONDS,
    FIXTURE,
    FIXTURE_SHA256,
    PREREGISTERED_GATE,
    RUBRIC,
)


def _budget(document: dict[str, object]) -> dict[str, object]:
    value = document.get("budget") or document.get("config", {}).get("budget")
    if not isinstance(value, dict):
        raise ValueError("persona_source_capsule_budget_missing")
    return value


def build_manifest(*, budget_document: dict[str, object], transport: str) -> dict[str, object]:
    fixture_bytes = FIXTURE.read_bytes()
    if hashlib.sha256(fixture_bytes).hexdigest() != FIXTURE_SHA256:
        raise ValueError("persona_source_capsule_fixture_digest_mismatch")
    fixture = PersonaSourceCapsuleFixtureV1.model_validate_json(fixture_bytes, strict=True)
    cases = []
    for row in fixture.cases:
        spec = {
            "fixture_sha256": FIXTURE_SHA256,
            "source_sha256": row.capsule.source_sha256,
            "capsule_sha256": row.capsule_sha256,
            "fake_proposal": row.valid_minimal_persona_card_batch_proposal,
            "preregistered_gate": PREREGISTERED_GATE,
        }
        cases.append({
            "id": row.case_id,
            "family": row.case_id,
            "lane": "persona-source-capsule-live",
            "split": "confirmation",
            "provenance": "synthetic-authored",
            "source": row.source_text,
            "request": "Generate exactly one strict PersonaCardBatchContentProposalV1.",
            "gold": json.dumps(spec, ensure_ascii=False, sort_keys=True),
            "rubric": RUBRIC,
        })
    return {
        "version": "quality-campaign-v1",
        "id": CAMPAIGN_ID,
        "purpose": (
            "Preregistered paired fresh production-prompt versus source-capsule prompt study. "
            "All eight pairs stay in the denominator; two isolated blind reviewers judge the "
            "frozen proposals. No production registry change or Persona save is authorized."
        ),
        "transport": transport,
        "adapter": "vibe_learner.persona_source_capsule_live:run_sample",
        "concurrency": CAMPAIGN_CONCURRENCY,
        "seed": CAMPAIGN_SEED,
        "repetitions": 1,
        "timeout_seconds": CAMPAIGN_TIMEOUT_SECONDS,
        "sample_deadline_seconds": CAMPAIGN_SAMPLE_DEADLINE_SECONDS,
        "sample_wire_limit": 1,
        "max_output_tokens": CAMPAIGN_MAX_OUTPUT_TOKENS,
        "input_reservation_tokens": CAMPAIGN_INPUT_RESERVATION_TOKENS,
        "thinking": "adaptive",
        "temperature": 0.2,
        "budget": _budget(budget_document),
        "cases": cases,
        "variants": [
            {
                "id": "production-prompt-fresh",
                "instruction": "One fresh production prompt wire; no capsule and no retry.",
            },
            {
                "id": "capsule-prompt-fresh",
                "instruction": "One independent fresh wire with the source capsule appendix; no retry.",
            },
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
