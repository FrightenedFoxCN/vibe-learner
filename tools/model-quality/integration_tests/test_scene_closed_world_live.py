from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from examples.prepare_scene_closed_world import (
    FIXTURE,
    build_baseline_manifest,
    build_repair_manifest,
)
from model_quality.protocol import Campaign, digest
from vibe_learner.scene_closed_world_live import (
    run_baseline_sample,
    run_repair_sample,
)


BUDGET = {
    "token_limit": 100000,
    "wire_limit": 100,
    "rpm": 60,
    "tpm": 200000,
    "max_inflight": 2,
    "expires_at": 9999999999,
    "stop_buffer_seconds": 1,
}


def _fixture_case() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"][0]


def _wire(proposal: dict[str, object], *, finish_reason: str = "stop"):
    return {
        "choices": [{
            "message": {"content": json.dumps(proposal, ensure_ascii=False)},
            "finish_reason": finish_reason,
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


def _repair_spec(*, passing: bool = False):
    row = _fixture_case()
    baseline = deepcopy(row["valid_minimal_scene_tree_proposal"])
    if not passing:
        baseline["scene_layers"][0]["children"].append(
            deepcopy(row["single_point_mutations"][0]["value"])
        )
    return row, {
        "source_text": row["source_text"],
        "policy": row["scene_closed_world_policy_v1"],
        "fake_proposal": row["valid_minimal_scene_tree_proposal"],
        "baseline": {
            "strict_candidate": True,
            "proposal": baseline,
            "issues": [],
        },
    }


def _invoke_repair(*, passing=False, raw=None):
    row, spec = _repair_spec(passing=passing)
    request = Mock(return_value=raw or _wire(row["valid_minimal_scene_tree_proposal"]))
    context = SimpleNamespace(
        transport=SimpleNamespace(
            campaign=SimpleNamespace(
                model="MiniMax-M3",
                transport="fake",
                max_output_tokens=4096,
            ),
            request=request,
        )
    )
    case = SimpleNamespace(
        id=row["case_id"],
        source=row["source_text"],
        gold=json.dumps(spec, ensure_ascii=False),
        rubric="scene-closed-world-repair-v1",
    )
    variant = SimpleNamespace(id="conditional-one-wire-repair")
    with TemporaryDirectory() as directory:
        context.storage = Path(directory)
        result = run_repair_sample(context, case, variant)
        evidence = json.loads(
            (context.storage / "scene-closed-world-evidence.json").read_text(
                encoding="utf-8"
            )
        )
    return result, request, evidence


def _invoke_baseline(raw):
    row = _fixture_case()
    request = Mock(return_value=raw)
    campaign = SimpleNamespace(
        model="MiniMax-M3",
        transport="fake",
        max_output_tokens=4096,
        timeout_seconds=90,
        temperature=0.2,
    )
    context = SimpleNamespace(
        transport=SimpleNamespace(campaign=campaign, request=request),
    )
    spec = {
        "source_text": row["source_text"],
        "layer_count": row["layer_count"],
        "policy": row["scene_closed_world_policy_v1"],
        "fake_proposal": row["valid_minimal_scene_tree_proposal"],
    }
    case = SimpleNamespace(
        id=row["case_id"],
        source=row["source_text"],
        gold=json.dumps(spec, ensure_ascii=False),
        rubric="scene-closed-world-baseline-v1",
    )
    variant = SimpleNamespace(id="production-shaped-baseline")
    with TemporaryDirectory() as directory:
        root = Path(directory)
        context.storage = root / "storage"
        context.storage.mkdir()
        context.database = root / "domain.sqlite3"
        result = run_baseline_sample(context, case, variant)
        evidence_path = context.storage / "scene-closed-world-evidence.json"
        evidence_bytes = evidence_path.read_bytes()
        evidence = json.loads(evidence_bytes)
    return result, request, evidence, hashlib.sha256(evidence_bytes).hexdigest()


def _write_frozen_baseline(root: Path, baseline: dict[str, object]) -> None:
    campaign = Campaign.model_validate(baseline, strict=True)
    config_digest = digest(campaign.model_dump())
    (root / "manifest.json").write_text(
        json.dumps({"config": campaign.model_dump(), "config_digest": config_digest}),
        encoding="utf-8",
    )
    samples = []
    for sample_id, identity, case, variant in campaign.samples():
        storage = root / case.id / variant.id / "0" / "storage"
        storage.mkdir(parents=True)
        spec = json.loads(case.gold)
        evidence_bytes = json.dumps({
            "case_id": case.id,
            "phase": "baseline",
            "strict_candidate": True,
            "proposal": spec["fake_proposal"],
            "issues": [],
            "production_trace_proposal": True,
        }).encode()
        evidence_path = storage / "scene-closed-world-evidence.json"
        evidence_path.write_bytes(evidence_bytes)
        evidence_sha256 = hashlib.sha256(evidence_bytes).hexdigest()
        samples.append({
            **identity,
            "sample_id": sample_id,
            "family": case.family,
            "state": "completed",
            "result": {
                "status": "completed",
                "metrics": {"strict_candidate": True},
                "scope": "domain-admitted-proposal; no product projection commit or read-back",
                "evidence": [{
                    "path": "scene-closed-world-evidence.json",
                    "contract": "scene-closed-world-live-evidence-v1",
                    "sha256": evidence_sha256,
                }],
            },
        })
    (root / "report.json").write_text(
        json.dumps({
            "version": "quality-report-v1",
            "campaign": campaign.id,
            "expected_samples": 6,
            "states": {"completed": 6},
            "samples": samples,
        }),
        encoding="utf-8",
    )


class SceneClosedWorldLiveTests(unittest.TestCase):
    def test_baseline_manifest_is_six_frozen_two_wire_proposals(self):
        manifest = build_baseline_manifest(
            budget_document={"budget": BUDGET},
            transport="fake",
        )
        self.assertEqual(len(manifest["cases"]), 6)
        self.assertEqual(manifest["sample_wire_limit"], 2)
        self.assertEqual(manifest["max_output_tokens"], 4096)
        self.assertEqual(len({case["family"] for case in manifest["cases"]}), 6)
        self.assertTrue(all(case["source"] == json.loads(case["gold"])["source_text"] for case in manifest["cases"]))

    def test_repair_manifest_freezes_baseline_without_mutating_it(self):
        baseline = build_baseline_manifest(
            budget_document={"budget": BUDGET},
            transport="fake",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_frozen_baseline(root, baseline)
            repair = build_repair_manifest(
                baseline_run=root,
                budget_document={"budget": BUDGET},
                transport="fake",
            )
        self.assertEqual(len(repair["cases"]), 6)
        self.assertEqual(repair["sample_wire_limit"], 1)
        self.assertTrue(all(json.loads(case["gold"])["baseline"]["strict_candidate"] for case in repair["cases"]))
        baseline_gold = {
            case["id"]: json.loads(case["gold"])
            for case in baseline["cases"]
        }
        for case in repair["cases"]:
            repair_gold = json.loads(case["gold"])
            self.assertEqual(repair_gold["policy"], baseline_gold[case["id"]]["policy"])
            self.assertRegex(repair_gold["baseline"]["evidence_sha256"], r"^[0-9a-f]{64}$")

    def test_repair_manifest_rejects_evidence_changed_after_report(self):
        baseline = build_baseline_manifest(
            budget_document={"budget": BUDGET},
            transport="fake",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_frozen_baseline(root, baseline)
            first = baseline["cases"][0]
            evidence_path = (
                root / first["id"] / "production-shaped-baseline" / "0"
                / "storage" / "scene-closed-world-evidence.json"
            )
            evidence_path.write_text('{"tampered":true}', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence_digest_mismatch"):
                build_repair_manifest(
                    baseline_run=root,
                    budget_document={"budget": BUDGET},
                    transport="fake",
                )

    def test_repair_manifest_cannot_switch_fake_baseline_to_live_transport(self):
        baseline = build_baseline_manifest(
            budget_document={"budget": BUDGET},
            transport="fake",
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            _write_frozen_baseline(root, baseline)
            with self.assertRaisesRegex(ValueError, "baseline_manifest_invalid"):
                build_repair_manifest(
                    baseline_run=root,
                    budget_document={"budget": BUDGET},
                    transport="minimax",
                )

    def test_passing_baseline_is_reused_without_wire(self):
        result, request, evidence = _invoke_repair(passing=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(
            result["scope"],
            "provider-proposal-only; no domain admission, commit or read-back",
        )
        self.assertFalse(evidence["repair_triggered"])
        request.assert_not_called()

    def test_baseline_missing_finish_is_infrastructure_not_success(self):
        row = _fixture_case()
        raw = _wire(row["valid_minimal_scene_tree_proposal"])
        del raw["choices"][0]["finish_reason"]
        result, _, evidence, evidence_sha256 = _invoke_baseline(raw)
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(result["failure_owner"], "infrastructure")
        self.assertEqual(evidence["wire_envelopes"][-1]["finish_reason"], "missing")
        self.assertEqual(result["evidence"][0]["sha256"], evidence_sha256)
        self.assertEqual(
            result["scope"],
            "domain-admitted-proposal; no product projection commit or read-back",
        )

    def test_baseline_unknown_finish_is_infrastructure_not_success(self):
        row = _fixture_case()
        raw = _wire(row["valid_minimal_scene_tree_proposal"])
        raw["choices"][0]["finish_reason"] = "unexpected-future-value"
        result, _, evidence, _ = _invoke_baseline(raw)
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(evidence["wire_envelopes"][-1]["finish_reason"], "unknown")

    def test_baseline_length_is_candidate_failure_not_success(self):
        row = _fixture_case()
        raw = _wire(
            row["valid_minimal_scene_tree_proposal"],
            finish_reason="length",
        )
        result, request, evidence, _ = _invoke_baseline(raw)
        self.assertEqual(result["status"], "candidate_failed")
        self.assertEqual(result["failure_owner"], "candidate")
        self.assertTrue(evidence["not_evaluable"])
        self.assertEqual(evidence["wire_envelopes"][-1]["finish_reason"], "length")
        self.assertLessEqual(request.call_count, 2)

    def test_typed_issue_triggers_exactly_one_strict_repair_wire(self):
        result, request, evidence = _invoke_repair()
        self.assertEqual(result["status"], "completed")
        request.assert_called_once()
        self.assertTrue(evidence["repair_triggered"])
        self.assertEqual(evidence["final_issues"], [])
        payload = request.call_args.args[0]
        self.assertEqual(payload["max_tokens"], 4096)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_length_is_candidate_failure_and_not_evaluable(self):
        row = _fixture_case()
        result, _, evidence = _invoke_repair(
            raw=_wire(row["valid_minimal_scene_tree_proposal"], finish_reason="length")
        )
        self.assertEqual(result["status"], "candidate_failed")
        self.assertEqual(result["failure_owner"], "candidate")
        self.assertTrue(evidence["not_evaluable"])
        self.assertEqual(evidence["wire_envelope"]["finish_reason"], "length")

    def test_missing_final_channel_is_infrastructure_without_reasoning_leak(self):
        raw = {
            "choices": [{
                "message": {"content": None, "reasoning_content": "private reasoning"},
                "finish_reason": "stop",
            }],
            "usage": {"completion_tokens": 10},
        }
        result, _, evidence = _invoke_repair(raw=raw)
        self.assertEqual(result["status"], "infrastructure_failed")
        self.assertEqual(result["failure_owner"], "infrastructure")
        self.assertNotIn("private reasoning", json.dumps(evidence))
        self.assertEqual(evidence["error_code"], "scene_repair_final_content_missing")


if __name__ == "__main__":
    unittest.main()
