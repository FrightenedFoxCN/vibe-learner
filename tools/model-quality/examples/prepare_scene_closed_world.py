"""Prepare frozen baseline or conditional repair for the M3 Scene experiment."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from model_quality.protocol import Campaign, digest


FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "persona-scene"
    / "scene-closed-world-v1.json"
)


def _budget(document: dict[str, object]) -> dict[str, object]:
    value = document.get("budget") or document.get("config", {}).get("budget")
    if not isinstance(value, dict):
        raise ValueError("scene_closed_world_budget_missing")
    return value


def _fixture_rows() -> list[dict[str, object]]:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    rows = fixture.get("cases")
    if fixture.get("version") != "scene-closed-world-fixture-v1":
        raise ValueError("scene_closed_world_fixture_version_invalid")
    if not isinstance(rows, list) or len(rows) != 6:
        raise ValueError("scene_closed_world_fixture_case_count_invalid")
    ids = [row.get("case_id") for row in rows if isinstance(row, dict)]
    if len(ids) != 6 or len(set(ids)) != 6 or not all(isinstance(value, str) for value in ids):
        raise ValueError("scene_closed_world_fixture_case_ids_invalid")
    return rows


def build_baseline_manifest(
    *,
    budget_document: dict[str, object],
    transport: str,
) -> dict[str, object]:
    cases = []
    for row in _fixture_rows():
        spec = {
            "source_text": row["source_text"],
            "layer_count": row["layer_count"],
            "policy": row["scene_closed_world_policy_v1"],
            "fake_proposal": row["valid_minimal_scene_tree_proposal"],
        }
        cases.append({
            "id": row["case_id"],
            "family": row["case_id"],
            "lane": "scene-closed-world-baseline",
            "split": "confirmation",
            "provenance": "synthetic-authored",
            "source": row["source_text"],
            "request": "Generate one strict SceneTreeProposalV1 from the source.",
            "gold": json.dumps(spec, ensure_ascii=False),
            "rubric": "scene-closed-world-baseline-v1",
        })
    return {
        "version": "quality-campaign-v1",
        "id": "m3-scene-closed-world-baseline-20260913-v1",
        "purpose": (
            "Freeze six production-shaped Scene proposals before any conditional repair. "
            "Typed closed-world issues are research triggers, not production commit evidence."
        ),
        "transport": transport,
        "adapter": "vibe_learner.scene_closed_world_live:run_baseline_sample",
        "concurrency": 2,
        "seed": 1311,
        "repetitions": 1,
        "timeout_seconds": 90,
        "sample_deadline_seconds": 300,
        "sample_wire_limit": 2,
        "max_output_tokens": 4096,
        "input_reservation_tokens": 100000,
        "thinking": "adaptive",
        "temperature": 0.2,
        "budget": _budget(budget_document),
        "cases": cases,
        "variants": [{
            "id": "production-shaped-baseline",
            "instruction": "Freeze one production-shaped Scene proposal before research repair.",
        }],
    }


def build_repair_manifest(
    *,
    baseline_run: Path,
    budget_document: dict[str, object],
    transport: str,
) -> dict[str, object]:
    baseline_manifest = json.loads(
        (baseline_run / "manifest.json").read_text(encoding="utf-8")
    )
    config = baseline_manifest.get("config") or baseline_manifest
    if (
        not isinstance(config, dict)
        or baseline_manifest.get("config_digest") != digest(config)
    ):
        raise ValueError("scene_closed_world_baseline_config_digest_invalid")
    campaign = Campaign.model_validate(config, strict=True)
    source_cases = config.get("cases")
    if (
        campaign.adapter
        != "vibe_learner.scene_closed_world_live:run_baseline_sample"
        or campaign.transport != transport
        or len(campaign.variants) != 1
        or campaign.variants[0].id != "production-shaped-baseline"
        or campaign.repetitions != 1
        or not isinstance(source_cases, list)
        or len(source_cases) != 6
    ):
        raise ValueError("scene_closed_world_baseline_manifest_invalid")
    report = json.loads((baseline_run / "report.json").read_text(encoding="utf-8"))
    report_samples = report.get("samples")
    if (
        report.get("version") != "quality-report-v1"
        or report.get("campaign") != campaign.id
        or report.get("expected_samples") != 6
        or not isinstance(report_samples, list)
        or len(report_samples) != 6
    ):
        raise ValueError("scene_closed_world_baseline_report_invalid")
    report_states = Counter(sample.get("state") for sample in report_samples)
    if (
        set(report_states) - {"completed", "candidate_failed"}
        or report.get("states") != dict(report_states)
    ):
        raise ValueError("scene_closed_world_baseline_not_terminal")
    expected_samples = {
        case.id: (sample_id, identity)
        for sample_id, identity, case, _ in campaign.samples()
    }
    samples_by_case: dict[str, dict[str, object]] = {}
    for sample in report_samples:
        case_id = sample.get("case")
        expected = expected_samples.get(case_id)
        result = sample.get("result")
        if (
            not isinstance(case_id, str)
            or expected is None
            or sample.get("sample_id") != expected[0]
            or sample.get("variant") != expected[1]["variant"]
            or sample.get("repetition") != expected[1]["repetition"]
            or not isinstance(result, dict)
            or result.get("status") != sample.get("state")
            or result.get("scope")
            != "domain-admitted-proposal; no product projection commit or read-back"
        ):
            raise ValueError("scene_closed_world_baseline_sample_invalid")
        references = result.get("evidence")
        if not isinstance(references, list) or len(references) != 1:
            raise ValueError("scene_closed_world_baseline_evidence_reference_invalid")
        reference = references[0]
        if (
            not isinstance(reference, dict)
            or reference.get("path") != "scene-closed-world-evidence.json"
            or reference.get("contract") != "scene-closed-world-live-evidence-v1"
            or not isinstance(reference.get("sha256"), str)
        ):
            raise ValueError("scene_closed_world_baseline_evidence_reference_invalid")
        samples_by_case[case_id] = sample
    source_by_id = {row["id"]: row for row in source_cases}
    cases = []
    for row in _fixture_rows():
        case_id = row["case_id"]
        source_case = source_by_id.get(case_id)
        if not isinstance(source_case, dict) or source_case.get("source") != row["source_text"]:
            raise ValueError(f"scene_closed_world_baseline_source_mismatch:{case_id}")
        frozen_spec = json.loads(source_case["gold"])
        if (
            source_case.get("rubric") != "scene-closed-world-baseline-v1"
            or frozen_spec.get("source_text") != source_case.get("source")
        ):
            raise ValueError(f"scene_closed_world_baseline_gold_mismatch:{case_id}")
        sample = samples_by_case.get(case_id)
        if not isinstance(sample, dict):
            raise ValueError(f"scene_closed_world_baseline_sample_missing:{case_id}")
        result = sample["result"]
        reference = result["evidence"][0]
        evidence_path = (
            baseline_run
            / case_id
            / "production-shaped-baseline"
            / "0"
            / "storage"
            / "scene-closed-world-evidence.json"
        )
        evidence_bytes = evidence_path.read_bytes()
        evidence_digest = hashlib.sha256(evidence_bytes).hexdigest()
        if evidence_digest != reference["sha256"]:
            raise ValueError(f"scene_closed_world_baseline_evidence_digest_mismatch:{case_id}")
        evidence = json.loads(evidence_bytes)
        if evidence.get("case_id") != case_id or evidence.get("phase") != "baseline":
            raise ValueError(f"scene_closed_world_baseline_evidence_mismatch:{case_id}")
        strict_candidate = bool(evidence.get("strict_candidate"))
        metrics = result.get("metrics")
        if (
            not isinstance(metrics, dict)
            or metrics.get("strict_candidate") is not strict_candidate
            or (
                sample["state"] == "completed"
                and (
                    not strict_candidate
                    or not evidence.get("production_trace_proposal")
                    or not isinstance(evidence.get("proposal"), dict)
                )
            )
            or (sample["state"] == "candidate_failed" and strict_candidate)
        ):
            raise ValueError(f"scene_closed_world_baseline_result_mismatch:{case_id}")
        baseline = {
            "strict_candidate": strict_candidate,
            "proposal": evidence.get("proposal"),
            "issues": evidence.get("issues", []),
            "sample_id": sample["sample_id"],
            "manifest_config_digest": baseline_manifest["config_digest"],
            "evidence_sha256": evidence_digest,
        }
        spec = {
            "source_text": row["source_text"],
            "policy": frozen_spec["policy"],
            "fake_proposal": frozen_spec["fake_proposal"],
            "baseline": baseline,
        }
        cases.append({
            "id": case_id,
            "family": case_id,
            "lane": "scene-closed-world-repair",
            "split": "confirmation",
            "provenance": "synthetic-authored",
            "source": row["source_text"],
            "request": "Conditionally repair only typed closed-world issues once.",
            "gold": json.dumps(spec, ensure_ascii=False),
            "rubric": "scene-closed-world-repair-v1",
        })
    return {
        "version": "quality-campaign-v1",
        "id": "m3-scene-closed-world-repair-20260913-v1",
        "purpose": (
            "At most one research-only repair wire over each frozen baseline with typed issues. "
            "No baseline, domain record, Tavern Message, or production trace may be overwritten."
        ),
        "transport": transport,
        "adapter": "vibe_learner.scene_closed_world_live:run_repair_sample",
        "concurrency": 2,
        "seed": 1312,
        "repetitions": 1,
        "timeout_seconds": 90,
        "sample_deadline_seconds": 300,
        "sample_wire_limit": 1,
        "max_output_tokens": 4096,
        "input_reservation_tokens": 100000,
        "thinking": "adaptive",
        "temperature": 0.1,
        "budget": _budget(budget_document),
        "cases": cases,
        "variants": [{
            "id": "conditional-one-wire-repair",
            "instruction": "Repair only typed issues once; reuse a passing frozen proposal without a wire.",
        }],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("baseline", "repair"), required=True)
    parser.add_argument("--baseline-run", type=Path)
    parser.add_argument("--budget-from", type=Path, required=True)
    parser.add_argument("--transport", choices=("fake", "minimax"), default="minimax")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    budget_document = json.loads(args.budget_from.read_text(encoding="utf-8"))
    if args.phase == "baseline":
        manifest = build_baseline_manifest(
            budget_document=budget_document,
            transport=args.transport,
        )
    else:
        if args.baseline_run is None:
            raise SystemExit("--baseline-run is required for repair")
        manifest = build_repair_manifest(
            baseline_run=args.baseline_run,
            budget_document=budget_document,
            transport=args.transport,
        )
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
