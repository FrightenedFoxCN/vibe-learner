"""Build a blinded paired-review packet from frozen Scene baseline/repair runs."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random

from app.models.scene import SceneTreeProposalV1
from model_quality.protocol import Campaign, digest

from examples.prepare_scene_closed_world import FIXTURE
from vibe_learner.scene_closed_world_policy import (
    SceneClosedWorldPolicyV1,
    validate_scene_closed_world,
)


BASELINE_VARIANT = "production-shaped-baseline"
REPAIR_VARIANT = "conditional-one-wire-repair"
EVIDENCE_NAME = "scene-closed-world-evidence.json"
EVIDENCE_CONTRACT = "scene-closed-world-live-evidence-v1"
FIXTURE_SHA256 = "3eb06390ff87b93a59d388489b6aca51a64aee7ecfd3f544fc90a0fa9b558cb1"
BASELINE_CAMPAIGN = "m3-scene-closed-world-baseline-20260913-v1"
REPAIR_CAMPAIGN = "m3-scene-closed-world-repair-20260913-v1"
REVIEW_SEED = 913613


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


def _validated_wire_counts(
    report: dict[str, object],
    *,
    expected_campaign: str,
    expected_sample_ids: set[str],
    expected_call_kind: str,
) -> Counter[str]:
    usage = report.get("campaign_usage")
    wires = usage.get("wires") if isinstance(usage, dict) else None
    if (
        not isinstance(wires, list)
        or usage.get("wire_count") != len(wires)
        or usage.get("unknown_usage_requests") != 0
        or usage.get("stopped") is not None
    ):
        raise ValueError("scene_review_wire_accounting_invalid")
    wire_ids: set[str] = set()
    charged_or_reserved_tokens = 0
    counts: Counter[str] = Counter()
    for wire in wires:
        metadata = wire.get("metadata") if isinstance(wire, dict) else None
        wire_id = wire.get("id") if isinstance(wire, dict) else None
        sample_id = wire.get("sample") if isinstance(wire, dict) else None
        started = wire.get("started") if isinstance(wire, dict) else None
        finished = wire.get("finished") if isinstance(wire, dict) else None
        charged = wire.get("charged") if isinstance(wire, dict) else None
        reserved = wire.get("reserved") if isinstance(wire, dict) else None
        if (
            not isinstance(wire_id, str)
            or not wire_id
            or wire_id in wire_ids
            or wire.get("campaign") != expected_campaign
            or sample_id not in expected_sample_ids
            or wire.get("state") != "finished"
            or not isinstance(started, (int, float))
            or not isinstance(finished, (int, float))
            or finished < started
            or not isinstance(metadata, dict)
            or metadata.get("call_kind") != expected_call_kind
            or metadata.get("http_status") != 200
            or not isinstance(reserved, int)
            or reserved < 0
            or (charged is not None and (not isinstance(charged, int) or charged < 0))
        ):
            raise ValueError("scene_review_wire_binding_invalid")
        wire_ids.add(wire_id)
        counts[sample_id] += 1
        charged_or_reserved_tokens += charged if charged is not None else reserved
    if usage.get("charged_or_reserved_tokens") != charged_or_reserved_tokens:
        raise ValueError("scene_review_wire_accounting_invalid")
    return counts


def _load_run(
    root: Path,
    *,
    expected_variant: str,
    expected_adapter: str,
    expected_campaign: str,
    expected_rubric: str,
    expected_phase: str,
    expected_scope: str,
) -> tuple[dict[str, object], dict[str, object], dict[str, dict[str, object]]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    config = manifest.get("config")
    if not isinstance(config, dict) or manifest.get("config_digest") != digest(config):
        raise ValueError("scene_review_run_config_digest_invalid")
    campaign = Campaign.model_validate(config, strict=True)
    if (
        campaign.adapter != expected_adapter
        or campaign.id != expected_campaign
        or campaign.transport != "minimax"
        or campaign.thinking != "adaptive"
        or len(campaign.variants) != 1
        or campaign.variants[0].id != expected_variant
        or campaign.repetitions != 1
    ):
        raise ValueError("scene_review_run_config_invalid")
    if any(
        case.split != "confirmation"
        or case.provenance != "synthetic-authored"
        or case.rubric != expected_rubric
        for case in campaign.cases
    ):
        raise ValueError("scene_review_case_config_invalid")
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    rows = report.get("samples")
    if (
        report.get("version") != "quality-report-v1"
        or report.get("campaign") != campaign.id
        or not isinstance(rows, list)
        or len(rows) != len(campaign.cases)
        or report.get("expected_samples") != len(campaign.cases)
        or report.get("scope")
        != "research infrastructure; not Harness evidence or independent quality certification"
    ):
        raise ValueError("scene_review_run_report_invalid")
    states = Counter(row.get("state") for row in rows if isinstance(row, dict))
    if report.get("states") != dict(states):
        raise ValueError("scene_review_run_state_summary_invalid")
    expected_samples = {
        case.id: (sample_id, identity, case.family)
        for sample_id, identity, case, _ in campaign.samples()
    }
    by_case: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("result"), dict):
            raise ValueError("scene_review_sample_invalid")
        case_id = row.get("case")
        expected = expected_samples.get(case_id)
        references = row["result"].get("evidence")
        expected_owner = (
            None
            if row.get("state") == "completed"
            else "candidate"
            if row.get("state") == "candidate_failed"
            else "infrastructure"
        )
        if (
            not isinstance(case_id, str)
            or case_id in by_case
            or expected is None
            or row.get("sample_id") != expected[0]
            or row.get("variant") != expected_variant
            or row.get("repetition") != expected[1]["repetition"]
            or row.get("family") != expected[2]
            or row["result"].get("status") != row.get("state")
            or row["result"].get("failure_owner") != expected_owner
            or row["result"].get("scope") != expected_scope
            or not isinstance(references, list)
            or len(references) != 1
        ):
            raise ValueError("scene_review_sample_invalid")
        reference = references[0]
        if (
            not isinstance(reference, dict)
            or reference.get("path") != EVIDENCE_NAME
            or reference.get("contract") != EVIDENCE_CONTRACT
            or not isinstance(reference.get("sha256"), str)
        ):
            raise ValueError("scene_review_evidence_reference_invalid")
        evidence_path = root / case_id / expected_variant / "0" / "storage" / EVIDENCE_NAME
        if _file_digest(evidence_path) != reference["sha256"]:
            raise ValueError(f"scene_review_evidence_digest_mismatch:{case_id}")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if (
            evidence.get("version") != "scene-closed-world-live-evidence-v1"
            or evidence.get("phase") != expected_phase
            or evidence.get("case_id") != case_id
        ):
            raise ValueError(f"scene_review_evidence_case_mismatch:{case_id}")
        by_case[case_id] = {"sample": row, "evidence": evidence}
    if set(by_case) != {case.id for case in campaign.cases}:
        raise ValueError("scene_review_case_set_invalid")
    return manifest, report, by_case


def build_packet(
    *,
    baseline_run: Path,
    repair_run: Path,
    seed: int,
) -> tuple[dict[str, object], dict[str, object]]:
    baseline_manifest, baseline_report, baseline = _load_run(
        baseline_run,
        expected_variant=BASELINE_VARIANT,
        expected_adapter="vibe_learner.scene_closed_world_live:run_baseline_sample",
        expected_campaign=BASELINE_CAMPAIGN,
        expected_rubric="scene-closed-world-baseline-v1",
        expected_phase="baseline",
        expected_scope="domain-admitted-proposal; no product projection commit or read-back",
    )
    repair_manifest, repair_report, repair = _load_run(
        repair_run,
        expected_variant=REPAIR_VARIANT,
        expected_adapter="vibe_learner.scene_closed_world_live:run_repair_sample",
        expected_campaign=REPAIR_CAMPAIGN,
        expected_rubric="scene-closed-world-repair-v1",
        expected_phase="conditional_repair",
        expected_scope="provider-proposal-only; no domain admission, commit or read-back",
    )
    baseline_config = baseline_manifest["config"]
    repair_config = repair_manifest["config"]
    baseline_cases = {row["id"]: row for row in baseline_config["cases"]}
    repair_cases = {row["id"]: row for row in repair_config["cases"]}
    if set(baseline_cases) != set(repair_cases) or len(baseline_cases) != 6:
        raise ValueError("scene_review_paired_case_set_invalid")
    if _file_digest(FIXTURE) != FIXTURE_SHA256:
        raise ValueError("scene_review_fixture_digest_invalid")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture_rows = {row["case_id"]: row for row in fixture.get("cases", [])}
    if fixture.get("version") != "scene-closed-world-fixture-v1" or set(
        fixture_rows
    ) != set(baseline_cases):
        raise ValueError("scene_review_fixture_invalid")

    case_ids = sorted(baseline_cases)
    shuffled = list(case_ids)
    random.Random(seed).shuffle(shuffled)
    intervention_on_a = set(shuffled[: len(shuffled) // 2])
    packet_rows: list[dict[str, object]] = []
    key_rows: list[dict[str, object]] = []
    baseline_wire_counts = _validated_wire_counts(
        baseline_report,
        expected_campaign=BASELINE_CAMPAIGN,
        expected_sample_ids={
            row["sample"]["sample_id"] for row in baseline.values()
        },
        expected_call_kind="generation",
    )
    repair_wire_counts = _validated_wire_counts(
        repair_report,
        expected_campaign=REPAIR_CAMPAIGN,
        expected_sample_ids={
            row["sample"]["sample_id"] for row in repair.values()
        },
        expected_call_kind="repair",
    )
    if (
        any(count > 2 for count in baseline_wire_counts.values())
        or any(count > 1 for count in repair_wire_counts.values())
    ):
        raise ValueError("scene_review_wire_accounting_invalid")
    for case_id in case_ids:
        baseline_case = baseline_cases[case_id]
        repair_case = repair_cases[case_id]
        fixture_row = fixture_rows[case_id]
        if baseline_case["source"] != repair_case["source"]:
            raise ValueError(f"scene_review_source_mismatch:{case_id}")
        baseline_gold = json.loads(baseline_case["gold"])
        expected_baseline_gold = {
            "source_text": fixture_row["source_text"],
            "layer_count": fixture_row["layer_count"],
            "policy": fixture_row["scene_closed_world_policy_v1"],
            "fake_proposal": fixture_row["valid_minimal_scene_tree_proposal"],
        }
        if (
            baseline_case["source"] != fixture_row["source_text"]
            or baseline_gold != expected_baseline_gold
        ):
            raise ValueError(f"scene_review_fixture_case_mismatch:{case_id}")
        repair_gold = json.loads(repair_case["gold"])
        frozen = repair_gold.get("baseline")
        baseline_sample = baseline[case_id]["sample"]
        baseline_evidence = baseline[case_id]["evidence"]
        baseline_ref = baseline_sample["result"]["evidence"][0]
        expected_frozen = {
            "strict_candidate": bool(baseline_evidence.get("strict_candidate")),
            "status": baseline_sample["state"],
            "failure_owner": baseline_sample["result"].get("failure_owner"),
            "policy_evaluable": baseline_evidence.get("policy_evaluable"),
            "proposal": baseline_evidence.get("proposal"),
            "issues": baseline_evidence.get("issues", []),
            "sample_id": baseline_sample["sample_id"],
            "manifest_config_digest": baseline_manifest["config_digest"],
            "evidence_sha256": baseline_ref["sha256"],
        }
        if (
            repair_gold.get("source_text") != baseline_case["source"]
            or repair_gold.get("policy") != baseline_gold["policy"]
            or repair_gold.get("fake_proposal") != baseline_gold["fake_proposal"]
            or frozen != expected_frozen
        ):
            raise ValueError(f"scene_review_baseline_binding_mismatch:{case_id}")

        initial = baseline_evidence.get("proposal")
        repair_evidence = repair[case_id]["evidence"]
        repair_sample = repair[case_id]["sample"]
        policy = SceneClosedWorldPolicyV1.model_validate(
            repair_gold["policy"],
            strict=True,
        )
        normalized_policy = policy.model_dump(mode="json")
        expected_baseline_issues = (
            [
                issue.model_dump(mode="json")
                for issue in validate_scene_closed_world(policy, initial)
            ]
            if isinstance(initial, dict)
            else []
        )
        triggered = bool(expected_baseline_issues)
        if (
            repair_evidence.get("policy") != normalized_policy
            or repair_evidence.get("baseline_status") != frozen["status"]
            or repair_evidence.get("baseline_strict_candidate")
            is not frozen["strict_candidate"]
            or baseline_wire_counts[baseline_sample["sample_id"]] != 1
            or repair_evidence.get("repair_triggered") is not triggered
            or repair_wire_counts[repair_sample["sample_id"]] != (1 if triggered else 0)
            or (
                triggered
                and (
                    repair_evidence.get("wire_count_expected") != 1
                    or repair_evidence.get("baseline_proposal") != frozen["proposal"]
                    or repair_evidence.get("baseline_issues")
                    != expected_baseline_issues
                    or frozen["issues"] != expected_baseline_issues
                )
            )
        ):
            raise ValueError(f"scene_review_repair_input_binding_invalid:{case_id}")
        final = repair_evidence.get("final_proposal")
        baseline_available = isinstance(initial, dict)
        repair_available = isinstance(final, dict)
        if baseline_available:
            initial = SceneTreeProposalV1.model_validate(initial, strict=True).model_dump(
                mode="json"
            )
        if repair_available:
            final = SceneTreeProposalV1.model_validate(final, strict=True).model_dump(
                mode="json"
            )
        if baseline_sample["state"] == "completed":
            if (
                not baseline_available
                or not baseline_evidence.get("strict_candidate")
                or not baseline_evidence.get("production_trace_proposal")
            ):
                raise ValueError(f"scene_review_completed_baseline_invalid:{case_id}")
        elif baseline_available or baseline_evidence.get("strict_candidate"):
            raise ValueError(f"scene_review_failed_baseline_claimed_candidate:{case_id}")
        if repair_sample["state"] == "completed":
            recomputed_final_issues = [
                issue.model_dump(mode="json")
                for issue in validate_scene_closed_world(policy, final)
            ] if isinstance(final, dict) else None
            if (
                not repair_available
                or not repair_evidence.get("strict_candidate")
                or repair_evidence.get("final_issues") != recomputed_final_issues
                or recomputed_final_issues != []
            ):
                raise ValueError(f"scene_review_completed_repair_invalid:{case_id}")
        elif repair_available or repair_evidence.get("strict_candidate"):
            raise ValueError(f"scene_review_failed_repair_claimed_candidate:{case_id}")

        pair_available = baseline_available and repair_available
        unavailable = {"not_evaluable": True, "reason": "strict_candidate_unavailable"}
        if not pair_available:
            initial = unavailable
            final = unavailable
        intervention_label = "final" if pair_available else "repair_failed"
        intervention = final
        order = (
            [intervention_label, "initial"]
            if case_id in intervention_on_a
            else ["initial", intervention_label]
        )
        values = {"initial": initial, intervention_label: intervention}
        candidates = {
            "candidate_a": values[order[0]],
            "candidate_b": values[order[1]],
        }
        packet_rows.append({
            "case_id": case_id,
            "authoritative_source": baseline_case["source"],
            **candidates,
        })
        key_rows.append({
            "case_id": case_id,
            "labels": {"candidate_a": order[0], "candidate_b": order[1]},
            "source_sha256": _digest(baseline_case["source"]),
            "candidate_a_sha256": _digest(candidates["candidate_a"]),
            "candidate_b_sha256": _digest(candidates["candidate_b"]),
            "baseline_evidence_sha256": baseline_ref["sha256"],
            "repair_evidence_sha256": repair[case_id]["sample"]["result"]["evidence"][0]["sha256"],
            "repair_candidate_available": pair_available,
        })

    packet = {
        "version": "m3-scene-closed-world-blinded-paired-review-v1",
        "scope": "synthetic authoritative source plus blinded Scene proposals only",
        "review_axes": [
            "topology_fidelity",
            "object_fidelity",
            "supported_detail_deletion",
            "relationship_and_permission_invention",
            "epistemic_and_temporal_invention",
        ],
        "grading": ["pass", "minor", "major", "not_evaluable"],
        "cases": packet_rows,
    }
    key = {
        "version": "m3-scene-closed-world-blinded-paired-review-key-v2",
        "packet_canonical_sha256": _digest(packet),
        "seed": seed,
        "baseline_config_digest": baseline_manifest["config_digest"],
        "repair_config_digest": repair_manifest["config_digest"],
        "baseline_report_sha256": _file_digest(baseline_run / "report.json"),
        "repair_report_sha256": _file_digest(repair_run / "report.json"),
        "fixture_sha256": FIXTURE_SHA256,
        "cases": key_rows,
    }
    return packet, key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", type=Path, required=True)
    parser.add_argument("--repair-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=REVIEW_SEED)
    args = parser.parse_args()
    packet, key = build_packet(
        baseline_run=args.baseline_run,
        repair_run=args.repair_run,
        seed=args.seed,
    )
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    args.key_output.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
