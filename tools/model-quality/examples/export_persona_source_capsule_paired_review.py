"""Rebuild a blinded Persona capsule review packet from one frozen live run.

The review packet deliberately contains only the authoritative synthetic source
and anonymous Persona proposals.  If either arm lacks a strict proposal, both
anonymous candidates become the same sentinel so run status cannot unblind the
failed arm.  The separately stored key binds every value back to the frozen
manifest, report, fixture, and adapter evidence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from app.models.persona_generation import PersonaCardBatchContentProposalV1
from examples.prepare_persona_source_capsule_live import build_manifest as build_live_manifest
from model_quality.protocol import Campaign, digest
from vibe_learner.persona_source_capsule import PersonaSourceCapsuleFixtureV1
from vibe_learner.persona_source_capsule_live import (
    BASELINE_VARIANT,
    CANDIDATE_VARIANT,
    EVIDENCE_CONTRACT,
    EVIDENCE_NAME,
    FIXTURE,
    FIXTURE_SHA256,
    PREREGISTERED_GATE,
    RUBRIC,
    SCOPE,
    build_payload,
    build_prompt_projection,
)


CAMPAIGN_ID = "m3-persona-source-capsule-paired-fresh-20260913-v1"
ADAPTER = "vibe_learner.persona_source_capsule_live:run_sample"
REVIEW_SEED = 913719
RUN_ANCHOR_VERSION = "m3-persona-source-capsule-frozen-run-anchor-v1"
UNAVAILABLE = {
    "not_evaluable": True,
    "reason": "strict_pair_unavailable",
}
TERMINAL_STATES = {
    "completed",
    "candidate_failed",
    "data_failed",
    "grader_failed",
    "metric_failed",
    "infrastructure_failed",
    "uncertain",
    "stopped",
}


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


def _repo_relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path(__file__).resolve().parents[3]).as_posix()
    except ValueError as exc:
        raise ValueError("persona_capsule_run_anchor_path_outside_repo") from exc


def build_run_anchor(run_root: Path) -> dict[str, object]:
    """Validate a terminal run and enumerate every review-consumed file digest."""
    _load_run(run_root)
    evidence_files = {
        _repo_relative(path): _file_digest(path)
        for path in sorted(run_root.glob(f"*/*/0/storage/{EVIDENCE_NAME}"))
    }
    return {
        "version": RUN_ANCHOR_VERSION,
        "run_root": _repo_relative(run_root),
        "manifest_file_sha256": _file_digest(run_root / "manifest.json"),
        "report_file_sha256": _file_digest(run_root / "report.json"),
        "evidence_files": evidence_files,
    }


def validate_run_anchor(run_root: Path, anchor: dict[str, object]) -> None:
    if set(anchor) != {
        "version",
        "run_root",
        "manifest_file_sha256",
        "report_file_sha256",
        "evidence_files",
    } or anchor.get("version") != RUN_ANCHOR_VERSION:
        raise ValueError("persona_capsule_run_anchor_schema_invalid")
    evidence_files = anchor.get("evidence_files")
    actual_evidence = {
        _repo_relative(path): _file_digest(path)
        for path in sorted(run_root.glob(f"*/*/0/storage/{EVIDENCE_NAME}"))
    }
    if (
        anchor.get("run_root") != _repo_relative(run_root)
        or anchor.get("manifest_file_sha256") != _file_digest(run_root / "manifest.json")
        or anchor.get("report_file_sha256") != _file_digest(run_root / "report.json")
        or not isinstance(evidence_files, dict)
        or evidence_files != actual_evidence
    ):
        raise ValueError("persona_capsule_run_anchor_mismatch")


def load_committed_run_anchor(anchor_path: Path, git_commit: str) -> dict[str, object]:
    """Require the anchor bytes to exist in the named immutable Git commit."""
    if re.fullmatch(r"[0-9a-f]{40}", git_commit) is None:
        raise ValueError("persona_capsule_run_anchor_commit_invalid")
    repo_root = Path(__file__).resolve().parents[3]
    relative = _repo_relative(anchor_path)
    result = subprocess.run(
        ["git", "show", f"{git_commit}:{relative}"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout != anchor_path.read_bytes():
        raise ValueError("persona_capsule_run_anchor_not_committed")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("persona_capsule_run_anchor_schema_invalid")
    return value


def _expected_owner(state: str) -> str | None:
    if state == "completed":
        return None
    if state in {"uncertain", "stopped", "infrastructure_failed"}:
        return "infrastructure"
    return state.removesuffix("_failed")


def _validated_wires(
    report: dict[str, object], expected_sample_ids: set[str]
) -> Counter[str]:
    usage = report.get("campaign_usage")
    wires = usage.get("wires") if isinstance(usage, dict) else None
    if not isinstance(wires, list) or usage.get("wire_count") != len(wires):
        raise ValueError("persona_capsule_review_wire_accounting_invalid")
    counts: Counter[str] = Counter()
    wire_ids: set[str] = set()
    charged_or_reserved = 0
    for wire in wires:
        metadata = wire.get("metadata") if isinstance(wire, dict) else None
        wire_id = wire.get("id") if isinstance(wire, dict) else None
        sample_id = wire.get("sample") if isinstance(wire, dict) else None
        reserved = wire.get("reserved") if isinstance(wire, dict) else None
        charged = wire.get("charged") if isinstance(wire, dict) else None
        if (
            not isinstance(wire_id, str)
            or not wire_id
            or wire_id in wire_ids
            or wire.get("campaign") != CAMPAIGN_ID
            or sample_id not in expected_sample_ids
            or wire.get("state") not in {"finished", "uncertain"}
            or not isinstance(wire.get("started"), (int, float))
            or not isinstance(wire.get("finished"), (int, float))
            or wire["finished"] < wire["started"]
            or (
                metadata is not None
                and (
                    not isinstance(metadata, dict)
                    or metadata.get("call_kind") != "generation"
                )
            )
            or (metadata is None and wire.get("state") != "uncertain")
            or not isinstance(reserved, int)
            or reserved < 0
            or not isinstance(charged, int)
            or charged < 0
        ):
            raise ValueError("persona_capsule_review_wire_binding_invalid")
        wire_ids.add(wire_id)
        counts[sample_id] += 1
        charged_or_reserved += charged
    unknown_usage = sum(
        not isinstance(wire.get("metadata"), dict)
        or wire["metadata"].get("total_tokens") is None
        for wire in wires
        if isinstance(wire, dict)
    )
    if (
        any(count > 1 for count in counts.values())
        or usage.get("charged_or_reserved_tokens") != charged_or_reserved
        or usage.get("unknown_usage_requests") != unknown_usage
    ):
        raise ValueError("persona_capsule_review_wire_accounting_invalid")
    return counts


def _load_run(run_root: Path):
    manifest_path = run_root / "manifest.json"
    report_path = run_root / "report.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = manifest.get("config")
    if not isinstance(config, dict) or manifest.get("config_digest") != digest(config):
        raise ValueError("persona_capsule_review_config_digest_invalid")
    campaign = Campaign.model_validate(config, strict=True)
    expected_config = Campaign.model_validate(
        build_live_manifest(
            budget_document={"budget": campaign.budget.model_dump(mode="json")},
            transport="minimax",
        ),
        strict=True,
    ).model_dump(mode="json")
    if (
        campaign.model_dump(mode="json") != expected_config
        or config != expected_config
        or campaign.id != CAMPAIGN_ID
        or campaign.adapter != ADAPTER
        or campaign.transport != "minimax"
        or campaign.model != "MiniMax-M3"
        or campaign.thinking != "adaptive"
        or campaign.temperature != 0.2
        or campaign.max_output_tokens != 4096
        or campaign.sample_wire_limit != 1
        or campaign.repetitions != 1
        or len(campaign.cases) != 8
        or {variant.id for variant in campaign.variants}
        != {BASELINE_VARIANT, CANDIDATE_VARIANT}
    ):
        raise ValueError("persona_capsule_review_campaign_invalid")
    if any(
        case.family != case.id
        or case.split != "confirmation"
        or case.provenance != "synthetic-authored"
        or case.rubric != RUBRIC
        for case in campaign.cases
    ):
        raise ValueError("persona_capsule_review_case_config_invalid")

    fixture_raw = FIXTURE.read_bytes()
    if hashlib.sha256(fixture_raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError("persona_capsule_review_fixture_digest_invalid")
    fixture = PersonaSourceCapsuleFixtureV1.model_validate_json(fixture_raw, strict=True)
    fixture_by_case = {case.case_id: case for case in fixture.cases}
    campaign_by_case = {case.id: case for case in campaign.cases}
    if len(fixture_by_case) != 8 or set(fixture_by_case) != set(campaign_by_case):
        raise ValueError("persona_capsule_review_fixture_case_set_invalid")
    for case_id, case in campaign_by_case.items():
        fixture_case = fixture_by_case[case_id]
        spec = json.loads(case.gold)
        if (
            case.source != fixture_case.source_text
            or spec
            != {
                "fixture_sha256": FIXTURE_SHA256,
                "source_sha256": fixture_case.capsule.source_sha256,
                "capsule_sha256": fixture_case.capsule_sha256,
                "fake_proposal": fixture_case.valid_minimal_persona_card_batch_proposal,
                "preregistered_gate": PREREGISTERED_GATE,
            }
        ):
            raise ValueError(f"persona_capsule_review_fixture_binding_invalid:{case_id}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = report.get("samples")
    if (
        report.get("version") != "quality-report-v1"
        or report.get("campaign") != CAMPAIGN_ID
        or report.get("transport") != "minimax"
        or report.get("scope")
        != "research infrastructure; not Harness evidence or independent quality certification"
        or report.get("expected_samples") != 16
        or report.get("independent_families") != 8
        or not isinstance(rows, list)
        or len(rows) != 16
    ):
        raise ValueError("persona_capsule_review_report_invalid")
    states = Counter(row.get("state") for row in rows if isinstance(row, dict))
    owners = Counter(
        row.get("result", {}).get("failure_owner")
        for row in rows
        if isinstance(row, dict)
        and isinstance(row.get("result"), dict)
        and row["result"].get("failure_owner")
    )
    if (
        report.get("states") != dict(states)
        or report.get("failure_owners") != dict(owners)
    ):
        raise ValueError("persona_capsule_review_state_summary_invalid")
    expected_samples = {
        sample_id: (identity, case, variant)
        for sample_id, identity, case, variant in campaign.samples()
    }
    expected_pairs: dict[str, dict[str, str]] = {}
    by_case: dict[str, dict[str, dict[str, object]]] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("persona_capsule_review_sample_invalid")
        sample_id = row.get("sample_id")
        expected = expected_samples.get(sample_id)
        result = row.get("result")
        if expected is None or not isinstance(result, dict):
            raise ValueError("persona_capsule_review_sample_invalid")
        identity, case, variant = expected
        state = row.get("state")
        if (
            state not in TERMINAL_STATES
            or row.get("campaign") != CAMPAIGN_ID
            or row.get("case") != case.id
            or row.get("variant") != variant.id
            or row.get("repetition") != identity["repetition"]
            or row.get("family") != case.family
            or result.get("status") != state
            or result.get("failure_owner") != _expected_owner(state)
            or (
                state == "completed"
                and result.get("scope") != SCOPE
            )
            or (
                state != "completed"
                and result.get("scope") not in {None, SCOPE}
            )
        ):
            raise ValueError("persona_capsule_review_sample_invalid")
        variant_rows = by_case.setdefault(case.id, {})
        if variant.id in variant_rows:
            raise ValueError("persona_capsule_review_duplicate_arm")
        references = result.get("evidence", [])
        if not isinstance(references, list) or len(references) > 1:
            raise ValueError("persona_capsule_review_evidence_reference_invalid")
        evidence = None
        evidence_sha256 = None
        if references:
            reference = references[0]
            if (
                not isinstance(reference, dict)
                or reference.get("path") != EVIDENCE_NAME
                or reference.get("contract") != EVIDENCE_CONTRACT
                or not isinstance(reference.get("sha256"), str)
            ):
                raise ValueError("persona_capsule_review_evidence_reference_invalid")
            evidence_path = (
                run_root / case.id / variant.id / "0" / "storage" / EVIDENCE_NAME
            )
            evidence_sha256 = _file_digest(evidence_path)
            if evidence_sha256 != reference["sha256"]:
                raise ValueError(
                    f"persona_capsule_review_evidence_digest_mismatch:{case.id}:{variant.id}"
                )
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            fixture_case = fixture_by_case[case.id]
            expected_projection = (
                build_prompt_projection(fixture_case.capsule)
                if variant.id == CANDIDATE_VARIANT
                else {"version": "production-prompt-no-capsule-projection-v1"}
            )
            expected_payload = build_payload(
                campaign=campaign,
                source=case.source,
                projection=(
                    expected_projection
                    if variant.id == CANDIDATE_VARIANT
                    else None
                ),
            )
            if (
                evidence.get("version") != EVIDENCE_CONTRACT
                or evidence.get("case_id") != case.id
                or evidence.get("variant") != variant.id
                or evidence.get("scope") != SCOPE
                or evidence.get("commit_evidence") != {"status": "not_applicable"}
                or evidence.get("source_sha256") != fixture_case.capsule.source_sha256
                or evidence.get("capsule_sha256") != fixture_case.capsule_sha256
                or evidence.get("prompt_projection_sha256")
                != _digest(expected_projection)
                or evidence.get("provider_payload_sha256")
                != _digest(expected_payload)
                or evidence.get("campaign_config_sha256")
                != _digest(campaign.model_dump(mode="json"))
            ):
                raise ValueError(
                    f"persona_capsule_review_evidence_binding_invalid:{case.id}:{variant.id}"
                )
        if state == "completed":
            if evidence is None or evidence.get("strict_candidate") is not True:
                raise ValueError("persona_capsule_review_completed_candidate_invalid")
            proposal = PersonaCardBatchContentProposalV1.model_validate(
                evidence.get("proposal"), strict=True
            )
            if len(proposal.cards) != 1:
                raise ValueError("persona_capsule_review_completed_candidate_invalid")
            proposal_value: object | None = proposal.model_dump(mode="json")
        else:
            if evidence is not None and (
                evidence.get("strict_candidate") is not False
                or "proposal" in evidence
            ):
                raise ValueError("persona_capsule_review_failed_candidate_invalid")
            proposal_value = None
        variant_rows[variant.id] = {
            "sample_id": sample_id,
            "state": state,
            "proposal": proposal_value,
            "evidence_sha256": evidence_sha256,
        }
        expected_pairs.setdefault(f"{case.id}:0", {})[variant.id] = state
    if any(
        set(arms) != {BASELINE_VARIANT, CANDIDATE_VARIANT}
        for arms in by_case.values()
    ) or set(by_case) != set(campaign_by_case):
        raise ValueError("persona_capsule_review_pair_matrix_invalid")
    if report.get("pairs") != expected_pairs:
        raise ValueError("persona_capsule_review_pair_summary_invalid")
    wire_counts = _validated_wires(report, set(expected_samples))
    for arms in by_case.values():
        for arm in arms.values():
            if arm["state"] == "completed" and wire_counts[arm["sample_id"]] != 1:
                raise ValueError("persona_capsule_review_completed_wire_missing")
    return manifest, report, campaign_by_case, by_case


def build_packet(
    *,
    run_root: Path,
    seed: int,
    run_anchor: dict[str, object],
    anchor_git_commit: str,
) -> tuple[dict[str, object], dict[str, object]]:
    validate_run_anchor(run_root, run_anchor)
    manifest, _, cases, results = _load_run(run_root)
    case_ids = sorted(cases)
    shuffled = list(case_ids)
    random.Random(seed).shuffle(shuffled)
    capsule_on_a = set(shuffled[: len(shuffled) // 2])
    packet_rows: list[dict[str, object]] = []
    key_rows: list[dict[str, object]] = []
    for case_id in case_ids:
        baseline = results[case_id][BASELINE_VARIANT]
        capsule = results[case_id][CANDIDATE_VARIANT]
        pair_available = (
            baseline["proposal"] is not None and capsule["proposal"] is not None
        )
        values = {
            BASELINE_VARIANT: baseline["proposal"] if pair_available else UNAVAILABLE,
            CANDIDATE_VARIANT: capsule["proposal"] if pair_available else UNAVAILABLE,
        }
        order = (
            [CANDIDATE_VARIANT, BASELINE_VARIANT]
            if case_id in capsule_on_a
            else [BASELINE_VARIANT, CANDIDATE_VARIANT]
        )
        candidates = {
            "candidate_a": values[order[0]],
            "candidate_b": values[order[1]],
        }
        source = cases[case_id].source
        packet_rows.append({
            "case_id": case_id,
            "authoritative_source": source,
            **candidates,
        })
        key_rows.append({
            "case_id": case_id,
            "labels": {"candidate_a": order[0], "candidate_b": order[1]},
            "source_sha256": _digest(source),
            "candidate_a_sha256": _digest(candidates["candidate_a"]),
            "candidate_b_sha256": _digest(candidates["candidate_b"]),
            "baseline_sample_id": baseline["sample_id"],
            "capsule_sample_id": capsule["sample_id"],
            "baseline_evidence_sha256": baseline["evidence_sha256"],
            "capsule_evidence_sha256": capsule["evidence_sha256"],
            "pair_strict_candidate": pair_available,
        })
    packet = {
        "version": "m3-persona-source-capsule-blinded-paired-review-v1",
        "scope": "synthetic authoritative source plus anonymous Persona proposals only",
        "review_axes": [
            "relationship_fidelity",
            "permission_fidelity",
            "profession_uncertainty",
            "shared_history_invention",
            "epistemic_provenance",
            "task_format_adherence",
        ],
        "grading": ["pass", "minor", "major", "not_evaluable"],
        "cases": packet_rows,
    }
    key = {
        "version": "m3-persona-source-capsule-blinded-paired-review-key-v2",
        "packet_canonical_sha256": _digest(packet),
        "seed": seed,
        "manifest_config_digest": manifest["config_digest"],
        "manifest_file_sha256": _file_digest(run_root / "manifest.json"),
        "report_file_sha256": _file_digest(run_root / "report.json"),
        "run_anchor_sha256": _digest(run_anchor),
        "run_anchor_git_commit": anchor_git_commit,
        "fixture_sha256": FIXTURE_SHA256,
        "proposal_commit": "not_applicable",
        "persona_save": False,
        "cases": key_rows,
    }
    return packet, key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--run-anchor", type=Path, required=True)
    parser.add_argument("--run-anchor-git-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--key-output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=REVIEW_SEED)
    args = parser.parse_args()
    run_anchor = load_committed_run_anchor(
        args.run_anchor, args.run_anchor_git_commit
    )
    packet, key = build_packet(
        run_root=args.run,
        seed=args.seed,
        run_anchor=run_anchor,
        anchor_git_commit=args.run_anchor_git_commit,
    )
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    args.key_output.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
