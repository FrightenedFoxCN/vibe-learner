from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

import fitz
from fastapi import HTTPException, UploadFile

from app.core.logging import get_logger
from app.models.domain import DocumentDebugRecord, DocumentRecord, DocumentSection
from app.persistence.document_process_operation_repository import (
    DocumentProcessAdmissionRace,
    DocumentProcessAlreadyActive,
    DocumentProcessDocumentNotFound,
    DocumentProcessOperationRepository,
    DocumentProcessStateConflict,
)
from app.services.document_parser import DocumentParser
from app.services.local_store import LocalJsonStore
from app.services.stream_interrupts import StreamInterruptedError
from app.services.study_arrangement import StudyArrangementService

logger = get_logger("vibe_learner.documents")


class DocumentService:
    def __init__(
        self,
        store: LocalJsonStore,
        parser: DocumentParser,
        arrangement_service: StudyArrangementService,
        process_repository: DocumentProcessOperationRepository | None = None,
    ) -> None:
        self.store = store
        self.parser = parser
        self.arrangement_service = arrangement_service
        self.process_repository = process_repository or DocumentProcessOperationRepository(
            store.database
        )

    def create_document(self, file: UploadFile) -> DocumentRecord:
        document_id = f"doc-{uuid4().hex[:10]}"
        suffix = Path(file.filename or "document.pdf").suffix or ".pdf"
        stored_name = f"{document_id}{suffix}"
        stored_path = self.store.upload_root / stored_name
        contents = file.file.read()
        stored_path.write_bytes(contents)

        document = DocumentRecord(
            id=document_id,
            title=Path(file.filename or stored_name).stem,
            original_filename=file.filename or stored_name,
            stored_path=str(stored_path),
            status="uploaded",
            ocr_status="pending",
            created_at=_now(),
            updated_at=_now(),
            sections=[],
            study_units=[],
            study_unit_count=0,
            page_count=0,
            chunk_count=0,
            preview_excerpt="",
            debug_ready=False,
        )
        documents = self._load_documents()
        documents.append(document)
        self._save_documents(documents)
        logger.info(
            "document.created id=%s filename=%s size_bytes=%s stored_path=%s",
            document.id,
            document.original_filename,
            len(contents),
            document.stored_path,
        )
        return document

    def process_document(
        self,
        document_id: str,
        *,
        force_ocr: bool = False,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
        operation_admitted_callback: Callable[[str], None] | None = None,
    ) -> DocumentRecord:
        try:
            operation, document = self.process_repository.admit(
                document_id=document_id,
                force_ocr=force_ocr,
            )
        except DocumentProcessDocumentNotFound as exc:
            raise HTTPException(status_code=404, detail="document_not_found") from exc
        except DocumentProcessAlreadyActive as exc:
            raise HTTPException(status_code=409, detail="document_processing_already_active") from exc
        except (DocumentProcessStateConflict, DocumentProcessAdmissionRace) as exc:
            raise HTTPException(status_code=409, detail="document_processing_state_conflict") from exc
        try:
            if operation_admitted_callback is not None:
                operation_admitted_callback(operation.operation_id)
            _emit_progress(
                progress_callback,
                "document_processing_started",
                {
                    "document_id": document.id,
                    "force_ocr": force_ocr,
                    "stored_path": document.stored_path,
                },
            )
            logger.info(
                "document.processing.start id=%s force_ocr=%s path=%s",
                document.id,
                force_ocr,
                document.stored_path,
            )
            _call_interrupt(interrupt_check)
            debug_report = self.parser.parse(
                document_id=document.id,
                title=document.title,
                stored_path=document.stored_path,
                force_ocr=force_ocr,
                progress_callback=progress_callback,
                interrupt_check=interrupt_check,
            )
            _call_interrupt(interrupt_check)
            document.status = "processed"
            document.ocr_status = debug_report.ocr_status
            study_units = self.arrangement_service.build_study_units(
                document=document,
                debug_report=debug_report,
            )
            _emit_progress(
                progress_callback,
                "study_units_built",
                {
                    "document_id": document.id,
                    "study_unit_count": len(study_units),
                    "plannable_count": len([unit for unit in study_units if unit.include_in_plan]),
                },
            )
            _call_interrupt(interrupt_check)
            debug_report.study_units = study_units
            document.study_units = study_units
            document.study_unit_count = len(study_units)
            document.sections = [
                DocumentSection(
                    id=unit.id,
                    document_id=unit.document_id,
                    title=unit.title,
                    page_start=unit.page_start,
                    page_end=unit.page_end,
                    level=1,
                )
                for unit in study_units
                if unit.include_in_plan
            ]
            document.page_count = debug_report.page_count
            document.chunk_count = len(debug_report.chunks)
            document.preview_excerpt = next(
                (page.text_preview for page in debug_report.pages if page.text_preview),
                "",
            )
            document.debug_ready = True
            document.updated_at = _now()
            self.process_repository.commit_success(
                operation_id=operation.operation_id,
                document=document,
                debug_report=debug_report,
            )
        except StreamInterruptedError:
            self.process_repository.mark_interrupted(operation_id=operation.operation_id)
            self._mirror_current_document_projection(document.id)
            logger.info("document.processing.interrupted id=%s", document.id)
            raise
        except fitz.FileDataError as exc:
            self.process_repository.mark_failed(
                operation_id=operation.operation_id,
                error_code="document_process_invalid_pdf",
            )
            self._mirror_current_document_projection(document.id)
            logger.exception("document.processing.invalid_pdf id=%s", document.id)
            raise HTTPException(status_code=400, detail="invalid_or_unsupported_pdf") from exc
        except Exception as exc:
            self.process_repository.mark_failed(
                operation_id=operation.operation_id,
                error_code=_document_process_error_code(exc),
            )
            self._mirror_current_document_projection(document.id)
            logger.exception("document.processing.failed id=%s", document.id)
            raise

        self._mirror_current_document_projection(document.id, debug_report=debug_report)
        try:
            _emit_progress(
                progress_callback,
                "document_processing_completed",
                {
                    "document_id": document.id,
                    "page_count": document.page_count,
                    "chunk_count": document.chunk_count,
                    "study_unit_count": document.study_unit_count,
                    "ocr_status": document.ocr_status,
                },
            )
        except Exception:
            logger.warning(
                "document.processing.progress_after_commit_ignored id=%s operation_id=%s",
                document.id,
                operation.operation_id,
                exc_info=True,
            )
        logger.info(
            "document.processing.end id=%s pages=%s chunks=%s raw_sections=%s study_units=%s extraction=%s ocr_applied=%s warnings=%s",
            document.id,
            document.page_count,
            document.chunk_count,
            len(debug_report.sections),
            len(document.sections),
            debug_report.extraction_method,
            debug_report.ocr_applied,
            len(debug_report.warnings),
        )
        return document

    def recover_abandoned_operations(self) -> int:
        recovered = self.process_repository.recover_abandoned()
        for operation in recovered:
            self._mirror_current_document_projection(operation.document_id)
        if recovered:
            logger.warning("document.processing.recovered_abandoned count=%s", len(recovered))
        return len(recovered)

    def list_documents(self) -> list[DocumentRecord]:
        return self._load_documents()

    def update_study_unit_title(
        self,
        *,
        document_id: str,
        study_unit_id: str,
        title: str,
    ) -> DocumentRecord:
        normalized_title = title.strip()
        if not normalized_title:
            raise HTTPException(status_code=422, detail="study_unit_title_required")

        documents = self._load_documents()
        document = self.require_document(document_id, documents)

        updated = False
        for unit in document.study_units:
            if unit.id != study_unit_id:
                continue
            unit.title = normalized_title
            updated = True
            break

        if not updated:
            raise HTTPException(status_code=404, detail="study_unit_not_found")

        for section in document.sections:
            if section.id == study_unit_id:
                section.title = normalized_title

        document.updated_at = _now()
        self._save_documents(documents)

        debug_report = self.store.load_item("document_debug", document_id, DocumentDebugRecord)
        if debug_report is not None:
            for unit in debug_report.study_units:
                if unit.id == study_unit_id:
                    unit.title = normalized_title
                    break
            self.store.save_item("document_debug", document_id, debug_report)

        return document

    def require_debug_report(self, document_id: str) -> DocumentDebugRecord:
        report = self.store.load_item("document_debug", document_id, DocumentDebugRecord)
        if report is None:
            raise HTTPException(status_code=404, detail="document_debug_not_found")
        return report

    def require_document(
        self, document_id: str, documents: list[DocumentRecord] | None = None
    ) -> DocumentRecord:
        if documents is None:
            documents = self._load_documents()
        for document in documents:
            if document.id == document_id:
                return document
        raise HTTPException(status_code=404, detail="document_not_found")

    def _load_documents(self) -> list[DocumentRecord]:
        return self.store.load_list("documents", DocumentRecord)

    def _save_documents(self, documents: list[DocumentRecord]) -> None:
        self.store.save_list("documents", documents)

    def _mirror_current_document_projection(
        self,
        document_id: str,
        *,
        debug_report: DocumentDebugRecord | None = None,
    ) -> None:
        documents = self._load_documents()
        if not any(document.id == document_id for document in documents):
            return
        self.store.mirror_document_projection(documents, debug_report)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_progress(
    callback: Callable[[str, dict[str, object]], None] | None,
    stage: str,
    payload: dict[str, object],
) -> None:
    if callback is None:
        return
    callback(stage, payload)


def _call_interrupt(callback: Callable[[], None] | None) -> None:
    if callback is None:
        return
    callback()


def _document_process_error_code(exc: Exception) -> str:
    name = type(exc).__name__.strip().lower()
    normalized = "".join(character if character.isalnum() else "_" for character in name)
    return f"document_process_{normalized or 'failed'}"[:128]
