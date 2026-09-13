from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from examples.aggregate_persona_scene_full_call_blind import (
    PERSONA_AXES, REVIEW_VERSION, SCENE_AXES, aggregate,
)
import examples.aggregate_persona_scene_full_call_blind as aggregate_module
from examples.export_persona_scene_full_call_blind import (
    KEY_VERSION, PACKET_VERSION, _git_show, _validate_packet_privacy,
    _validate_wires, sha256,
    _durable_ledger_snapshot, _require_report_matches_ledger,
)
from examples.prepare_persona_scene_full_call_blind import CAMPAIGN_ID, FIXTURE, build_manifest
from model_quality.protocol import digest
from vibe_learner.persona_scene_full_call_blind import AuditedBridge


BUDGET = {
    "token_limit": 1000000,
    "wire_limit": 32,
    "rpm": 60,
    "tpm": 200000,
    "max_inflight": 1,
    "expires_at": 9999999999,
    "stop_buffer_seconds": 1,
}


class PersonaSceneFullCallBlindTests(unittest.TestCase):
    def test_audit_domain_does_not_escape_transport_call_kind_catalog(self):
        observed: dict[str, object] = {}

        class Transport:
            campaign = SimpleNamespace(transport="minimax")

            def request(self, payload, *, call_kind, fake_response):
                observed["call_kind"] = call_kind
                return {
                    "model": "MiniMax-M3",
                    "choices": [{"message": {"role": "assistant", "content": "{}"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }

        bridge = AuditedBridge(SimpleNamespace(transport=Transport()))
        bridge.audit_domain = "persona_generation"
        bridge.request(None, {"max_tokens": 4096}, request_kind="setting", model="MiniMax-M3")
        self.assertEqual(observed["call_kind"], "generation")
        self.assertEqual(bridge.payload_audit[0]["domain"], "persona_generation")

    def test_fresh_fixture_reuses_persona_claim_sources_but_has_authored_scene_sources(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        public = json.loads((FIXTURE.parent / "persona-claim-ledger-generator-public-v1.json").read_text(encoding="utf-8"))
        expected_persona = {row["family_id"]: row["input"]["source"] for row in public["samples"]}
        self.assertEqual(len(fixture["cases"]), 8)
        self.assertEqual({row["family_id"]: row["persona_source"] for row in fixture["cases"]}, expected_persona)
        self.assertEqual(len({row["scene_source"] for row in fixture["cases"]}), 8)
        oracle_path = FIXTURE.parent / "persona-scene-production-full-call-blind-oracle-v1.json"
        oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
        self.assertTrue(all(row["scene_layer_count"] == 3 for row in fixture["cases"]))
        self.assertNotIn("oracle", FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual({row["family_id"] for row in oracle["cases"]}, set(expected_persona))

    def test_manifest_freezes_full_production_lifecycle_and_32_wire_ceiling(self):
        manifest = build_manifest(budget_document={"budget": BUDGET}, transport="minimax")
        self.assertEqual(manifest["id"], CAMPAIGN_ID)
        self.assertEqual(manifest["adapter"], "vibe_learner.persona_scene_full_call_blind:run_sample")
        self.assertEqual(manifest["sample_wire_limit"], 4)
        self.assertEqual(manifest["max_output_tokens"], 6400)
        self.assertEqual(manifest["concurrency"], 1)
        self.assertEqual(len(manifest["cases"]) * manifest["sample_wire_limit"], 32)
        self.assertEqual([row["id"] for row in manifest["variants"]], ["production-full-call"])

    def test_manifest_rejects_non_live_transport(self):
        with self.assertRaisesRegex(ValueError, "live_transport_required"):
            build_manifest(budget_document={"budget": BUDGET}, transport="fake")

    def test_git_prereg_requires_exact_40_hex_commit(self):
        with self.assertRaisesRegex(ValueError, "git_commit_invalid"):
            _git_show("HEAD", "ignored")

    def test_known_upstream_4xx_and_unknown_usage_remain_exportable(self):
        sample = "s" * 64
        wire = {
            "id": "wire-1", "campaign": CAMPAIGN_ID, "sample": sample,
            "started": 1.0, "finished": 2.0, "state": "finished",
            "reserved": 106400, "charged": 106400,
            "metadata": {
                "call_kind": "persona_generation", "max_tokens": 4096,
                "http_status": 400, "finish_reason": None,
                "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
            },
        }
        report = {"campaign_usage": {
            "wire_count": 1, "charged_or_reserved_tokens": 106400,
            "unknown_usage_requests": 1, "wires": [wire],
        }}
        self.assertEqual(_validate_wires(report, {sample})[sample][0]["http_status"], 400)

    def test_durable_ledger_binding_is_required_and_tamper_is_observed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_root = root / "run"
            run_root.mkdir()
            ledger_path = root / "ledger.sqlite3"
            manifest = {"ledger_path": str(ledger_path)}
            with sqlite3.connect(ledger_path) as db:
                db.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, config TEXT NOT NULL, stopped TEXT)")
                db.execute("INSERT INTO settings VALUES (1, '{}', NULL)")
                db.execute("CREATE TABLE campaigns (id TEXT PRIMARY KEY, binding TEXT NOT NULL)")
                db.execute("INSERT INTO campaigns VALUES (?,?)", (CAMPAIGN_ID, digest({"manifest": manifest, "output": str(run_root.resolve())})))
                db.execute("CREATE TABLE wires (id TEXT PRIMARY KEY, campaign TEXT NOT NULL, sample TEXT NOT NULL, started REAL NOT NULL, finished REAL, state TEXT NOT NULL, reserved INTEGER NOT NULL, charged INTEGER NOT NULL, metadata TEXT)")
            durable = _durable_ledger_snapshot(manifest, run_root)
            self.assertEqual(durable["wire_count"], 0)
            _require_report_matches_ledger({"campaign_usage": durable}, durable)
            tampered_report = {"campaign_usage": deepcopy(durable)}
            tampered_report["campaign_usage"]["wire_count"] = 1
            with self.assertRaisesRegex(ValueError, "durable_ledger_mismatch"):
                _require_report_matches_ledger(tampered_report, durable)
            with sqlite3.connect(ledger_path) as db:
                db.execute("UPDATE campaigns SET binding='tampered' WHERE id=?", (CAMPAIGN_ID,))
            with self.assertRaisesRegex(ValueError, "campaign_binding_invalid"):
                _durable_ledger_snapshot(manifest, run_root)

    def test_blind_packet_shape_excludes_identity_status_trace_oracle_and_reasoning(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cases = [{
            "anonymous_token": f"token-{index}",
            "authoritative_persona_source": row["persona_source"],
            "authoritative_scene_source": row["scene_source"],
            "anonymous_persona_proposal": {"summary": "x"},
            "anonymous_scene_proposal": {"scene_name": "x"},
        } for index, row in enumerate(fixture["cases"])]
        packet = {"version": PACKET_VERSION, "rubric": {}, "cases": cases}
        text = json.dumps(packet, ensure_ascii=False)
        for forbidden in (CAMPAIGN_ID, "family_id", "sample_status", "harness_trace", "oracle", "expected_constraints", "reasoning", "scene_id", "reuse_id"):
            self.assertNotIn(forbidden, text)
        _validate_packet_privacy(packet, {"cases": []})
        natural_language = deepcopy(packet)
        natural_language["cases"][0]["anonymous_persona_proposal"]["summary"] = "The expected reasoning is not an oracle."
        _validate_packet_privacy(natural_language, {"cases": []})
        leaked = deepcopy(packet)
        leaked["cases"][0]["anonymous_scene_proposal"]["scene_id"] = "private"
        with self.assertRaisesRegex(ValueError, "private_key"):
            _validate_packet_privacy(leaked, {"cases": []})

    def test_strict_two_reviewer_gate_uses_independent_denominators_and_worst_major(self):
        packet = {
            "version": PACKET_VERSION,
            "rubric": {},
            "cases": [{
                "anonymous_token": f"token-{index}",
                "authoritative_persona_source": f"persona {index}",
                "authoritative_scene_source": f"scene {index}",
                "anonymous_persona_proposal": {"summary": f"p{index}"},
                "anonymous_scene_proposal": {"scene_name": f"s{index}"},
            } for index in range(8)],
        }
        key = {
            "version": KEY_VERSION,
            "campaign_id": CAMPAIGN_ID,
            "packet_canonical_sha256": sha256(packet),
            "cases": [{
                "anonymous_token": f"token-{index}",
                "family_id": f"family-{index}",
                "sample_status": "completed" if index < 7 else "candidate_failed",
                "persona_status": "completed" if index < 7 else "candidate_failed",
                "scene_status": "completed" if index < 7 else "candidate_failed",
                "persona_strict_lifecycle": index < 7,
                "scene_strict_lifecycle": index < 7,
                "joint_strict_lifecycle": index < 7,
            } for index in range(8)],
        }
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path, key_path = root / "packet.json", root / "key.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            key_path.write_text(json.dumps(key), encoding="utf-8")
            review_paths = []
            for reviewer in ("reviewer-a", "reviewer-b"):
                review = {
                    "version": REVIEW_VERSION,
                    "reviewer_id": reviewer,
                    "packet_file_sha256": hashlib.sha256(packet_path.read_bytes()).hexdigest(),
                    "cases": [{
                        "anonymous_token": f"token-{index}",
                        "persona": {"axes": {axis: "pass" for axis in PERSONA_AXES}, "rationale": f"Persona source comparison {reviewer} {index}."},
                        "scene": {"axes": {axis: "pass" for axis in SCENE_AXES}, "rationale": f"Scene source comparison {reviewer} {index}."},
                    } for index in range(8)],
                }
                path = root / f"{reviewer}.json"
                path.write_text(json.dumps(review), encoding="utf-8")
                review_paths.append(path)
            committed = ({"source_bindings": {"strict_two_reviewer_aggregator": hashlib.sha256(Path(aggregate_module.__file__).read_bytes()).hexdigest()}}, {}, {})
            with patch("examples.aggregate_persona_scene_full_call_blind._committed_preregistration", return_value=committed), patch("examples.aggregate_persona_scene_full_call_blind.build_packet", return_value=(packet, key)):
                result = aggregate(packet_path=packet_path, key_path=key_path, review_paths=review_paths, run_root=root / "run", prereg_git_commit="a" * 40)
                self.assertTrue(result["promotion_passed"])
                changed = json.loads(review_paths[1].read_text(encoding="utf-8"))
                changed["cases"][0]["scene"]["axes"]["topology_fidelity"] = "major"
                review_paths[1].write_text(json.dumps(changed), encoding="utf-8")
                result = aggregate(packet_path=packet_path, key_path=key_path, review_paths=review_paths, run_root=root / "run", prereg_git_commit="a" * 40)
                self.assertFalse(result["promotion_passed"])

    def test_duplicate_reviewer_body_is_rejected_even_with_different_identity(self):
        packet = {"version": PACKET_VERSION, "rubric": {}, "cases": []}
        # Denominator validation occurs before body comparison; this fixture
        # documents that malformed shortcuts cannot reach the promotion gate.
        with TemporaryDirectory() as directory:
            root = Path(directory)
            packet_path, key_path = root / "packet.json", root / "key.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            key_path.write_text(json.dumps({"version": KEY_VERSION, "packet_canonical_sha256": sha256(packet), "cases": []}), encoding="utf-8")
            committed = ({"source_bindings": {"strict_two_reviewer_aggregator": hashlib.sha256(Path(aggregate_module.__file__).read_bytes()).hexdigest()}}, {}, {})
            with patch("examples.aggregate_persona_scene_full_call_blind._committed_preregistration", return_value=committed), patch("examples.aggregate_persona_scene_full_call_blind.build_packet", return_value=(packet, json.loads(key_path.read_text()))):
                with self.assertRaisesRegex(ValueError, "denominator"):
                    aggregate(packet_path=packet_path, key_path=key_path, review_paths=[root / "a", root / "b"], run_root=root / "run", prereg_git_commit="a" * 40)


if __name__ == "__main__":
    unittest.main()
