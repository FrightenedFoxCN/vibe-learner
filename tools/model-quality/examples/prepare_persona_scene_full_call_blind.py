"""Prepare the frozen production Persona -> Scene full-call blind campaign.

This is a single-arm, absolute-review campaign.  Every family remains in each
domain denominator.  The adapter may use only production's bounded initial and
repair calls: at most two Persona wires plus two Scene wires per family.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "persona-scene" / "persona-scene-production-full-call-blind-v1.json"
PREREGISTRATION = ROOT / "fixtures" / "persona-scene" / "persona-scene-production-full-call-blind-preregistration-v1.json"
CAMPAIGN_ID = "m3-persona-scene-production-full-call-blind-20260913-v1"
ADAPTER = "vibe_learner.persona_scene_full_call_blind:run_sample"
RUBRIC = "persona-scene-production-full-call-absolute-blind-v1"
REPOSITORY = Path(__file__).resolve().parents[3]
SOURCE_TREE_RULES = (
    "services/ai/app/**/*.py",
    "services/ai/app/prompts/**/*.txt",
    "tools/model-quality/model_quality/**/*.py",
)
SOURCE_TREE_EXACT_PATHS = (
    "services/ai/pyproject.toml",
    "services/ai/uv.lock",
    "tools/model-quality/pyproject.toml",
    "tools/model-quality/uv.lock",
    "tools/model-quality/integrations/vibe_learner/common.py",
    "tools/model-quality/fixtures/persona-scene/persona-scene-production-full-call-blind-v1.json",
    "tools/model-quality/fixtures/persona-scene/persona-scene-production-full-call-blind-oracle-v1.json",
    "tools/model-quality/examples/prepare_persona_scene_full_call_blind.py",
    "tools/model-quality/integrations/vibe_learner/persona_scene_full_call_blind.py",
    "tools/model-quality/examples/export_persona_scene_full_call_blind.py",
    "tools/model-quality/examples/aggregate_persona_scene_full_call_blind.py",
    "tools/model-quality/integration_tests/test_persona_scene_full_call_blind.py",
)


def source_tree_paths(repository: Path = REPOSITORY) -> tuple[str, ...]:
    paths: set[str] = set(SOURCE_TREE_EXACT_PATHS)
    paths.update(path.relative_to(repository).as_posix() for path in (repository / "services/ai/app").rglob("*.py"))
    paths.update(path.relative_to(repository).as_posix() for path in (repository / "services/ai/app/prompts").rglob("*.txt"))
    paths.update(path.relative_to(repository).as_posix() for path in (repository / "tools/model-quality/model_quality").rglob("*.py"))
    return tuple(sorted(paths))


def source_tree_binding(repository: Path = REPOSITORY) -> dict[str, object]:
    manifest = {path: sha256_file(repository / path) for path in source_tree_paths(repository)}
    return {
        "rules": list(SOURCE_TREE_RULES),
        "exact_paths": list(SOURCE_TREE_EXACT_PATHS),
        "path_count": len(manifest),
        "canonical_manifest_sha256": hashlib.sha256(canonical(manifest).encode("utf-8")).hexdigest(),
    }


def canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_inputs() -> tuple[dict[str, object], dict[str, object]]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    prereg = json.loads(PREREGISTRATION.read_text(encoding="utf-8"))
    if (
        fixture.get("version") != "persona-scene-production-full-call-blind-fixture-v1"
        or fixture.get("campaign_id") != CAMPAIGN_ID
        or prereg.get("version") != "persona-scene-production-full-call-blind-preregistration-v1"
        or prereg.get("campaign_id") != CAMPAIGN_ID
    ):
        raise ValueError("full_call_preregistration_identity_mismatch")
    bindings = prereg.get("source_bindings")
    bound_paths = {
        "fixture": FIXTURE,
        "prepare_manifest": Path(__file__),
        "adapter": ROOT / "integrations" / "vibe_learner" / "persona_scene_full_call_blind.py",
        "blind_packet_key_exporter": ROOT / "examples" / "export_persona_scene_full_call_blind.py",
        "strict_two_reviewer_aggregator": ROOT / "examples" / "aggregate_persona_scene_full_call_blind.py",
        "tests": ROOT / "integration_tests" / "test_persona_scene_full_call_blind.py",
    }
    if not isinstance(bindings, dict) or bindings != {name: sha256_file(path) for name, path in bound_paths.items()}:
        raise ValueError("full_call_preregistered_source_binding_mismatch")
    if prereg.get("source_tree_binding") != source_tree_binding():
        raise ValueError("full_call_required_source_tree_mismatch")
    runtime = prereg.get("runtime_binding")
    expected_runtime = {
        "model": "MiniMax-M3", "transport": "minimax", "thinking": "adaptive",
        "temperature": 0.2, "max_output_tokens": 6400,
        "production_initial_max_tokens": 4096, "production_repair_max_tokens": 6144,
        "timeout_seconds": 90, "sample_deadline_seconds": 600,
        "concurrency": 1, "repetitions": 1, "seed": 91341,
        "variant": "production-full-call", "sample_wire_limit": 4,
        "persona_wire_limit_per_family": 2, "scene_wire_limit_per_family": 2,
        "campaign_wire_limit": 32,
    }
    if not isinstance(runtime, dict) or any(runtime.get(key) != value for key, value in expected_runtime.items()):
        raise ValueError("full_call_preregistered_runtime_binding_mismatch")
    return fixture, prereg


def build_manifest(*, budget_document: dict[str, object], transport: str) -> dict[str, object]:
    if transport != "minimax":
        raise ValueError("full_call_live_transport_required")
    fixture, prereg = _load_inputs()
    rows = fixture.get("cases")
    if not isinstance(rows, list) or len(rows) != 8:
        raise ValueError("full_call_fixture_must_have_eight_cases")
    ids = [row.get("family_id") for row in rows if isinstance(row, dict)]
    if len(ids) != 8 or len(set(ids)) != 8 or any(not isinstance(value, str) for value in ids):
        raise ValueError("full_call_family_ids_invalid")
    budget = budget_document.get("budget") or budget_document.get("config", {}).get("budget")
    if not isinstance(budget, dict):
        raise ValueError("budget_document_missing_budget")
    cases = []
    for row in rows:
        public_source = {
            "persona_source": row["persona_source"],
            "scene_source": row["scene_source"],
        }
        cases.append({
            "id": row["family_id"],
            "family": row["family_id"],
            "lane": "persona-scene-production-full-call-blind",
            "split": "confirmation",
            "provenance": "human-authored-synthetic",
            "source": canonical(public_source),
            "request": "Run the complete production Persona and Scene generation/save/read-back lifecycle.",
            "gold": "{}",
            "rubric": RUBRIC,
        })
    return {
        "version": "quality-campaign-v1",
        "id": CAMPAIGN_ID,
        "purpose": "Absolute blind assessment of complete production Persona and Scene generation, strict v3 proposal evidence, save, immediate read-back, and restart read-back over eight fresh families.",
        "transport": "minimax",
        "adapter": ADAPTER,
        "concurrency": 1,
        "seed": 91341,
        "repetitions": 1,
        "timeout_seconds": 90,
        "sample_deadline_seconds": 600,
        "sample_wire_limit": 4,
        "max_output_tokens": 6400,
        "input_reservation_tokens": 100000,
        "thinking": "adaptive",
        "temperature": 0.2,
        "budget": budget,
        "cases": cases,
        "variants": [{
            "id": "production-full-call",
            "instruction": "Use unchanged production endpoints and their single bounded repair; never substitute fixture output, retry a failed family, or replace a sample.",
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-from", type=Path, required=True)
    parser.add_argument("--transport", choices=("minimax",), default="minimax")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_manifest(
        budget_document=json.loads(args.budget_from.read_text(encoding="utf-8")),
        transport=args.transport,
    )
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
