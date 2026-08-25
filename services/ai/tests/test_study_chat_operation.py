import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
from tempfile import TemporaryDirectory

from app.models.study_chat_operation import (
    StudyChatOperationRequestPayload,
    StudyChatOperationStatus,
)
from app.models.study_question import (
    StudyQuestionProposalV1,
    project_study_question_proposal,
)
from app.persistence.database import Database
from app.persistence.study_chat_operation_repository import (
    StudyChatOperationAlreadyActive,
    StudyChatOperationAdmissionRace,
    StudyChatOperationRepository,
    StudyChatOperationRequestMismatch,
)
from app.persistence.models import StudyChatOperationRow, StudyQuestionAttemptRow
from app.persistence.study_session_repository import StudySessionRepository
from app.models.domain import (
    SceneProfileRecord,
    SessionFollowUpRecord,
    StudyChatResult,
    StudySessionRecord,
)
from app.models.api import (
    StudyChatExchangeResponse,
    StudyChatOperationReceiptResponse,
)
from app.models.study_chat_operation import StudyChatOperationRecord
from app.services.study_chat_preflight import (
    StudyChatPreflightError,
    validate_study_chat_preclaim,
)
from pydantic import ValidationError


class StudyChatOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        self.database.create_schema()
        self.sessions = StudySessionRepository(self.database)
        self.operations = StudyChatOperationRepository(self.database)
        self.sessions.create(
            StudySessionRecord(
                id="session-operation",
                document_id="doc",
                persona_id="persona",
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

    def payload(self, message: str = "hello") -> StudyChatOperationRequestPayload:
        return StudyChatOperationRequestPayload(
            message=message,
            message_kind="learner",
            follow_up_id="",
            hidden_message_prefix="",
            expected_session_revision=0,
            attachments=[],
        )

    def test_same_request_replays_without_second_claim(self) -> None:
        admitted = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-0001",
            request_payload=self.payload(),
        )
        replay = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-0001",
            request_payload=self.payload(),
        )
        self.assertEqual(replay.operation_id, admitted.operation_id)
        running, claimed = self.operations.claim(
            operation_id=admitted.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        replayed, claimed_again = self.operations.claim(
            operation_id=admitted.operation_id,
            timeout_seconds=30,
        )
        self.assertFalse(claimed_again)
        self.assertEqual(replayed.execution_token, running.execution_token)

    def test_same_key_different_payload_is_rejected(self) -> None:
        self.operations.admit(
            session_id="session-operation",
            client_request_id="request-0002",
            request_payload=self.payload(),
        )
        with self.assertRaises(StudyChatOperationRequestMismatch):
            self.operations.admit(
                session_id="session-operation",
                client_request_id="request-0002",
                request_payload=self.payload("changed"),
            )

    def test_not_committed_is_safe_only_before_claim(self) -> None:
        operation = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-0003",
            request_payload=self.payload(),
        )
        terminal = self.operations.mark_not_committed(
            operation_id=operation.operation_id,
            error_code="study_chat_input_not_committed",
        )
        receipt = self.operations.receipt(terminal)
        self.assertEqual(receipt.status, StudyChatOperationStatus.NOT_COMMITTED)
        self.assertTrue(receipt.safe_to_retry)

        invalid = terminal.model_dump(mode="json")
        invalid.update(
            claim_count=1,
            execution_token="token",
            execution_started_at="2026-08-12T00:00:01+00:00",
        )
        with self.assertRaises(ValidationError):
            StudyChatOperationRecord.model_validate(invalid)

    def test_provider_started_uncertain_operation_never_reclaims_or_retries(self) -> None:
        operation = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-provider-uncertain-0001",
            request_payload=self.payload(),
        )
        running, claimed = self.operations.claim(
            operation_id=operation.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        self.operations.mark_provider_started(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
        )
        uncertain = self.operations.mark_uncertain(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
            error_code="study_provider_read_back_unsupported",
        )
        receipt = self.operations.receipt(uncertain)
        self.assertEqual(receipt.status, StudyChatOperationStatus.UNCERTAIN)
        self.assertFalse(receipt.safe_to_retry)
        replay = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-provider-uncertain-0001",
            request_payload=self.payload(),
        )
        self.assertEqual(replay.operation_id, operation.operation_id)
        self.assertEqual(replay.status, StudyChatOperationStatus.UNCERTAIN)
        _, claimed_again = self.operations.claim(
            operation_id=operation.operation_id,
            timeout_seconds=30,
        )
        self.assertFalse(claimed_again)

    def test_concurrent_admission_allows_exactly_one_active_operation(self) -> None:
        worker_count = 4
        barrier = Barrier(worker_count)

        def admit(index: int):
            barrier.wait(timeout=5)
            try:
                return self.operations.admit(
                    session_id="session-operation",
                    client_request_id=f"request-concurrent-{index:04d}",
                    request_payload=self.payload(),
                )
            except (StudyChatOperationAlreadyActive, StudyChatOperationAdmissionRace):
                return None

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            results = list(executor.map(admit, range(worker_count)))
        admitted = [item for item in results if item is not None]
        self.assertEqual(len(admitted), 1)
        with self.database.session() as db_session:
            rows = db_session.query(StudyChatOperationRow).all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].active_slot, 1)

    def test_expired_running_operation_becomes_uncertain_and_cannot_reclaim(self) -> None:
        operation = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-timeout-0001",
            request_payload=self.payload(),
        )
        running, claimed = self.operations.claim(
            operation_id=operation.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        with self.database.session() as db_session:
            row = db_session.get(StudyChatOperationRow, running.operation_id)
            assert row is not None
            row.execution_deadline_at = "2026-01-01T00:00:00+00:00"
        expired = self.operations.require(
            session_id="session-operation",
            client_request_id="request-timeout-0001",
        )
        self.assertEqual(expired.status, StudyChatOperationStatus.UNCERTAIN)
        self.assertEqual(expired.error_code, "study_chat_execution_deadline_expired")
        self.assertFalse(self.operations.receipt(expired).safe_to_retry)
        _, claimed_again = self.operations.claim(
            operation_id=running.operation_id,
            timeout_seconds=30,
        )
        self.assertFalse(claimed_again)

    def test_preclaim_rejects_deterministic_revision_follow_up_and_scene_conflicts(self) -> None:
        session = self.sessions.require("session-operation")
        validate_study_chat_preclaim(
            session=session,
            request_payload=self.payload(),
        )
        with self.assertRaisesRegex(
            StudyChatPreflightError,
            "study_chat_preflight_revision_changed",
        ):
            validate_study_chat_preclaim(
                session=session.model_copy(update={"revision": 1}),
                request_payload=self.payload(),
            )
        scheduled = self.payload().model_copy(
            update={
                "message_kind": "scheduled_follow_up",
                "follow_up_id": "follow-up-missing",
            }
        )
        with self.assertRaisesRegex(StudyChatPreflightError, "follow_up_not_pending"):
            validate_study_chat_preclaim(
                session=session,
                request_payload=scheduled,
            )
        pending_session = session.model_copy(
            update={
                "pending_follow_ups": [
                    SessionFollowUpRecord(
                        id="follow-up-pending",
                        status="pending",
                        due_at="2026-08-12T00:00:30+00:00",
                        hidden_message="continue",
                        created_at="2026-08-12T00:00:00+00:00",
                    )
                ]
            }
        )
        validate_study_chat_preclaim(
            session=pending_session,
            request_payload=scheduled.model_copy(
                update={"follow_up_id": "follow-up-pending"}
            ),
        )
        broken_scene = session.model_copy(
            update={
                "scene_profile": SceneProfileRecord(
                    scene_id="scene-root",
                    title="Scene",
                    summary="Bound profile without instance",
                ),
                "scene_instance_id": "",
            }
        )
        with self.assertRaisesRegex(
            StudyChatPreflightError,
            "session_scene_binding_required",
        ):
            validate_study_chat_preclaim(
                session=broken_scene,
                request_payload=self.payload(),
            )

    def test_turn_and_committed_receipt_publish_atomically(self) -> None:
        operation = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-0004",
            request_payload=self.payload(),
        )
        running, claimed = self.operations.claim(
            operation_id=operation.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        self.operations.mark_provider_started(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
        )

        result = StudyChatResult(reply="world", citations=[], character_events=[])

        def response_payload(session: StudySessionRecord) -> dict[str, object]:
            return {
                **result.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            }

        committed_session, expected_payload = self.sessions.commit_chat_operation_turn(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
            learner_message="hello",
            learner_message_kind="learner",
            learner_attachments=[],
            result=result,
            prepared_study_unit_id=None,
            completed_follow_up_id="",
            cancel_pending_follow_ups=True,
            prepared_effect_batch=None,
            build_response_payload=response_payload,
        )
        committed = self.operations.require(
            session_id="session-operation",
            client_request_id="request-0004",
        )
        self.assertEqual(committed.status, StudyChatOperationStatus.COMMITTED)
        self.assertEqual(committed.response_payload, expected_payload)
        self.assertEqual(committed.committed_session_revision, committed_session.revision)
        self.assertEqual(committed.committed_turn_id, committed_session.turns[-1].id)
        replay = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-0004",
            request_payload=self.payload(),
        )
        self.assertEqual(replay.operation_id, committed.operation_id)
        self.assertEqual(replay.status, StudyChatOperationStatus.COMMITTED)
        response = StudyChatOperationReceiptResponse.model_validate(
            self.operations.receipt(committed).model_dump(mode="json")
        )
        self.assertEqual(response.result.session.id, "session-operation")

    def test_committed_chat_receipt_survives_durable_question_attempt_patch(self) -> None:
        operation = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-question-0001",
            request_payload=self.payload(),
        )
        running, claimed = self.operations.claim(
            operation_id=operation.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        self.operations.mark_provider_started(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
        )
        question = project_study_question_proposal(
            StudyQuestionProposalV1(
                question_type="multiple_choice",
                prompt="Which vector set is a basis?",
                options=[
                    {"key": "A", "text": "Independent and spanning"},
                    {"key": "B", "text": "Dependent and non-spanning"},
                ],
                answer_key="A",
                explanation="A basis is independent and spanning.",
            )
        )
        result = StudyChatResult(
            reply="Choose the basis.",
            citations=[],
            character_events=[],
            interactive_question=question,
        )
        committed_session, expected_payload = self.sessions.commit_chat_operation_turn(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
            learner_message="hello",
            learner_message_kind="learner",
            learner_attachments=[],
            result=result,
            prepared_study_unit_id=None,
            completed_follow_up_id="",
            cancel_pending_follow_ups=True,
            prepared_effect_batch=None,
            build_response_payload=lambda session: {
                **result.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )
        attempt = self.sessions.commit_question_attempt(
            session_id=committed_session.id,
            turn_id=committed_session.turns[-1].id,
            expected_session_revision=committed_session.revision,
            client_attempt_id="client-question-attempt-0001",
            submitted_answer="A",
        )

        recovered = self.operations.require(
            session_id="session-operation",
            client_request_id="request-question-0001",
        )

        self.assertEqual(recovered.status, StudyChatOperationStatus.COMMITTED)
        self.assertEqual(recovered.response_payload, expected_payload)
        self.assertEqual(attempt.committed_revision, committed_session.revision + 1)
        current_question = (
            self.sessions.require("session-operation").turns[-1].interactive_question
        )
        self.assertIsNotNone(current_question)
        assert current_question is not None
        self.assertIsNotNone(current_question.result)
        assert current_question.result is not None
        self.assertEqual(current_question.result.attempt_id, attempt.attempt_id)
        receipt_payload = self.operations.receipt(recovered).model_dump(mode="json")
        receipt_payload["result"] = StudyChatExchangeResponse.model_validate(
            receipt_payload["result"]
        ).model_dump(mode="json")
        public_receipt = StudyChatOperationReceiptResponse.model_validate(
            receipt_payload
        ).model_dump(mode="json")
        public_question = public_receipt["result"]["session"]["turns"][-1][
            "interactive_question"
        ]
        self.assertIsNone(public_question["result"])
        self.assertNotIn("grading_spec", public_question)

        follow_up_payload = self.payload("continue").model_copy(
            update={"expected_session_revision": attempt.committed_revision}
        )
        follow_up = self.operations.admit(
            session_id="session-operation",
            client_request_id="request-after-question-0001",
            request_payload=follow_up_payload,
        )
        follow_up_running, claimed = self.operations.claim(
            operation_id=follow_up.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        self.operations.mark_provider_started(
            operation_id=follow_up_running.operation_id,
            execution_token=follow_up_running.execution_token,
        )
        follow_up_result = StudyChatResult(
            reply="Continue after the answer.",
            citations=[],
            character_events=[],
        )
        self.sessions.commit_chat_operation_turn(
            operation_id=follow_up_running.operation_id,
            execution_token=follow_up_running.execution_token,
            learner_message="continue",
            learner_message_kind="learner",
            learner_attachments=[],
            result=follow_up_result,
            prepared_study_unit_id=None,
            completed_follow_up_id="",
            cancel_pending_follow_ups=True,
            prepared_effect_batch=None,
            build_response_payload=lambda session: {
                **follow_up_result.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )
        follow_up_receipt = self.operations.receipt(
            self.operations.require(
                session_id="session-operation",
                client_request_id="request-after-question-0001",
            )
        ).model_dump(mode="json")
        follow_up_receipt["result"] = StudyChatExchangeResponse.model_validate(
            follow_up_receipt["result"]
        ).model_dump(mode="json")
        public_follow_up = StudyChatOperationReceiptResponse.model_validate(
            follow_up_receipt
        ).model_dump(mode="json")
        answered_question = public_follow_up["result"]["session"]["turns"][-2][
            "interactive_question"
        ]
        self.assertIsNotNone(answered_question["result"])
        self.assertNotIn("normalized_answer", answered_question["result"])
        self.assertNotIn("grading_spec", answered_question)

        with self.database.session() as db_session:
            attempt_row = db_session.get(StudyQuestionAttemptRow, attempt.attempt_id)
            assert attempt_row is not None
            db_session.delete(attempt_row)
        with self.assertRaisesRegex(
            ValueError,
            "study_chat_operation_question_attempt_read_back_missing",
        ):
            self.operations.require(
                session_id="session-operation",
                client_request_id="request-question-0001",
            )


if __name__ == "__main__":
    unittest.main()
