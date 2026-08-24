from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import unittest
from unittest.mock import patch

from app.models.domain import LearningPlanRecord, StudyChatResult, StudySessionRecord
from app.models.api import StudyChatExchangeResponse
from app.models.study_chat_effect import (
    STUDY_AFFINITY_DELTA_ADAPTER,
    STUDY_AFFINITY_DELTA_PROPOSAL_CONTRACT,
    StudyAffinityDeltaEffectProposalV1,
    StudyMemoryUpsertEffectProposalV1,
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
)
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from app.models.study_chat_operation import study_chat_response_digest
from app.persistence.database import Database
from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
from app.persistence.models import LearningPlanRow, StudyChatOperationRow
from app.persistence.study_session_repository import StudySessionRepository
from app.services.study_chat_effects import (
    StudyChatEffectCollector,
    commit_study_chat_effects,
)


class StudyChatEffectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        self.database.create_schema()
        self.sessions = StudySessionRepository(self.database)
        self.operations = StudyChatOperationRepository(self.database)
        plan = LearningPlanRecord(
            id="plan-effect",
            document_id="doc",
            persona_id="persona",
            course_title="Course",
            objective="Learn",
            overview="Overview",
            today_tasks=[],
            schedule=[
                {
                    "id": "schedule-1",
                    "unit_id": "unit",
                    "title": "Unit",
                    "focus": "Focus",
                    "activity_type": "study",
                }
            ],
            created_at="2026-08-12T00:00:00+00:00",
        )
        with self.database.session() as db_session:
            db_session.add(
                LearningPlanRow(
                    id=plan.id,
                    document_id=plan.document_id,
                    persona_id=plan.persona_id,
                    creation_mode=plan.creation_mode,
                    course_title=plan.course_title,
                    created_at=plan.created_at,
                    payload=plan.model_dump(mode="json"),
                )
            )
        self.sessions.create(
            StudySessionRecord(
                id="session-effect",
                document_id="doc",
                persona_id="persona",
                plan_id="plan-effect",
                study_unit_id="unit",
                status="active",
                turns=[],
                revision=0,
                last_turn_sequence=0,
                created_at="2026-08-12T00:00:00+00:00",
                updated_at="2026-08-12T00:00:00+00:00",
            )
        )

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def test_prepared_confirmation_has_no_business_write_until_final_commit(self) -> None:
        running = self._running_operation("request-effect-0001")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids={"schedule-1"},
        )
        prepared = collector.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS,
                schedule_ids=["schedule-1"],
                schedule_status="completed",
                note="done",
            )
        )
        self.assertEqual(prepared.slot, 0)
        self.assertEqual(self.sessions.require("session-effect").plan_confirmations, [])

        result = StudyChatResult(reply="saved", citations=[], character_events=[])
        committed, _ = self.sessions.commit_chat_operation_turn(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
            learner_message="hello",
            learner_message_kind="learner",
            learner_attachments=[],
            result=result,
            prepared_study_unit_id=None,
            completed_follow_up_id="",
            cancel_pending_follow_ups=True,
            prepared_effect_batch=collector.prepared_batch(),
            build_response_payload=lambda session: {
                **result.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )
        self.assertEqual(len(committed.plan_confirmations), 1)
        confirmation = committed.plan_confirmations[0]
        self.assertEqual(confirmation.action_type, "update_plan_progress")
        self.assertEqual(confirmation.status, "pending")
        self.assertEqual(committed.turns[-1].assistant_reply, "saved")

        replayed = self.operations.admit(
            session_id="session-effect",
            client_request_id="request-effect-0001",
            request_payload=self._payload(),
        )
        self.assertEqual(replayed.status.value, "committed")
        self.assertEqual(
            len(self.sessions.require("session-effect").plan_confirmations),
            1,
        )

    def test_fenced_final_commit_leaves_prepared_effect_unwritten(self) -> None:
        running = self._running_operation("request-effect-0002")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids=set(),
        )
        collector.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
                course_title="New course title",
            )
        )
        collector.prepare_memory_upsert(
            StudyMemoryUpsertEffectProposalV1(key="focus", content="algebra")
        )
        collector.prepare_affinity_delta(
            StudyAffinityDeltaEffectProposalV1(delta=5, reason="progress")
        )
        with self.assertRaisesRegex(RuntimeError, "study_session_operation_fenced"):
            self.sessions.commit_chat_operation_turn(
                operation_id=running.operation_id,
                execution_token="wrong-token",
                learner_message="hello",
                learner_message_kind="learner",
                learner_attachments=[],
                result=StudyChatResult(reply="ignored", citations=[], character_events=[]),
                prepared_study_unit_id=None,
                completed_follow_up_id="",
                cancel_pending_follow_ups=True,
                prepared_effect_batch=collector.prepared_batch(),
                build_response_payload=lambda session: {"session": session.model_dump(mode="json")},
            )
        record = self.sessions.require("session-effect")
        self.assertEqual(record.plan_confirmations, [])
        self.assertEqual(record.session_memory, [])
        self.assertEqual(record.affinity_state.events, [])
        self.assertEqual(record.turns, [])

    def test_mixed_batch_uses_global_slots_overlay_order_and_clamp(self) -> None:
        running = self._running_operation("request-effect-mixed-0001")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids={"schedule-1"},
        )
        first_memory = collector.prepare_memory_upsert(
            StudyMemoryUpsertEffectProposalV1(key="focus", content="first")
        )
        affinity_effects = [
            collector.prepare_affinity_delta(
                StudyAffinityDeltaEffectProposalV1(delta=20, reason=f"step-{index}")
            )
            for index in range(6)
        ]
        final_memory = collector.prepare_memory_upsert(
            StudyMemoryUpsertEffectProposalV1(key="focus", content="final")
        )
        confirmation = collector.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS,
                schedule_ids=["schedule-1"],
                schedule_status="completed",
            )
        )
        self.assertEqual(first_memory.slot, 0)
        self.assertEqual([item.slot for item in affinity_effects], list(range(1, 7)))
        self.assertEqual(final_memory.slot, 7)
        self.assertEqual(confirmation.slot, 8)
        memory_overlay = collector.preview_session_memory([])
        self.assertEqual(memory_overlay[-1]["content"], "final")
        self.assertFalse(memory_overlay[-1]["committed"])
        affinity_overlay = collector.preview_affinity_state(
            self.sessions.require("session-effect").affinity_state
        )
        self.assertEqual(affinity_overlay["score"], 100)
        self.assertFalse(affinity_overlay["committed"])

        committed, payload = self._commit(running, collector.prepared_batch())
        self.assertEqual(committed.session_memory[0].content, "final")
        self.assertEqual(committed.affinity_state.score, 100)
        self.assertEqual(len(committed.affinity_state.events), 6)
        self.assertEqual(len(committed.plan_confirmations), 1)
        receipt = payload["_committed_effect_batch"]
        self.assertEqual(
            [item["effect_kind"] for item in receipt["effects"]],
            ["memory_upsert"] + ["affinity_delta"] * 6 + ["memory_upsert", "plan_confirmation"],
        )
        public_payload = StudyChatExchangeResponse.model_validate(payload).model_dump(
            mode="json"
        )
        self.assertNotIn("_committed_effect_batch", public_payload)

    def test_final_payload_failure_rolls_back_all_mixed_effects(self) -> None:
        running = self._running_operation("request-effect-mixed-0002")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids={"schedule-1"},
        )
        collector.prepare_memory_upsert(
            StudyMemoryUpsertEffectProposalV1(key="focus", content="pending")
        )
        collector.prepare_affinity_delta(
            StudyAffinityDeltaEffectProposalV1(delta=10, reason="pending")
        )
        with self.assertRaisesRegex(RuntimeError, "invalid_final"):
            self.sessions.commit_chat_operation_turn(
                operation_id=running.operation_id,
                execution_token=running.execution_token,
                learner_message="hello",
                learner_message_kind="learner",
                learner_attachments=[],
                result=StudyChatResult(reply="ignored", citations=[], character_events=[]),
                prepared_study_unit_id=None,
                completed_follow_up_id="",
                cancel_pending_follow_ups=True,
                prepared_effect_batch=collector.prepared_batch(),
                build_response_payload=lambda _session: (_ for _ in ()).throw(
                    RuntimeError("invalid_final")
                ),
            )
        record = self.sessions.require("session-effect")
        self.assertEqual(record.turns, [])
        self.assertEqual(record.session_memory, [])
        self.assertEqual(record.affinity_state.events, [])

    def test_adapter_failure_after_first_effect_rolls_back_transaction(self) -> None:
        running = self._running_operation("request-effect-mixed-0003")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids=set(),
        )
        collector.prepare_memory_upsert(
            StudyMemoryUpsertEffectProposalV1(key="focus", content="pending")
        )
        collector.prepare_affinity_delta(
            StudyAffinityDeltaEffectProposalV1(delta=10, reason="pending")
        )
        from app.services import study_chat_effects

        original = study_chat_effects._apply_prepared_effect
        calls = 0

        def fail_second(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("forced_adapter_failure")
            return original(**kwargs)

        with patch(
            "app.services.study_chat_effects._apply_prepared_effect",
            side_effect=fail_second,
        ):
            with self.assertRaisesRegex(RuntimeError, "forced_adapter_failure"):
                self._commit(running, collector.prepared_batch())
        record = self.sessions.require("session-effect")
        self.assertEqual(record.turns, [])
        self.assertEqual(record.session_memory, [])
        self.assertEqual(record.affinity_state.events, [])

    def test_committed_effect_receipt_tamper_fails_read_back(self) -> None:
        running = self._running_operation("request-effect-mixed-0004")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids=set(),
        )
        collector.prepare_memory_upsert(
            StudyMemoryUpsertEffectProposalV1(key="focus", content="committed")
        )
        self._commit(running, collector.prepared_batch())
        with self.database.session() as db_session:
            row = db_session.get(StudyChatOperationRow, running.operation_id)
            assert row is not None and row.response_payload is not None
            payload = deepcopy(row.response_payload)
            payload["_committed_effect_batch"]["effects"][0]["content"] = "forged"
            row.response_payload = payload
            row.response_digest = study_chat_response_digest(payload)
        with self.assertRaisesRegex(ValueError, "memory_upsert_read_back_mismatch"):
            self.operations.require(
                session_id="session-effect",
                client_request_id="request-effect-mixed-0004",
            )

    def test_final_commit_rejects_effects_from_another_operation(self) -> None:
        running = self._running_operation("request-effect-0003")
        collector = StudyChatEffectCollector(
            operation_id="study-chat-op-foreign",
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids=set(),
        )
        collector.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
                course_title="Foreign operation",
            )
        )
        with self.assertRaisesRegex(ValueError, "operation_mismatch"):
            self.sessions.commit_chat_operation_turn(
                operation_id=running.operation_id,
                execution_token=running.execution_token,
                learner_message="hello",
                learner_message_kind="learner",
                learner_attachments=[],
                result=StudyChatResult(reply="ignored", citations=[], character_events=[]),
                prepared_study_unit_id=None,
                completed_follow_up_id="",
                cancel_pending_follow_ups=True,
                prepared_effect_batch=collector.prepared_batch(),
                build_response_payload=lambda session: {"session": session.model_dump(mode="json")},
            )
        record = self.sessions.require("session-effect")
        self.assertEqual(record.plan_confirmations, [])
        self.assertEqual(record.turns, [])

    def test_prepare_rejects_schedule_outside_authoritative_plan(self) -> None:
        collector = StudyChatEffectCollector(
            operation_id="study-chat-op-schedule",
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids={"schedule-1"},
        )
        with self.assertRaisesRegex(ValueError, "schedule_target_unknown"):
            collector.prepare_plan_confirmation(
                StudyPlanConfirmationEffectProposalV1(
                    action=StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS,
                    schedule_ids=["schedule-foreign"],
                    schedule_status="completed",
                )
            )

    def test_collector_bounds_effect_count(self) -> None:
        collector = StudyChatEffectCollector(
            operation_id="study-chat-op-effect-limit",
            session_id="session-effect",
            plan_id=None,
            allowed_schedule_ids=set(),
        )
        for index in range(12):
            collector.prepare_memory_upsert(
                StudyMemoryUpsertEffectProposalV1(
                    key=f"key-{index}",
                    content="value",
                )
            )
        with self.assertRaisesRegex(ValueError, "effect_limit_exceeded"):
            collector.prepare_affinity_delta(
                StudyAffinityDeltaEffectProposalV1(delta=1)
            )

    def test_final_commit_rejects_forged_effect_identity(self) -> None:
        running = self._running_operation("request-effect-0004")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids=set(),
        )
        collector.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
                course_title="Forged identity",
            )
        )
        batch = collector.prepared_batch()
        assert batch is not None
        forged_effect = batch.effects[0].model_copy(update={"effect_id": "study-effect-forged"})
        forged_batch = batch.model_copy(update={"effects": [forged_effect]})
        with self.assertRaisesRegex(ValueError, "effect_identity_mismatch"):
            self._commit(running, forged_batch)
        self.assertEqual(self.sessions.require("session-effect").turns, [])

    def test_final_commit_rejects_forged_slot_adapter_and_contract(self) -> None:
        for suffix, update, error in (
            ("slot", {"slot": 1}, "slots_not_contiguous"),
            ("adapter", {"adapter": STUDY_AFFINITY_DELTA_ADAPTER}, "adapter_mismatch"),
            (
                "contract",
                {"proposal_contract": STUDY_AFFINITY_DELTA_PROPOSAL_CONTRACT},
                "contract_mismatch",
            ),
        ):
            with self.subTest(forgery=suffix):
                operation_id = f"study-chat-op-forge-{suffix}"
                collector = StudyChatEffectCollector(
                    operation_id=operation_id,
                    session_id="session-effect",
                    plan_id="plan-effect",
                    allowed_schedule_ids=set(),
                )
                collector.prepare_memory_upsert(
                    StudyMemoryUpsertEffectProposalV1(
                        key=f"focus-{suffix}",
                        content="pending",
                    )
                )
                batch = collector.prepared_batch()
                assert batch is not None
                forged = batch.effects[0].model_copy(update=update)
                forged_batch = batch.model_copy(update={"effects": [forged]})
                with self.assertRaisesRegex(ValueError, error):
                    commit_study_chat_effects(
                        record=self.sessions.require("session-effect").model_copy(deep=True),
                        batch=forged_batch,
                        expected_operation_id=operation_id,
                        allowed_schedule_ids=set(),
                        committed_at="2026-08-24T00:00:00+00:00",
                    )

    def test_final_commit_rejects_forged_batch_identity(self) -> None:
        running = self._running_operation("request-effect-0006")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-effect",
            allowed_schedule_ids=set(),
        )
        collector.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
                course_title="Forged batch",
            )
        )
        batch = collector.prepared_batch()
        assert batch is not None
        forged_effect = batch.effects[0].model_copy(
            update={"effect_batch_id": "study-effect-batch-forged"}
        )
        forged_batch = batch.model_copy(
            update={
                "effect_batch_id": "study-effect-batch-forged",
                "effects": [forged_effect],
            }
        )
        with self.assertRaisesRegex(ValueError, "batch_identity_mismatch"):
            self._commit(running, forged_batch)
        self.assertEqual(self.sessions.require("session-effect").turns, [])

    def test_final_commit_rejects_foreign_plan_target(self) -> None:
        running = self._running_operation("request-effect-0005")
        collector = StudyChatEffectCollector(
            operation_id=running.operation_id,
            session_id="session-effect",
            plan_id="plan-foreign",
            allowed_schedule_ids=set(),
        )
        collector.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
                course_title="Foreign plan",
            )
        )
        with self.assertRaisesRegex(ValueError, "target_mismatch"):
            self._commit(running, collector.prepared_batch())
        self.assertEqual(self.sessions.require("session-effect").turns, [])

    def _commit(self, running, prepared_effect_batch):
        result = StudyChatResult(reply="ignored", citations=[], character_events=[])
        return self.sessions.commit_chat_operation_turn(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
            learner_message="hello",
            learner_message_kind="learner",
            learner_attachments=[],
            result=result,
            prepared_study_unit_id=None,
            completed_follow_up_id="",
            cancel_pending_follow_ups=True,
            prepared_effect_batch=prepared_effect_batch,
            build_response_payload=lambda session: {
                **result.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )

    def _running_operation(self, request_id: str):
        admitted = self.operations.admit(
            session_id="session-effect",
            client_request_id=request_id,
            request_payload=self._payload(),
        )
        running, claimed = self.operations.claim(
            operation_id=admitted.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        return running

    @staticmethod
    def _payload() -> StudyChatOperationRequestPayload:
        return StudyChatOperationRequestPayload(
            message="hello",
            message_kind="learner",
            follow_up_id="",
            hidden_message_prefix="",
            expected_session_revision=0,
            attachments=[],
        )


if __name__ == "__main__":
    unittest.main()
