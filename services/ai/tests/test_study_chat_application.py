from app.services.study_chat_attachments import StudyChatAttachmentService
from app.services.study_chat_application import StudyChatApplication
import json
from types import SimpleNamespace
from unittest.mock import patch
from app.services.model_provider import OpenAIModelProvider
from app.services.study_chat_attachments import PreparedStudyChatAttachments
from tests.support.study_chat import StudyChatOperationTestCase
from tests.support.study_chat_samples import study_persona, raw_chat_reply


class StudyChatApplicationTests(StudyChatOperationTestCase):
    def test_repair_failure_marks_operation_uncertain_and_commits_no_turn(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            chat_model="gpt-test",
            chat_tools_enabled=False,
            timeout_seconds=3,
        )
        invalid = json.dumps({"mood": "calm", "action": "point"})
        responses = [(raw_chat_reply(invalid), []), (raw_chat_reply(invalid), [])]

        def run_failed_chat(context):
            return provider.generate_chat(
                persona=study_persona(),
                section_id="unit-1",
                message="Explain vector bases",
            )

        runtime_settings = SimpleNamespace(
            effective_settings=lambda: SimpleNamespace(
                openai_timeout_seconds=3,
                openai_chat_tool_max_rounds=1,
            )
        )
        session_service = SimpleNamespace(require_session=self.sessions.require)
        prepared = PreparedStudyChatAttachments(
            records=[],
            attachment_context="",
            multimodal_parts=[],
        )

        with (
            patch.object(self.container, "study_chat_operation_repository", self.operations),
            patch.object(self.container, "study_session_service", session_service),
            patch.object(self.container, "runtime_settings_service", runtime_settings),
            patch.object(self.container, "model_provider", provider),
            patch.object(self.container, "store", object()),
            patch.object(StudyChatAttachmentService, "prepare", return_value=prepared),
            patch.object(StudyChatAttachmentService, "cleanup"),
            patch.object(StudyChatApplication, "execute", side_effect=run_failed_chat),
            patch.object(
                provider,
                "_request_openai_chat_completion",
                side_effect=responses,
            ) as request,
        ):
            receipt = self.container.study_chat_application().admit(
                session_id="session-invalid-reply",
                client_request_id="invalid-reply-request-0001",
                expected_session_revision=0,
                message="Explain vector bases",
                message_kind="learner",
                follow_up_id="",
                hidden_message_prefix="",
                attachment_inputs=[],
                )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(receipt.status, "uncertain")
        self.assertFalse(receipt.safe_to_retry)
        self.assertIsNone(receipt.result)
        session = self.sessions.require("session-invalid-reply")
        self.assertEqual(session.revision, 0)
        self.assertEqual(session.last_turn_sequence, 0)
        self.assertEqual(session.turns, [])

    def test_admission_forwards_validated_session_prelude_kind_to_execution(self) -> None:
        captured: dict[str, object] = {}

        def fail_after_capture(context):
            captured.update(vars(context))
            raise RuntimeError("captured_message_kind")

        runtime_settings = SimpleNamespace(
            effective_settings=lambda: SimpleNamespace(
                openai_timeout_seconds=3,
                openai_chat_tool_max_rounds=1,
            )
        )
        session_service = SimpleNamespace(require_session=self.sessions.require)
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            chat_model="gpt-test",
            timeout_seconds=3,
        )
        prepared = PreparedStudyChatAttachments(
            records=[],
            attachment_context="",
            multimodal_parts=[],
        )

        with (
            patch.object(self.container, "study_chat_operation_repository", self.operations),
            patch.object(self.container, "study_session_service", session_service),
            patch.object(self.container, "runtime_settings_service", runtime_settings),
            patch.object(self.container, "model_provider", provider),
            patch.object(self.container, "store", object()),
            patch.object(StudyChatAttachmentService, "prepare", return_value=prepared),
            patch.object(StudyChatAttachmentService, "cleanup"),
            patch.object(StudyChatApplication, "execute", side_effect=fail_after_capture),
        ):
            receipt = self.container.study_chat_application().admit(
                session_id="session-invalid-reply",
                client_request_id="prelude-kind-forwarding-0001",
                expected_session_revision=0,
                message="正式对话开始前的预处理消息",
                message_kind=" session_prelude ",
                follow_up_id="",
                hidden_message_prefix="",
                attachment_inputs=[],
                )

        self.assertEqual(receipt.status, "uncertain")
        self.assertEqual(captured["message_kind"], "session_prelude")

    def test_settings_update_does_not_replace_captured_execution_provider(self) -> None:
        application = self.container.study_chat_application()
        provider = application.dependencies.model_provider
        rounds = application.dependencies.runtime_settings.openai_chat_tool_max_rounds
        self.container.update_runtime_settings({"openai_chat_tool_max_rounds": rounds + 1})
        next_application = self.container.study_chat_application()
        self.assertIs(application.dependencies.model_provider, provider)
        self.assertIs(application.dependencies.pedagogy_orchestrator.model_provider, provider)
        self.assertEqual(application.dependencies.runtime_settings.openai_chat_tool_max_rounds, rounds)
        self.assertIsNot(next_application.dependencies.model_provider, provider)
        self.assertEqual(next_application.dependencies.runtime_settings.openai_chat_tool_max_rounds, rounds + 1)
