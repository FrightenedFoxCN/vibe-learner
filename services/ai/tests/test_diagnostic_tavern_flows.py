"""Real admitted Tavern fault/retry paths with only provider output scripted."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from tests.support.tavern_provider import SequencedTavernProvider
from tests.test_persona_lifecycle import create_request


class TavernDiagnosticContainer(Container):
    def _build_model_provider(self, settings):
        assert settings.plan_provider == "mock"
        return SequencedTavernProvider(fail_calls={2})


class DiagnosticTavernFlowTests(TestCase):
    def test_partial_replay_and_child_retry_keep_canonical_identity_and_message_scope(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(settings=Settings(database_url=f"sqlite:///{root / 'domain.db'}",
                storage_root=str(root / "data"), plan_provider="mock", ocr_engine="disabled"),
                container_factory=TavernDiagnosticContainer)
            with TestClient(app) as client:
                personas = []
                for index in range(3):
                    payload = create_request().model_dump(mode="json")
                    payload["name"] = f"PRIVATE_PERSONA_{index}"
                    response = client.post("/personas", json=payload)
                    self.assertEqual(response.status_code, 200, response.text)
                    personas.append(response.json()["id"])
                created = client.post("/tavern/rooms", json={"title": "PRIVATE_ROOM", "persona_ids": personas, "idempotency_key": "diagnostic-room"})
                self.assertEqual(created.status_code, 200, created.text)
                room_id = created.json()["room"]["id"]
                headers = {"X-Debug-Flow-Id": "tavern_fault_flow", "X-Debug-Action-Id": "turn"}
                payload = {"input": {"kind": "user_message", "content": "PRIVATE_MESSAGE"}, "mode": "facilitated",
                    "target_persona_ids": personas, "guidance": "PRIVATE_GUIDANCE", "idempotency_key": "diagnostic-turn", "expected_room_revision": 0}
                failed = client.post(f"/tavern/rooms/{room_id}/turns", json=payload, headers=headers)
                self.assertEqual(failed.status_code, 502, failed.text)
                source_id = failed.json()["detail"]["run_id"]
                replay = client.post(f"/tavern/rooms/{room_id}/turns", json=payload, headers={**headers, "X-Debug-Action-Id": "replay"})
                self.assertEqual(replay.status_code, 200, replay.text)
                source = replay.json()
                self.assertEqual(source["run"]["status"], "partial")
                self.assertEqual([step["status"] for step in source["run"]["speaker_steps"]], ["completed", "failed", "blocked"])
                provider = app.state.container.tavern_service.model_provider
                self.assertEqual(len(provider.calls), 2)
                retry = client.post(f"/tavern/rooms/{room_id}/runs/{source_id}/retry",
                    json={"idempotency_key": "diagnostic-retry", "expected_room_revision": 1},
                    headers={**headers, "X-Debug-Action-Id": "retry"})
                self.assertEqual(retry.status_code, 200, retry.text)
                child = retry.json()
                self.assertEqual(child["run"]["status"], "completed")
                self.assertEqual(child["run"]["parent_run_id"], source_id)
                self.assertIsNone(child["input_message"])
                self.assertEqual([item["persona_id"] for item in provider.calls], [personas[0], personas[1], personas[1], personas[2]])
                repository = app.state.container.tavern_service.repository
                parent_binding = repository.require_harness_operation(source_id)
                child_binding = repository.require_harness_operation(child["run"]["id"])
                self.assertEqual(child_binding.parent_harness_operation_id, parent_binding.harness_operation_id)
                self.assertNotEqual(child_binding.harness_operation_id, parent_binding.harness_operation_id)
                store = app.state.diagnostics
                store.queue.join()
                by_action = {}
                for action, response in (("turn", failed), ("replay", replay), ("retry", retry)):
                    events = [item["event"] for item in store.query(0, 100, {"action_id": action})]
                    self.assertTrue(events)
                    self.assertLess(len(events), 100)
                    self.assertTrue(all(event["flow_id"] == headers["X-Debug-Flow-Id"] for event in events))
                    self.assertTrue(all(event["request_id"] == response.headers["x-request-id"] for event in events))
                    by_action[action] = events
                runtime = HarnessRuntimeRepository(app.state.container.database)
                for action, binding in (("turn", parent_binding), ("retry", child_binding)):
                    refs = [event["harness"] for event in by_action[action] if event.get("harness")]
                    self.assertTrue(refs)
                    self.assertEqual({ref["operation_id"] for ref in refs}, {binding.harness_operation_id})
                    traces = runtime.list_operation_traces(binding.harness_operation_id)
                    self.assertTrue({ref["trace_id"] for ref in refs if ref["trace_id"]}.issubset({trace.trace_id for trace in traces}))
                    outcomes = [trace.terminal_trace.commit_evidence.status.value for trace in traces if trace.terminal_trace]
                    self.assertIn("committed", outcomes)
                    if action == "turn":
                        self.assertIn("not_committed", outcomes)
                for action, result in (("replay", source), ("retry", child)):
                    messages = [event["resource"] for event in by_action[action] if (event.get("resource") or {}).get("resource_type") == "tavern_message"]
                    self.assertEqual({item["resource_id"] for item in messages}, {item["id"] for item in result["generated_messages"]} | ({result["input_message"]["id"]} if result["input_message"] else set()))
                    expected_messages = ([result["input_message"]] if result["input_message"] else []) + result["generated_messages"]
                    self.assertEqual({item["resource_id"]: (item["sequence"], item["parent_resource_id"]) for item in messages},
                        {item["id"]: (item["sequence"], room_id) for item in expected_messages})
                self.assertFalse(any(event.get("resource") for event in by_action["turn"]))
                for secret in ("PRIVATE_PERSONA", "PRIVATE_ROOM", "PRIVATE_MESSAGE", "PRIVATE_GUIDANCE", "planned_actor_failure"):
                    self.assertNotIn(secret, json.dumps(by_action))

    def test_cancel_fences_late_provider_and_retains_separate_request_diagnostics(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from unittest.mock import patch

        with TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(settings=Settings(database_url=f"sqlite:///{root / 'domain.db'}",
                storage_root=str(root / "data"), plan_provider="mock", ocr_engine="disabled"),
                container_factory=TavernDiagnosticContainer)
            with TestClient(app) as client:
                personas = client.get("/personas").json()["items"]
                persona_id = personas[0]["id"]
                created = client.post("/tavern/rooms", json={"title": "PRIVATE_CANCEL_ROOM", "persona_ids": [persona_id], "idempotency_key": "cancel-room"})
                self.assertEqual(created.status_code, 200, created.text)
                room_id = created.json()["room"]["id"]
                service = app.state.container.tavern_service
                provider = service.model_provider
                started, released = Event(), Event()
                original = provider.generate_tavern_actor_reply

                def waiting_provider(**kwargs):
                    started.set()
                    if not released.wait(timeout=10):
                        raise RuntimeError("PRIVATE_CANCEL_WAIT_TIMEOUT")
                    return original(**kwargs)

                headers = {"X-Debug-Flow-Id": "cancel_flow", "X-Debug-Action-Id": "turn"}
                payload = {"input": {"kind": "user_message", "content": "PRIVATE_CANCEL_MESSAGE"}, "mode": "direct",
                    "target_persona_ids": [persona_id], "idempotency_key": "cancel-turn", "expected_room_revision": 0}
                with patch.object(provider, "generate_tavern_actor_reply", side_effect=waiting_provider), ThreadPoolExecutor(max_workers=1) as executor:
                    worker = executor.submit(client.post, f"/tavern/rooms/{room_id}/turns", json=payload, headers=headers)
                    try:
                        self.assertTrue(started.wait(timeout=5))
                        run = service.repository.get_run_by_idempotency_key(room_id=room_id, idempotency_key="cancel-turn")
                        self.assertIsNotNone(run)
                        canceled = client.post(f"/tavern/rooms/{room_id}/runs/{run.id}/cancel", headers={**headers, "X-Debug-Action-Id": "cancel"})
                        self.assertEqual(canceled.status_code, 200, canceled.text)
                        self.assertEqual(canceled.json()["run"]["status"], "canceled")
                    finally:
                        released.set()
                    late = worker.result(timeout=5)
                self.assertEqual(late.status_code, 409, late.text)
                self.assertEqual(late.json()["detail"]["code"], "tavern_run_canceled")
                self.assertEqual(len(provider.calls), 1)
                self.assertEqual(service.repository.list_run_messages(run.id), [])
                room = service.repository.require_room(room_id)
                self.assertEqual([item.author_kind.value for item in room.messages], ["user"])
                resumed = client.post(f"/tavern/rooms/{room_id}/runs/{run.id}/resume", headers={**headers, "X-Debug-Action-Id": "resume"})
                self.assertEqual(resumed.status_code, 200, resumed.text)
                self.assertEqual(resumed.json()["run"]["status"], "canceled")
                self.assertEqual(resumed.json()["generated_messages"], [])
                self.assertEqual(len(provider.calls), 1)
                store = app.state.diagnostics
                store.queue.join()
                all_events = []
                for action, response in (("turn", late), ("cancel", canceled), ("resume", resumed)):
                    events = [item["event"] for item in store.query(0, 100, {"action_id": action})]
                    self.assertTrue(events)
                    self.assertLess(len(events), 100)
                    self.assertTrue(all(event["flow_id"] == "cancel_flow" for event in events))
                    self.assertTrue(all(event["request_id"] == response.headers["x-request-id"] for event in events))
                    self.assertTrue(all(event["resource"]["resource_id"] in {room_id, run.id, room.messages[0].id} for event in events if event.get("resource")))
                    if action == "turn":
                        self.assertFalse(any(event.get("resource") for event in events))
                    else:
                        self.assertEqual({event["resource"]["resource_id"] for event in events if event.get("resource")}, {room_id, run.id, room.messages[0].id})
                    all_events.extend(events)
                binding = service.repository.require_harness_operation(run.id)
                refs = [event["harness"] for event in all_events if event.get("harness")]
                self.assertTrue(refs)
                self.assertEqual({ref["operation_id"] for ref in refs}, {binding.harness_operation_id})
                traces = HarnessRuntimeRepository(app.state.container.database).list_operation_traces(binding.harness_operation_id)
                self.assertTrue({ref["trace_id"] for ref in refs if ref["trace_id"]}.issubset({trace.trace_id for trace in traces}))
                terminal = [trace.terminal_trace for trace in traces if trace.terminal_trace]
                self.assertTrue(terminal)
                self.assertTrue(all(trace.commit_evidence.status.value == "not_committed" for trace in terminal))
                for secret in ("PRIVATE_CANCEL_ROOM", "PRIVATE_CANCEL_MESSAGE", "PRIVATE_CANCEL_WAIT_TIMEOUT"):
                    self.assertNotIn(secret, json.dumps(all_events))
            restarted = create_app(settings=Settings(database_url=f"sqlite:///{root / 'domain.db'}",
                storage_root=str(root / "data"), plan_provider="mock", ocr_engine="disabled"),
                container_factory=TavernDiagnosticContainer)
            with TestClient(restarted) as client:
                read_back = client.post(f"/tavern/rooms/{room_id}/runs/{run.id}/resume",
                    headers={"X-Debug-Flow-Id": "cancel_flow", "X-Debug-Action-Id": "restart_resume"})
                self.assertEqual(read_back.status_code, 200, read_back.text)
                self.assertEqual(read_back.json()["run"]["status"], "canceled")
                self.assertEqual(read_back.json()["generated_messages"], [])
                self.assertEqual(restarted.state.container.tavern_service.model_provider.calls, [])
                self.assertEqual(restarted.state.container.tavern_service.repository.require_harness_operation(run.id), binding)
                restarted.state.diagnostics.queue.join()
                old_events = [item["event"] for item in restarted.state.diagnostics.query(0, 100, {"action_id": "turn"})]
                self.assertEqual({event["event_id"] for event in old_events}, {event["event_id"] for event in all_events if event["action_id"] == "turn"})
                new_events = [item["event"] for item in restarted.state.diagnostics.query(0, 100, {"action_id": "restart_resume"})]
                self.assertTrue(new_events)
                self.assertTrue(all(event["request_id"] == read_back.headers["x-request-id"] and event["flow_id"] == "cancel_flow" for event in new_events))
                self.assertEqual({event["resource"]["resource_id"] for event in new_events if event.get("resource")}, {room_id, run.id, room.messages[0].id})
                self.assertTrue({event["event_id"] for event in new_events}.isdisjoint({event["event_id"] for event in all_events}))
                self.assertNotIn("PRIVATE_CANCEL_MESSAGE", json.dumps(new_events))
