from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
import tempfile
import unittest
from unittest.mock import Mock, patch

import fitz
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.models.domain import (
    DialogueTurnRecord,
    LearnerAttachmentRecord,
    StudySessionRecord,
)
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.storage_lifecycle import StorageLifecycleService
from app.services.token_usage import TokenUsageService


class StorageLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = LocalJsonStore(Path(temp.name) / "store")
        self.addCleanup(self.store.close)
        self.usage = Mock(spec=TokenUsageService)
        self.usage.clear.return_value = 2
        self.lifecycle = StorageLifecycleService(self.store, self.usage)

    def test_unsupported_bucket_rejects_entire_batch_before_cleanup(self) -> None:
        marker = self.store.runtime_temp_root / "keep.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(
            ValueError, "^cleanup_bucket_not_supported:uploads$"
        ):
            self.lifecycle.cleanup(buckets=[" runtime_temp ", "token_usage", "uploads"])

        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.usage.clear.assert_not_called()

    def test_valid_and_empty_batches_preserve_existing_semantics(self) -> None:
        self.assertEqual(self.lifecycle.cleanup(buckets=["", "  "]), [])
        self.usage.clear.assert_not_called()
        self.assertEqual(
            self.lifecycle.cleanup(buckets=["  token_usage  "]),
            [{"bucket": "token_usage", "removed_count": 2}],
        )
        self.usage.clear.assert_called_once_with()

    def test_invalid_attachment_scope_rejects_entire_batch(self) -> None:
        with self.assertRaisesRegex(ValueError, "study_chat_session_id_invalid"):
            self.lifecycle.cleanup(
                buckets=["token_usage", "chat_attachments"], session_id="../uploads"
            )
        self.usage.clear.assert_not_called()

    def test_global_cleanup_does_not_follow_attachment_symlinks(self) -> None:
        upload = self.store.upload_root / "outside"
        upload.mkdir()
        operation = "study-chat-op-" + "1" * 16
        sentinel = upload / operation / "file.pdf"
        sentinel.parent.mkdir()
        sentinel.write_bytes(b"not attachment storage")
        (self.store.chat_attachment_root / "symlink-session").symlink_to(upload)
        session = self.store.chat_attachment_root / "real-session"
        session.mkdir()
        (session / operation).symlink_to(sentinel.parent)

        for scope in ("", "symlink-session", "real-session"):
            self.assertEqual(
                self.lifecycle.cleanup(buckets=["chat_attachments"], session_id=scope),
                [{"bucket": "chat_attachments", "removed_count": 0}],
            )
        self.assertEqual(sentinel.read_bytes(), b"not attachment storage")


class StudyAttachmentCleanupAPITests(unittest.TestCase):
    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.client = self.enterContext(
            TestClient(
                create_app(
                    settings=Settings(
                        database_url=f"sqlite:///{root / 'api.db'}",
                        storage_root=str(root / "storage"),
                        plan_provider="mock",
                        ocr_engine="disabled",
                    )
                )
            )
        )
        self.container = self.client.app.state.container
        self.root = self.container.store.chat_attachment_root
        with fitz.open() as pdf:
            pdf.new_page().insert_text((72, 72), "Synthetic attachment retention test")
            self.pdf_bytes = pdf.tobytes()

    def new_session(self):
        response = self.client.post(
            "/study-sessions",
            json={
                "document_id": "",
                "persona_id": self.container.persona_engine.list_personas()[0].id,
                "study_unit_id": "cleanup-regression",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def cleanup(self, session_id="", *, removed):
        response = self.client.post(
            "/storage/cleanup",
            json={
                "buckets": ["chat_attachments"],
                "session_id": session_id,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            {
                "items": [
                    {"bucket": "chat_attachments", "removed_count": removed},
                ]
            },
        )

    def stage_residue(self, session_id, operation_id):
        path = self.root / session_id / operation_id / "residue.pdf"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.pdf_bytes)
        return path

    def admit(self, session, request_id):
        return self.container.study_chat_operation_repository.admit(
            session_id=session["id"],
            client_request_id=request_id,
            request_payload=StudyChatOperationRequestPayload(
                message="Synthetic",
                message_kind="learner",
                follow_up_id="",
                hidden_message_prefix="",
                expected_session_revision=session["revision"],
                attachments=[],
            ),
        )

    def test_cleanup_preserves_inflight_pdf_and_committed_receipt(self) -> None:
        session = self.new_session()
        session_id = session["id"]
        repo = self.container.study_chat_operation_repository
        rejected = self.admit(session, "cleanup-rejected-request")
        repo.mark_not_committed(operation_id=rejected.operation_id, error_code="test")
        rejected_file = self.stage_residue(session_id, rejected.operation_id)
        orphan = self.stage_residue("other-session", "study-chat-op-" + "2" * 16)
        legacy = self.root / session_id / "attach-0000000000-legacy.pdf"
        legacy.write_bytes(self.pdf_bytes)

        request = {
            "client_request_id": "cleanup-live-pdf-request",
            "expected_session_revision": str(session["revision"]),
            "message": "Read the attached synthetic PDF.",
        }
        chat_url = f"/study-sessions/{session_id}/chat-with-attachments"

        def chat():
            return self.client.post(
                chat_url,
                data=request,
                files=[
                    ("files", ("synthetic.pdf", self.pdf_bytes, "application/pdf")),
                ],
            )

        started, resume = Event(), Event()
        generate_chat = MockModelProvider.generate_chat

        def pause_with_staged_file(provider, **kwargs):
            started.set()
            if not resume.wait(10):
                raise AssertionError("test did not release mocked model")
            return generate_chat(provider, **kwargs)

        with patch.object(MockModelProvider, "generate_chat", pause_with_staged_file):
            with ThreadPoolExecutor(max_workers=1) as worker:
                future = worker.submit(chat)
                try:
                    self.assertTrue(started.wait(10), "chat never reached mocked model")
                    active = repo.get_active(session_id=session_id)
                    self.assertIsNotNone(active)
                    [staged_file] = list(
                        (self.root / session_id / active.operation_id).iterdir()
                    )
                    self.cleanup(session_id, removed=1)
                    self.assertFalse(rejected_file.parent.exists())
                    self.assertTrue(orphan.exists())
                    self.assertEqual(staged_file.read_bytes(), self.pdf_bytes)
                finally:
                    resume.set()
                response = future.result(timeout=10)
        self.assertEqual(response.status_code, 200, response.text)
        receipt = response.json()
        self.assertEqual(receipt["status"], "committed", receipt)
        [attachment] = (
            self.container.study_session_repository.require(session_id)
            .turns[-1]
            .learner_attachments
        )
        file_url = (
            f"/study-sessions/{session_id}/attachments/{attachment.attachment_id}"
        )
        original_image = self.client.get(f"{file_url}/pages/1/image")
        self.assertEqual(original_image.status_code, 200)
        self.assertTrue(original_image.content.startswith(b"\x89PNG\r\n\x1a\n"))

        self.cleanup(session_id, removed=0)
        self.cleanup(removed=1)
        self.cleanup(removed=0)
        self.assertFalse(orphan.parent.exists())
        self.assertEqual(legacy.read_bytes(), self.pdf_bytes)
        download = self.client.get(f"{file_url}/file")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, self.pdf_bytes)
        page = self.client.get(f"{file_url}/pages/1/image")
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.content, original_image.content)
        read_back = self.client.get(
            f"/study-sessions/{session_id}/chat-operations/{request['client_request_id']}"
        )
        self.assertEqual(read_back.status_code, 200, read_back.text)
        self.assertEqual(read_back.json(), receipt)
        self.assertEqual(chat().json(), receipt)

    def test_fenced_worker_is_not_known_quiescent(self) -> None:
        session = self.new_session()
        repo = self.container.study_chat_operation_repository
        operation = self.admit(session, "cleanup-fenced-request")
        operation, claimed = repo.claim(
            operation_id=operation.operation_id, timeout_seconds=30
        )
        self.assertTrue(claimed)
        path = self.stage_residue(session["id"], operation.operation_id)
        repo.mark_uncertain(
            operation_id=operation.operation_id,
            execution_token=operation.execution_token,
            error_code="study_chat_execution_deadline_expired",
        )

        self.cleanup(removed=0)
        self.assertEqual(path.read_bytes(), self.pdf_bytes)

    def test_referenced_legacy_projection_wins_over_orphan_classification(self) -> None:
        session_id = "legacy-imported-session"
        operation_id = "study-chat-op-" + "3" * 16
        referenced = self.stage_residue(session_id, operation_id)
        unreferenced = referenced.with_name("unreferenced.pdf")
        unreferenced.write_bytes(self.pdf_bytes)
        at = "2026-01-01T00:00:00+00:00"
        attachment = LearnerAttachmentRecord(
            attachment_id="legacy-ref",
            name="legacy.pdf",
            mime_type="application/pdf",
            kind="pdf",
            stored_path=str(referenced),
            page_count=1,
            previewable=True,
        )
        self.container.study_session_repository.import_legacy(
            [
                StudySessionRecord(
                    id=session_id,
                    document_id="",
                    persona_id="legacy-persona",
                    study_unit_id="legacy",
                    status="active",
                    revision=1,
                    last_turn_sequence=1,
                    created_at=at,
                    updated_at=at,
                    turns=[
                        DialogueTurnRecord(
                            id="legacy-turn",
                            sequence=1,
                            learner_message="Old attachment",
                            learner_attachments=[attachment],
                            assistant_reply="Legacy reply",
                            citations=[],
                            character_events=[],
                            created_at=at,
                        )
                    ],
                )
            ]
        )
        self.cleanup(removed=1)
        self.assertFalse(unreferenced.exists())
        response = self.client.get(
            f"/study-sessions/{session_id}/attachments/{attachment.attachment_id}/file"
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, self.pdf_bytes)
