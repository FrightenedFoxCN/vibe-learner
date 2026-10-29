"""Application-owned partial work; checkpoint state never proves Document commit."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.document_processing import DocumentProcessRuntimeOutputV1
from app.models.domain import DocumentDebugRecord, DocumentRecord, StudyUnitRecord

CHECKPOINT_MAX_BYTES = 8 * 1024 * 1024
CHECKPOINT_MAX_PAGES = 10_000


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CheckpointLine(_Strict):
    text: str
    font_size: float


class CheckpointOcrResultV1(_Strict):
    text: str = ""
    status: Literal["completed", "failed", "unavailable"]
    engine_name: str | None = None
    model_id: str | None = None
    warning: str = ""
    language_hint: str | None = None


class CheckpointWarningV1(_Strict):
    code: str
    message: str
    page_number: int | None = None


class ExtractedPageCheckpointV1(_Strict):
    page_number: int = Field(ge=1, le=CHECKPOINT_MAX_PAGES)
    line_entries: list[CheckpointLine]
    dominant_font_size: float
    extraction_source: str
    warnings: list[CheckpointWarningV1]
    used_ocr: bool
    ocr_result: CheckpointOcrResultV1 | None = None


class DocumentCheckpointSnapshotV1(_Strict):
    contract_version: Literal["document-checkpoint-v1"] = "document-checkpoint-v1"
    operation_id: str
    document_id: str
    upload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    configuration_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    force_ocr: bool
    page_count: int = Field(ge=0)
    pages: list[ExtractedPageCheckpointV1] = Field(max_length=CHECKPOINT_MAX_PAGES)
    report: DocumentDebugRecord | None = None
    output: DocumentProcessRuntimeOutputV1 | None = None
    storage_limited: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        numbers = [page.page_number for page in self.pages]
        if (
            numbers != list(range(1, len(numbers) + 1))
            or len(numbers) > self.page_count
        ):
            raise ValueError("document_checkpoint_page_order_invalid")
        if self.report is not None and (
            self.report.document_id != self.document_id
            or self.report.page_count != self.page_count
        ):
            raise ValueError("document_checkpoint_report_scope_invalid")
        if self.output is not None and self.output.debug_report != self.report:
            raise ValueError("document_checkpoint_output_scope_invalid")
        return self


class CheckpointPagePreviewV1(_Strict):
    page_number: int = Field(ge=1, le=CHECKPOINT_MAX_PAGES)
    text_preview: str = Field(max_length=400)
    extraction_source: Literal[
        "text", "ocr", "ocr_attempted", "ocr_unavailable", "ocr_failed"
    ]


class DocumentCheckpointResponseV1(_Strict):
    contract_version: Literal["document-checkpoint-response-v1"] = (
        "document-checkpoint-response-v1"
    )
    operation_id: str
    document_id: str
    operation_status: Literal["running", "failed", "interrupted", "committed"]
    page_count: int = Field(ge=0)
    completed_page_count: int = Field(ge=0)
    stage: Literal["pages", "parsed", "study_units"]
    force_ocr: bool
    storage_limited: bool
    child_operation_id: str | None
    pages: list[CheckpointPagePreviewV1] = Field(max_length=64)
    study_units: list["StudyUnitRecord"]
    result: DocumentRecord | None
    projection_state: Literal["committed", "checkpoint_only"]


DocumentCheckpointResponseV1.model_rebuild()
