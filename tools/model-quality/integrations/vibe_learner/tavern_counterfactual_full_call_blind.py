"""Production full-call Tavern counterfactual-twin experiment.

Each sample creates one committed-shape Persona snapshot and one committed-shape
Scene projection, creates and reads a room through the public API, and performs
one direct single-target turn.  The production Tavern decoder, v3 runtime,
message commit read-back, replay path, and restart reads are the experiment;
the readiness oracle and review key are never projected into the provider call.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.models.domain import SceneLayerStateRecord
from app.models.tavern import TavernRoomDetail, TavernRunListResponse, TavernTurnResponse
from app.models.scene import build_scene_profile
from app.models.tavern_commit import (
    revalidate_tavern_message_committed_projection,
)
from app.models.tavern import build_tavern_persona_message_committed_projection
from app.models.harness import (
    build_tavern_persona_message_commit_binding,
    validate_harness_operation_commit,
)
from model_quality.runner import atomic_json

from .common import Bridge, create_app, envelope, safe_traces, settings, traces
from .tavern_counterfactual_twins import (
    FAMILY_IDS,
    TavernCounterfactualFixtureV1,
    canonical_sha256,
)


CAMPAIGN_ID = "m3-tavern-counterfactual-production-full-call-blind-20260913-v1"
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/persona-scene/tavern-counterfactual-twins-v1.json"
FIXTURE_SHA256 = "f2b85d63c25c1584042da96a16348e1c74d036f60a2fd231c6c432a204c75b0f"
RUBRIC = "m3-tavern-counterfactual-production-full-call-blind-rubric-v1"
VARIANT = "production-full-call"
EVIDENCE_NAME = "tavern-counterfactual-full-call-evidence.json"
EVIDENCE_CONTRACT = "tavern-counterfactual-full-call-evidence-v1"
SCOPE = "production Tavern full call; one Message primary_output_only plus separately checked Room/Run/Step operations"
SEED = 91341
CONCURRENCY = 2
TIMEOUT_SECONDS = 90
SAMPLE_DEADLINE_SECONDS = 420
MAX_OUTPUT_TOKENS = 4096
INPUT_RESERVATION_TOKENS = 100000
SAMPLE_WIRE_LIMIT = 3
DENOMINATOR = 10
GATE = {
    "denominator_families": 10,
    "double_strict_min": 9,
    "denied_evaluable_min": 4,
    "explicitly_unknown_evaluable_min": 4,
    "shared_authority_and_sensitivity_min": 9,
    "reviewer_new_major_max": 0,
    "reviewers": 2,
    "completed_operational_checks_required": True,
    "message_commit_scope": "primary_output_only",
    "max_wires_per_twin": 3,
    "max_wires_total": 60,
}


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_fixture() -> TavernCounterfactualFixtureV1:
    raw = FIXTURE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
        raise ValueError("tavern_full_call_fixture_digest_mismatch")
    fixture = TavernCounterfactualFixtureV1.model_validate_json(raw, strict=True)
    if tuple(row.family_id for row in fixture.families) != FAMILY_IDS:
        raise ValueError("tavern_full_call_fixture_catalog_mismatch")
    return fixture


def sample_catalog() -> list[dict[str, str]]:
    """Stable runner identities. Family, axis and polarity stay out of review packets."""
    rows: list[dict[str, str]] = []
    for index, family in enumerate(load_fixture().families, start=1):
        for arm, twin in (("x", family.supported), ("y", family.second)):
            rows.append({
                "case_id": f"twin-{index:02}-{arm}",
                "family_id": family.family_id,
                "arm": arm,
                "polarity": twin.polarity,
                "source": twin.source_text,
                "source_sha256": twin.source_sha256,
            })
    return rows


def build_public_input(*, family, twin, peer) -> dict[str, str]:
    """Offline prepare projection; no oracle, axis, polarity, ids, or seals."""
    relationship = twin.authoritative_value if family.authority == "participant_snapshot" else (
        "The actor must use only the committed room snapshot and transcript."
    )
    scene_summary = twin.authoritative_value if family.authority == "scene_snapshot" else (
        "A quiet catalog desk. No facts beyond the committed snapshot are implied."
    )
    return {
        "version": "tavern-counterfactual-production-input-v1",
        "authoritative_source": twin.source_text,
        "persona_relationship": relationship,
        "scene_summary": scene_summary,
        "opening_prompt": (
            twin.authoritative_value
            if family.authority == "transcript_snapshot"
            else "The committed opening contains no additional authority claim."
        ),
        "request": _user_message(false_premise=peer.authoritative_value),
        "guidance": PUBLIC_GUIDANCE,
    }


def _load_public_input(raw: str) -> dict[str, str]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in items:
            if key in value:
                raise ValueError("tavern_full_call_public_input_duplicate_key")
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=pairs)
    if not isinstance(value, dict) or set(value) != {
        "version", "authoritative_source", "persona_relationship",
        "scene_summary", "opening_prompt", "request", "guidance",
    } or value.get("version") != "tavern-counterfactual-production-input-v1":
        raise ValueError("tavern_full_call_public_input_schema_invalid")
    if any(not isinstance(item, str) or not item for item in value.values()):
        raise ValueError("tavern_full_call_public_input_value_invalid")
    return value


def _persona_payload(*, public: dict[str, str]) -> dict[str, object]:
    return {
        "name": "Blind Actor",
        "summary": "A careful catalog assistant who corrects false premises and preserves explicit uncertainty.",
        "relationship": public["persona_relationship"],
        "learner_address": "visitor",
        "system_prompt": "Use only the committed Tavern room snapshot. Correct denied premises, preserve explicit unknowns, and finish the requested catalog task.",
        "reference_hints": [],
        "slots": [{
            "kind": "teaching_method", "label": "method",
            "content": "State the authority-sensitive answer, then inventory the requested materials.",
            "weight": 50, "locked": False, "sort_order": 0,
        }],
        "available_emotions": ["calm"],
        "available_actions": ["inventory"],
        "default_speech_style": "plain",
    }


def _scene_save_payload(*, public: dict[str, str]) -> dict[str, object]:
    summary = public["scene_summary"]
    return {
        "contract_version": "scene-committed-save-v1", "expected_revision": 0,
        "scene_name": "Blind scene", "scene_summary": summary,
        "scene_layers": [{
            "id": "blind-layer", "title": "Catalog desk",
            "scope_label": "room", "summary": "A catalog work surface.", "atmosphere": "quiet",
            "rules": "Only committed authority applies.", "entrance": "main entrance",
            "tags": "", "reuse_id": "blind-reuse", "reuse_hint": "",
            "objects": [], "children": [],
        }],
        "selected_layer_id": "blind-layer", "collapsed_layer_ids": [],
    }


def _user_message(*, false_premise: str) -> str:
    return (
        f'A visitor asserts: "{false_premise}." Check that specific premise against the '
        "committed authority, correct it or preserve explicit uncertainty as required, "
        "then inventory paper, seal, and lamp."
    )


PUBLIC_GUIDANCE = "Use only committed authority; correct the stated opposite premise, preserve unknowns, then inventory paper, seal, and lamp."


def _failed_candidate_run(container, *, room_id: str, idempotency_key: str) -> bool:
    repository = container.tavern_service.repository
    run = repository.get_run_by_idempotency_key(room_id=room_id, idempotency_key=idempotency_key)
    if run is None or run.status.value != "failed" or not run.speaker_steps:
        return False
    if any(step.status.value != "failed" for step in run.speaker_steps):
        return False
    try:
        binding = repository.require_harness_operation(run.id)
    except Exception:
        return False
    terminal = traces(container, binding.harness_operation_id)
    return bool(terminal) and all(item.status == "failed" for item in terminal)


def _turn_failure_status(response, bridge: Bridge, *, container, room_id: str, idempotency_key: str) -> str:
    if bridge.failure is not None:
        return "uncertain"
    if 400 <= response.status_code < 500:
        return "data_failed"
    if _failed_candidate_run(container, room_id=room_id, idempotency_key=idempotency_key):
        return "candidate_failed"
    return "infrastructure_failed"


def _fake_reply(_: object) -> dict[str, object]:
    # Fake transport exercises decode/commit only; it is never semantic evidence.
    return envelope(json.dumps({
        "text": "I will follow the committed authority, then inventory the requested materials.",
        "mood": "calm", "action": "inventory", "speech_style": "plain",
        "delivery_cue": "careful", "state_commentary": "",
        "addressed_participant_ids": [],
    }))


def _result(context, *, status: str, error_code: str | None, evidence: dict[str, object]):
    atomic_json(context.storage / EVIDENCE_NAME, evidence)
    result: dict[str, object] = {
        "status": status,
        "failure_owner": None if status == "completed" else (
            "infrastructure" if status in {"infrastructure_failed", "uncertain"}
            else status.removesuffix("_failed")
        ),
        "scope": SCOPE,
        "metrics": evidence.get("operational_checks", {}),
        "evidence": [{
            "path": EVIDENCE_NAME,
            "contract": EVIDENCE_CONTRACT,
            "sha256": _file_sha(context.storage / EVIDENCE_NAME),
        }],
    }
    if error_code:
        result["error_code"] = error_code
    return result


def run_sample(context, case, variant):
    bridge = Bridge(context, _fake_reply)
    evidence: dict[str, Any] = {
        "version": EVIDENCE_CONTRACT,
        "campaign_id": CAMPAIGN_ID,
        "case_id": case.id,
        "message_commit_scope": "primary_output_only",
    }
    try:
        public = _load_public_input(case.source)
        binding = json.loads(case.gold)
        if (
            case.rubric != RUBRIC or variant.id != VARIANT
            or binding != {
                "fixture_sha256": FIXTURE_SHA256,
                "public_input_sha256": canonical_sha256(public),
            }
        ):
            raise ValueError("tavern_full_call_case_binding_mismatch")
        campaign = context.transport.campaign
        expected_ids = [f"twin-{index:02}-{arm}" for index in range(1, 11) for arm in ("x", "y")]
        if (
            campaign.id != CAMPAIGN_ID or campaign.seed != SEED
            or campaign.concurrency != CONCURRENCY or campaign.repetitions != 1
            or campaign.timeout_seconds != TIMEOUT_SECONDS
            or campaign.sample_deadline_seconds != SAMPLE_DEADLINE_SECONDS
            or campaign.sample_wire_limit != SAMPLE_WIRE_LIMIT
            or campaign.max_output_tokens != MAX_OUTPUT_TOKENS
            or campaign.input_reservation_tokens != INPUT_RESERVATION_TOKENS
            or campaign.adapter != "vibe_learner.tavern_counterfactual_full_call_blind:run_sample"
            or [item.id for item in campaign.cases] != expected_ids
            or [item.id for item in campaign.variants] != [VARIANT]
            or campaign.autoscale is not None
            or campaign.model != "MiniMax-M3" or campaign.thinking != "adaptive"
            or campaign.temperature != 0.2 or campaign.transport not in {"fake", "minimax"}
        ):
            raise ValueError("tavern_full_call_campaign_mismatch")
        for configured in campaign.cases:
            configured_public = _load_public_input(configured.source)
            configured_binding = json.loads(configured.gold)
            if (
                configured.rubric != RUBRIC
                or configured_binding != {
                    "fixture_sha256": FIXTURE_SHA256,
                    "public_input_sha256": canonical_sha256(configured_public),
                }
            ):
                raise ValueError("tavern_full_call_campaign_case_mismatch")
    except Exception as exc:
        evidence["exception_class"] = type(exc).__name__
        return _result(context, status="data_failed", error_code="tavern_full_call_input_invalid", evidence=evidence)

    config = settings(context)
    try:
        with bridge.installed():
            app = create_app(settings=config)
            with TestClient(app) as client:
                persona_response = client.post("/personas", json=_persona_payload(public=public))
                persona_response.raise_for_status()
                persona = persona_response.json()
                persona_readback = next(
                    row for row in client.get("/personas").json()["items"] if row["id"] == persona["id"]
                )
                scene_response = client.post(
                    "/scene-library", json=_scene_save_payload(public=public)
                )
                scene_response.raise_for_status()
                scene = scene_response.json()
                scene_readback_response = client.get(f"/scene-library/{scene['scene_id']}")
                scene_readback_response.raise_for_status()
                scene_readback = scene_readback_response.json()
                scene_profile = build_scene_profile(
                    scene_name=scene["scene_name"], scene_summary=scene["scene_summary"],
                    scene_layers=[SceneLayerStateRecord.model_validate(item) for item in scene["scene_layers"]],
                    selected_layer_id=scene["selected_layer_id"],
                ).model_dump(mode="json")
                room_response = client.post("/tavern/rooms", json={
                    "title": "Counterfactual production full call",
                    "persona_ids": [persona["id"]],
                    "scene_profile": scene_profile,
                    "opening_prompt": public["opening_prompt"],
                    "idempotency_key": f"blind-room-{case.id}",
                })
                room_response.raise_for_status()
                room = TavernRoomDetail.model_validate(room_response.json())
                snapshot_response = client.get(f"/tavern/rooms/{room.room.id}")
                snapshot_response.raise_for_status()
                snapshot = TavernRoomDetail.model_validate(snapshot_response.json())
                if (
                    len(snapshot.messages) != 1
                    or snapshot.messages[0].sequence != 1
                    or snapshot.messages[0].content != public["opening_prompt"]
                ):
                    raise ValueError("tavern_full_call_opening_transcript_readback_invalid")
                turn_payload = {
                    "input": {"kind": "user_message", "content": public["request"]},
                    "mode": "direct", "target_persona_ids": [persona["id"]],
                    "guidance": public["guidance"],
                    "idempotency_key": f"blind-turn-{case.id}",
                    "expected_room_revision": snapshot.room.revision,
                }
                turn_response = client.post(f"/tavern/rooms/{room.room.id}/turns", json=turn_payload)
                if turn_response.status_code != 200:
                    evidence.update(turn_http=turn_response.status_code, provider_calls=bridge.calls)
                    failure_status = _turn_failure_status(
                        turn_response, bridge, container=app.state.container,
                        room_id=room.room.id, idempotency_key=turn_payload["idempotency_key"],
                    )
                    return _result(
                        context,
                        status=failure_status,
                        error_code="tavern_full_call_turn_unavailable",
                        evidence=evidence,
                    )
                turn = TavernTurnResponse.model_validate(turn_response.json())
                if len(turn.generated_messages) != 1 or len(turn.run.speaker_steps) != 1:
                    raise ValueError("tavern_full_call_single_target_projection_invalid")
                message = turn.generated_messages[0]
                repository = app.state.container.tavern_service.repository
                committed = repository.get_actor_commit_read_back(message_id=message.id)
                committed_projection = build_tavern_persona_message_committed_projection(
                    message=committed[0], run=committed[1], step=committed[2],
                    participants=committed[3], reply_anchor=committed[4],
                )
                revalidate_tavern_message_committed_projection(committed_projection)
                terminal = traces(app.state.container, repository.require_harness_operation(turn.run.id).harness_operation_id)
                committed_traces = [
                    item for item in terminal if item.commit_evidence.status == "committed"
                ]
                commit_binding = build_tavern_persona_message_commit_binding(committed_projection)
                if len(committed_traces) == 1:
                    validate_harness_operation_commit(
                        committed_traces[0], commit_binding,
                        message=committed[0], run=committed[1], step=committed[2],
                        participants=committed[3], reply_anchor=committed[4],
                    )
                before_replay_wires = bridge.calls
                replay_response = client.post(f"/tavern/rooms/{room.room.id}/turns", json=turn_payload)
                replay_response.raise_for_status()
                replay = TavernTurnResponse.model_validate(replay_response.json())
                room_after = TavernRoomDetail.model_validate(client.get(f"/tavern/rooms/{room.room.id}").json())
                runs_after = TavernRunListResponse.model_validate(client.get(f"/tavern/rooms/{room.room.id}/runs").json())

            with TestClient(create_app(settings=config)) as restarted:
                restart_room_response = restarted.get(f"/tavern/rooms/{room.room.id}")
                restart_runs_response = restarted.get(f"/tavern/rooms/{room.room.id}/runs")
                restart_room_response.raise_for_status()
                restart_runs_response.raise_for_status()
                restart_room = TavernRoomDetail.model_validate(restart_room_response.json())
                restart_runs = TavernRunListResponse.model_validate(restart_runs_response.json())

        operational = {
            "persona_record_readback": (
                persona_readback["id"] == persona["id"]
                and persona_readback["revision"] == persona["revision"]
                and persona_readback["relationship"] == public["persona_relationship"]
                and persona_readback["system_prompt"] == persona["system_prompt"]
            ),
            "scene_record_readback": (
                scene_readback == scene
                and scene_readback["scene_summary"] == public["scene_summary"]
            ),
            "snapshot_readback": (
                snapshot.room.id == room.room.id and len(snapshot.participants) == 1
                and snapshot.participants[0].persona_snapshot.relationship == public["persona_relationship"]
                and snapshot.room.scene_profile is not None
                and snapshot.room.scene_profile.summary == public["scene_summary"]
            ),
            "prior_transcript_committed": (
                turn.input_message is not None
                and snapshot.messages[0].sequence < turn.input_message.sequence
                and turn.input_message.reply_to_message_id == ""
            ),
            # A 200 TavernTurnResponse is only emitted after the production provider
            # adapter strictly decoded the complete TavernActorReply. We intentionally
            # do not fabricate non-persisted delivery_cue/state_commentary fields from
            # the committed Message projection.
            "production_route_strict_acceptance": True,
            "single_target_completed": turn.run.status.value == "completed" and len(turn.generated_messages) == 1,
            "test_turn_reply_anchor": turn.input_message is not None and message.reply_to_message_id == turn.input_message.id,
            "terminal_v3": len(terminal) == 1 and terminal[0].status in {"passed", "repaired"},
            "message_primary_output_only": len(committed_traces) == 1 and commit_binding.message_id == message.id,
            "run_step_readback": len(runs_after.items) == 1 and runs_after.items[0].speaker_steps[0].message_id == message.id,
            "idempotent_replay_no_new_wire": replay.model_dump(mode="json") == turn.model_dump(mode="json") and bridge.calls == before_replay_wires,
            "restart_room_readback": restart_room.model_dump(mode="json") == room_after.model_dump(mode="json"),
            "restart_runs_readback": restart_runs.model_dump(mode="json") == runs_after.model_dump(mode="json"),
            "wire_ceiling": bridge.calls <= SAMPLE_WIRE_LIMIT,
        }
        evidence.update({
            "fixture_sha256": FIXTURE_SHA256,
            "source": public["authoritative_source"],
            "source_sha256": canonical_sha256(public["authoritative_source"]),
            "public_request": public["request"],
            "public_guidance": public["guidance"],
            "reply": message.content,
            "reply_sha256": canonical_sha256(message.content),
            "provider_calls": bridge.calls,
            "operational_checks": operational,
            "trace_summary": safe_traces(terminal),
            "room_snapshot_sha256": canonical_sha256(snapshot.model_dump(mode="json")),
            "restart_room_sha256": canonical_sha256(restart_room.model_dump(mode="json")),
            "restart_runs_sha256": canonical_sha256(restart_runs.model_dump(mode="json")),
            "private_resource_ids": [
                persona["id"], scene["scene_id"], room.room.id, turn.run.id,
                message.id, message.reply_to_message_id,
            ],
        })
        if not all(operational.values()):
            return _result(context, status="infrastructure_failed", error_code="tavern_full_call_operational_check_failed", evidence=evidence)
        return _result(context, status="completed", error_code=None, evidence=evidence)
    except Exception as exc:
        evidence.update(exception_class=type(exc).__name__, provider_calls=bridge.calls)
        return _result(
            context,
            status="uncertain" if bridge.failure else "infrastructure_failed",
            error_code="tavern_full_call_adapter_failed",
            evidence=evidence,
        )
