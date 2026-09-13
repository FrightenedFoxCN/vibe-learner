"""One complete, unchanged production Persona -> Scene call per fresh family.

The production endpoints own decode, bounded repair, v3 proposal evidence and
projection.  This adapter then performs the ordinary user save and exact
read-back boundaries.  A failed generation is never replaced with fixture
content and is never rerun; the other domain is still attempted so Persona,
Scene, and joint denominators stay independently observable.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from typing import Any

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.models.api import PersonaCardGenerateResponse, SceneTreeGenerateResponse
from app.models.persona_generation import PersonaCardBatchContentProposalV1
from app.models.scene import SceneTreeGeneratedProjectionV1
from model_quality.ledger import GateClosed
from model_quality.runner import atomic_json
from model_quality.transport import WireFailure
from examples.prepare_persona_scene_full_call_blind import (
    source_tree_binding,
)

from .common import Bridge, create_app, settings as common_settings


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "persona-scene" / "persona-scene-production-full-call-blind-v1.json"
PREREGISTRATION = ROOT / "fixtures" / "persona-scene" / "persona-scene-production-full-call-blind-preregistration-v1.json"
CAMPAIGN_ID = "m3-persona-scene-production-full-call-blind-20260913-v1"
RUBRIC = "persona-scene-production-full-call-absolute-blind-v1"
VARIANT = "production-full-call"
EVIDENCE_NAME = "persona-scene-full-call-evidence.json"
EVIDENCE_CONTRACT = "persona-scene-production-full-call-evidence-v1"
SCOPE = "domain-primary-output-readback"
SEALED_CONTROL_MARKERS = (
    "persona_focus", "scene_direct_children", "scene_required_objects",
    "scene_permission_rules", "forbidden_inventions", "expected_codes",
    "expected_constraints", "review_oracle",
)


class AuditedBridge(Bridge):
    """Record only safe payload binding facts, including the actual token cap."""

    def __init__(self, context: Any):
        super().__init__(context, lambda _payload: (_ for _ in ()).throw(GateClosed("fake_output_forbidden")))
        self.payload_audit: list[dict[str, object]] = []
        self.audit_domain = "generation"

    def request(self, adapter, payload, *, request_kind, model):
        serialized = _canonical(payload)
        audit = {
            "domain": self.audit_domain,
            "max_tokens": payload.get("max_tokens") if isinstance(payload, dict) else None,
            "payload_sha256": _sha256_bytes(serialized.encode("utf-8")),
            "sealed_control_marker_hits": [marker for marker in SEALED_CONTROL_MARKERS if marker in serialized],
            "issued_wire": None,
        }
        self.payload_audit.append(audit)
        try:
            result = super().request(adapter, payload, request_kind=request_kind, model=model)
        except GateClosed:
            audit["issued_wire"] = False
            raise
        except WireFailure:
            audit["issued_wire"] = True
            raise
        except Exception:
            # Unknown bridge failures cannot claim a wire either way.
            audit["issued_wire"] = None
            raise
        audit["issued_wire"] = True
        return result


def _payload_audit_passed(bridge: AuditedBridge) -> bool:
    return (
        len(bridge.payload_audit) == bridge.calls
        and all(not row["sealed_control_marker_hits"] for row in bridge.payload_audit)
        and all(row["max_tokens"] in {4096, 6144} for row in bridge.payload_audit)
        and all(
            [row["max_tokens"] for row in bridge.payload_audit if row["domain"] == domain]
            in ([], [4096], [4096, 6144])
            for domain in ("persona_generation", "scene_generation")
        )
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_manifest() -> dict[str, object]:
    """Runner-recorded closure over every production/research input glob."""
    return {
        "version": "persona-scene-full-call-source-tree-v1",
        "campaign_id": CAMPAIGN_ID,
        "source_tree_binding": source_tree_binding(),
        "preregistration_sha256": _sha256_bytes(PREREGISTRATION.read_bytes()),
    }


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _trace_is_strict_proposal(trace: object) -> bool:
    if not isinstance(trace, dict):
        return False
    evidence = trace.get("commit_evidence")
    return (
        trace.get("trace_schema_version") == "harness-trace-v3"
        and trace.get("status") in {"passed", "repaired"}
        and isinstance(evidence, dict)
        and evidence.get("status") == "not_applicable"
    )


def _persona_proposal(response: PersonaCardGenerateResponse) -> dict[str, object]:
    proposal = PersonaCardBatchContentProposalV1.model_validate({
        "summary": response.summary,
        "relationship": response.relationship,
        "learner_address": response.learner_address,
        "cards": [{
            "title": card.title,
            "kind": card.kind,
            "label": card.label,
            "content": card.content,
            "tags": card.tags,
            "source_note": card.source_note,
        } for card in response.items],
    }, strict=True)
    return proposal.model_dump(mode="json")


def _persona_save_payload(name: str, proposal: dict[str, object]) -> dict[str, object]:
    cards = proposal["cards"]
    assert isinstance(cards, list)
    return {
        "name": name,
        "summary": proposal["summary"],
        "relationship": proposal["relationship"],
        "learner_address": proposal["learner_address"],
        "system_prompt": "仅依据已保存的人格资料行动；未知事实保持未知，不扩张关系或权限。",
        "reference_hints": [],
        "slots": [{
            "kind": card["kind"],
            "label": card["label"],
            "content": card["content"],
            "weight": 50,
            "locked": False,
            "sort_order": index,
        } for index, card in enumerate(cards) if isinstance(card, dict)],
        "available_emotions": ["calm"],
        "available_actions": ["idle"],
        "default_speech_style": "concise",
    }


def _scene_projection(response: SceneTreeGenerateResponse) -> dict[str, object]:
    return SceneTreeGeneratedProjectionV1.model_validate({
        "schema_version": "scene-tree-generated-projection-v1",
        "scene_name": response.scene_name,
        "scene_summary": response.scene_summary,
        "selected_layer_id": response.selected_layer_id,
        "scene_layers": [row.model_dump(mode="json") for row in response.scene_layers],
    }, strict=True).model_dump(mode="json")


def _scene_save_payload(projection: dict[str, object]) -> dict[str, object]:
    return {
        "contract_version": "scene-committed-save-v1",
        "expected_revision": 0,
        "scene_name": projection["scene_name"],
        "scene_summary": projection["scene_summary"],
        "scene_layers": projection["scene_layers"],
        "selected_layer_id": projection["selected_layer_id"],
        "collapsed_layer_ids": [],
    }


def _http_failure(response: Any, domain_transport_failure: Exception | None) -> tuple[str, str]:
    if domain_transport_failure is not None:
        status = "uncertain" if isinstance(domain_transport_failure, WireFailure) and domain_transport_failure.uncertain else "infrastructure_failed"
        return status, getattr(domain_transport_failure, "code", type(domain_transport_failure).__name__)
    try:
        detail = response.json().get("detail")
    except (AttributeError, TypeError, ValueError):
        detail = None
    code = detail.get("code") if isinstance(detail, dict) else detail
    if response.status_code == 502 and isinstance(code, str) and (
        code.startswith("setting_model_")
        or code.startswith("setting_persona_")
        or code.startswith("setting_scene_")
    ):
        return "candidate_failed", code
    if 400 <= response.status_code < 500:
        return "data_failed", str(code or f"http_{response.status_code}")
    return "infrastructure_failed", str(code or f"http_{response.status_code}")


def _read_persona(client: TestClient, persona_id: str) -> dict[str, object] | None:
    response = client.get("/personas")
    if response.status_code != 200:
        return None
    matches = [row for row in response.json().get("items", []) if row.get("id") == persona_id]
    return matches[0] if len(matches) == 1 else None


def _empty_domain() -> dict[str, object]:
    return {
        "status": "not_started",
        "error_code": None,
        "generation_http": None,
        "wire_count": 0,
        "strict_response": False,
        "v3_proposal": False,
        "proposal": None,
        "saved": False,
        "immediate_readback_equal": False,
        "restart_readback_equal": False,
        "strict_lifecycle_success": False,
    }


def _load_case(case: Any) -> dict[str, object]:
    fixture_raw = FIXTURE.read_bytes()
    prereg_raw = PREREGISTRATION.read_bytes()
    fixture = json.loads(fixture_raw)
    prereg = json.loads(prereg_raw)
    repository = Path(__file__).resolve().parents[4]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, capture_output=True, text=True, check=False)
    git_revision = head.stdout.strip()
    prereg_path = PREREGISTRATION.relative_to(repository).as_posix()
    committed_prereg = subprocess.run(
        ["git", "show", f"{git_revision}:{prereg_path}"],
        cwd=repository, capture_output=True, check=False,
    ) if re.fullmatch(r"[0-9a-f]{40}", git_revision) else None
    source_paths = {
        "fixture": FIXTURE,
        "prepare_manifest": ROOT / "examples" / "prepare_persona_scene_full_call_blind.py",
        "adapter": Path(__file__),
        "blind_packet_key_exporter": ROOT / "examples" / "export_persona_scene_full_call_blind.py",
        "strict_two_reviewer_aggregator": ROOT / "examples" / "aggregate_persona_scene_full_call_blind.py",
        "tests": ROOT / "integration_tests" / "test_persona_scene_full_call_blind.py",
    }
    runtime = prereg.get("runtime_binding")
    rows = [row for row in fixture.get("cases", []) if row.get("family_id") == case.id]
    if len(rows) != 1:
        raise ValueError("full_call_fixture_case_mismatch")
    row = rows[0]
    public = _canonical({"persona_source": row["persona_source"], "scene_source": row["scene_source"]})
    if (
        fixture.get("campaign_id") != CAMPAIGN_ID
        or committed_prereg is None
        or committed_prereg.returncode != 0
        or committed_prereg.stdout != prereg_raw
        or prereg.get("campaign_id") != CAMPAIGN_ID
        or prereg.get("source_bindings") != {
            name: _sha256_bytes(path.read_bytes()) for name, path in source_paths.items()
        }
        or prereg.get("source_tree_binding") != source_tree_binding(repository)
        or not isinstance(runtime, dict)
        or runtime.get("production_initial_max_tokens") != 4096
        or runtime.get("production_repair_max_tokens") != 6144
        or runtime.get("environment_allowlist") != ["K3_API_KEY"]
        or case.rubric != RUBRIC
        or case.source != public
        or case.gold != "{}"
    ):
        raise ValueError("full_call_case_binding_mismatch")
    return row


def _validate_campaign(context: Any, variant: Any) -> None:
    campaign = context.transport.campaign
    if (
        campaign.id != CAMPAIGN_ID
        or campaign.adapter != "vibe_learner.persona_scene_full_call_blind:run_sample"
        or campaign.transport != "minimax"
        or campaign.model != "MiniMax-M3"
        or campaign.thinking != "adaptive"
        or campaign.temperature != 0.2
        or campaign.max_output_tokens != 6400
        or campaign.sample_wire_limit != 4
        or campaign.repetitions != 1
        or campaign.concurrency != 1
        or len(campaign.cases) != 8
        or [item.id for item in campaign.variants] != [VARIANT]
        or variant.id != VARIANT
    ):
        raise ValueError("full_call_campaign_config_mismatch")


def run_sample(context: Any, case: Any, variant: Any) -> dict[str, object]:
    evidence: dict[str, object] = {
        "version": EVIDENCE_CONTRACT,
        "campaign_id": CAMPAIGN_ID,
        "case_id": case.id,
        "scope": SCOPE,
        "failure_policy": "no_rerun_no_replacement_no_fixture_fallback",
        "persona": _empty_domain(),
        "scene": _empty_domain(),
    }
    bridge = AuditedBridge(context)
    try:
        spec = _load_case(case)
        _validate_campaign(context, variant)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {
            "status": "data_failed",
            "failure_owner": "data",
            "error_code": "full_call_fixture_or_preregistration_invalid",
            "scope": SCOPE,
        }

    # Keep the production setting boundary: 4096 initially and 6144 only for
    # its one bounded repair.  The campaign ceiling is 6400, not the initial
    # request size.
    config = common_settings(context)
    domain_transport_failures: dict[str, Exception | None] = {"persona": None, "scene": None}
    try:
        with bridge.installed():
            app = create_app(settings=config)
            with TestClient(app) as client:
                persona_before = bridge.calls
                bridge.failure = None
                bridge.audit_domain = "persona_generation"
                persona = evidence["persona"]
                assert isinstance(persona, dict)
                try:
                    persona_http = client.post("/persona-cards/generate", json={
                        "mode": "long_text", "input_text": spec["persona_source"], "count": 1,
                    })
                except Exception as exc:
                    persona_http = None
                    domain_transport_failures["persona"] = bridge.failure
                    failure = domain_transport_failures["persona"]
                    persona.update(
                        status="uncertain" if isinstance(failure, WireFailure) and failure.uncertain else "infrastructure_failed",
                        error_code=getattr(failure, "code", type(exc).__name__),
                    )
                persona["generation_http"] = persona_http.status_code if persona_http is not None else None
                persona["wire_count"] = bridge.calls - persona_before
                if persona["wire_count"] > 2:
                    raise RuntimeError("persona_wire_ceiling_exceeded")
                saved_persona: dict[str, object] | None = None
                if persona_http is not None and persona_http.status_code == 200:
                    try:
                        decoded = PersonaCardGenerateResponse.model_validate_json(persona_http.content, strict=True)
                        proposal = _persona_proposal(decoded)
                        persona.update(strict_response=True, proposal=proposal, v3_proposal=_trace_is_strict_proposal(persona_http.json().get("harness_trace")))
                        if not persona["v3_proposal"]:
                            raise ValueError("persona_v3_proposal_invalid")
                        save = client.post("/personas", json=_persona_save_payload(str(spec["persona_name"]), proposal))
                        if save.status_code != 200:
                            persona.update(status="lifecycle_failed", error_code=f"persona_save_http_{save.status_code}")
                        else:
                            saved_persona = save.json()
                            immediate = _read_persona(client, str(saved_persona["id"]))
                            persona.update(saved=True, immediate_readback_equal=immediate == saved_persona, status="generated")
                    except (AssertionError, KeyError, TypeError, ValueError, ValidationError) as exc:
                        persona.update(status="candidate_failed", error_code=type(exc).__name__)
                elif persona_http is not None:
                    domain_transport_failures["persona"] = bridge.failure
                    status, code = _http_failure(persona_http, domain_transport_failures["persona"])
                    persona.update(status=status, error_code=code)

                scene_before = bridge.calls
                bridge.failure = None
                bridge.audit_domain = "scene_generation"
                scene = evidence["scene"]
                assert isinstance(scene, dict)
                try:
                    scene_http = client.post("/scene-setup/generate", json={
                        "mode": "long_text", "input_text": spec["scene_source"], "layer_count": spec["scene_layer_count"],
                    })
                except Exception as exc:
                    scene_http = None
                    domain_transport_failures["scene"] = bridge.failure
                    failure = domain_transport_failures["scene"]
                    scene.update(
                        status="uncertain" if isinstance(failure, WireFailure) and failure.uncertain else "infrastructure_failed",
                        error_code=getattr(failure, "code", type(exc).__name__),
                    )
                scene["generation_http"] = scene_http.status_code if scene_http is not None else None
                scene["wire_count"] = bridge.calls - scene_before
                if scene["wire_count"] > 2 or bridge.calls > 4:
                    raise RuntimeError("scene_or_family_wire_ceiling_exceeded")
                saved_scene: dict[str, object] | None = None
                if scene_http is not None and scene_http.status_code == 200:
                    try:
                        decoded_scene = SceneTreeGenerateResponse.model_validate_json(scene_http.content, strict=True)
                        projection = _scene_projection(decoded_scene)
                        scene.update(strict_response=True, proposal=projection, v3_proposal=_trace_is_strict_proposal(scene_http.json().get("harness_trace")))
                        if not scene["v3_proposal"]:
                            raise ValueError("scene_v3_proposal_invalid")
                        save_scene = client.post("/scene-library", json=_scene_save_payload(projection))
                        if save_scene.status_code != 200:
                            scene.update(status="lifecycle_failed", error_code=f"scene_save_http_{save_scene.status_code}")
                        else:
                            saved_scene = save_scene.json()
                            immediate_scene = client.get(f"/scene-library/{saved_scene['scene_id']}")
                            scene.update(saved=True, immediate_readback_equal=(immediate_scene.status_code == 200 and immediate_scene.json() == saved_scene), status="generated")
                    except (AssertionError, KeyError, TypeError, ValueError, ValidationError) as exc:
                        scene.update(status="candidate_failed", error_code=type(exc).__name__)
                elif scene_http is not None:
                    domain_transport_failures["scene"] = bridge.failure
                    status, code = _http_failure(scene_http, domain_transport_failures["scene"])
                    scene.update(status=status, error_code=code)

            before_restart = bridge.calls
            with TestClient(create_app(settings=config)) as restarted:
                if saved_persona is not None:
                    restart_persona = _read_persona(restarted, str(saved_persona["id"]))
                    persona["restart_readback_equal"] = restart_persona == saved_persona
                if saved_scene is not None:
                    restart_scene = restarted.get(f"/scene-library/{saved_scene['scene_id']}")
                    scene["restart_readback_equal"] = restart_scene.status_code == 200 and restart_scene.json() == saved_scene
            if bridge.calls != before_restart:
                raise RuntimeError("restart_readback_used_provider")

        for domain in (persona, scene):
            domain["strict_lifecycle_success"] = all(bool(domain[key]) for key in (
                "strict_response", "v3_proposal", "saved", "immediate_readback_equal", "restart_readback_equal",
            ))
            if domain["strict_lifecycle_success"]:
                domain["status"] = "completed"
            elif domain["status"] == "generated":
                domain["status"] = "lifecycle_failed"
                domain["error_code"] = "readback_mismatch"
        evidence["provider_calls"] = bridge.calls
        evidence["wire_payload_audit"] = bridge.payload_audit
        evidence["wire_payload_audit_passed"] = _payload_audit_passed(bridge)
        evidence["joint_strict_lifecycle_success"] = bool(persona["strict_lifecycle_success"] and scene["strict_lifecycle_success"])
        evidence["failure_attribution"] = {"persona": persona["status"], "scene": scene["status"]}
        terminal_statuses = {str(persona["status"]), str(scene["status"])}
        if evidence["joint_strict_lifecycle_success"]:
            status = "completed"
        elif "uncertain" in terminal_statuses or any(
            isinstance(failure, WireFailure) and failure.uncertain
            for failure in domain_transport_failures.values()
        ):
            status = "uncertain"
        elif terminal_statuses & {"infrastructure_failed", "lifecycle_failed"}:
            status = "infrastructure_failed"
        elif "data_failed" in terminal_statuses:
            status = "data_failed"
        else:
            status = "candidate_failed"
    except Exception as exc:
        evidence["adapter_exception_class"] = type(exc).__name__
        evidence["provider_calls"] = bridge.calls
        evidence["wire_payload_audit"] = bridge.payload_audit
        evidence["wire_payload_audit_passed"] = _payload_audit_passed(bridge)
        status = "uncertain" if any(
            isinstance(failure, WireFailure) and failure.uncertain
            for failure in domain_transport_failures.values()
        ) else "infrastructure_failed"

    atomic_json(context.storage / EVIDENCE_NAME, evidence)
    evidence_sha = _sha256_bytes((context.storage / EVIDENCE_NAME).read_bytes())
    return {
        "status": status,
        "failure_owner": None if status == "completed" else "infrastructure" if status in {"uncertain", "infrastructure_failed"} else status.removesuffix("_failed"),
        "metrics": {
            "persona_strict_lifecycle": bool(evidence["persona"].get("strict_lifecycle_success")),
            "scene_strict_lifecycle": bool(evidence["scene"].get("strict_lifecycle_success")),
            "joint_strict_lifecycle": bool(evidence.get("joint_strict_lifecycle_success")),
        },
        "scope": SCOPE,
        "evidence": [{"path": EVIDENCE_NAME, "contract": EVIDENCE_CONTRACT, "sha256": evidence_sha}],
    }
