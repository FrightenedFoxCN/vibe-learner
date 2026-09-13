"""Export a minimal absolute-blind packet and a separate sealed key.

The packet contains only an anonymous token, the two authoritative sources,
and ID-free anonymous proposals.  Family/campaign identity, terminal status,
trace, expected constraints, oracle, key material, and model reasoning remain
exclusively outside the packet.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import subprocess

from model_quality.ledger import Ledger
from model_quality.protocol import Campaign, digest
from vibe_learner.persona_scene_full_call_blind import (
    CAMPAIGN_ID, EVIDENCE_CONTRACT, EVIDENCE_NAME, FIXTURE, PREREGISTRATION, RUBRIC, SCOPE,
)
from examples.prepare_persona_scene_full_call_blind import (
    ADAPTER, SOURCE_TREE_EXACT_PATHS, SOURCE_TREE_RULES, canonical,
)


PACKET_VERSION = "persona-scene-production-full-call-absolute-blind-packet-v1"
KEY_VERSION = "persona-scene-production-full-call-absolute-blind-key-v1"
UNAVAILABLE = {"not_evaluable": True}
REVIEW_SEED = 91343
TERMINAL_STATES = {"completed", "candidate_failed", "data_failed", "infrastructure_failed", "uncertain", "stopped"}
SEALED_ORACLE = FIXTURE.parent / "persona-scene-production-full-call-blind-oracle-v1.json"
REPOSITORY = Path(__file__).resolve().parents[3]
PREREG_REPO_PATH = PREREGISTRATION.relative_to(REPOSITORY).as_posix()


def _git_show(commit: str, path: str) -> bytes:
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("full_call_prereg_git_commit_invalid")
    result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=REPOSITORY, capture_output=True, check=False)
    if result.returncode != 0:
        raise ValueError(f"full_call_prereg_path_not_committed:{path}")
    return result.stdout


def _committed_source_tree(commit: str) -> tuple[dict[str, str], dict[str, object]]:
    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit],
        cwd=REPOSITORY, capture_output=True, text=True, check=False,
    )
    if listing.returncode != 0:
        raise ValueError("full_call_source_tree_commit_invalid")
    committed_paths = set(listing.stdout.splitlines())
    selected = {
        path for path in committed_paths
        if (
            path.startswith("services/ai/app/") and path.endswith(".py")
            or path.startswith("services/ai/app/prompts/") and path.endswith(".txt")
            or path.startswith("tools/model-quality/model_quality/") and path.endswith(".py")
        )
    }
    selected.update(SOURCE_TREE_EXACT_PATHS)
    if not selected.issubset(committed_paths):
        raise ValueError("full_call_source_tree_path_not_committed")
    manifest = {path: hashlib.sha256(_git_show(commit, path)).hexdigest() for path in sorted(selected)}
    binding = {
        "rules": list(SOURCE_TREE_RULES),
        "exact_paths": list(SOURCE_TREE_EXACT_PATHS),
        "path_count": len(manifest),
        "canonical_manifest_sha256": hashlib.sha256(canonical(manifest).encode("utf-8")).hexdigest(),
    }
    return manifest, binding


def _committed_preregistration(commit: str, *, verify_current_exporter: bool = True) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    raw = _git_show(commit, PREREG_REPO_PATH)
    prereg = json.loads(raw)
    research_paths = {
        "fixture": "tools/model-quality/fixtures/persona-scene/persona-scene-production-full-call-blind-v1.json",
        "prepare_manifest": "tools/model-quality/examples/prepare_persona_scene_full_call_blind.py",
        "adapter": "tools/model-quality/integrations/vibe_learner/persona_scene_full_call_blind.py",
        "blind_packet_key_exporter": "tools/model-quality/examples/export_persona_scene_full_call_blind.py",
        "strict_two_reviewer_aggregator": "tools/model-quality/examples/aggregate_persona_scene_full_call_blind.py",
        "tests": "tools/model-quality/integration_tests/test_persona_scene_full_call_blind.py",
    }
    source_tree_manifest, source_tree_binding = _committed_source_tree(commit)
    if (
        prereg.get("campaign_id") != CAMPAIGN_ID
        or prereg.get("source_bindings") != {name: hashlib.sha256(_git_show(commit, path)).hexdigest() for name, path in research_paths.items()}
        or prereg.get("source_tree_binding") != source_tree_binding
    ):
        raise ValueError("full_call_committed_prereg_closure_invalid")
    oracle_path = "tools/model-quality/fixtures/persona-scene/persona-scene-production-full-call-blind-oracle-v1.json"
    oracle_raw = _git_show(commit, oracle_path)
    if prereg.get("review_bindings") != {"sealed_review_oracle": hashlib.sha256(oracle_raw).hexdigest()}:
        raise ValueError("full_call_committed_oracle_binding_invalid")
    if verify_current_exporter and file_sha256(Path(__file__)) != prereg["source_bindings"]["blind_packet_key_exporter"]:
        raise ValueError("full_call_exporter_worktree_drift")
    fixture = json.loads(_git_show(commit, research_paths["fixture"]))
    oracle = json.loads(oracle_raw)
    return prereg, fixture, oracle


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_scene_ids(value: object) -> object:
    if isinstance(value, list):
        return [_strip_scene_ids(item) for item in value]
    if isinstance(value, dict):
        forbidden = {"id", "reuse_id", "selected_layer_id", "config_id", "scene_id", "created_at", "updated_at", "scene_profile"}
        return {key: _strip_scene_ids(item) for key, item in value.items() if key not in forbidden}
    return value


def _walk(value: object):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def _validate_packet_privacy(packet: dict[str, object], key: dict[str, object]) -> None:
    forbidden_keys = {
        "campaign_id", "family_id", "sample_id", "sample_status", "persona_status",
        "scene_status", "harness_trace", "trace", "oracle", "expected", "reasoning",
        "id", "reuse_id", "selected_layer_id", "scene_id", "persona_id",
    }
    private_values = {CAMPAIGN_ID}
    for row in key["cases"]:
        private_values.update(value for name, value in row.items() if name in {"family_id", "sample_id", "evidence_sha256"} and isinstance(value, str))
    for value in _walk(packet):
        if isinstance(value, dict) and forbidden_keys.intersection(value):
            raise ValueError("full_call_blind_packet_private_key")
        if isinstance(value, str) and value in private_values:
            raise ValueError("full_call_blind_packet_private_identifier")


def _validate_wires(report: dict[str, object], expected_sample_ids: set[str]) -> dict[str, list[dict[str, object]]]:
    usage = report.get("campaign_usage")
    wires = usage.get("wires") if isinstance(usage, dict) else None
    if not isinstance(wires, list) or usage.get("wire_count") != len(wires) or len(wires) > 32:
        raise ValueError("full_call_wire_accounting_invalid")
    by_sample = {sample_id: [] for sample_id in expected_sample_ids}
    wire_ids: set[str] = set()
    charged = 0
    unknown = 0
    for wire in wires:
        metadata = wire.get("metadata") if isinstance(wire, dict) else None
        wire_id = wire.get("id") if isinstance(wire, dict) else None
        sample_id = wire.get("sample") if isinstance(wire, dict) else None
        state = wire.get("state") if isinstance(wire, dict) else None
        if (
            not isinstance(wire_id, str) or not wire_id or wire_id in wire_ids
            or wire.get("campaign") != CAMPAIGN_ID
            or sample_id not in expected_sample_ids
            or state not in {"finished", "uncertain"}
            or not isinstance(wire.get("started"), (int, float))
            or not isinstance(wire.get("finished"), (int, float))
            or wire["finished"] < wire["started"]
            or not isinstance(wire.get("reserved"), int) or wire["reserved"] < 0
            or not isinstance(wire.get("charged"), int) or wire["charged"] < 0
            or not isinstance(metadata, dict)
            or metadata.get("call_kind") not in {"persona_generation", "scene_generation"}
            or metadata.get("max_tokens") not in {4096, 6144}
            or (metadata.get("http_status") is not None and not isinstance(metadata.get("http_status"), int))
            or (metadata.get("finish_reason") is not None and metadata.get("finish_reason") not in {"stop", "length", "tool_calls", "content_filter", "function_call"})
        ):
            raise ValueError("full_call_wire_binding_invalid")
        for token_key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            token_value = metadata.get(token_key)
            if token_value is not None and (not isinstance(token_value, int) or token_value < 0):
                raise ValueError("full_call_wire_usage_invalid")
        if state == "finished" and (
            not isinstance(metadata.get("http_status"), int)
            or not 200 <= metadata["http_status"] < 500
        ):
            raise ValueError("full_call_finished_wire_http_status_invalid")
        if (
            metadata.get("total_tokens") is not None
            and isinstance(metadata.get("prompt_tokens"), int)
            and isinstance(metadata.get("completion_tokens"), int)
            and metadata.get("total_tokens") != metadata["prompt_tokens"] + metadata["completion_tokens"]
        ):
            raise ValueError("full_call_wire_usage_sum_invalid")
        wire_ids.add(wire_id)
        charged += wire["charged"]
        unknown += metadata.get("total_tokens") is None
        by_sample[sample_id].append({
            "wire_id": wire_id,
            "call_kind": metadata["call_kind"],
            "http_status": metadata.get("http_status"),
            "finish_reason": metadata.get("finish_reason"),
            "max_tokens": metadata["max_tokens"],
            "prompt_tokens": metadata.get("prompt_tokens"),
            "completion_tokens": metadata.get("completion_tokens"),
            "total_tokens": metadata.get("total_tokens"),
            "state": state,
        })
    if usage.get("charged_or_reserved_tokens") != charged or usage.get("unknown_usage_requests") != unknown:
        raise ValueError("full_call_wire_usage_summary_invalid")
    for rows in by_sample.values():
        persona = [row for row in rows if row["call_kind"] == "persona_generation"]
        scene = [row for row in rows if row["call_kind"] == "scene_generation"]
        if len(persona) > 2 or len(scene) > 2 or len(rows) > 4:
            raise ValueError("full_call_per_sample_wire_ceiling_invalid")
        for domain_rows in (persona, scene):
            caps = [row["max_tokens"] for row in domain_rows]
            if caps not in ([], [4096], [4096, 6144]):
                raise ValueError("full_call_production_repair_token_sequence_invalid")
    return by_sample


def _durable_ledger_snapshot(manifest: dict[str, object], run_root: Path) -> dict[str, object]:
    raw_path = manifest.get("ledger_path")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("full_call_ledger_path_missing")
    ledger_path = Path(raw_path)
    if not ledger_path.is_absolute() or not ledger_path.is_file():
        raise ValueError("full_call_ledger_path_invalid")
    with ledger_path.open("rb") as stream:
        header = stream.read(16)
    if header != b"SQLite format 3\x00":
        raise ValueError("full_call_ledger_path_invalid")
    uri = f"file:{ledger_path.as_posix()}?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as db:
            row = db.execute("SELECT binding FROM campaigns WHERE id=?", (CAMPAIGN_ID,)).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("full_call_ledger_schema_invalid") from exc
    expected_binding = digest({"manifest": manifest, "output": str(run_root.resolve())})
    if row is None or row[0] != expected_binding:
        raise ValueError("full_call_ledger_campaign_binding_invalid")
    return Ledger(ledger_path).snapshot(CAMPAIGN_ID)


def _require_report_matches_ledger(report: dict[str, object], durable_usage: dict[str, object]) -> None:
    if report.get("campaign_usage") != durable_usage:
        raise ValueError("full_call_report_durable_ledger_mismatch")


def _load_run(run_root: Path, *, prereg_git_commit: str) -> tuple[Campaign, dict[str, object], dict[str, dict[str, object]], dict[str, object], dict[str, object]]:
    current_prereg, current_fixture, current_oracle = _committed_preregistration(prereg_git_commit)
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    source = manifest.get("source")
    execution_commit = source.get("git_revision") if isinstance(source, dict) else None
    if not isinstance(execution_commit, str):
        raise ValueError("full_call_execution_commit_missing")
    prereg, fixture, oracle = _committed_preregistration(
        execution_commit, verify_current_exporter=False
    )
    if current_fixture != fixture or current_oracle != oracle:
        raise ValueError("full_call_export_correction_fixture_drift")
    config = manifest.get("config")
    if not isinstance(config, dict) or manifest.get("config_digest") != digest(config):
        raise ValueError("full_call_manifest_digest_invalid")
    campaign = Campaign.model_validate(config, strict=True)
    fixed_config = {
        "id": CAMPAIGN_ID, "transport": "minimax", "model": "MiniMax-M3", "adapter": ADAPTER,
        "concurrency": 1, "seed": 91341, "repetitions": 1, "timeout_seconds": 90,
        "sample_deadline_seconds": 600, "sample_wire_limit": 4, "max_output_tokens": 6400,
        "input_reservation_tokens": 100000, "thinking": "adaptive", "temperature": 0.2,
    }
    if any(config.get(key) != value for key, value in fixed_config.items()):
        raise ValueError("full_call_manifest_not_preregistered_config")
    expected_cases = [{
        "id": row["family_id"], "family": row["family_id"],
        "lane": "persona-scene-production-full-call-blind", "split": "confirmation",
        "provenance": "synthetic-authored",
        "source": canonical({"persona_source": row["persona_source"], "scene_source": row["scene_source"]}),
        "request": "Run the complete production Persona and Scene generation/save/read-back lifecycle.",
        "gold": "{}", "rubric": RUBRIC,
    } for row in fixture["cases"]]
    if config.get("cases") != expected_cases or config.get("variants") != [{"id": "production-full-call", "instruction": "Use unchanged production endpoints and their single bounded repair; never substitute fixture output, retry a failed family, or replace a sample."}]:
        raise ValueError("full_call_manifest_case_or_variant_drift")
    recorded_runner = source.get("runner_and_adapter_source", {}) if isinstance(source, dict) else {}
    committed_tree_manifest, committed_tree_binding = _committed_source_tree(execution_commit)
    required_recorded = {
        Path(path).name: digest_value
        for path, digest_value in committed_tree_manifest.items()
        if path.startswith("tools/model-quality/model_quality/") and path.endswith(".py")
    }
    expected_adapter_manifest = {
        "version": "persona-scene-full-call-source-tree-v1",
        "campaign_id": CAMPAIGN_ID,
        "source_tree_binding": committed_tree_binding,
        "preregistration_sha256": hashlib.sha256(_git_show(execution_commit, PREREG_REPO_PATH)).hexdigest(),
    }
    if (
        campaign.id != CAMPAIGN_ID or campaign.adapter != ADAPTER
        or manifest.get("endpoint") != "https://api.minimax.cn/v1/chat/completions"
        or manifest.get("credential_env") != "K3_API_KEY"
        or manifest.get("scope") != "standalone research campaign"
        or not isinstance(source, dict) or source.get("git_revision") != execution_commit
        or not str(source.get("python", "")).startswith("3.12.13")
        or source.get("lock_digest") != committed_tree_manifest["tools/model-quality/uv.lock"]
        or re.fullmatch(r"[0-9a-f]{64}", str(source.get("tracked_dirty_digest", ""))) is None
        or source.get("adapter_source_manifest") != expected_adapter_manifest
        or recorded_runner.get("adapter") != prereg["source_bindings"]["adapter"]
        or any(recorded_runner.get(name) != value for name, value in required_recorded.items())
    ):
        raise ValueError("full_call_campaign_identity_invalid")
    report = json.loads((run_root / "report.json").read_text(encoding="utf-8"))
    samples = report.get("samples")
    if (
        report.get("version") != "quality-report-v1"
        or report.get("campaign") != CAMPAIGN_ID
        or report.get("transport") != "minimax"
        or report.get("expected_samples") != 8
        or not isinstance(samples, list)
        or len(samples) != 8
    ):
        raise ValueError("full_call_report_invalid")
    durable_usage = _durable_ledger_snapshot(manifest, run_root)
    _require_report_matches_ledger(report, durable_usage)
    states = Counter(row.get("state") for row in samples if isinstance(row, dict))
    if report.get("states") != dict(states) or any(state not in TERMINAL_STATES for state in states):
        raise ValueError("full_call_report_states_invalid")
    expected_samples = {sample_id: (identity, case, variant) for sample_id, identity, case, variant in campaign.samples()}
    wires_by_sample = _validate_wires(report, set(expected_samples))
    by_family: dict[str, dict[str, object]] = {}
    for row in samples:
        sample_id = row.get("sample_id") if isinstance(row, dict) else None
        expected_row = expected_samples.get(sample_id)
        result = row.get("result") if isinstance(row, dict) else None
        if expected_row is None or not isinstance(result, dict):
            raise ValueError("full_call_sample_identity_invalid")
        identity, case, variant = expected_row
        if (
            row.get("case") != case.id
            or row.get("family") != case.family
            or row.get("variant") != variant.id
            or row.get("repetition") != identity["repetition"]
            or result.get("status") != row.get("state")
        ):
            raise ValueError("full_call_sample_binding_invalid")
        refs = result.get("evidence", [])
        evidence = None
        if refs:
            if not isinstance(refs, list) or len(refs) != 1:
                raise ValueError("full_call_evidence_reference_invalid")
            ref = refs[0]
            path = run_root / case.id / variant.id / "0" / "storage" / EVIDENCE_NAME
            if (
                ref.get("path") != EVIDENCE_NAME
                or ref.get("contract") != EVIDENCE_CONTRACT
                or ref.get("sha256") != file_sha256(path)
            ):
                raise ValueError("full_call_evidence_digest_invalid")
            evidence = json.loads(path.read_text(encoding="utf-8"))
            if (
                evidence.get("version") != EVIDENCE_CONTRACT
                or evidence.get("campaign_id") != CAMPAIGN_ID
                or evidence.get("case_id") != case.id
                or evidence.get("scope") != SCOPE
                or evidence.get("provider_calls", 0) > 4
                or evidence.get("wire_payload_audit_passed") is not True
            ):
                raise ValueError("full_call_evidence_binding_invalid")
            for domain in ("persona", "scene"):
                item = evidence.get(domain)
                if not isinstance(item, dict) or item.get("wire_count", 0) > 2:
                    raise ValueError("full_call_domain_wire_ceiling_invalid")
        if evidence is not None:
            audit = evidence.get("wire_payload_audit")
            safe_wires = wires_by_sample[sample_id]
            issued_audit = [item for item in audit if item.get("issued_wire") is True] if isinstance(audit, list) else []
            audited_shapes = [
                (item.get("domain"), item.get("max_tokens"))
                for item in issued_audit
            ] if isinstance(audit, list) else []
            wire_shapes = [
                (item["call_kind"], item["max_tokens"])
                for item in safe_wires
            ]
            if (
                not isinstance(audit, list)
                or len(audit) > 4
                or audited_shapes != wire_shapes
                or any(item.get("sealed_control_marker_hits") != [] for item in audit)
            ):
                raise ValueError("full_call_wire_payload_audit_mismatch")
        by_family[case.id] = {"sample": row, "evidence": evidence, "wires": wires_by_sample[sample_id]}
    if oracle.get("campaign_id") != CAMPAIGN_ID:
        raise ValueError("full_call_fixture_prereg_binding_invalid")
    return campaign, report, by_family, fixture, oracle


def build_packet(run_root: Path, *, prereg_git_commit: str, seed: int = REVIEW_SEED) -> tuple[dict[str, object], dict[str, object]]:
    campaign, report, by_family, fixture, sealed_oracle = _load_run(run_root, prereg_git_commit=prereg_git_commit)
    rows = fixture["cases"]
    oracle_by_family = {row["family_id"]: row for row in sealed_oracle["cases"]}
    if set(oracle_by_family) != {row["family_id"] for row in rows}:
        raise ValueError("full_call_sealed_oracle_family_set_invalid")
    tokens = {row["family_id"]: hashlib.sha256(f"{seed}:{row['family_id']}".encode()).hexdigest()[:20] for row in rows}
    order = list(rows)
    random.Random(seed).shuffle(order)
    packet_cases = []
    key_cases = []
    for row in order:
        family = row["family_id"]
        run = by_family[family]
        evidence = run["evidence"]
        persona = evidence.get("persona", {}) if isinstance(evidence, dict) else {}
        scene = evidence.get("scene", {}) if isinstance(evidence, dict) else {}
        persona_proposal = persona.get("proposal") if persona.get("strict_response") is True else None
        scene_proposal = scene.get("proposal") if scene.get("strict_response") is True else None
        packet_cases.append({
            "anonymous_token": tokens[family],
            "authoritative_persona_source": row["persona_source"],
            "authoritative_scene_source": row["scene_source"],
            "anonymous_persona_proposal": persona_proposal if isinstance(persona_proposal, dict) else UNAVAILABLE,
            "anonymous_scene_proposal": _strip_scene_ids(scene_proposal) if isinstance(scene_proposal, dict) else UNAVAILABLE,
        })
        key_cases.append({
            "anonymous_token": tokens[family],
            "family_id": family,
            "sample_id": run["sample"]["sample_id"],
            "sample_status": run["sample"]["state"],
            "persona_status": persona.get("status"),
            "scene_status": scene.get("status"),
            "persona_application": {"generation_http": persona.get("generation_http"), "error_code": persona.get("error_code")},
            "scene_application": {"generation_http": scene.get("generation_http"), "error_code": scene.get("error_code")},
            "persona_strict_lifecycle": persona.get("strict_lifecycle_success") is True,
            "scene_strict_lifecycle": scene.get("strict_lifecycle_success") is True,
            "joint_strict_lifecycle": persona.get("strict_lifecycle_success") is True and scene.get("strict_lifecycle_success") is True,
            "oracle": oracle_by_family[family],
            "evidence_sha256": file_sha256(run_root / family / "production-full-call" / "0" / "storage" / EVIDENCE_NAME) if evidence is not None else None,
            "provider_wires": run["wires"],
        })
    packet = {
        "version": PACKET_VERSION,
        "rubric": {
            "instruction": "Judge each anonymous proposal only against its authoritative source. Do not infer hidden run state. Grade every listed axis pass, minor, major, or not_evaluable; use not_evaluable only for the explicit sentinel.",
            "persona_axes": ["relationship_fidelity", "permission_fidelity", "profession_fidelity", "shared_history_fidelity", "epistemic_fidelity", "format_adherence"],
            "scene_axes": ["topology_fidelity", "object_fidelity", "permission_fidelity", "source_fidelity", "format_adherence"],
            "grades": ["pass", "minor", "major", "not_evaluable"],
        },
        "cases": packet_cases,
    }
    key = {
        "version": KEY_VERSION,
        "campaign_id": CAMPAIGN_ID,
        "seed": seed,
        "packet_canonical_sha256": sha256(packet),
        "manifest_file_sha256": file_sha256(run_root / "manifest.json"),
        "report_file_sha256": file_sha256(run_root / "report.json"),
        "fixture_file_sha256": hashlib.sha256(_git_show(prereg_git_commit, "tools/model-quality/fixtures/persona-scene/persona-scene-production-full-call-blind-v1.json")).hexdigest(),
        "sealed_oracle_file_sha256": hashlib.sha256(_git_show(prereg_git_commit, "tools/model-quality/fixtures/persona-scene/persona-scene-production-full-call-blind-oracle-v1.json")).hexdigest(),
        "preregistration_file_sha256": hashlib.sha256(_git_show(prereg_git_commit, PREREG_REPO_PATH)).hexdigest(),
        "prereg_git_commit": prereg_git_commit,
        "run_prereg_git_commit": json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))["source"]["git_revision"],
        "run_tracked_dirty_digest": json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))["source"]["tracked_dirty_digest"],
        "exporter_file_sha256": file_sha256(Path(__file__)),
        "cases": key_cases,
    }
    _validate_packet_privacy(packet, key)
    return packet, key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--prereg-git-commit", required=True)
    args = parser.parse_args()
    packet, key = build_packet(args.run, prereg_git_commit=args.prereg_git_commit)
    args.packet.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.key.write_text(json.dumps(key, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
