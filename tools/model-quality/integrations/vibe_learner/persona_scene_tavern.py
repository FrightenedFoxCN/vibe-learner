"""Production-shaped Persona/Scene -> Tavern shadow quality experiment.

The existing v3 traces remain the operational source of truth.  This adapter
adds a research-only semantic ledger over synthetic inputs; it does not turn
semantic scores into Harness commit evidence or automatically save proposals
outside the isolated sample database.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.models.domain import SceneLayerStateRecord
from app.models.scene import build_scene_profile, decode_scene_tree_proposal, project_scene_tree_proposal
from app.models.tavern import TavernTurnResponse

from .common import Bridge, create_app, envelope, outcome, settings, source_manifest, traces


RUBRIC = "persona-scene-tavern-shadow-v1"


def _contains_all(text: str, values: list[str]) -> bool:
    folded = text.casefold()
    return all(value.casefold() in folded for value in values)


def _contains_none(text: str, values: list[str]) -> bool:
    folded = text.casefold()
    return all(value.casefold() not in folded for value in values)


def _trace_is_proposal(trace: dict[str, object]) -> bool:
    evidence = trace.get("commit_evidence")
    return (
        trace.get("status") in {"passed", "repaired"}
        and isinstance(evidence, dict)
        and evidence.get("status") == "not_applicable"
    )


def _http_failure_status(
    response,
    bridge: Bridge,
    *,
    verified_candidate_tavern_run_id: str | None = None,
) -> str:
    if bridge.failure is not None:
        return "uncertain"
    try:
        detail = response.json().get("detail")
    except (AttributeError, TypeError, ValueError):
        detail = None
    structured_code = detail.get("code") if isinstance(detail, dict) else None
    has_terminal_tavern_receipt = (
        structured_code == "tavern_run_failed"
        and detail.get("recovery_action") == "replay_same_request"
        and isinstance(detail.get("run_id"), str)
        and bool(detail["run_id"])
        and detail["run_id"] == verified_candidate_tavern_run_id
    )
    candidate_codes = {
        "setting_model_invalid_json",
        "setting_model_invalid_payload",
        "setting_persona_card_count_mismatch",
    }
    has_setting_candidate_code = (
        isinstance(detail, str) and detail in candidate_codes
    )
    if response.status_code == 502 and (
        has_setting_candidate_code or has_terminal_tavern_receipt
    ):
        return "candidate_failed"
    if 400 <= response.status_code < 500:
        return "data_failed"
    return "infrastructure_failed"


def _verified_candidate_tavern_run_id(
    container,
    *,
    room_id: str,
    idempotency_key: str,
) -> str | None:
    repository = container.tavern_service.repository
    run = repository.get_run_by_idempotency_key(
        room_id=room_id,
        idempotency_key=idempotency_key,
    )
    # This shadow flow is direct and schedules exactly one actor. Facilitated
    # partial runs require step-scoped trace correlation and are out of scope.
    if run is None or run.status.value != "failed":
        return None
    failed_steps = [step for step in run.speaker_steps if step.status.value == "failed"]
    candidate_error_codes = {
        "tavern_actor_harness_failed",
        "tavern_actor_invalid_payload",
    }
    if not failed_steps or any(
        step.error_code not in candidate_error_codes for step in failed_steps
    ):
        return None
    binding = repository.require_harness_operation(run.id)
    terminal = [
        execution.terminal_trace
        for execution in container.tavern_service.harness_runtime_repository.list_operation_traces(
            binding.harness_operation_id
        )
        if execution.terminal_trace is not None
    ]
    if not terminal or any(trace.status != "failed" for trace in terminal):
        return None
    return run.id


def _persona_save_payload(name: str, generated: dict[str, object]) -> dict[str, object]:
    items = generated.get("items")
    if not isinstance(items, list):
        raise ValueError("persona_items_missing")
    return {
        "name": name,
        "summary": generated.get("summary", ""),
        "relationship": generated.get("relationship", ""),
        "learner_address": generated.get("learner_address", ""),
        "system_prompt": "只依据房间快照和当前对话作答；未知信息明确说未知。",
        "reference_hints": [],
        "slots": [
            {
                "kind": item["kind"],
                "label": item["label"],
                "content": item["content"],
                "weight": 50,
                "locked": False,
                "sort_order": index,
            }
            for index, item in enumerate(items)
        ],
        "available_emotions": ["calm"],
        "available_actions": ["idle"],
        "default_speech_style": "简洁",
    }


def _scene_save_payload(generated: dict[str, object]) -> dict[str, object]:
    return {
        key: generated[key]
        for key in ("scene_name", "scene_summary", "scene_layers", "selected_layer_id")
    } | {
        "contract_version": "scene-committed-save-v1",
        "expected_revision": 0,
        "collapsed_layer_ids": [],
    }


def _fake_response(spec: dict[str, object], call_number: int) -> dict[str, object]:
    if call_number == 1:
        return envelope(json.dumps(spec["fake_persona"], ensure_ascii=False))
    if call_number == 2:
        return envelope(json.dumps(spec["fake_scene"], ensure_ascii=False))
    return envelope(json.dumps(spec["fake_tavern"], ensure_ascii=False))


def run_sample(context, case, variant):
    if case.rubric != RUBRIC or variant.id != "shadow-chain":
        return {
            "status": "data_failed",
            "failure_owner": "data",
            "error_code": "wrong_persona_scene_tavern_shadow_contract",
        }
    try:
        spec = json.loads(case.gold)
        persona_input = spec["persona_input"]
        scene_input = spec["scene_input"]
        user_message = spec["user_message"]
        expected = spec["expected"]
        if not all(isinstance(value, dict) for value in (persona_input, scene_input, expected)):
            raise ValueError("invalid_shadow_fixture")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return {
            "status": "data_failed",
            "failure_owner": "data",
            "error_code": "invalid_persona_scene_tavern_shadow_fixture",
        }

    bridge = Bridge(context, lambda payload: _fake_response(spec, bridge.calls))
    evidence: dict[str, object] = {
        "fixture": "persona-scene-tavern-shadow-v1",
        "case_id": case.id,
        "strategy": {
            "operational": "production-v3",
            "semantic": "research-shadow-ledger-v1",
            "review": "independent-manual-required",
        },
    }
    config = settings(context)
    try:
        with bridge.installed():
            app = create_app(settings=config)
            with TestClient(app) as client:
                persona_response = client.post("/persona-cards/generate", json=persona_input)
                scene_response = client.post("/scene-setup/generate", json=scene_input)
                evidence["generation_http"] = {
                    "persona": persona_response.status_code,
                    "scene": scene_response.status_code,
                }
                persona_generated = persona_response.status_code == 200
                scene_generated = scene_response.status_code == 200
                generation_failures = [
                    _http_failure_status(response, bridge)
                    for response in (persona_response, scene_response)
                    if response.status_code != 200
                ]
                if any(status != "candidate_failed" for status in generation_failures):
                    failure_status = (
                        "uncertain" if "uncertain" in generation_failures
                        else "infrastructure_failed" if "infrastructure_failed" in generation_failures
                        else "data_failed"
                    )
                    return outcome(
                        context,
                        {"generation_boundary_completed": False},
                        evidence,
                        status=failure_status,
                    )
                if persona_generated:
                    generated_persona = persona_response.json()
                    persona_trace = generated_persona["harness_trace"]
                else:
                    fake_persona = spec["fake_persona"]
                    generated_persona = {
                        "summary": fake_persona["summary"],
                        "relationship": fake_persona["relationship"],
                        "learner_address": fake_persona["learner_address"],
                        "items": fake_persona["cards"],
                    }
                    persona_trace = {}
                if scene_generated:
                    generated_scene = scene_response.json()
                    scene_trace = generated_scene["harness_trace"]
                else:
                    fallback_projection = project_scene_tree_proposal(
                        decode_scene_tree_proposal(spec["fake_scene"])
                    )
                    generated_scene = fallback_projection.model_dump(mode="json")
                    scene_trace = {}
                evidence["downstream_fixture_fallback"] = {
                    "persona": not persona_generated,
                    "scene": not scene_generated,
                    "scope": "research-only; never counted as model generation success",
                }

                evidence["phase"] = "save_persona"
                saved_persona_response = client.post(
                    "/personas",
                    json=_persona_save_payload(str(spec["persona_name"]), generated_persona),
                )
                saved_persona_response.raise_for_status()
                saved_persona = saved_persona_response.json()
                evidence["phase"] = "save_scene"
                saved_scene_response = client.post(
                    "/scene-library", json=_scene_save_payload(generated_scene)
                )
                saved_scene_response.raise_for_status()
                saved_scene = saved_scene_response.json()
                room_scene_profile = build_scene_profile(
                    scene_name=saved_scene["scene_name"],
                    scene_summary=saved_scene["scene_summary"],
                    scene_layers=[
                        SceneLayerStateRecord.model_validate(item)
                        for item in saved_scene["scene_layers"]
                    ],
                    selected_layer_id=saved_scene["selected_layer_id"],
                ).model_dump(mode="json")

                evidence["phase"] = "create_room"
                room_response = client.post(
                    "/tavern/rooms",
                    json={
                        "title": "合成跨域质量实验",
                        "persona_ids": [saved_persona["id"]],
                        "scene_profile": room_scene_profile,
                        "idempotency_key": "shadow-room-" + context.transport.sample[:40],
                    },
                )
                room_response.raise_for_status()
                room_id = room_response.json()["room"]["id"]
                room_before = client.get(f"/tavern/rooms/{room_id}").json()

                evidence["phase"] = "mutate_sources"
                persona_update = {
                    key: saved_persona[key]
                    for key in (
                        "name", "relationship", "learner_address", "system_prompt",
                        "reference_hints", "slots", "available_emotions",
                        "available_actions", "default_speech_style",
                    )
                } | {
                    "expected_revision": saved_persona["revision"],
                    "summary": "源 Persona 已在建房后修改；房间快照不得采用本句。",
                }
                client.patch(f"/personas/{saved_persona['id']}", json=persona_update).raise_for_status()
                scene_update = _scene_save_payload(generated_scene) | {
                    "expected_revision": saved_scene["revision"],
                    "scene_summary": "源 Scene 已在建房后修改；房间快照不得采用本句。",
                }
                client.put(f"/scene-library/{saved_scene['scene_id']}", json=scene_update).raise_for_status()
                room_after_source_edits = client.get(f"/tavern/rooms/{room_id}").json()

                evidence["phase"] = "run_turn"
                turn_payload = {
                    "input": {"kind": "user_message", "content": user_message},
                    "mode": "direct",
                    "target_persona_ids": [saved_persona["id"]],
                    "guidance": "只依据房间建立时冻结的人格与场景快照回答。",
                    "idempotency_key": "shadow-turn-" + context.transport.sample[:40],
                    "expected_room_revision": room_before["room"]["revision"],
                }
                turn_response = client.post(
                    f"/tavern/rooms/{room_id}/turns", json=turn_payload
                )
                evidence["turn_http"] = turn_response.status_code
                if turn_response.status_code != 200:
                    verified_run_id = _verified_candidate_tavern_run_id(
                        app.state.container,
                        room_id=room_id,
                        idempotency_key=turn_payload["idempotency_key"],
                    )
                    return outcome(
                        context,
                        {"turn_completed": False},
                        evidence,
                        status=_http_failure_status(
                            turn_response,
                            bridge,
                            verified_candidate_tavern_run_id=verified_run_id,
                        ),
                    )
                turn = TavernTurnResponse.model_validate(turn_response.json())
                binding = app.state.container.tavern_service.repository.require_harness_operation(turn.run.id)
                terminal = traces(app.state.container, binding.harness_operation_id)
                readback = client.get(f"/tavern/rooms/{room_id}").json()
                before_replay_calls = bridge.calls
                replay = client.post(f"/tavern/rooms/{room_id}/turns", json=turn_payload)

            with TestClient(create_app(settings=config)) as restarted:
                restart_readback = restarted.get(f"/tavern/rooms/{room_id}")

        persona_projection = {
            "summary": generated_persona.get("summary"),
            "relationship": generated_persona.get("relationship"),
            "learner_address": generated_persona.get("learner_address"),
            "items": [
                {
                    key: item.get(key)
                    for key in ("title", "kind", "label", "content", "tags", "source_note")
                }
                for item in generated_persona.get("items", [])
                if isinstance(item, dict)
            ],
        }
        persona_text = json.dumps(
            persona_projection,
            ensure_ascii=False,
        )
        scene_text = json.dumps(
            {
                key: generated_scene.get(key)
                for key in ("scene_name", "scene_summary", "scene_layers")
            },
            ensure_ascii=False,
        )
        tavern_text = "\n".join(message.content for message in turn.generated_messages)
        lexical_triage = {
            "persona_required": persona_generated and _contains_all(persona_text, expected["persona_required"]),
            "persona_forbidden": persona_generated and _contains_none(persona_text, expected["persona_forbidden"]),
            "scene_required": scene_generated and _contains_all(scene_text, expected["scene_required"]),
            "scene_forbidden": scene_generated and _contains_none(scene_text, expected["scene_forbidden"]),
            "tavern_required": _contains_all(tavern_text, expected["tavern_required"]),
            "tavern_forbidden": _contains_none(tavern_text, expected["tavern_forbidden"]),
        }
        snapshot_equal = (
            room_before["participants"] == room_after_source_edits["participants"]
            and room_before["room"]["scene_profile"]
            == room_after_source_edits["room"]["scene_profile"]
        )
        replay_equal = replay.status_code == 200 and replay.json() == turn_response.json()
        restart_equal = restart_readback.status_code == 200 and restart_readback.json() == readback
        operational = {
            "persona_proposal_v3": persona_generated and _trace_is_proposal(persona_trace),
            "scene_proposal_v3": scene_generated and _trace_is_proposal(scene_trace),
            "source_save_readback": bool(saved_persona["id"] and saved_scene["scene_id"]),
            "room_snapshot_stable": snapshot_equal,
            "tavern_committed_v3": (
                turn.run.status.value == "completed"
                and len(terminal) == 1
                and all(
                    trace.status in {"passed", "repaired"}
                    and trace.commit_evidence.status == "committed"
                    for trace in terminal
                )
            ),
            "idempotent_replay": replay_equal and bridge.calls == before_replay_calls,
            "restart_readback": restart_equal,
        }
        evidence.update(
            provider_calls=bridge.calls,
            operation_id=binding.harness_operation_id,
            generated={
                "persona": json.loads(persona_text),
                "scene": json.loads(scene_text),
                "tavern_messages": [message.model_dump(mode="json") for message in turn.generated_messages],
            },
            lexical_triage=lexical_triage,
            operational_checks=operational,
            manual_review_axes=[
                "persona_fidelity", "scene_fidelity", "relationship_invention",
                "task_and_format_adherence",
            ],
        )
        return outcome(
            context,
            operational,
            evidence,
            status="uncertain" if bridge.failure else None,
        )
    except Exception as exc:
        evidence["exception_class"] = type(exc).__name__
        return outcome(
            context,
            {"adapter_completed": False},
            evidence,
            status="uncertain" if bridge.failure else "infrastructure_failed",
        )
