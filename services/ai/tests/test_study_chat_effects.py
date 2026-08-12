from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.models.domain import StudyChatResult, StudySessionRecord
from app.models.study_chat_effect import (
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
)
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from app.persistence.database import Database
from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
from app.persistence.study_session_repository import StudySessionRepository
from app.services.study_chat_effects import StudyChatEffectCollector


class StudyChatEffectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        self.database.create_schema()
        self.sessions = StudySessionRepository(self.database)
        self.operations = StudyChatOperationRepository(self.database)
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
        self.assertEqual(record.turns, [])

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
        return self.sessions.commit_chat_operation_turn(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
            learner_message="hello",
            learner_message_kind="learner",
            learner_attachments=[],
            result=StudyChatResult(reply="ignored", citations=[], character_events=[]),
            prepared_study_unit_id=None,
            completed_follow_up_id="",
            cancel_pending_follow_ups=True,
            prepared_effect_batch=prepared_effect_batch,
            build_response_payload=lambda session: {"session": session.model_dump(mode="json")},
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
