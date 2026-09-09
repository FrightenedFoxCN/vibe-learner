from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from contextlib import ExitStack
import unittest
from unittest.mock import Mock, patch

from app.api import routes
from app.models.domain import (
    CharacterStateEvent,
    Citation,
    PersonaProfile,
    StudyChatResult,
    StudySessionRecord,
)
from app.models.harness import HarnessCommitStatus
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from app.persistence.database import Database
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.storage import StorageManager
from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
from app.persistence.study_session_repository import StudySessionRepository
from app.services.local_store import LocalJsonStore
from app.services.study_sessions import StudySessionService
from app.services.study_v3 import StudyV3SnapshotService


class StudyV3RuntimeTests(unittest.TestCase):
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
        self.session_id = "session-study-v3"
        self.sessions.create(
            StudySessionRecord(
                id=self.session_id,
                document_id="",
                persona_id="persona-study-v3",
                study_unit_id="unit-study-v3",
                study_unit_title="Vectors",
                status="active",
                turns=[],
                revision=0,
                last_turn_sequence=0,
                created_at="2026-09-03T00:00:00+00:00",
                updated_at="2026-09-03T00:00:00+00:00",
            )
        )

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def _result(self) -> StudyChatResult:
        return StudyChatResult(
            reply="A basis is linearly independent and spans the space.",
            citations=[
                Citation(
                    section_id="unit-study-v3",
                    title="Vectors",
                    page_start=1,
                    page_end=1,
                )
            ],
            character_events=[
                CharacterStateEvent(
                    emotion="calm",
                    action="point",
                    speech_style="steady",
                    scene_hint="",
                    line_segment_id="session-study-v3:chat:0",
                    timing_hint="normal",
                )
            ],
        )

    def _protected_payload(self) -> dict[str, object]:
        return {
            "schema_name": "StudyChatProtectedSnapshot",
            "schema_version": "study-chat-protected-snapshot-v1",
            "dependencies": {
                "input": {},
                "session": {},
                "persona": {},
                "bound_plan": None,
                "active_plan": None,
                "document": None,
                "document_debug": None,
                "memory_sessions": [],
                "session_prompt": "private prompt",
                "model_message": "private learner message",
                "active_plan_context": "",
                "attachment_context": "",
                "learner_multimodal_parts": [],
                "session_state_context": "",
                "active_scene_summary": "",
                "active_scene_context": "",
                "learner_attachments": [],
            },
        }

    def _patches(self, provider_call):
        return (
            patch.object(routes.container, "store", self.store),
            patch.object(routes.container, "study_session_repository", self.sessions),
            patch.object(
                routes.container,
                "study_chat_operation_repository",
                self.operations,
            ),
            patch.object(
                routes.container,
                "study_session_service",
                self.session_service,
            ),
            patch.object(
                routes.container,
                "runtime_settings_service",
                SimpleNamespace(
                    effective_settings=lambda: SimpleNamespace(
                        openai_timeout_seconds=3,
                        openai_chat_tool_max_rounds=1,
                    )
                ),
            ),
            patch.object(
                routes.container,
                "model_provider",
                SimpleNamespace(
                    supports_chat_page_image_tools=lambda: False,
                    supports_chat_generated_image_tools=lambda: False,
                ),
            ),
            patch.object(
                routes.container,
                "plan_service",
                SimpleNamespace(find_latest_plan=lambda **_kwargs: None),
            ),
            patch.object(
                routes.container,
                "persona_engine",
                SimpleNamespace(
                    require_persona=lambda _persona_id: PersonaProfile(
                        id="persona-study-v3",
                        name="Study V3 Tutor",
                        source="test",
                        summary="fixture",
                        system_prompt="",
                        available_emotions=["calm"],
                        available_actions=["point"],
                        default_speech_style="steady",
                    )
                ),
            ),
            patch.object(
                routes.container,
                "pedagogy_orchestrator",
                SimpleNamespace(generate_chat_reply=provider_call),
            ),
        )

    def _run(self, *, client_request_id: str):
        return routes._admit_and_run_study_chat(
            session_id=self.session_id,
            client_request_id=client_request_id,
            expected_session_revision=0,
            message="Explain a basis",
            message_kind="learner",
            follow_up_id="",
            hidden_message_prefix="",
            attachment_inputs=[],
        )

    def test_authorized_snapshot_precedes_single_provider_call_and_atomic_commit(self) -> None:
        events: list[str] = []
        original_resolve = HarnessArtifactRepository.resolve

        def resolve(repository, request, **kwargs):
            events.append("resolve")
            return original_resolve(repository, request, **kwargs)

        provider = Mock(side_effect=lambda **_kwargs: (events.append("provider"), self._result())[1])
        with ExitStack() as stack:
            for patcher in self._patches(provider):
                stack.enter_context(patcher)
            stack.enter_context(
                patch.object(HarnessArtifactRepository, "resolve", resolve)
            )
            receipt = self._run(client_request_id="request-study-v3-success")
            replay = self._run(client_request_id="request-study-v3-success")

        self.assertEqual(events, ["resolve", "provider"])
        provider.assert_called_once()
        self.assertEqual(receipt.status, "committed")
        self.assertEqual(replay.operation_id, receipt.operation_id)
        session = self.sessions.require(self.session_id)
        self.assertEqual((session.revision, session.last_turn_sequence), (1, 1))
        self.assertEqual(len(session.turns), 1)
        operation = self.operations.require(
            session_id=self.session_id,
            client_request_id="request-study-v3-success",
        )
        self.assertIsNotNone(operation.harness_trace)
        assert operation.harness_trace is not None
        self.assertEqual(
            operation.harness_trace.commit_evidence.status,
            HarnessCommitStatus.COMMITTED,
        )
        serialized = operation.harness_trace.model_dump_json()
        self.assertNotIn("Explain a basis", serialized)
        self.assertNotIn("A basis is linearly independent", serialized)

    def test_authorization_failure_calls_no_provider_and_writes_no_turn(self) -> None:
        provider = Mock(return_value=self._result())
        with ExitStack() as stack:
            for patcher in self._patches(provider):
                stack.enter_context(patcher)
            stack.enter_context(
                patch.object(
                HarnessArtifactRepository,
                "resolve",
                side_effect=PermissionError("harness_artifact_grant_denied"),
                )
            )
            receipt = self._run(client_request_id="request-study-v3-denied")

        provider.assert_not_called()
        self.assertEqual(receipt.status, "uncertain")
        session = self.sessions.require(self.session_id)
        self.assertEqual((session.revision, len(session.turns)), (0, 0))
        operation = self.operations.require(
            session_id=self.session_id,
            client_request_id="request-study-v3-denied",
        )
        self.assertIsNotNone(operation.harness_trace)
        assert operation.harness_trace is not None
        self.assertEqual(
            operation.harness_trace.commit_evidence.status,
            HarnessCommitStatus.NOT_COMMITTED,
        )

    def test_commit_failure_leaves_session_unchanged_and_records_non_commit(self) -> None:
        provider = Mock(return_value=self._result())
        with ExitStack() as stack:
            for patcher in self._patches(provider):
                stack.enter_context(patcher)
            stack.enter_context(
                patch.object(
                    self.sessions,
                    "commit_chat_operation_turn",
                    side_effect=RuntimeError("study_commit_fixture_failure"),
                )
            )
            receipt = self._run(client_request_id="request-study-v3-commit-failure")

        provider.assert_called_once()
        self.assertEqual(receipt.status, "uncertain")
        session = self.sessions.require(self.session_id)
        self.assertEqual((session.revision, len(session.turns)), (0, 0))
        operation = self.operations.require(
            session_id=self.session_id,
            client_request_id="request-study-v3-commit-failure",
        )
        self.assertIsNotNone(operation.harness_trace)
        assert operation.harness_trace is not None
        self.assertEqual(
            operation.harness_trace.commit_evidence.status,
            HarnessCommitStatus.NOT_COMMITTED,
        )

    def test_protected_replay_reports_retention_failure(self) -> None:
        operation = self.operations.admit(
            session_id=self.session_id,
            client_request_id="request-study-v3-retention",
            request_payload=StudyChatOperationRequestPayload(
                message="private learner message",
                message_kind="learner",
                follow_up_id="",
                hidden_message_prefix="",
                expected_session_revision=0,
                attachments=[],
            ),
        )
        binding = self.operations.require_harness_operation(operation.operation_id)
        artifacts = HarnessArtifactRepository(self.database)
        snapshots = StudyV3SnapshotService(artifacts)
        snapshot, grant_id = snapshots.register_session_snapshot(
            operation_binding=binding,
            payload=self._protected_payload(),
        )
        resolved = snapshots.resolve_snapshot(
            operation_binding=binding,
            snapshot=snapshot,
            grant_id=grant_id,
        )
        self.assertIn(b"private learner message", resolved)
        self.assertTrue(artifacts.delete_artifact(artifact_id=snapshot.artifact_id))
        with self.assertRaisesRegex(PermissionError, "not_found"):
            snapshots.resolve_snapshot(
                operation_binding=binding,
                snapshot=snapshot,
                grant_id=grant_id,
            )


if __name__ == "__main__":
    unittest.main()
