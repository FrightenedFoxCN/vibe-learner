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
