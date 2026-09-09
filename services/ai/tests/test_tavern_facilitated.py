from __future__ import annotations

from tests.support.api import ContainerTestCase, isolated_client

from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api import tavern_routes
from app.models.api import CreatePersonaRequest
from app.models.harness_operation import HarnessOperationResolutionStatus
from app.models.tavern import RetryTavernRunRequest, TavernActorReply, TavernTurnRequest
from app.persistence.database import Database
from app.persistence.models import (
    TavernMessageRow,
    TavernRoomRow,
    TavernRunRow,
    TavernRunStepRow,
)
from app.persistence.storage import StorageManager
from app.persistence.tavern_repository import TavernRepository
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider, OpenAIModelProvider
from app.services.persona import PersonaEngine
from app.services.tavern import TavernService


class SequencedTavernProvider(MockModelProvider):
    def __init__(self, *, fail_calls: set[int] | None = None) -> None:
        self.fail_calls = set(fail_calls or set())
        self.calls: list[dict[str, object]] = []

    def generate_tavern_actor_reply(self, **kwargs) -> TavernActorReply:
        call_number = len(self.calls) + 1
        self.calls.append(
            {
                "call_number": call_number,
                "persona_id": kwargs["persona"].id,
                "recent_message_ids": [item.id for item in kwargs["recent_messages"]],
                "recent_persona_ids": [
                    item.persona_id
                    for item in kwargs["recent_messages"]
                    if item.persona_id
                ],
                "user_message": kwargs["user_message"],
                "turn_kind": kwargs["turn_kind"],
                "required_target_id": kwargs["required_target_id"],
            }
        )
        if call_number in self.fail_calls:
            raise RuntimeError(f"planned_actor_failure:{call_number}")
        return TavernActorReply(
            text=f"{kwargs['persona'].name} 完成第 {call_number} 次回应。",
            mood="calm",
            action="微微颔首，望向上一位说话者",
            speech_style="克制",
            delivery_cue="停顿后自然接话",
            state_commentary="按服务端安排推进多人互动",
            addressed_participant_ids=[],
        )


class TavernFacilitatedApiTests(ContainerTestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.database = Database(f"sqlite:///{root / 'tavern-facilitated.db'}")
        self.database.create_schema()
        self.storage = StorageManager(root / "data")
        self.store = LocalJsonStore(self.database, self.storage)
        self.repository = TavernRepository(self.database)
        self.persona_engine = PersonaEngine(
            self.store,
            tavern_reference_counter=self.repository.count_persona_references,
        )
        self.personas = [self._create_persona(name) for name in ("阿澜", "柏舟", "长风")]
        self.provider = SequencedTavernProvider()
        self.service = TavernService(
            repository=self.repository,
            persona_engine=self.persona_engine,
            model_provider=self.provider,
        )
        self.container = SimpleNamespace(tavern_service=self.service)
        app = FastAPI()
        app.include_router(tavern_routes.router)
        self.client = isolated_client(app, self.container)

    def tearDown(self) -> None:
        self.client.close()
        self.store.close()
        self.temp_dir.cleanup()

    def _create_persona(self, name: str):
        return self.persona_engine.create_persona(
            CreatePersonaRequest(
                name=name,
                summary=f"{name} 会认真倾听，并保持自己的立场。",
                relationship="同行者",
                learner_address="你",
                system_prompt="保持身份稳定，不代替其他角色发言。",
                slots=[],
            )
        )

    def _create_room(self, *, opening_prompt: str = "") -> dict:
        response = self.client.post(
            "/tavern/rooms",
            json={
                "title": "群星酒馆",
                "persona_ids": [item.id for item in self.personas],
                "opening_prompt": opening_prompt,
                "idempotency_key": f"facilitated-room-{len(opening_prompt)}",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def _facilitated_payload(
        self,
        *,
        key: str,
        revision: int,
        target_ids: list[str] | None = None,
        trigger: dict[str, str] | None = None,
    ) -> dict:
        return {
            "input": trigger or {"kind": "user_message", "content": "请大家依次谈谈这个选择。"},
            "mode": "facilitated",
            "target_persona_ids": target_ids or [item.id for item in self.personas],
            "guidance": "让角色互相回应，但保留各自立场",
            "idempotency_key": key,
            "expected_room_revision": revision,
        }

    def test_facilitated_schedule_is_roster_owned_and_order_insensitive_for_replay(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        roster_ids = [item.id for item in self.personas]
        payload = self._facilitated_payload(
            key="facilitated-order-1",
            revision=0,
            target_ids=list(reversed(roster_ids)),
        )

        response = self.client.post(f"/tavern/rooms/{room_id}/turns", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["run"]["scheduled_participant_ids"], roster_ids)
        self.assertEqual(
            [item["persona_id"] for item in result["generated_messages"]],
            roster_ids,
        )
        self.assertEqual(
            [item["sequence"] for item in result["generated_messages"]],
            [2, 3, 4],
        )
        self.assertEqual([item["persona_id"] for item in self.provider.calls], roster_ids)
        operation_binding = self.repository.require_harness_operation(
            result["run"]["id"]
        )
        persisted_messages = self.repository.list_run_messages(result["run"]["id"])
        self.assertEqual(len(persisted_messages), 3)
        self.assertEqual(
            {
                item.commit_metadata.operation_id
                for item in persisted_messages
                if item.commit_metadata is not None
            },
            {operation_binding.harness_operation_id},
        )
        self.assertTrue(all(item.commit_metadata is not None for item in persisted_messages))

        replay = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json={**payload, "target_persona_ids": roster_ids[1:] + roster_ids[:1]},
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["run"]["id"], result["run"]["id"])
        self.assertEqual(len(self.provider.calls), 3)

    def test_each_actor_sees_prior_commits_and_reply_chain_is_persisted(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        response = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(key="facilitated-context-1", revision=0),
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        messages = result["generated_messages"]

        self.assertEqual(self.provider.calls[0]["recent_persona_ids"], [])
        self.assertEqual(
            self.provider.calls[1]["recent_persona_ids"],
            [self.personas[0].id],
        )
        self.assertEqual(
            self.provider.calls[2]["recent_persona_ids"],
            [self.personas[0].id, self.personas[1].id],
        )
        room = self.client.get(f"/tavern/rooms/{room_id}").json()
        user_message = room["messages"][0]
        self.assertEqual(messages[0]["reply_to_message_id"], user_message["id"])
        self.assertEqual(messages[1]["reply_to_message_id"], messages[0]["id"])
        self.assertEqual(messages[2]["reply_to_message_id"], messages[1]["id"])
        self.assertEqual(messages[1]["addressed_participant_ids"], [self.personas[0].id])
        self.assertEqual(messages[2]["addressed_participant_ids"], [self.personas[1].id])
        self.assertEqual(messages[1]["harness_trace"]["status"], "repaired")
        self.assertIn(
            "restore_scheduled_reply_target",
            messages[1]["harness_trace"]["recovery_strategy"],
        )

    def test_continue_uses_latest_anchor_without_fabricating_a_user_message(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        direct = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json={
                "input": {"kind": "user_message", "content": "先从阿澜开始。"},
                "mode": "direct",
                "target_persona_ids": [self.personas[0].id],
                "idempotency_key": "continue-direct-1",
                "expected_room_revision": 0,
            },
        )
        self.assertEqual(direct.status_code, 200, direct.text)
        anchor = direct.json()["generated_messages"][0]
        before = self.client.get(f"/tavern/rooms/{room_id}").json()

        continued = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(
                key="continue-facilitated-1",
                revision=1,
                target_ids=[self.personas[0].id, self.personas[1].id],
                trigger={"kind": "continue", "anchor_message_id": anchor["id"]},
            ),
        )
        self.assertEqual(continued.status_code, 200, continued.text)
        result = continued.json()
        self.assertEqual(result["run"]["trigger_kind"], "continue")
        self.assertIsNone(result["run"]["input_message_id"])
        self.assertIsNone(result["input_message"])
        self.assertEqual(result["generated_messages"][0]["reply_to_message_id"], anchor["id"])
        after = self.client.get(f"/tavern/rooms/{room_id}").json()
        self.assertEqual(after["message_count"], before["message_count"] + 2)
        self.assertEqual(
            [item["author_kind"] for item in after["messages"]],
            ["user", "persona", "persona", "persona"],
        )

        stale = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(
                key="continue-stale-anchor",
                revision=2,
                target_ids=[self.personas[0].id, self.personas[1].id],
                trigger={"kind": "continue", "anchor_message_id": anchor["id"]},
            ),
        )
        self.assertEqual(stale.status_code, 409)
        self.assertIn("tavern_continue_anchor_stale", stale.text)

    def test_direct_continue_allows_one_persona_to_keep_speaking(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        initial = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json={
                "input": {"kind": "user_message", "content": "请先说说你的看法。"},
                "mode": "direct",
                "target_persona_ids": [self.personas[0].id],
                "idempotency_key": "direct-continue-initial",
                "expected_room_revision": 0,
            },
        )
        self.assertEqual(initial.status_code, 200, initial.text)
        anchor = initial.json()["generated_messages"][0]
        continued = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json={
                "input": {"kind": "continue", "anchor_message_id": anchor["id"]},
                "mode": "direct",
                "target_persona_ids": [self.personas[0].id],
                "idempotency_key": "direct-continue-next",
                "expected_room_revision": 1,
            },
        )
        self.assertEqual(continued.status_code, 200, continued.text)
        self.assertIsNone(continued.json()["input_message"])
        self.assertEqual(len(continued.json()["generated_messages"]), 1)
        self.assertEqual(
            continued.json()["generated_messages"][0]["reply_to_message_id"],
            anchor["id"],
        )
        self.assertEqual(
            continued.json()["generated_messages"][0]["addressed_participant_ids"],
            [],
        )

    def test_middle_failure_persists_partial_run_and_retry_only_runs_remaining_actors(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        self.provider.fail_calls = {2}
        source_payload = self._facilitated_payload(
            key="facilitated-partial-1",
            revision=0,
        )
        failed = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=source_payload,
        )
        self.assertEqual(failed.status_code, 502, failed.text)
        error_detail = failed.json()["detail"]
        self.assertEqual(error_detail["code"], "tavern_run_failed")
        self.assertEqual(error_detail["recovery_action"], "replay_same_request")
        self.assertEqual(error_detail["current_revision"], 1)
        source = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key="facilitated-partial-1",
        )
        assert source is not None
        self.assertEqual(source.status.value, "partial")
        self.assertEqual(
            [item.status.value for item in source.speaker_steps],
            ["completed", "failed", "blocked"],
        )
        self.assertEqual(source.terminal_sequence, 2)
        room_after_failure = self.client.get(f"/tavern/rooms/{room_id}").json()
        self.assertEqual(room_after_failure["message_count"], 2)
        self.assertEqual(len(self.provider.calls), 2)

        source_replay = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=source_payload,
        )
        self.assertEqual(source_replay.status_code, 200, source_replay.text)
        self.assertEqual(source_replay.json()["run"]["status"], "partial")
        self.assertEqual(
            [item["persona_id"] for item in source_replay.json()["generated_messages"]],
            [self.personas[0].id],
        )
        self.assertEqual(len(self.provider.calls), 2)

        self.provider.fail_calls.clear()
        retried = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{source.id}/retry",
            json={
                "idempotency_key": "facilitated-retry-1",
                "expected_room_revision": 1,
            },
        )
        self.assertEqual(retried.status_code, 200, retried.text)
        child = retried.json()["run"]
        self.assertEqual(child["status"], "completed")
        self.assertIsNone(retried.json()["input_message"])
        self.assertEqual(child["parent_run_id"], source.id)
        self.assertEqual(child["root_run_id"], source.id)
        source_binding = self.repository.require_harness_operation(source.id)
        child_binding = self.repository.require_harness_operation(child["id"])
        self.assertNotEqual(
            child_binding.harness_operation_id,
            source_binding.harness_operation_id,
        )
        self.assertEqual(
            child_binding.parent_harness_operation_id,
            source_binding.harness_operation_id,
        )
        child_messages = self.repository.list_run_messages(child["id"])
        self.assertTrue(all(item.commit_metadata is not None for item in child_messages))
        self.assertEqual(
            {
                item.commit_metadata.operation_id
                for item in child_messages
                if item.commit_metadata is not None
            },
            {child_binding.harness_operation_id},
        )
        source_after_retry = self.repository.get_run(source.id)
        assert source_after_retry is not None
        failed_parent_trace = next(
            item
            for item in source_after_retry.harness_trace
            if item.status.value == "failed"
        )
        self.assertEqual(
            child_messages[0].harness_trace.parent_trace_id,
            failed_parent_trace.trace_id,
        )
        recent_window = self.client.get(f"/tavern/rooms/{room_id}/runs?limit=1")
        self.assertEqual(recent_window.status_code, 200, recent_window.text)
        self.assertEqual(
            [item["id"] for item in recent_window.json()["items"]],
            [child["id"]],
        )
        recovery = self.client.get(f"/tavern/rooms/{room_id}/run-recovery?limit=1")
        self.assertEqual(recovery.status_code, 200, recovery.text)
        chain = recovery.json()["items"][0]
        self.assertEqual(chain["run_ids"], [source.id, child["id"]])
        self.assertEqual(chain["leaf_run"]["id"], child["id"])
        self.assertEqual(chain["chain_status"], "recovered")
        self.assertEqual(chain["recovery_action"], "none")
        self.assertEqual(
            chain["completed_participant_ids"],
            [item.id for item in self.personas],
        )
        self.assertEqual(chain["unfinished_participant_ids"], [])
        self.assertEqual(
            child["scheduled_participant_ids"],
            [self.personas[1].id, self.personas[2].id],
        )
        self.assertEqual([item["persona_id"] for item in self.provider.calls], [
            self.personas[0].id,
            self.personas[1].id,
            self.personas[1].id,
            self.personas[2].id,
        ])
        generated = retried.json()["generated_messages"]
        self.assertEqual([item["sequence"] for item in generated], [3, 4])
        self.assertEqual(
            generated[0]["reply_to_message_id"],
            source.speaker_steps[0].message_id,
        )
        final_room = self.client.get(f"/tavern/rooms/{room_id}").json()
        self.assertEqual(final_room["message_count"], 4)
        self.assertEqual(
            [item["persona_id"] for item in final_room["messages"] if item["persona_id"]],
            [item.id for item in self.personas],
        )
        persisted_source = self.repository.get_run(source.id)
        assert persisted_source is not None
        self.assertEqual(persisted_source.status.value, "partial")

        replay = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{source.id}/retry",
            json={
                "idempotency_key": "facilitated-retry-1",
                "expected_room_revision": 1,
            },
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["run"]["id"], child["id"])
        self.assertEqual(len(self.provider.calls), 4)

        second_child = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{source.id}/retry",
            json={
                "idempotency_key": "facilitated-retry-2",
                "expected_room_revision": 2,
            },
        )
        self.assertEqual(second_child.status_code, 409)
        self.assertIn("tavern_retry_already_created", second_child.text)

    def test_first_actor_failure_blocks_later_steps_without_calling_them(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        self.provider.fail_calls = {1}
        payload = self._facilitated_payload(key="facilitated-first-fail", revision=0)
        response = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=payload,
        )
        self.assertEqual(response.status_code, 502, response.text)
        run = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key="facilitated-first-fail",
        )
        assert run is not None
        self.assertEqual(run.status.value, "failed")
        self.assertEqual(
            [item.status.value for item in run.speaker_steps],
            ["failed", "blocked", "blocked"],
        )
        self.assertEqual(len(self.provider.calls), 1)
        room = self.client.get(f"/tavern/rooms/{room_id}").json()
        self.assertEqual(room["message_count"], 1)
        self.assertEqual(room["messages"][0]["author_kind"], "user")

        replay = self.client.post(f"/tavern/rooms/{room_id}/turns", json=payload)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json()["run"]["id"], run.id)
        self.assertEqual(replay.json()["run"]["status"], "failed")
        self.assertEqual(replay.json()["generated_messages"], [])
        self.assertEqual(len(self.provider.calls), 1)

    def test_retry_rejects_archived_room_and_changed_context(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        self.provider.fail_calls = {2}
        failed = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(key="retry-archive-source", revision=0),
        )
        self.assertEqual(failed.status_code, 502, failed.text)
        source = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key="retry-archive-source",
        )
        assert source is not None

        archived = self.client.patch(
            f"/tavern/rooms/{room_id}",
            json={"status": "archived", "expected_revision": 1},
        )
        self.assertEqual(archived.status_code, 200, archived.text)
        rejected = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{source.id}/retry",
            json={
                "idempotency_key": "retry-archived-room",
                "expected_room_revision": 2,
            },
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("tavern_room_not_active", rejected.text)

        restored = self.client.patch(
            f"/tavern/rooms/{room_id}",
            json={"status": "active", "expected_revision": 2},
        )
        self.assertEqual(restored.status_code, 200, restored.text)
        changed = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{source.id}/retry",
            json={
                "idempotency_key": "retry-changed-context",
                "expected_room_revision": 3,
            },
        )
        self.assertEqual(changed.status_code, 409)
        self.assertIn("tavern_retry_context_changed", changed.text)

    def test_context_failure_after_step_claim_is_terminal_not_stuck_pending(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        with patch.object(
            self.repository,
            "list_recent_messages",
            side_effect=RuntimeError("planned_context_read_failure"),
        ):
            response = self.client.post(
                f"/tavern/rooms/{room_id}/turns",
                json=self._facilitated_payload(
                    key="facilitated-context-failure",
                    revision=0,
                ),
            )
        self.assertEqual(response.status_code, 502, response.text)
        run = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key="facilitated-context-failure",
        )
        assert run is not None
        self.assertEqual(run.status.value, "failed")
        self.assertEqual(
            [item.status.value for item in run.speaker_steps],
            ["failed", "blocked", "blocked"],
        )
        self.assertEqual(run.speaker_steps[0].harness_trace.stage, "context_load")

    def test_pending_run_after_begin_crash_resumes_after_service_restart(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="takeover-begin-crash", revision=0)
        )
        with patch.object(self.service, "_execute_run", side_effect=SystemExit("crash")):
            with self.assertRaises(SystemExit):
                self.service.run_turn(room_id=room_id, payload=payload)

        abandoned = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        assert abandoned is not None
        admitted_binding = self.repository.require_harness_operation(abandoned.id)
        self.assertEqual(abandoned.status.value, "pending")
        self.assertEqual([step.status.value for step in abandoned.speaker_steps], ["pending"] * 3)

        restarted = TavernService(
            repository=self.repository,
            persona_engine=self.persona_engine,
            model_provider=self.provider,
        )
        self.container.tavern_service = restarted
        response = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{abandoned.id}/resume"
        )
        self.assertEqual(response.status_code, 200, response.text)
        recovered = response.json()
        self.assertEqual(recovered["run"]["status"], "completed")
        self.assertEqual(len(recovered["generated_messages"]), 3)
        restarted_binding = TavernRepository(
            self.database
        ).require_harness_operation(abandoned.id)
        self.assertEqual(restarted_binding, admitted_binding)
        self.assertEqual(
            {
                item.commit_metadata.operation_id
                for item in self.repository.list_run_messages(abandoned.id)
                if item.commit_metadata is not None
            },
            {admitted_binding.harness_operation_id},
        )
        room = self.repository.require_room(room_id)
        self.assertEqual(
            [item.author_kind.value for item in room.messages],
            ["user", "persona", "persona", "persona"],
        )

    def test_legacy_pending_run_fails_closed_without_provider_or_identity_fabrication(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="legacy-unbound-pending", revision=0)
        )
        with patch.object(self.service, "_execute_run", side_effect=SystemExit("crash")):
            with self.assertRaises(SystemExit):
                self.service.run_turn(room_id=room_id, payload=payload)

        abandoned = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        assert abandoned is not None
        legacy_run_id = "tavern-run-legacy-unbound-pending"
        with self.database.session() as session:
            source = session.get(TavernRunRow, abandoned.id)
            assert source is not None
            session.add(
                TavernRunRow(
                    id=legacy_run_id,
                    harness_operation_id=None,
                    room_id=source.room_id,
                    idempotency_key="legacy-unbound-pending-fixture",
                    parent_run_id=None,
                    status=source.status,
                    mode=source.mode,
                    input_message_id=source.input_message_id,
                    expected_room_revision=source.expected_room_revision,
                    error_code=source.error_code,
                    created_at=source.created_at,
                    completed_at=source.completed_at,
                    payload={**source.payload, "root_run_id": legacy_run_id},
                )
            )
            session.flush()
            for step in abandoned.speaker_steps:
                session.add(
                    TavernRunStepRow(
                        run_id=legacy_run_id,
                        step_index=step.step_index,
                        persona_id=step.persona_id,
                        participant_prompt_hash=step.participant_prompt_hash,
                        status=step.status.value,
                        message_id=None,
                        reply_to_message_id=step.reply_to_message_id,
                        error_code=step.error_code,
                        started_at=step.started_at,
                        completed_at=step.completed_at,
                        lease_owner="",
                        lease_expires_at="",
                        claim_count=step.claim_count,
                        payload={"harness_trace": None},
                    )
                )

        provider_calls_before = len(self.provider.calls)
        restarted = TavernService(
            repository=TavernRepository(self.database),
            persona_engine=self.persona_engine,
            model_provider=self.provider,
        )
        self.container.tavern_service = restarted
        response = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{legacy_run_id}/resume"
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("tavern_harness_operation_legacy_unbound", response.text)
        self.assertEqual(len(self.provider.calls), provider_calls_before)
        terminal = self.repository.get_run(legacy_run_id)
        assert terminal is not None
        self.assertEqual(terminal.status.value, "failed")
        self.assertEqual(
            [item.status.value for item in terminal.speaker_steps],
            ["failed", "blocked", "blocked"],
        )
        resolution = self.repository.resolve_harness_operation(legacy_run_id)
        self.assertEqual(
            resolution.status,
            HarnessOperationResolutionStatus.LEGACY_UNBOUND,
        )
        self.assertIsNone(resolution.binding)

    def test_expired_generating_step_takeover_skips_completed_messages(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="takeover-claim-crash", revision=0)
        )
        original_generate = self.provider.generate_tavern_actor_reply

        def crash_second_actor(**kwargs):
            reply = original_generate(**kwargs)
            if len(self.provider.calls) == 2:
                raise SystemExit("crash-after-claim")
            return reply

        with patch.object(
            self.provider,
            "generate_tavern_actor_reply",
            side_effect=crash_second_actor,
        ):
            with self.assertRaises(SystemExit):
                self.service.run_turn(room_id=room_id, payload=payload)

        abandoned = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        assert abandoned is not None
        self.assertEqual(
            [step.status.value for step in abandoned.speaker_steps],
            ["completed", "generating", "pending"],
        )
        first_message_id = abandoned.speaker_steps[0].message_id

        active_lease = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{abandoned.id}/resume"
        )
        self.assertEqual(active_lease.status_code, 409, active_lease.text)
        self.assertIn("tavern_run_in_progress", active_lease.text)
        self.assertEqual(len(self.provider.calls), 2)

        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tavern_run_steps SET lease_expires_at = ? "
                "WHERE run_id = ? AND step_index = 1",
                ("2020-01-01T00:00:00+00:00", abandoned.id),
            )

        restarted = TavernService(
            repository=self.repository,
            persona_engine=self.persona_engine,
            model_provider=self.provider,
        )
        self.container.tavern_service = restarted
        response = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{abandoned.id}/resume"
        )
        self.assertEqual(response.status_code, 200, response.text)
        recovered = response.json()
        self.assertEqual(recovered["run"]["status"], "completed")
        self.assertEqual(recovered["run"]["speaker_steps"][0]["message_id"], first_message_id)
        self.assertEqual(len(self.repository.list_run_messages(abandoned.id)), 3)
        self.assertEqual(len(self.provider.calls), 4)

    def test_legacy_generating_step_without_lease_is_immediately_takeable(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="legacy-empty-lease", revision=0)
        )
        with patch.object(self.service, "_execute_run", side_effect=SystemExit("crash")):
            with self.assertRaises(SystemExit):
                self.service.run_turn(room_id=room_id, payload=payload)
        run = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        assert run is not None
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tavern_run_steps SET status = 'generating', lease_owner = '', "
                "lease_expires_at = '', claim_count = 0 WHERE run_id = ? AND step_index = 0",
                (run.id,),
            )

        response = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{run.id}/resume"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["run"]["status"], "completed")
        self.assertEqual(response.json()["run"]["speaker_steps"][0]["claim_count"], 1)

    def test_terminal_resume_replays_and_terminal_cancel_conflicts(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        completed = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(key="terminal-completed", revision=0),
        )
        self.assertEqual(completed.status_code, 200, completed.text)
        completed_run = completed.json()["run"]
        resumed = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{completed_run['id']}/resume"
        )
        self.assertEqual(resumed.status_code, 200, resumed.text)
        self.assertEqual(resumed.json()["run"]["id"], completed_run["id"])
        rejected_cancel = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{completed_run['id']}/cancel"
        )
        self.assertEqual(rejected_cancel.status_code, 409, rejected_cancel.text)
        cancel_detail = rejected_cancel.json()["detail"]
        self.assertEqual(cancel_detail["code"], "tavern_run_not_cancelable")
        self.assertEqual(cancel_detail["run_id"], completed_run["id"])

        self.provider.fail_calls = {len(self.provider.calls) + 2}
        partial = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(key="terminal-partial", revision=1),
        )
        self.assertEqual(partial.status_code, 502, partial.text)
        partial_run = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key="terminal-partial",
        )
        assert partial_run is not None
        messages_before = [item.id for item in self.repository.list_run_messages(partial_run.id)]
        resumed_partial = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{partial_run.id}/resume"
        )
        self.assertEqual(resumed_partial.status_code, 200, resumed_partial.text)
        self.assertEqual(resumed_partial.json()["run"]["status"], "partial")
        rejected_partial_cancel = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{partial_run.id}/cancel"
        )
        self.assertEqual(rejected_partial_cancel.status_code, 409)
        self.assertEqual(
            [item.id for item in self.repository.list_run_messages(partial_run.id)],
            messages_before,
        )

    def test_cancel_during_generation_returns_conflict_to_original_worker(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="cancel-live-worker", revision=0)
        )
        generation_started = Event()
        release_generation = Event()
        original_generate = self.provider.generate_tavern_actor_reply

        def wait_for_cancel(**kwargs):
            generation_started.set()
            if not release_generation.wait(timeout=3):
                raise RuntimeError("cancel_test_release_timeout")
            return original_generate(**kwargs)

        with patch.object(
            self.provider,
            "generate_tavern_actor_reply",
            side_effect=wait_for_cancel,
        ):
            with ThreadPoolExecutor(max_workers=1) as executor:
                worker = executor.submit(
                    self.service.run_turn,
                    room_id=room_id,
                    payload=payload,
                )
                self.assertTrue(generation_started.wait(timeout=3))
                run = self.repository.get_run_by_idempotency_key(
                    room_id=room_id,
                    idempotency_key=payload.idempotency_key,
                )
                assert run is not None
                canceled = self.client.post(
                    f"/tavern/rooms/{room_id}/runs/{run.id}/cancel"
                )
                self.assertEqual(canceled.status_code, 200, canceled.text)
                release_generation.set()
                with self.assertRaises(HTTPException) as context:
                    worker.result(timeout=3)

        self.assertEqual(context.exception.status_code, 409)
        self.assertIn("tavern_run_canceled", str(context.exception.detail))
        self.assertEqual(self.repository.list_run_messages(run.id), [])
        persisted = self.repository.require_room(room_id)
        self.assertEqual(
            [item.author_kind.value for item in persisted.messages],
            ["user"],
        )
        canceled_run = self.repository.get_run(run.id)
        assert canceled_run is not None
        canceled_trace = canceled_run.speaker_steps[0].harness_trace
        self.assertIsNotNone(canceled_trace)
        assert canceled_trace is not None
        self.assertEqual(canceled_trace.trace_schema_version, "harness-trace-v3")
        self.assertEqual(canceled_trace.status.value, "failed")
        self.assertEqual(
            canceled_trace.commit_evidence.status.value,
            "not_committed",
        )

        repeated = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{run.id}/cancel"
        )
        self.assertEqual(repeated.status_code, 200, repeated.text)
        self.assertEqual(repeated.json()["run"]["status"], "canceled")

    def test_active_heartbeat_prevents_false_takeover_past_original_lease(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="heartbeat-live-worker", revision=0)
        )
        generation_started = Event()
        release_generation = Event()
        original_generate = self.provider.generate_tavern_actor_reply

        def wait_past_lease(**kwargs):
            generation_started.set()
            if not release_generation.wait(timeout=5):
                raise RuntimeError("heartbeat_test_release_timeout")
            return original_generate(**kwargs)

        heartbeat_service = TavernService(
            repository=self.repository,
            persona_engine=self.persona_engine,
            model_provider=self.provider,
            step_lease_seconds=2,
        )
        self.container.tavern_service = heartbeat_service
        with patch.object(
            self.provider,
            "generate_tavern_actor_reply",
            side_effect=wait_past_lease,
        ):
            with ThreadPoolExecutor(max_workers=1) as executor:
                worker = executor.submit(
                    heartbeat_service.run_turn,
                    room_id=room_id,
                    payload=payload,
                )
                self.assertTrue(generation_started.wait(timeout=3))
                run = self.repository.get_run_by_idempotency_key(
                    room_id=room_id,
                    idempotency_key=payload.idempotency_key,
                )
                assert run is not None
                time.sleep(2.4)
                takeover = self.client.post(
                    f"/tavern/rooms/{room_id}/runs/{run.id}/resume"
                )
                self.assertEqual(takeover.status_code, 409, takeover.text)
                self.assertIn("tavern_run_in_progress", takeover.text)
                self.assertEqual(len(self.provider.calls), 0)
                release_generation.set()
                completed = worker.result(timeout=3)

        self.assertEqual(completed.run.status.value, "completed")
        persisted = self.repository.get_run(run.id)
        assert persisted is not None
        self.assertEqual(persisted.speaker_steps[0].claim_count, 1)

    def test_expired_step_claim_budget_becomes_durable_failure(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="lease-claims-exhausted", revision=0)
        )
        with patch.object(self.service, "_execute_run", side_effect=SystemExit("crash")):
            with self.assertRaises(SystemExit):
                self.service.run_turn(room_id=room_id, payload=payload)
        run = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        assert run is not None
        actor = self.repository.require_room(room_id).participants[0]
        trace = self.service.actor_harness.build_lease_exhaustion_trace(
            actor=actor,
            policy=self.repository.require_room(room_id).room.harness_policy,
            claim_count=2,
            max_claims=2,
        )
        for claim_number in range(2):
            self.repository.claim_step(
                run_id=run.id,
                step_index=0,
                lease_owner=f"abandoned-worker-{claim_number}",
                lease_seconds=120,
                max_claims=2,
                exhaustion_trace=trace,
            )
            with self.database.engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE tavern_run_steps SET lease_expires_at = ? "
                    "WHERE run_id = ? AND step_index = 0",
                    ("2020-01-01T00:00:00.000000+00:00", run.id),
                )

        bounded_service = TavernService(
            repository=self.repository,
            persona_engine=self.persona_engine,
            model_provider=self.provider,
            max_step_claims=2,
        )
        self.container.tavern_service = bounded_service
        response = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{run.id}/resume"
        )
        self.assertEqual(response.status_code, 200, response.text)
        terminal = response.json()["run"]
        self.assertEqual(terminal["status"], "failed")
        self.assertEqual(terminal["error_code"], "tavern_run_claims_exhausted")
        self.assertEqual(terminal["speaker_steps"][0]["status"], "failed")
        self.assertEqual(terminal["speaker_steps"][0]["claim_count"], 2)
        self.assertEqual(
            terminal["speaker_steps"][0]["harness_trace"]["stage"],
            "lease_recovery",
        )
        self.assertEqual(len(self.provider.calls), 0)

    def test_cancel_wins_cas_against_original_worker_commit(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        payload = TavernTurnRequest.model_validate(
            self._facilitated_payload(key="cancel-cas-race", revision=0)
        )
        with patch.object(self.service, "_execute_run", side_effect=SystemExit("crash")):
            with self.assertRaises(SystemExit):
                self.service.run_turn(room_id=room_id, payload=payload)
        run = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        )
        assert run is not None
        step = self.repository.claim_step(
            run_id=run.id,
            step_index=0,
            lease_owner="original-worker",
            lease_seconds=120,
            max_claims=3,
            exhaustion_trace=self.service.actor_harness.build_lease_exhaustion_trace(
                actor=self.repository.require_room(room_id).participants[0],
                policy=self.repository.require_room(room_id).room.harness_policy,
                claim_count=3,
                max_claims=3,
            ),
        )
        canceled = self.client.post(f"/tavern/rooms/{room_id}/runs/{run.id}/cancel")
        self.assertEqual(canceled.status_code, 200, canceled.text)
        self.assertEqual(canceled.json()["run"]["status"], "canceled")
        self.assertEqual(
            [item["status"] for item in canceled.json()["run"]["speaker_steps"]],
            ["canceled", "canceled", "canceled"],
        )
        message = self.service._generate_actor_message(
            run=run,
            actor=self.repository.require_room(room_id).participants[0],
            detail=self.repository.require_room(room_id),
            recent_messages=[],
            input_content="请大家依次谈谈这个选择。",
            required_target_id="",
        )
        with self.assertRaisesRegex(Exception, "lease_lost|canceled"):
            self.repository.complete_step(
                run_id=run.id,
                step_index=step.step_index,
                message=message,
                completed_at="2026-08-12T00:01:00+00:00",
                finalize_run=False,
                lease_owner="original-worker",
                claim_count=step.claim_count,
            )
        self.assertEqual(self.repository.list_run_messages(run.id), [])

    def test_retry_context_digest_detects_prompt_hash_tampering_without_revision_change(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        self.provider.fail_calls = {2}
        failed = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(key="retry-digest-source", revision=0),
        )
        self.assertEqual(failed.status_code, 502, failed.text)
        source = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key="retry-digest-source",
        )
        assert source is not None
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tavern_participants SET prompt_hash = ? "
                "WHERE room_id = ? AND persona_id = ?",
                ("tampered-prompt-hash", room_id, self.personas[1].id),
            )

        rejected = self.client.post(
            f"/tavern/rooms/{room_id}/runs/{source.id}/retry",
            json={
                "idempotency_key": "retry-digest-rejected",
                "expected_room_revision": 1,
            },
        )
        self.assertEqual(rejected.status_code, 409)
        self.assertIn("tavern_retry_context_changed", rejected.text)

    def test_tail_and_before_cursors_restore_latest_transcript_page(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        response = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(key="facilitated-tail-page", revision=0),
        )
        self.assertEqual(response.status_code, 200, response.text)

        tail = self.client.get(
            f"/tavern/rooms/{room_id}",
            params={"tail": True, "limit": 2},
        )
        self.assertEqual(tail.status_code, 200, tail.text)
        self.assertEqual(
            [item["sequence"] for item in tail.json()["messages"]],
            [3, 4],
        )
        self.assertEqual(tail.json()["next_before_sequence"], 3)
        self.assertIsNone(tail.json()["next_after_sequence"])

        previous = self.client.get(
            f"/tavern/rooms/{room_id}",
            params={"before_sequence": 3, "limit": 2},
        )
        self.assertEqual(previous.status_code, 200, previous.text)
        self.assertEqual(
            [item["sequence"] for item in previous.json()["messages"]],
            [1, 2],
        )
        self.assertIsNone(previous.json()["next_before_sequence"])

        conflict = self.client.get(
            f"/tavern/rooms/{room_id}",
            params={"tail": True, "after_sequence": 1},
        )
        self.assertEqual(conflict.status_code, 400)
        self.assertIn("tavern_message_cursor_conflict", conflict.text)

    def test_cursors_cover_transcripts_larger_than_the_page_limit(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        with self.database.session() as session:
            session.add_all(
                TavernMessageRow(
                    id=f"long-transcript-{sequence}",
                    room_id=room_id,
                    sequence=sequence,
                    author_kind="system",
                    content=f"历史消息 {sequence}",
                    created_at="2026-08-12T00:00:00+00:00",
                    payload={},
                )
                for sequence in range(1, 206)
            )
            room = session.get(TavernRoomRow, room_id)
            assert room is not None
            room.last_sequence = 205

        first = self.client.get(f"/tavern/rooms/{room_id}")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["message_count"], 205)
        self.assertEqual(
            [item["sequence"] for item in first.json()["messages"]],
            list(range(1, 201)),
        )
        self.assertEqual(first.json()["next_after_sequence"], 200)

        forward_tail = self.client.get(
            f"/tavern/rooms/{room_id}",
            params={"after_sequence": 200},
        )
        self.assertEqual(forward_tail.status_code, 200, forward_tail.text)
        self.assertEqual(
            [item["sequence"] for item in forward_tail.json()["messages"]],
            list(range(201, 206)),
        )
        self.assertIsNone(forward_tail.json()["next_after_sequence"])

        latest = self.client.get(
            f"/tavern/rooms/{room_id}",
            params={"tail": True},
        )
        self.assertEqual(latest.status_code, 200, latest.text)
        self.assertEqual(
            [item["sequence"] for item in latest.json()["messages"]],
            list(range(6, 206)),
        )
        self.assertEqual(latest.json()["next_before_sequence"], 6)

        oldest = self.client.get(
            f"/tavern/rooms/{room_id}",
            params={"before_sequence": 6},
        )
        self.assertEqual(oldest.status_code, 200, oldest.text)
        self.assertEqual(
            [item["sequence"] for item in oldest.json()["messages"]],
            list(range(1, 6)),
        )
        self.assertIsNone(oldest.json()["next_before_sequence"])

    def test_concurrent_retry_creates_exactly_one_child_run(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        self.provider.fail_calls = {2}
        failed = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(key="concurrent-retry-source", revision=0),
        )
        self.assertEqual(failed.status_code, 502, failed.text)
        source = self.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key="concurrent-retry-source",
        )
        assert source is not None
        self.provider.fail_calls.clear()
        barrier = Barrier(2)

        def retry(index: int):
            barrier.wait()
            return self.service.retry_run(
                room_id=room_id,
                source_run_id=source.id,
                payload=RetryTavernRunRequest(
                    idempotency_key=f"concurrent-retry-{index}",
                    expected_room_revision=1,
                ),
            )

        outcomes = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(retry, index) for index in range(2)]
            for future in futures:
                try:
                    outcomes.append(("ok", future.result()))
                except HTTPException as exc:
                    outcomes.append(("conflict", exc))

        self.assertEqual([item[0] for item in outcomes].count("ok"), 1)
        self.assertEqual([item[0] for item in outcomes].count("conflict"), 1)
        children = [
            item
            for item in self.repository.list_runs(room_id)
            if item.parent_run_id == source.id
        ]
        self.assertEqual(len(children), 1)
        self.assertEqual(children[0].status.value, "completed")

    def test_model_recovery_state_is_isolated_between_facilitated_actors(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://example.invalid/v1",
            plan_model="test-model",
            chat_model="test-model",
        )
        self.service.model_provider = provider
        invalid_payload = {
            "choices": [
                {"finish_reason": "stop", "message": {"content": '{"text":"缺字段"}'}}
            ]
        }

        def valid_payload(text: str, target_ids: list[str]) -> dict:
            targets = ",".join(f'"{item}"' for item in target_ids)
            return {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": (
                                f'{{"text":"{text}","mood":"calm","action":"点头",'
                                '"speech_style":"warm","delivery_cue":"自然回应",'
                                '"state_commentary":"保持身份",'
                                f'"addressed_participant_ids":[{targets}]}}'
                            )
                        },
                    }
                ]
            }

        with patch.object(
            provider,
            "_request_openai_chat_completion",
            side_effect=[
                (invalid_payload, 1),
                (valid_payload("第一位修复后回应。", []), 1),
                (valid_payload("第二位直接回应。", [self.personas[0].id]), 1),
            ],
        ):
            response = self.client.post(
                f"/tavern/rooms/{room_id}/turns",
                json=self._facilitated_payload(
                    key="facilitated-recovery-isolation",
                    revision=0,
                    target_ids=[self.personas[0].id, self.personas[1].id],
                ),
            )

        self.assertEqual(response.status_code, 200, response.text)
        traces = [
            item["harness_trace"] for item in response.json()["generated_messages"]
        ]
        self.assertEqual(traces[0]["status"], "repaired")
        self.assertIn("retry_strict_actor_reply", traces[0]["recovery_strategy"])
        self.assertEqual(traces[1]["status"], "passed")
        self.assertEqual(traces[1]["recovery_strategy"], "none")

    def test_trigger_and_target_shape_validation_is_explicit(self) -> None:
        created = self._create_room()
        room_id = created["room"]["id"]
        direct_continue = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json={
                "input": {"kind": "continue", "anchor_message_id": "missing-message"},
                "mode": "direct",
                "target_persona_ids": [self.personas[0].id],
                "idempotency_key": "invalid-direct-continue",
                "expected_room_revision": 0,
            },
        )
        self.assertEqual(direct_continue.status_code, 409)
        self.assertIn("tavern_continue_anchor_stale", direct_continue.text)

        one_target = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(
                key="invalid-one-target",
                revision=0,
                target_ids=[self.personas[0].id],
            ),
        )
        self.assertEqual(one_target.status_code, 422)

        duplicate_target = self.client.post(
            f"/tavern/rooms/{room_id}/turns",
            json=self._facilitated_payload(
                key="invalid-duplicate-target",
                revision=0,
                target_ids=[self.personas[0].id, self.personas[0].id],
            ),
        )
        self.assertEqual(duplicate_target.status_code, 422)


if __name__ == "__main__":
    unittest.main()
