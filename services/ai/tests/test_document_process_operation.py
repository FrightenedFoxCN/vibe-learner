from __future__ import annotations

import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException, UploadFile

from app.models.document_process_operation import (
    DocumentProcessOperationStatus,
    DocumentProcessProjectionState,
)
from app.models.domain import (
    DocumentChunkRecord,
    DocumentDebugRecord,
    DocumentPageRecord,
    StudyUnitRecord,
)
from app.persistence.document_process_operation_repository import (
    DocumentProcessOperationRepository,
    DocumentProcessReadBackError,
)
from app.persistence.models import DocumentDebugRow
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.stream_interrupts import StreamInterruptedError


class _FakeParser:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.force_ocr_calls: list[bool] = []

    def parse(self, **kwargs: object) -> DocumentDebugRecord:
        self.force_ocr_calls.append(bool(kwargs["force_ocr"]))
        if self.failure is not None:
            raise self.failure
        return _debug_report(str(kwargs["document_id"]))


class _FakeArrangement:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure

    def build_study_units(self, *, document, debug_report) -> list[StudyUnitRecord]:
        if self.failure is not None:
            raise self.failure
        return [
            StudyUnitRecord(
                id=f"{document.id}:study-unit:1",
                document_id=document.id,
                title="Atomic processing",
                page_start=1,
                page_end=1,
                source_section_ids=[],
                summary="A deterministic test unit.",
                confidence=1.0,
            )
        ]


class DocumentProcessOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_success_commits_document_debug_and_terminal_truth_atomically(self) -> None:
        parser = _FakeParser()
        service = self._service(parser=parser)
        document = self._create_document(service, "success.pdf")

        processed = service.process_document(document.id, force_ocr=True)
        operation = service.process_repository.latest(document_id=document.id)
        debug = service.require_debug_report(document.id)

        self.assertEqual(processed.status, "processed")
        self.assertTrue(processed.debug_ready)
        self.assertEqual(debug.document_id, document.id)
        self.assertEqual(parser.force_ocr_calls, [True])
        self.assertIsNotNone(operation)
        assert operation is not None
        self.assertEqual(operation.status, DocumentProcessOperationStatus.COMMITTED)
        self.assertEqual(operation.projection_state, DocumentProcessProjectionState.COMMITTED)
        self.assertTrue(operation.document_digest)
        self.assertTrue(operation.debug_digest)
        self.assertTrue(operation.request_payload.force_ocr)

    def test_cleanup_failure_reaches_failed_terminal_state_without_debug_projection(self) -> None:
        service = self._service(
            parser=_FakeParser(),
            arrangement=_FakeArrangement(failure=RuntimeError("cleanup_failed")),
        )
        document = self._create_document(service, "cleanup.pdf")

        with self.assertRaisesRegex(RuntimeError, "cleanup_failed"):
            service.process_document(document.id)

        self._assert_failed_without_debug(service, document.id)

    def test_projection_faults_roll_back_both_projections_and_terminalize_operation(self) -> None:
        for stage in (
            "before_debug_projection",
            "after_debug_projection",
            "after_document_projection",
            "before_terminal_commit",
        ):
            with self.subTest(stage=stage):
                repository = DocumentProcessOperationRepository(
                    self.store.database,
                    fault_injector=lambda current, expected=stage: (
                        _raise_fault(current) if current == expected else None
                    ),
                )
                service = self._service(parser=_FakeParser(), repository=repository)
                document = self._create_document(service, f"{stage}.pdf")

                with self.assertRaisesRegex(RuntimeError, f"fault:{stage}"):
                    service.process_document(document.id)

                self._assert_failed_without_debug(service, document.id)

    def test_interrupt_during_first_progress_event_restores_base_projection(self) -> None:
        service = self._service(parser=_FakeParser())
        document = self._create_document(service, "interrupt.pdf")

        def interrupt_progress(stage: str, _payload: dict[str, object]) -> None:
            if stage == "document_processing_started":
                raise StreamInterruptedError("stream_interrupted")

        with self.assertRaises(StreamInterruptedError):
            service.process_document(document.id, progress_callback=interrupt_progress)

        refreshed = service.require_document(document.id)
        operation = service.process_repository.latest(document_id=document.id)
        self.assertEqual(refreshed.status, "uploaded")
        self.assertEqual(refreshed.ocr_status, "pending")
        self.assertIsNotNone(operation)
        assert operation is not None
        self.assertEqual(operation.status, DocumentProcessOperationStatus.INTERRUPTED)
        self.assertEqual(operation.projection_state, DocumentProcessProjectionState.NOT_COMMITTED)

    def test_startup_recovery_terminalizes_abandoned_operation(self) -> None:
        service = self._service(parser=_FakeParser())
        document = self._create_document(service, "abandoned.pdf")
        operation, _processing_document = service.process_repository.admit(
            document_id=document.id,
            force_ocr=False,
        )

        recovered_count = service.recover_abandoned_operations()
        recovered = service.process_repository.require(operation_id=operation.operation_id)
        refreshed = service.require_document(document.id)

        self.assertEqual(recovered_count, 1)
        self.assertEqual(recovered.status, DocumentProcessOperationStatus.FAILED)
        self.assertEqual(recovered.error_code, "document_process_abandoned_on_startup")
        self.assertEqual(refreshed.status, "failed")
        self.assertNotEqual(refreshed.status, "processing")

    def test_committed_read_back_detects_debug_projection_tampering(self) -> None:
        service = self._service(parser=_FakeParser())
        document = self._create_document(service, "tamper.pdf")
        service.process_document(document.id)

        with self.store.database.session() as session:
            row = session.get(DocumentDebugRow, document.id)
            assert row is not None
            payload = dict(row.payload or {})
            payload["page_count"] = 99
            row.payload = payload

        with self.assertRaises(DocumentProcessReadBackError):
            service.process_repository.latest(document_id=document.id)

    def test_post_commit_progress_failure_does_not_change_committed_outcome(self) -> None:
        service = self._service(parser=_FakeParser())
        document = self._create_document(service, "post-commit-progress.pdf")

        def fail_only_after_commit(stage: str, _payload: dict[str, object]) -> None:
            if stage == "document_processing_completed":
                raise RuntimeError("progress_sink_unavailable")

        processed = service.process_document(
            document.id,
            progress_callback=fail_only_after_commit,
        )
        operation = service.process_repository.latest(document_id=document.id)

        self.assertEqual(processed.status, "processed")
        self.assertIsNotNone(operation)
        assert operation is not None
        self.assertEqual(operation.status, DocumentProcessOperationStatus.COMMITTED)

    def test_missing_document_is_reported_without_creating_an_operation(self) -> None:
        service = self._service(parser=_FakeParser())

        with self.assertRaises(HTTPException) as raised:
            service.process_document("doc-missing")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertIsNone(
            service.process_repository.latest(document_id="doc-missing")
        )

    def _service(
        self,
        *,
        parser: _FakeParser,
        arrangement: _FakeArrangement | None = None,
        repository: DocumentProcessOperationRepository | None = None,
    ) -> DocumentService:
        return DocumentService(
            self.store,
            parser,  # type: ignore[arg-type]
            arrangement or _FakeArrangement(),  # type: ignore[arg-type]
            process_repository=repository,
        )

    @staticmethod
    def _create_document(service: DocumentService, filename: str):
        return service.create_document(
            UploadFile(
                filename=filename,
                file=io.BytesIO(b"fake-pdf-for-deterministic-parser"),
                headers={"content-type": "application/pdf"},
            )
        )

    def _assert_failed_without_debug(
        self,
        service: DocumentService,
        document_id: str,
    ) -> None:
        refreshed = service.require_document(document_id)
        operation = service.process_repository.latest(document_id=document_id)
        self.assertEqual(refreshed.status, "failed")
        self.assertEqual(refreshed.ocr_status, "failed")
        self.assertIsNotNone(operation)
        assert operation is not None
        self.assertEqual(operation.status, DocumentProcessOperationStatus.FAILED)
        self.assertEqual(operation.projection_state, DocumentProcessProjectionState.NOT_COMMITTED)
        self.assertFalse(operation.document_digest)
        self.assertFalse(operation.debug_digest)
        with self.assertRaises(HTTPException) as raised:
            service.require_debug_report(document_id)
        self.assertEqual(raised.exception.status_code, 404)


def _debug_report(document_id: str) -> DocumentDebugRecord:
    return DocumentDebugRecord(
        document_id=document_id,
        parser_name="deterministic-test-parser",
        processed_at="2026-08-24T00:00:00+00:00",
        page_count=1,
        total_characters=24,
        extraction_method="text",
        ocr_status="completed",
        ocr_applied=False,
        pages=[
            DocumentPageRecord(
                page_number=1,
                char_count=24,
                word_count=3,
                text_preview="Atomic processing content",
                dominant_font_size=12.0,
                extraction_source="text",
                heading_candidates=[],
            )
        ],
        sections=[],
        chunks=[
            DocumentChunkRecord(
                id=f"{document_id}:chunk:1",
                document_id=document_id,
                section_id="",
                page_start=1,
                page_end=1,
                char_count=24,
                text_preview="Atomic processing content",
                content="Atomic processing content",
            )
        ],
        warnings=[],
        dominant_language_hint="en",
    )


def _raise_fault(stage: str) -> None:
    raise RuntimeError(f"fault:{stage}")


if __name__ == "__main__":
    unittest.main()
