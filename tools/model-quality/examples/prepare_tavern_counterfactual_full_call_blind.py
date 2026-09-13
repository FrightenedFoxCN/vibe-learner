"""Prepare, but never dispatch, the frozen Tavern full-call blind campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys

from model_quality.protocol import digest

from vibe_learner.tavern_counterfactual_full_call_blind import (
    CAMPAIGN_ID, CONCURRENCY, FIXTURE_SHA256, GATE, INPUT_RESERVATION_TOKENS,
    MAX_OUTPUT_TOKENS, RUBRIC, SAMPLE_DEADLINE_SECONDS, SAMPLE_WIRE_LIMIT,
    SEED, TIMEOUT_SECONDS, VARIANT, build_public_input, canonical_sha256,
    load_fixture, sample_catalog,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
PREREG_VERSION = "m3-tavern-counterfactual-production-full-call-blind-preregistration-v1"
_BOUND_FILES = (
    "tools/model-quality/integrations/vibe_learner/tavern_counterfactual_full_call_blind.py",
    "tools/model-quality/integrations/vibe_learner/tavern_counterfactual_twins.py",
    "tools/model-quality/examples/prepare_tavern_counterfactual_full_call_blind.py",
    "tools/model-quality/examples/export_tavern_counterfactual_full_call_blind.py",
    "tools/model-quality/examples/aggregate_tavern_counterfactual_full_call_blind.py",
    "tools/model-quality/fixtures/persona-scene/tavern-counterfactual-twins-v1.json",
    "tools/model-quality/fixtures/persona-scene/tavern-counterfactual-production-full-call-blind-rubric-v1.json",
    "tools/model-quality/integrations/vibe_learner/common.py",
    "tools/model-quality/model_quality/__main__.py",
    "tools/model-quality/model_quality/runner.py",
    "tools/model-quality/model_quality/transport.py",
    "tools/model-quality/model_quality/ledger.py",
    "tools/model-quality/model_quality/protocol.py",
    "services/ai/app/app_factory.py",
    "services/ai/app/api/tavern_routes.py",
    "services/ai/app/core/bootstrap.py",
    "services/ai/app/models/tavern.py",
    "services/ai/app/models/tavern_commit.py",
    "services/ai/app/models/tavern_integrity.py",
    "services/ai/app/persistence/tavern_repository.py",
    "services/ai/app/services/provider_tavern.py",
    "services/ai/app/services/tavern.py",
    "services/ai/app/services/tavern_harness.py",
    "services/ai/app/services/tavern_v3.py",
    "services/ai/uv.lock",
)
BOUND_FILES = tuple(sorted(set(_BOUND_FILES) | {
    path.relative_to(REPO_ROOT).as_posix()
    for root in (REPO_ROOT / "services/ai/app", REPO_ROOT / "tools/model-quality/model_quality")
    for path in root.rglob("*.py")
} | {
    path.relative_to(REPO_ROOT).as_posix()
    for path in (REPO_ROOT / "services/ai/app/prompts").rglob("*.txt")
}))


def _budget(document: dict[str, object]) -> dict[str, object]:
    value = document.get("budget") or document.get("config", {}).get("budget")
    if not isinstance(value, dict):
        raise ValueError("tavern_full_call_budget_missing")
    return value


def build_manifest(*, budget_document: dict[str, object], transport: str) -> dict[str, object]:
    fixture_by_id = {row.family_id: row for row in load_fixture().families}
    cases = []
    for row in sample_catalog():
        family = fixture_by_id[row["family_id"]]
        twin = family.supported if row["arm"] == "x" else family.second
        peer = family.second if row["arm"] == "x" else family.supported
        public = build_public_input(family=family, twin=twin, peer=peer)
        cases.append({
            "id": row["case_id"],
            "family": row["family_id"],
            "lane": "tavern-counterfactual-production-full-call-blind",
            "split": "confirmation",
            "provenance": "synthetic-authored-counterfactual-twin",
            "source": json.dumps(public, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            "request": "Perform one production Tavern direct turn against the committed snapshot.",
            "gold": json.dumps({
                "fixture_sha256": FIXTURE_SHA256,
                "public_input_sha256": canonical_sha256(public),
            }, ensure_ascii=False, sort_keys=True),
            "rubric": RUBRIC,
        })
    if len(cases) != 20 or len({row["id"] for row in cases}) != 20:
        raise ValueError("tavern_full_call_case_catalog_invalid")
    return {
        "version": "quality-campaign-v1",
        "id": CAMPAIGN_ID,
        "purpose": (
            "One immutable production full-call per counterfactual arm. All ten families "
            "remain in the denominator; unavailable arms become symmetric blind sentinels."
        ),
        "transport": transport,
        "adapter": "vibe_learner.tavern_counterfactual_full_call_blind:run_sample",
        "concurrency": CONCURRENCY, "seed": SEED, "repetitions": 1,
        "timeout_seconds": TIMEOUT_SECONDS,
        "sample_deadline_seconds": SAMPLE_DEADLINE_SECONDS,
        "sample_wire_limit": SAMPLE_WIRE_LIMIT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "input_reservation_tokens": INPUT_RESERVATION_TOKENS,
        "thinking": "adaptive", "temperature": 0.2,
        "budget": _budget(budget_document),
        "cases": cases,
        "variants": [{
            "id": VARIANT,
            "instruction": "Committed-shape Persona/Scene to one direct Tavern turn; bounded production repair only.",
        }],
    }


def build_preregistration(*, manifest: dict[str, object]) -> dict[str, object]:
    if manifest.get("id") != CAMPAIGN_ID or manifest.get("transport") != "minimax":
        raise ValueError("tavern_full_call_prereg_requires_live_manifest")
    files = {path: hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest() for path in BOUND_FILES}
    return {
        "version": PREREG_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "ordinary_git_preregistration": True,
        "fixture_sha256": FIXTURE_SHA256,
        "campaign_manifest_canonical_sha256": digest(manifest),
        "bound_file_sha256": files,
        "working_directory": "tools/model-quality",
        "entrypoint": "uv run --project ../../services/ai python -m model_quality --manifest <frozen-manifest> --output <new-run-root> --ledger <frozen-ledger-path>",
        "argv_contract": {
            "manifest": "exact frozen manifest bytes",
            "output": "new empty run root",
            "ledger": "campaign-specific durable ledger path",
            "resume": False,
            "rerun": False,
        },
        "config": manifest,
        "runtime": {
            "python_implementation": platform.python_implementation(),
            "python_version": platform.python_version(),
            "executable_basename": Path(sys.executable).name,
            "platform": platform.platform(),
        },
        "environment_allowlist": ["K3_API_KEY"],
        "adapter_explicit_file_read_allowlist": [],
        "wire_policy": {
            "samples": 20, "maximum_per_sample": 3, "maximum_total": 60,
            "replay_must_add_zero": True,
        },
        "blind_policy": {
            "random_seed": 913413,
            "hide": ["family", "axis", "polarity", "resource_ids", "status", "trace", "repair", "provider_reasoning", "key"],
            "failed_pair": "byte-identical two-sided sentinel",
        },
        "gate": GATE,
        "production_registry_change": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-from", type=Path, required=True)
    parser.add_argument("--transport", choices=("fake", "minimax"), default="minimax")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prereg-output", type=Path)
    args = parser.parse_args()
    manifest = build_manifest(
        budget_document=json.loads(args.budget_from.read_text(encoding="utf-8")),
        transport=args.transport,
    )
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.prereg_output is not None:
        prereg = build_preregistration(manifest=manifest)
        args.prereg_output.write_text(json.dumps(prereg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
