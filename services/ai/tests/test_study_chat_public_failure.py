from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.models.domain import (
    PersonaProfile,
    SessionFollowUpRecord,
    StudySessionRecord,
)
from app.persistence.database import Database
from app.persistence.storage import StorageManager
from app.persistence.study_chat_operation_repository import (
    StudyChatOperationRepository,
)
from app.persistence.study_session_repository import StudySessionRepository
from app.services.local_store import LocalJsonStore
from app.services.study_sessions import StudySessionService


class StudyChatPublicProviderFailureTests(unittest.TestCase):
    def test_catalog_failure_is_not_committed_before_claim_or_provider(self) -> None:
        from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG

        request_id = "request-public-catalog-0001"
        provider_call = Mock()
        with (
            patch.object(routes.container, "study_chat_operation_repository", self.operations),
            patch.object(routes.container, "study_session_service", self.session_service),
            patch.object(routes.container, "pedagogy_orchestrator", SimpleNamespace(generate_chat_reply=provider_call)),
            patch.dict(TOOL_CATALOG[CHAT_STAGE]["ask_fill_blank_question"], {"description": "drifted"}),
            TestClient(app) as client,
        ):
            response = self._post_chat(client, client_request_id=request_id, with_attachment=False)
            self.assertEqual(response.status_code, 200)
            receipt = response.json()
            self.assertEqual(receipt["status"], "not_committed")
            self.assertTrue(receipt["safe_to_retry"])
            self.assertEqual(receipt["error_code"], "study_chat_not_committed_study_tool_catalog_invalid")
        provider_call.assert_not_called()
        record = self.operations.require(session_id=self.session_id, client_request_id=request_id)
        self.assertEqual(record.claim_count, 0)
        self.assertFalse(record.provider_started_at)
        self.assertEqual(self.sessions.require(self.session_id).revision, 0)

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        self.database.create_schema()
        self.storage = StorageManager(Path(self.temp.name) / "data")
        self.store = LocalJsonStore(self.database, self.storage)
        self.sessions = StudySessionRepository(self.database)
        self.operations = StudyChatOperationRepository(
            self.database,
            chat_attachment_root=self.storage.chat_attachment_root,
        )
        self.session_service = StudySessionService(
            self.store,
            repository=self.sessions,
        )
        self.session_id = "session-public-provider-failure"
        self.sessions.create(
            StudySessionRecord(
                id=self.session_id,
                document_id="",
                persona_id="persona-public-provider-failure",
                study_unit_id="unit-1",
                status="active",
                turns=[],
                pending_follow_ups=[
                    SessionFollowUpRecord(
                        id="follow-up-must-remain-pending",
                        status="pending",
                        delay_seconds=30,
                        due_at="2026-08-25T00:00:30+00:00",
                        hidden_message="do not commit cancellation",
                        created_at="2026-08-25T00:00:00+00:00",
                    )
                ],
                revision=0,
                last_turn_sequence=0,
                created_at="2026-08-25T00:00:00+00:00",
                updated_at="2026-08-25T00:00:00+00:00",
            )
        )

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def test_public_post_and_get_preserve_timeout_uncertainty_without_reexecution(self) -> None:
        self._assert_public_failure(
            client_request_id="request-public-timeout-0001",
            provider_error=RuntimeError("openai_chat_request_timeout"),
            expected_error_code="study_chat_uncertain_chat_model_timeout",
            with_attachment=False,
        )

    def test_public_attachment_post_and_get_compensate_connection_failure_staging(self) -> None:
        self._assert_public_failure(
            client_request_id="request-public-connection-0001",
            provider_error=RuntimeError("openai_chat_request_network_error"),
            expected_error_code="study_chat_uncertain_chat_model_network_error",
            with_attachment=True,
        )

    def _assert_public_failure(
        self,
        *,
        client_request_id: str,
        provider_error: RuntimeError,
        expected_error_code: str,
        with_attachment: bool,
    ) -> None:
        provider_call = Mock(side_effect=provider_error)
        orchestrator = SimpleNamespace(generate_chat_reply=provider_call)
        model_provider = SimpleNamespace(
            supports_chat_page_image_tools=lambda: True,
            supports_chat_generated_image_tools=lambda: False,
        )
        runtime_settings = SimpleNamespace(
            effective_settings=lambda: SimpleNamespace(
                openai_timeout_seconds=3,
                openai_chat_tool_max_rounds=1,
            )
        )
        plan_service = SimpleNamespace(
            find_latest_plan=lambda **_kwargs: None,
        )
        persona_engine = SimpleNamespace(
            require_persona=lambda _persona_id: PersonaProfile(
                id="persona-public-provider-failure",
                name="Failure Fixture Tutor",
                source="test",
                summary="Fixture persona",
                system_prompt="",
                available_emotions=["calm"],
                available_actions=["point"],
                default_speech_style="steady",
            )
        )
        cleanup_observations: list[bool] = []
        original_cleanup = routes.cleanup_staged_study_chat_operation_attachments

        def observe_cleanup(*, store, session_id: str, operation_id: str) -> int:
            operation_root = Path(store.chat_attachment_root) / session_id / operation_id
            cleanup_observations.append(
                operation_root.is_dir() and any(operation_root.iterdir())
            )
            return original_cleanup(
                store=store,
                session_id=session_id,
                operation_id=operation_id,
            )

        with (
            patch.object(routes.container, "store", self.store),
            patch.object(routes.container, "study_session_repository", self.sessions),
            patch.object(
                routes.container,
                "study_chat_operation_repository",
                self.operations,
            ),
            patch.object(routes.container, "study_session_service", self.session_service),
            patch.object(routes.container, "runtime_settings_service", runtime_settings),
            patch.object(routes.container, "model_provider", model_provider),
            patch.object(routes.container, "plan_service", plan_service),
            patch.object(routes.container, "persona_engine", persona_engine),
            patch.object(routes.container, "pedagogy_orchestrator", orchestrator),
            patch.object(
                routes,
                "cleanup_staged_study_chat_operation_attachments",
                side_effect=observe_cleanup,
            ),
            TestClient(app) as client,
        ):
            post_response = self._post_chat(
                client,
                client_request_id=client_request_id,
                with_attachment=with_attachment,
            )
            self.assertEqual(post_response.status_code, 200)
            posted = post_response.json()
            self._assert_uncertain_receipt(
                posted,
                client_request_id=client_request_id,
                expected_error_code=expected_error_code,
            )
            operation_id = posted["operation_id"]
            operation_root = (
                self.storage.chat_attachment_root / self.session_id / operation_id
            )
            self.assertFalse(operation_root.exists())

            get_response = client.get(
                f"/study-sessions/{self.session_id}/chat-operations/{client_request_id}"
            )
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json(), posted)

            replay_response = self._post_chat(
                client,
                client_request_id=client_request_id,
                with_attachment=with_attachment,
            )
            self.assertEqual(replay_response.status_code, 200)
            self.assertEqual(replay_response.json(), posted)

        self.assertEqual(provider_call.call_count, 1)
        operation = self.operations.require(
            session_id=self.session_id,
            client_request_id=client_request_id,
        )
        self.assertTrue(operation.provider_started_at)
        self.assertEqual(operation.status.value, "uncertain")
        self.assertIsNone(operation.response_payload)
        self.assertIsNone(operation.committed_session_revision)
        self.assertIsNone(operation.committed_turn_id)
        self.assertIsNone(operation.committed_turn_sequence)
        session = self.sessions.require(self.session_id)
        self.assertEqual(session.revision, 0)
        self.assertEqual(session.last_turn_sequence, 0)
        self.assertEqual(session.turns, [])
        self.assertEqual(session.pending_follow_ups[0].status, "pending")
        if with_attachment:
            self.assertEqual(cleanup_observations, [True, False, False])
        else:
            self.assertEqual(cleanup_observations, [False, False, False])

    def _post_chat(
        self,
        client: TestClient,
        *,
        client_request_id: str,
        with_attachment: bool,
    ):
        if with_attachment:
            return client.post(
                f"/study-sessions/{self.session_id}/chat-with-attachments",
                data={
                    "client_request_id": client_request_id,
                    "expected_session_revision": "0",
                    "message": "Explain this diagram",
                    "message_kind": "learner",
                    "follow_up_id": "",
                    "hidden_message_prefix": "",
                },
                files={
                    "files": (
                        "diagram.png",
                        b"fixture-image-bytes",
                        "image/png",
                    )
                },
            )
        return client.post(
            f"/study-sessions/{self.session_id}/chat",
            json={
                "client_request_id": client_request_id,
                "expected_session_revision": 0,
                "message": "Explain the topic",
                "message_kind": "learner",
                "follow_up_id": "",
                "hidden_message_prefix": "",
            },
        )

    def _assert_uncertain_receipt(
        self,
        receipt: dict[str, object],
        *,
        client_request_id: str,
        expected_error_code: str,
    ) -> None:
        self.assertEqual(receipt["session_id"], self.session_id)
        self.assertEqual(receipt["client_request_id"], client_request_id)
        self.assertEqual(receipt["status"], "uncertain")
        self.assertFalse(receipt["safe_to_retry"])
        self.assertEqual(receipt["error_code"], expected_error_code)
        self.assertIsNone(receipt["result"])
        self.assertIsNone(receipt["committed_session_revision"])
        self.assertIsNone(receipt["committed_turn_id"])
        self.assertIsNone(receipt["committed_turn_sequence"])


if __name__ == "__main__":
    unittest.main()
