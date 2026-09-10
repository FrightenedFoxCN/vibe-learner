"""Abrupt Tavern worker exit followed by real HTTP lease recovery."""
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from app.app_factory import create_app
from app.core.settings import Settings
from tests.test_diagnostic_tavern_flows import TavernDiagnosticContainer


def application(root):
    return create_app(settings=Settings(database_url=f"sqlite:///{root / 'domain.db'}",
        storage_root=str(root / "data"), plan_provider="mock", ocr_engine="disabled"),
        container_factory=TavernDiagnosticContainer)


def child(root):
    app = application(root)
    with TestClient(app) as client:
        ids = [item["id"] for item in client.get("/personas").json()["items"]][:2]
        assert len(ids) == 2
        created = client.post("/tavern/rooms", json={"title": "PRIVATE_CRASH_ROOM", "persona_ids": ids, "idempotency_key": "crash-room"})
        room_id = created.json()["room"]["id"]
        (root / "identity.json").write_text(json.dumps({"room_id": room_id, "personas": ids}))
        provider = app.state.container.tavern_service.model_provider
        original = provider.generate_tavern_actor_reply

        def interrupted(**kwargs):
            if len(provider.calls) == 1:
                # Persist a known diagnostic prefix before abrupt exit. Queued-tail
                # loss is intentionally outside this test's acceptance claim.
                app.state.diagnostics.queue.join()
                os._exit(73)
            return original(**kwargs)

        with patch.object(provider, "generate_tavern_actor_reply", side_effect=interrupted):
            client.post(f"/tavern/rooms/{room_id}/turns", json={"input": {"kind": "user_message", "content": "PRIVATE_CRASH_MESSAGE"},
                "mode": "facilitated", "target_persona_ids": ids, "idempotency_key": "crash-turn", "expected_room_revision": 0},
                headers={"X-Debug-Flow-Id": "crash_flow", "X-Debug-Action-Id": "original"})
        raise AssertionError("crash point not reached")


class DiagnosticTavernCrashTests(unittest.TestCase):
    def test_partial_process_exit_retains_diagnostics_and_recovers_expired_claim(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.run([sys.executable, "-m", "tests.test_diagnostic_tavern_crash", "--child", str(root)],
                cwd=Path(__file__).parents[1], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 73, result.stderr[-2000:])
            identity = json.loads((root / "identity.json").read_text())
            room_id = identity["room_id"]
            app = application(root)
            with TestClient(app) as client:
                service = app.state.container.tavern_service
                run = service.repository.get_run_by_idempotency_key(room_id=room_id, idempotency_key="crash-turn")
                self.assertEqual([step.status.value for step in run.speaker_steps], ["completed", "generating"])
                previous = [message.model_dump(mode="json") for message in service.repository.list_run_messages(run.id)]
                self.assertEqual(len(previous), 1)
                binding = service.repository.require_harness_operation(run.id)
                old = [item["event"] for item in app.state.diagnostics.query(0, 100, {"action_id": "original"})]
                self.assertTrue(old)
                self.assertLess(len(old), 100)
                self.assertFalse(any(event["name"] == "request_finished" for event in old))
                self.assertEqual({event["harness"]["operation_id"] for event in old if event.get("harness")}, {binding.harness_operation_id})
                # Advance only this abandoned lease; no wall-clock sleep or
                # production lease duration changes are required.
                with app.state.container.database.engine.begin() as connection:
                    connection.execute(text("UPDATE tavern_run_steps SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE run_id=:run_id AND status='generating'"), {"run_id": run.id})
                recovered = client.post(f"/tavern/rooms/{room_id}/runs/{run.id}/resume",
                    headers={"X-Debug-Flow-Id": "crash_flow", "X-Debug-Action-Id": "recover"})
                self.assertEqual(recovered.status_code, 200, recovered.text)
                self.assertEqual(recovered.json()["run"]["status"], "completed")
                self.assertEqual(len(service.model_provider.calls), 1)
                self.assertEqual(recovered.json()["run"]["speaker_steps"][1]["claim_count"], 2)
                messages = service.repository.list_run_messages(run.id)
                self.assertEqual(len(messages), 2)
                self.assertEqual(messages[0].model_dump(mode="json"), previous[0])
                self.assertEqual(service.repository.require_harness_operation(run.id), binding)
                app.state.diagnostics.queue.join()
                new = [item["event"] for item in app.state.diagnostics.query(0, 100, {"action_id": "recover"})]
                self.assertTrue(new)
                self.assertLess(len(new), 100)
                self.assertTrue(all(event["request_id"] == recovered.headers["x-request-id"] and event["flow_id"] == "crash_flow" for event in new))
                self.assertEqual({event["harness"]["operation_id"] for event in new if event.get("harness")}, {binding.harness_operation_id})
                from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
                canonical = HarnessRuntimeRepository(app.state.container.database).list_operation_traces(binding.harness_operation_id)
                self.assertTrue({event["harness"]["trace_id"] for event in old + new if event.get("harness") and event["harness"]["trace_id"]}.issubset({trace.trace_id for trace in canonical}))
                resource_messages = [event["resource"] for event in new if (event.get("resource") or {}).get("resource_type") == "tavern_message"]
                expected = [recovered.json()["input_message"], *recovered.json()["generated_messages"]]
                self.assertEqual({item["resource_id"]: item["sequence"] for item in resource_messages}, {item["id"]: item["sequence"] for item in expected})
                self.assertTrue({event["request_id"] for event in old}.isdisjoint({event["request_id"] for event in new}))
                for secret in ("PRIVATE_CRASH_ROOM", "PRIVATE_CRASH_MESSAGE"):
                    self.assertNotIn(secret, json.dumps(old + new))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child(Path(sys.argv[2]))
    else:
        unittest.main()
