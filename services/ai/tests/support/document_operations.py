"""Deterministic parsing samples and injected processing failures."""
from __future__ import annotations
import io
from fastapi import UploadFile
from app.models.domain import (
    DocumentChunkRecord,
    DocumentDebugRecord,
    DocumentPageRecord,
    StudyUnitRecord,
)
from app.services.documents import DocumentService

class FakeDocumentParser:
    def __init__(self, *, failure: Exception | None = None) -> None:
        self.failure = failure
        self.force_ocr_calls: list[bool] = []

    def parse(self, **kwargs: object) -> DocumentDebugRecord:
        self.force_ocr_calls.append(bool(kwargs["force_ocr"]))
        if self.failure is not None:
            raise self.failure
        return document_debug_report(str(kwargs["document_id"]))


class FakeStudyArrangement:
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


class UnavailableOcrParser(FakeDocumentParser):
    def parse(self, **kwargs: object) -> DocumentDebugRecord:
        self.force_ocr_calls.append(bool(kwargs["force_ocr"]))
        return document_debug_report(str(kwargs["document_id"])).model_copy(
            update={
                "ocr_status": "unavailable",
                "ocr_applied": False,
                "ocr_warnings": ["ocr_engine_unavailable"],
            }
        )


def document_debug_report(document_id: str) -> DocumentDebugRecord:
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


def create_document(service: DocumentService, filename: str):
    return service.create_document(
        UploadFile(
            filename=filename,
            file=io.BytesIO(b"fake-pdf-for-deterministic-parser"),
            headers={"content-type": "application/pdf"},
        )
    )

