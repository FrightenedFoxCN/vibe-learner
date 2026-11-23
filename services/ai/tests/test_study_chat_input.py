import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.services.study_chat_application import _admit_and_run_study_chat
from app.services.study_chat_attachments import StudyChatAttachmentInput, StudyChatAttachmentService
from app.services.study_chat_errors import StudyChatApplicationError


class ReachedAdmission(Exception):
    pass


class StudyChatInputTests(unittest.TestCase):
    def setUp(self):
        self.admit = Mock(side_effect=ReachedAdmission)
        self.dependencies = SimpleNamespace(
            study_chat_operation_repository=SimpleNamespace(admit=self.admit),
            attachments=StudyChatAttachmentService,
        )

    def submit(self, message, attachments=(), *, kind="learner"):
        return _admit_and_run_study_chat(
            session_id="study-test",
            client_request_id="study-request",
            expected_session_revision=0,
            message=message,
            message_kind=kind,
            follow_up_id="",
            hidden_message_prefix="not a learner message",
            attachment_inputs=attachments,
            execute=Mock(),
            dependencies=self.dependencies,
        )

    def test_blank_learner_input_is_rejected_before_admission(self):
        empty_file = StudyChatAttachmentInput(filename="empty.txt", mime_type="text/plain", raw_bytes=b"")
        for attachments in ((), (empty_file,)):
            with self.assertRaises(StudyChatApplicationError) as raised:
                self.submit(" \n\t", attachments)
            self.assertEqual(raised.exception.status_code, 422)
            self.assertEqual(raised.exception.detail, "study_chat_message_or_attachment_required")
        self.admit.assert_not_called()

    def test_text_or_nonempty_attachment_reaches_admission(self):
        attachment = StudyChatAttachmentInput(filename="note.txt", mime_type="text/plain", raw_bytes=b"note")
        with self.assertRaises(ReachedAdmission):
            self.submit("What is the main idea?")
        with self.assertRaises(ReachedAdmission):
            self.submit("", (attachment,))
        self.assertEqual(self.admit.call_count, 2)
