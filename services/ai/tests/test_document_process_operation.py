from __future__ import annotations

from tests.support.document_operations import FakeDocumentParser, FakeStudyArrangement, UnavailableOcrParser, create_document
import io
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException, UploadFile

from app.models.document_process_operation import (
    DocumentProcessOperationStatus,
    DocumentProcessProjectionState,
)
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationResolutionStatus,
)
from app.persistence.document_process_operation_repository import (
    DocumentProcessOperationRepository,
    DocumentProcessReadBackError,
)
from app.persistence.models import DocumentDebugRow
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.stream_interrupts import StreamInterruptedError


class DocumentProcessOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_uninstrumented_stages_do_not_invent_parser_timings(self) -> None:
        service = self._service(parser=FakeDocumentParser())
        document = service.create_document(UploadFile(filename="metrics.pdf", file=io.BytesIO(b"pdf")))
        harness = service.harness_service
        with (
            patch.object(harness, "emit_document_stage_evidence", wraps=harness.emit_document_stage_evidence) as stages,
            patch.object(harness, "emit_ocr_stage_evidence", wraps=harness.emit_ocr_stage_evidence) as ocr,
            patch.object(harness, "emit_study_unit_cleanup_evidence", wraps=harness.emit_study_unit_cleanup_evidence) as cleanup,
            patch("app.services.documents.time.perf_counter", side_effect=[1.0, 1.125]),
        ):
            service.process_document(document.id)
        for call in [*stages.call_args_list, ocr.call_args]:
            evidence = call.kwargs["evidence"]
            self.assertIsNone(evidence.duration_ms)
            self.assertIsNone(evidence.attempt_count)
        measured = cleanup.call_args.kwargs["evidence"]
        self.assertEqual(measured.duration_ms, 125)
        self.assertEqual(measured.attempt_count, 1)

    def test_success_commits_document_debug_and_terminal_truth_atomically(self) -> None:
        parser = FakeDocumentParser()
        service = self._service(parser=parser)
        document = create_document(service, "success.pdf")

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

    def test_admission_persists_harness_operation_identity_atomically(self) -> None:
        service = self._service(parser=FakeDocumentParser())
        document = create_document(service, "identity.pdf")

        operation, _ = service.process_repository.admit(
            document_id=document.id,
            force_ocr=False,
        )
        resolution = service.process_repository.harness_operations.resolve_domain(
            domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
            domain_operation_id=operation.operation_id,
        )

        self.assertEqual(
            resolution.status,
            HarnessOperationResolutionStatus.RESOLVED,
        )
        assert resolution.binding is not None
        self.assertEqual(resolution.binding.workflow.value, "document_parse")
        self.assertEqual(resolution.binding.entry_stage.value, "document_parse")

    def test_cleanup_failure_reaches_failed_terminal_state_without_debug_projection(self) -> None:
        service = self._service(
            parser=FakeDocumentParser(),
            arrangement=FakeStudyArrangement(failure=RuntimeError("cleanup_failed")),
        )
        document = create_document(service, "cleanup.pdf")

        with self.assertRaisesRegex(RuntimeError, "cleanup_failed"):
            service.process_document(document.id)

        self._assert_failed_without_debug(service, document.id)

    def test_forced_ocr_unavailable_does_not_commit_a_synthetic_study_unit(self) -> None:
        service = self._service(parser=UnavailableOcrParser())
        document = create_document(service, "ocr-unavailable.pdf")

        with self.assertRaisesRegex(RuntimeError, "document_ocr_unavailable"):
            service.process_document(document.id, force_ocr=True)

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
                service = self._service(parser=FakeDocumentParser(), repository=repository)
                document = create_document(service, f"{stage}.pdf")

                with self.assertRaisesRegex(RuntimeError, f"fault:{stage}"):
                    service.process_document(document.id)

                self._assert_failed_without_debug(service, document.id)

    def test_interrupt_during_first_progress_event_restores_base_projection(self) -> None:
        service = self._service(parser=FakeDocumentParser())
        document = create_document(service, "interrupt.pdf")

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
        service = self._service(parser=FakeDocumentParser())
        document = create_document(service, "abandoned.pdf")
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
        service = self._service(parser=FakeDocumentParser())
        document = create_document(service, "tamper.pdf")
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
        service = self._service(parser=FakeDocumentParser())
        document = create_document(service, "post-commit-progress.pdf")

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
        service = self._service(parser=FakeDocumentParser())

        with self.assertRaises(HTTPException) as raised:
            service.process_document("doc-missing")

        self.assertEqual(raised.exception.status_code, 404)
        self.assertIsNone(
            service.process_repository.latest(document_id="doc-missing")
        )

    def _service(
        self,
        *,
        parser: FakeDocumentParser,
        arrangement: FakeStudyArrangement | None = None,
        repository: DocumentProcessOperationRepository | None = None,
    ) -> DocumentService:
        return DocumentService(
            self.store,
            parser,  # type: ignore[arg-type]
            arrangement or FakeStudyArrangement(),  # type: ignore[arg-type]
            process_repository=repository,
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


def _raise_fault(stage: str) -> None:
    raise RuntimeError(f"fault:{stage}")


if __name__ == "__main__":
    unittest.main()
