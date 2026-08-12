import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.models.study_chat_operation import (
    StudyChatOperationRequestPayload,
    StudyChatOperationStatus,
)
from app.persistence.database import Database
from app.persistence.study_chat_operation_repository import (
    StudyChatOperationRepository,
    StudyChatOperationRequestMismatch,
)
from app.persistence.study_session_repository import StudySessionRepository
from app.models.domain import StudyChatResult, StudySessionRecord
from app.models.api import StudyChatOperationReceiptResponse
from app.models.study_chat_operation import StudyChatOperationRecord
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


if __name__ == "__main__":
    unittest.main()
