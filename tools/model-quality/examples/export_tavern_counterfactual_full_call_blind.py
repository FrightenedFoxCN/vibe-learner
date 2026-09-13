"""Strictly rebuild the anonymous Tavern counterfactual review packet and key."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from model_quality.protocol import Campaign, digest
from examples.prepare_tavern_counterfactual_full_call_blind import build_manifest
from examples.prepare_tavern_counterfactual_full_call_blind import (
    BOUND_FILES, PREREG_VERSION, REPO_ROOT,
)
from vibe_learner.tavern_counterfactual_full_call_blind import (
    CAMPAIGN_ID, EVIDENCE_CONTRACT, EVIDENCE_NAME, FIXTURE_SHA256, GATE,
    RUBRIC, SAMPLE_WIRE_LIMIT, SCOPE, VARIANT, load_fixture, sample_catalog,
)


REVIEW_SEED = 913413
PACKET_VERSION = "m3-tavern-counterfactual-production-full-call-blinded-review-v1"
KEY_VERSION = "m3-tavern-counterfactual-production-full-call-blinded-key-v1"
UNAVAILABLE = {"not_evaluable": True, "reason": "strict_family_pair_unavailable"}
AXES = [
    "authority_fidelity", "false_premise_handling",
    "relationship_permission_fidelity", "epistemic_world_fidelity",
    "task_adherence", "counterfactual_sensitivity",
]
TERMINAL = {
    "completed", "candidate_failed", "data_failed", "grader_failed",
    "metric_failed", "infrastructure_failed", "uncertain", "stopped",
}
PREREG_PATH = REPO_ROOT / "docs/quality/evidence/m3-tavern-counterfactual-production-full-call-blind-preregistration-2026-09-13.json"
RUBRIC_PATH = REPO_ROOT / "tools/model-quality/fixtures/persona-scene/tavern-counterfactual-production-full-call-blind-rubric-v1.json"


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def value_sha(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rubric() -> dict[str, object]:
    rubric = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    if (
        not isinstance(rubric, dict) or rubric.get("version") != RUBRIC
        or rubric.get("campaign_id") != CAMPAIGN_ID
    ):
        raise ValueError("tavern_full_call_rubric_invalid")
    return rubric


def public_rubric() -> dict[str, object]:
    """Reviewer projection omits campaign identity while retaining all rules."""
    rubric = load_rubric().copy()
    rubric.pop("campaign_id")
    return rubric


def _owner(state: str) -> str | None:
    if state == "completed":
        return None
    if state in {"uncertain", "stopped", "infrastructure_failed"}:
        return "infrastructure"
    return state.removesuffix("_failed")


def load_run(run_root: Path) -> tuple[Campaign, dict[str, object], dict[str, dict[str, object]]]:
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    config = manifest.get("config")
    if not isinstance(config, dict) or manifest.get("config_digest") != digest(config):
        raise ValueError("tavern_full_call_config_digest_invalid")
    campaign = Campaign.model_validate(config, strict=True)
    expected = Campaign.model_validate(build_manifest(
        budget_document={"budget": campaign.budget.model_dump(mode="json")},
        transport="minimax",
    )).model_dump(mode="json")
    if config != expected or campaign.id != CAMPAIGN_ID or campaign.transport != "minimax":
        raise ValueError("tavern_full_call_campaign_invalid")
    report = json.loads((run_root / "report.json").read_text(encoding="utf-8"))
    rows = report.get("samples")
    if (
        report.get("version") != "quality-report-v1" or report.get("campaign") != CAMPAIGN_ID
        or report.get("expected_samples") != 20 or report.get("independent_families") != 10
        or not isinstance(rows, list) or len(rows) != 20
    ):
        raise ValueError("tavern_full_call_report_invalid")
    states = Counter(row.get("state") for row in rows if isinstance(row, dict))
    if report.get("states") != dict(states):
        raise ValueError("tavern_full_call_state_summary_invalid")
    expected_samples = {sample_id: (identity, case, variant) for sample_id, identity, case, variant in campaign.samples()}
    by_case: dict[str, dict[str, object]] = {}
    for row in rows:
        result = row.get("result") if isinstance(row, dict) else None
        expected_row = expected_samples.get(row.get("sample_id")) if isinstance(row, dict) else None
        if not isinstance(result, dict) or expected_row is None:
            raise ValueError("tavern_full_call_sample_invalid")
        identity, case, variant = expected_row
        state = row.get("state")
        if (
            state not in TERMINAL or result.get("status") != state
            or result.get("failure_owner") != _owner(state)
            or row.get("case") != case.id or row.get("family") != case.family
            or row.get("variant") != VARIANT or variant.id != VARIANT
            or row.get("repetition") != identity["repetition"] or case.id in by_case
        ):
            raise ValueError("tavern_full_call_sample_binding_invalid")
        references = result.get("evidence")
        if not isinstance(references, list) or len(references) != 1:
            raise ValueError("tavern_full_call_evidence_reference_invalid")
        reference = references[0]
        evidence_path = run_root / case.id / VARIANT / "0" / "storage" / EVIDENCE_NAME
        if (
            not isinstance(reference, dict) or reference.get("path") != EVIDENCE_NAME
            or reference.get("contract") != EVIDENCE_CONTRACT
            or reference.get("sha256") != file_sha(evidence_path)
        ):
            raise ValueError("tavern_full_call_evidence_digest_invalid")
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        if evidence.get("case_id") != case.id or evidence.get("campaign_id") != CAMPAIGN_ID:
            raise ValueError("tavern_full_call_evidence_case_invalid")
        if state == "completed":
            checks = evidence.get("operational_checks")
            if (
                evidence.get("message_commit_scope") != "primary_output_only"
                or not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values())
                or not isinstance(evidence.get("reply"), str) or not evidence["reply"]
            ):
                raise ValueError("tavern_full_call_completed_operational_evidence_invalid")
        by_case[case.id] = {"sample": row, "evidence": evidence, "case": case.model_dump(mode="json")}
    if set(by_case) != {row["case_id"] for row in sample_catalog()}:
        raise ValueError("tavern_full_call_case_set_invalid")

    usage = report.get("campaign_usage")
    wires = usage.get("wires") if isinstance(usage, dict) else None
    if (
        not isinstance(wires, list) or usage.get("wire_count") != len(wires)
        or len(wires) > 60 or usage.get("stopped") is not None
    ):
        raise ValueError("tavern_full_call_wire_accounting_invalid")
    counts: Counter[str] = Counter()
    valid_samples = set(expected_samples)
    seen_wires: set[str] = set()
    charged_or_reserved = 0
    unknown_usage = 0
    for wire in wires:
        metadata = wire.get("metadata") if isinstance(wire, dict) else None
        started = wire.get("started") if isinstance(wire, dict) else None
        finished = wire.get("finished") if isinstance(wire, dict) else None
        reserved = wire.get("reserved") if isinstance(wire, dict) else None
        charged = wire.get("charged") if isinstance(wire, dict) else None
        if (
            not isinstance(wire, dict) or not isinstance(wire.get("id"), str)
            or wire["id"] in seen_wires or wire.get("campaign") != CAMPAIGN_ID
            or wire.get("sample") not in valid_samples or wire.get("state") not in {"finished", "uncertain"}
            or not isinstance(started, (int, float)) or not isinstance(finished, (int, float)) or finished < started
            or not isinstance(reserved, int) or reserved < 0
            or not isinstance(charged, int) or charged < 0
            or (isinstance(metadata, dict) and metadata.get("call_kind") != "generation")
            or (metadata is None and wire.get("state") != "uncertain")
        ):
            raise ValueError("tavern_full_call_wire_binding_invalid")
        seen_wires.add(wire["id"])
        counts[wire["sample"]] += 1
        charged_or_reserved += charged
        unknown_usage += not isinstance(metadata, dict) or metadata.get("total_tokens") is None
    if (
        any(count > SAMPLE_WIRE_LIMIT for count in counts.values())
        or usage.get("charged_or_reserved_tokens") != charged_or_reserved
        or usage.get("unknown_usage_requests") != unknown_usage
    ):
        raise ValueError("tavern_full_call_wire_ceiling_exceeded")
    for value in by_case.values():
        evidence_calls = value["evidence"].get("provider_calls")
        sample_id = value["sample"].get("sample_id")
        if not isinstance(evidence_calls, int) or evidence_calls != counts[sample_id]:
            raise ValueError("tavern_full_call_evidence_wire_count_mismatch")
    return campaign, report, by_case


def _load_committed_preregistration(*, path: Path, commit: str, campaign_config: dict[str, object]) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("tavern_full_call_prereg_commit_invalid")
    try:
        relative = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError as exc:
        raise ValueError("tavern_full_call_prereg_path_outside_repository") from exc
    result = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=REPO_ROOT, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError("tavern_full_call_prereg_not_committed")
    prereg = json.loads(result.stdout)
    if (
        not isinstance(prereg, dict) or prereg.get("version") != PREREG_VERSION
        or prereg.get("campaign_id") != CAMPAIGN_ID
        or prereg.get("ordinary_git_preregistration") is not True
        or prereg.get("campaign_manifest_canonical_sha256") != digest(campaign_config)
        or prereg.get("config") != campaign_config or prereg.get("gate") != GATE
        or prereg.get("fixture_sha256") != FIXTURE_SHA256
    ):
        raise ValueError("tavern_full_call_prereg_binding_invalid")
    bound = prereg.get("bound_file_sha256")
    expected = {name: file_sha(REPO_ROOT / name) for name in BOUND_FILES}
    if bound != expected:
        raise ValueError("tavern_full_call_prereg_source_drift")
    for name, expected_sha in expected.items():
        committed = subprocess.run(
            ["git", "show", f"{commit}:{name}"], cwd=REPO_ROOT,
            capture_output=True, check=False,
        )
        if committed.returncode != 0 or hashlib.sha256(committed.stdout).hexdigest() != expected_sha:
            raise ValueError("tavern_full_call_prereg_source_not_committed")
    return prereg


def build_packet(*, run_root: Path, prereg_git_commit: str, prereg_path: Path = PREREG_PATH, seed: int = REVIEW_SEED) -> tuple[dict[str, object], dict[str, object]]:
    if re.fullmatch(r"[0-9a-f]{40}", prereg_git_commit) is None:
        raise ValueError("tavern_full_call_prereg_commit_invalid")
    campaign, report, by_case = load_run(run_root)
    frozen_config = build_manifest(
        budget_document={"budget": campaign.budget.model_dump(mode="json")},
        transport="minimax",
    )
    prereg = _load_committed_preregistration(
        path=prereg_path, commit=prereg_git_commit,
        campaign_config=frozen_config,
    )
    fixture = load_fixture()
    rng = random.Random(seed)
    family_order = list(fixture.families)
    rng.shuffle(family_order)
    packet_rows: list[dict[str, object]] = []
    key_rows: list[dict[str, object]] = []
    for pair_index, family in enumerate(family_order, start=1):
        catalog = [row for row in sample_catalog() if row["family_id"] == family.family_id]
        left, right = by_case[catalog[0]["case_id"]], by_case[catalog[1]["case_id"]]
        completed = left["sample"]["state"] == "completed" and right["sample"]["state"] == "completed"
        blindable = completed and all(
            isinstance(row["evidence"].get("private_resource_ids"), list)
            and not any(
                isinstance(token, str) and token and token in row["evidence"].get("reply", "")
                for token in row["evidence"]["private_resource_ids"]
            )
            for row in (left, right)
        )
        strict = bool(completed and blindable)
        # Family order is seeded and shuffled; exactly five pairs flip so the
        # hidden supported arm is balanced 5/5 across A and B.
        flip = pair_index <= 5
        arm_rows = [right, left] if flip else [left, right]
        if strict:
            candidates = [
                {
                    "authoritative_source": row["evidence"]["source"],
                    "request": row["evidence"]["public_request"],
                    "guidance": row["evidence"]["public_guidance"],
                    "response": row["evidence"]["reply"],
                }
                for row in arm_rows
            ]
        else:
            candidates = [UNAVAILABLE.copy(), UNAVAILABLE.copy()]
        pair_id = f"pair-{pair_index:02}"
        packet_rows.append({"pair_id": pair_id, "candidate_a": candidates[0], "candidate_b": candidates[1]})
        labels = ([catalog[1], catalog[0]] if flip else catalog)
        key_rows.append({
            "pair_id": pair_id, "family_id": family.family_id, "axis": family.axis,
            "second_polarity": family.second_polarity, "strict_pair": strict,
            "labels": {"candidate_a": labels[0], "candidate_b": labels[1]},
            "candidate_a_sha256": value_sha(candidates[0]),
            "candidate_b_sha256": value_sha(candidates[1]),
        })
    packet = {
        "version": PACKET_VERSION,
        "scope": "anonymous committed authority plus final Tavern response only",
        "review_axes": AXES,
        "grading": ["pass", "minor", "major", "not_evaluable"],
        "rubric": public_rubric(),
        "cases": packet_rows,
    }
    key = {
        "version": KEY_VERSION, "campaign_id": CAMPAIGN_ID, "seed": seed,
        "prereg_git_commit": prereg_git_commit, "fixture_sha256": FIXTURE_SHA256,
        "prereg_canonical_sha256": value_sha(prereg),
        "manifest_file_sha256": file_sha(run_root / "manifest.json"),
        "report_file_sha256": file_sha(run_root / "report.json"),
        "rubric_file_sha256": file_sha(RUBRIC_PATH),
        "packet_canonical_sha256": value_sha(packet), "gate": GATE, "cases": key_rows,
    }
    return packet, key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--prereg-git-commit", required=True)
    parser.add_argument("--prereg", type=Path, default=PREREG_PATH)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    args = parser.parse_args()
    packet, key = build_packet(run_root=args.run, prereg_git_commit=args.prereg_git_commit, prereg_path=args.prereg)
    args.packet.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.key.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
