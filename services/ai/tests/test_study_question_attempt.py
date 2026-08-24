from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from app.models.api import StudyQuestionAttemptRequest, StudySessionResponse
from app.models.domain import LearnerAttachmentRecord, StudyChatResult
from app.models.study_question import (
    StudyQuestionProposalV1,
    project_study_question_proposal,
)
from app.models.study_chat_operation import (
    STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION,
    StudyChatOperationRecord,
    StudyChatOperationRequestPayload,
    study_chat_request_fingerprint,
    study_chat_response_digest,
)
from app.persistence.models import StudyQuestionAttemptRow
from app.services.local_store import LocalJsonStore
from app.services.study_sessions import StudySessionService


class StudyQuestionAttemptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp_dir.name))
        self.service = StudySessionService(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _question_session(
        self,
        *,
        session_id: str,
        question_type: str = "multiple_choice",
        prompt: str = "Pick A",
        accepted_answers: list[str] | None = None,
    ):
        session = self.service.create_session(
            session_id=session_id,
            document_id=f"doc-{session_id}",
            persona_id="mentor-aurora",
            study_unit_id="unit-1",
        )
        proposal = (
            StudyQuestionProposalV1(
                question_type="multiple_choice",
                prompt=prompt,
                options=[
                    {"key": "A", "text": "First"},
                    {"key": "B", "text": "Second"},
                ],
                answer_key="A",
                explanation="A is the expected option.",
                call_back=True,
            )
            if question_type == "multiple_choice"
            else StudyQuestionProposalV1(
                question_type="fill_blank",
                prompt=prompt,
                accepted_answers=accepted_answers or ["Alpha Beta"],
                explanation="Use the normalized term.",
                call_back=True,
            )
        )
        return self.service.append_turn(
            session_id=session.id,
            learner_message="Give me a question",
            result=StudyChatResult(
                reply="Question ready",
                citations=[],
                character_events=[],
                interactive_question=project_study_question_proposal(proposal),
            ),
        )

    def test_unanswered_public_projection_never_exposes_grading_material(self) -> None:
        session = self._question_session(session_id="session-public-question")
        public = StudySessionResponse.model_validate(
            session.model_dump(mode="json")
        ).model_dump(mode="json")
        question = public["turns"][0]["interactive_question"]
        self.assertIsNone(question["result"])
        self.assertNotIn("grading_spec", question)
        self.assertNotIn("answer_key", question)
        self.assertNotIn("accepted_answers", question)
        self.assertNotIn("explanation", question)

    def test_public_turn_attachment_never_exposes_local_storage_path(self) -> None:
        session = self.service.create_session(
            session_id="session-public-attachment",
            document_id="doc-public-attachment",
            persona_id="mentor-aurora",
            study_unit_id="unit-1",
        )
        session = self.service.append_turn(
            session_id=session.id,
            learner_message="Read this file",
            learner_attachments=[
                LearnerAttachmentRecord(
                    attachment_id="attachment-public-1",
                    name="notes.txt",
                    mime_type="text/plain",
                    kind="text",
                    size_bytes=12,
                    text_excerpt="public excerpt",
                    stored_path="/private/staging/session-public-attachment/notes.txt",
                )
            ],
            result=StudyChatResult(
                reply="I read the notes.",
                citations=[],
                character_events=[],
            ),
        )

        public = StudySessionResponse.model_validate(
            session.model_dump(mode="json")
        ).model_dump(mode="json")
        attachment = public["turns"][0]["learner_attachments"][0]
        self.assertEqual(attachment["attachment_id"], "attachment-public-1")
        self.assertNotIn("stored_path", attachment)

        schema_text = str(StudySessionResponse.model_json_schema())
        self.assertNotIn("stored_path", schema_text)

    def test_legacy_question_payload_is_migrated_then_redacted(self) -> None:
        session = self._question_session(session_id="session-legacy-question")
        payload = session.model_dump(mode="json")
        payload["turns"][0]["interactive_question"] = {
            "question_type": "multiple_choice",
            "prompt": "Legacy prompt",
            "difficulty": "medium",
            "topic": "legacy",
            "options": [
                {"key": "A", "text": "First"},
                {"key": "B", "text": "Second"},
            ],
            "call_back": True,
            "answer_key": "A",
            "accepted_answers": [],
            "explanation": "Legacy private explanation",
            "submitted_answer": "",
            "is_correct": None,
            "feedback_text": "",
        }
        public = StudySessionResponse.model_validate(payload).model_dump(mode="json")
        question = public["turns"][0]["interactive_question"]
        self.assertEqual(question["schema_version"], "study-interactive-question-v2")
        self.assertIsNone(question["result"])
        self.assertNotIn("answer_key", question)
        self.assertNotIn("grading_spec", question)

    def test_historical_chat_exchange_version_remains_digest_valid(self) -> None:
        request = StudyChatOperationRequestPayload(
            message="hello",
            message_kind="learner",
            follow_up_id="",
            hidden_message_prefix="",
            expected_session_revision=0,
        )
        response_payload = {"legacy": True}
        base = {
            "operation_id": "study-chat-op-legacy",
            "session_id": "session-legacy-operation",
            "client_request_id": "client-request-legacy",
            "request_schema_version": "study-chat-request-v1",
            "fingerprint_contract_version": STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION,
            "request_fingerprint": study_chat_request_fingerprint(request),
            "request_payload": request.model_dump(mode="json"),
            "status": "committed",
            "admitted_session_revision": 0,
            "execution_token": "execution-token",
            "claim_count": 1,
            "execution_started_at": "2026-08-13T00:00:00+00:00",
            "execution_deadline_at": "2026-08-13T00:01:00+00:00",
            "committed_session_revision": 1,
            "committed_turn_id": "turn-1",
            "committed_turn_sequence": 1,
            "response_schema_version": "study-chat-exchange-v1",
            "response_payload": response_payload,
            "response_digest": study_chat_response_digest(response_payload),
            "created_at": "2026-08-13T00:00:00+00:00",
            "updated_at": "2026-08-13T00:00:01+00:00",
            "completed_at": "2026-08-13T00:00:01+00:00",
        }
        self.assertEqual(
            StudyChatOperationRecord.model_validate(base).response_schema_version,
            "study-chat-exchange-v1",
        )
        with self.assertRaises(ValidationError):
            StudyChatOperationRecord.model_validate(
                {**base, "response_schema_version": "study-chat-exchange-unknown"}
            )

    def test_request_rejects_all_client_owned_grading_fields(self) -> None:
        with self.assertRaises(ValidationError):
            StudyQuestionAttemptRequest.model_validate(
                {
                    "turn_id": "turn-1",
                    "expected_session_revision": 1,
                    "client_attempt_id": "client-attempt-1",
                    "submitted_answer": "A",
                    "is_correct": True,
                    "answer_key": "A",
                }
            )

    def test_server_grades_and_same_normalized_request_is_idempotent(self) -> None:
        session = self._question_session(
            session_id="session-fill-normalization",
            question_type="fill_blank",
            accepted_answers=["Ｆｏｏ   Bar"],
        )
        turn_id = session.turns[0].id
        committed = self.service.record_question_attempt(
            session_id=session.id,
            turn_id=turn_id,
            expected_session_revision=session.revision,
            client_attempt_id="client-attempt-normalized",
            submitted_answer="foo bar",
        )
        duplicate = self.service.record_question_attempt(
            session_id=session.id,
            turn_id=turn_id,
            expected_session_revision=session.revision,
            client_attempt_id="client-attempt-normalized",
            submitted_answer="ＦＯＯ   BAR",
        )
        self.assertTrue(committed.is_correct)
        self.assertEqual(duplicate.attempt_id, committed.attempt_id)
        self.assertEqual(
            self.service.require_session(session.id).revision,
            session.revision + 1,
        )

    def test_same_key_different_answer_and_same_turn_different_key_fail_closed(self) -> None:
        session = self._question_session(session_id="session-attempt-conflicts")
        turn_id = session.turns[0].id
        self.service.record_question_attempt(
            session_id=session.id,
            turn_id=turn_id,
            expected_session_revision=session.revision,
            client_attempt_id="client-attempt-conflict",
            submitted_answer="A",
        )
        with self.assertRaises(HTTPException) as mismatch:
            self.service.record_question_attempt(
                session_id=session.id,
                turn_id=turn_id,
                expected_session_revision=session.revision,
                client_attempt_id="client-attempt-conflict",
                submitted_answer="B",
            )
        self.assertEqual(mismatch.exception.status_code, 409)
        self.assertEqual(mismatch.exception.detail, "study_question_attempt_request_mismatch")

        with self.assertRaises(HTTPException) as replay:
            self.service.record_question_attempt(
                session_id=session.id,
                turn_id=turn_id,
                expected_session_revision=session.revision + 1,
                client_attempt_id="client-attempt-other",
                submitted_answer="A",
            )
        self.assertEqual(replay.exception.status_code, 409)
        self.assertEqual(replay.exception.detail, "study_question_attempt_turn_already_answered")

    def test_turn_identity_disambiguates_duplicate_prompts_and_cross_session_targets(self) -> None:
        session = self._question_session(
            session_id="session-duplicate-prompt",
            prompt="Same prompt",
        )
        session = self.service.append_turn(
            session_id=session.id,
            learner_message="Again",
            result=StudyChatResult(
                reply="Second question",
                citations=[],
                character_events=[],
                interactive_question=project_study_question_proposal(
                    StudyQuestionProposalV1(
                        question_type="multiple_choice",
                        prompt="Same prompt",
                        options=[
                            {"key": "A", "text": "First"},
                            {"key": "B", "text": "Second"},
                        ],
                        answer_key="B",
                    )
                ),
            ),
        )
        first_turn_id, second_turn_id = [turn.id for turn in session.turns]
        committed = self.service.record_question_attempt(
            session_id=session.id,
            turn_id=second_turn_id,
            expected_session_revision=session.revision,
            client_attempt_id="client-attempt-second-turn",
            submitted_answer="B",
        )
        self.assertTrue(committed.is_correct)
        refreshed = self.service.require_session(session.id)
        self.assertIsNone(refreshed.turns[0].interactive_question.result)
        self.assertIsNotNone(refreshed.turns[1].interactive_question.result)

        other = self._question_session(session_id="session-cross-target")
        with self.assertRaises(HTTPException) as cross_target:
            self.service.record_question_attempt(
                session_id=other.id,
                turn_id=first_turn_id,
                expected_session_revision=other.revision,
                client_attempt_id="client-attempt-cross-target",
                submitted_answer="A",
            )
        self.assertEqual(cross_target.exception.status_code, 404)

    def test_stale_revision_fails_before_any_attempt_row_or_answer_write(self) -> None:
        session = self._question_session(session_id="session-stale-attempt")
        turn_id = session.turns[0].id
        with self.assertRaises(HTTPException) as stale:
            self.service.record_question_attempt(
                session_id=session.id,
                turn_id=turn_id,
                expected_session_revision=session.revision - 1,
                client_attempt_id="client-attempt-stale",
                submitted_answer="A",
            )
        self.assertEqual(stale.exception.status_code, 409)
        refreshed = self.service.require_session(session.id)
        self.assertEqual(refreshed.revision, session.revision)
        self.assertIsNone(refreshed.turns[0].interactive_question.result)
        with self.store.database.session() as database_session:
            self.assertIsNone(
                database_session.scalar(
                    select(StudyQuestionAttemptRow).where(
                        StudyQuestionAttemptRow.client_attempt_id
                        == "client-attempt-stale"
                    )
                )
            )

    def test_concurrent_same_request_commits_once(self) -> None:
        session = self._question_session(session_id="session-concurrent-same")
        turn_id = session.turns[0].id

        def submit():
            return self.service.record_question_attempt(
                session_id=session.id,
                turn_id=turn_id,
                expected_session_revision=session.revision,
                client_attempt_id="client-attempt-concurrent",
                submitted_answer="A",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit(), range(2)))
        self.assertEqual(results[0].attempt_id, results[1].attempt_id)
        self.assertEqual(
            self.service.require_session(session.id).revision,
            session.revision + 1,
        )

    def test_concurrent_different_attempts_allow_one_commit(self) -> None:
        session = self._question_session(session_id="session-concurrent-different")
        turn_id = session.turns[0].id

        def submit(client_attempt_id: str):
            try:
                return self.service.record_question_attempt(
                    session_id=session.id,
                    turn_id=turn_id,
                    expected_session_revision=session.revision,
                    client_attempt_id=client_attempt_id,
                    submitted_answer="A",
                )
            except HTTPException as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    submit,
                    ["client-attempt-race-a", "client-attempt-race-b"],
                )
            )
        successes = [result for result in results if not isinstance(result, HTTPException)]
        failures = [result for result in results if isinstance(result, HTTPException)]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].status_code, 409)
        self.assertEqual(
            self.service.require_session(session.id).revision,
            session.revision + 1,
        )


if __name__ == "__main__":
    unittest.main()
