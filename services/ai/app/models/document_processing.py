from __future__ import annotations

from typing import ClassVar, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from app.models.harness import HarnessContractRef, HarnessSafeManifest
from app.models.domain import DocumentDebugRecord, StudyUnitRecord


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


DOCUMENT_INPUT_CONTRACT = HarnessContractRef(
    name="DocumentProcessInputManifest", version="document-process-input-manifest-v1"
)


DOCUMENT_SNAPSHOT_CONTRACT = HarnessContractRef(
    name="DocumentProcessProtectedInput", version="document-process-protected-input-v1"
)


DOCUMENT_POLICY_CONTRACT = HarnessContractRef(
    name="DocumentProcessHarnessPolicy", version="document-process-harness-v1"
)


DOCUMENT_ADAPTER_CONTRACT = HarnessContractRef(
    name="DocumentProcessWorkflowAdapter", version="document-process-workflow-adapter-v1"
)


DOCUMENT_TRACE_CONTRACT = HarnessContractRef(
    name="DocumentProcessRuntimeOutput", version="document-process-runtime-output-v1"
)


DOCUMENT_STAGE_INPUT_CONTRACT = HarnessContractRef(
    name="DocumentStageInputManifest", version="document-stage-input-manifest-v1"
)


DOCUMENT_STAGE_PROTECTED_INPUT_CONTRACT = HarnessContractRef(
    name="DocumentStageProtectedInput",
    version="document-stage-protected-input-v1",
)


DOCUMENT_STAGE_POLICY_CONTRACT = HarnessContractRef(
    name="DocumentStageHarnessPolicy", version="document-stage-harness-v1"
)


DOCUMENT_STAGE_ADAPTER_CONTRACT = HarnessContractRef(
    name="DocumentStageWorkflowAdapter", version="document-stage-workflow-adapter-v1"
)


DOCUMENT_STAGE_TRACE_CONTRACT = HarnessContractRef(
    name="DocumentStageEvidence", version="document-stage-evidence-v1"
)


class DocumentProcessInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"document_id", "force_ocr"}
    )

    document_id: str
    force_ocr: bool


class DocumentProcessRuntimeOutputV1(_StrictModel):
    schema_name: Literal["DocumentProcessRuntimeOutput"] = (
        "DocumentProcessRuntimeOutput"
    )
    schema_version: Literal["document-process-runtime-output-v1"] = (
        "document-process-runtime-output-v1"
    )
    debug_report: DocumentDebugRecord
    study_units: list[StudyUnitRecord]

    @model_validator(mode="after")
    def validate_document_output(self) -> "DocumentProcessRuntimeOutputV1":
        page_count = self.debug_report.page_count
        if page_count < 1 or self.debug_report.total_characters < 0:
            raise ValueError("document_counts_invalid")
        if page_count != len(self.debug_report.pages):
            raise ValueError("document_page_coverage_invalid")
        page_numbers = [item.page_number for item in self.debug_report.pages]
        if page_numbers != list(range(1, page_count + 1)):
            raise ValueError("document_page_order_invalid")
        for page in self.debug_report.pages:
            if page.char_count < 0 or page.word_count < 0:
                raise ValueError("document_page_counts_invalid")
            if page.char_count == 0 and page.word_count != 0:
                raise ValueError("document_page_word_count_invalid")

        sections = self.debug_report.sections
        section_ids = {section.id for section in sections}
        if len(section_ids) != len(sections):
            raise ValueError("document_section_identity_invalid")
        for section in sections:
            if (
                section.document_id != self.debug_report.document_id
                or section.level < 1
                or section.page_start < 1
                or section.page_end < section.page_start
                or section.page_end > page_count
            ):
                raise ValueError("document_section_boundary_invalid")

        chunks = self.debug_report.chunks
        chunk_ids = {chunk.id for chunk in chunks}
        if len(chunk_ids) != len(chunks):
            raise ValueError("document_chunk_identity_invalid")
        for chunk in chunks:
            if (
                chunk.document_id != self.debug_report.document_id
                or (sections and chunk.section_id not in section_ids)
                or chunk.page_start < 1
                or chunk.page_end < chunk.page_start
                or chunk.page_end > page_count
                or chunk.char_count < 0
            ):
                raise ValueError("document_chunk_boundary_invalid")

        def is_synthetic_study_anchor(section_id: str) -> bool:
            prefix = f"{self.debug_report.document_id}:study-anchor:"
            return section_id.startswith(prefix) and len(section_id) > len(prefix)

        if any(
            unit.document_id != self.debug_report.document_id
            or unit.page_start < 1
            or unit.page_end < unit.page_start
            or unit.page_end > page_count
            or any(
                section_id not in section_ids
                and not is_synthetic_study_anchor(section_id)
                for section_id in unit.source_section_ids
            )
            for unit in self.study_units
        ):
            raise ValueError("study_unit_boundary_invalid")
        return self


class DocumentStageInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"document_id", "stage", "item_count"}
    )

    document_id: str
    stage: Literal[
        "page_extraction",
        "section_detection",
        "chunk_building",
        "ocr_page",
        "study_unit_cleanup",
    ]
    item_count: int


class DocumentStageEvidenceV1(_StrictModel):
    schema_name: Literal["DocumentStageEvidence"] = "DocumentStageEvidence"
    schema_version: Literal["document-stage-evidence-v1"] = (
        "document-stage-evidence-v1"
    )
    stage: Literal[
        "page_extraction",
        "section_detection",
        "chunk_building",
        "ocr_page",
        "study_unit_cleanup",
    ]
    outcome: Literal["passed", "applied", "not_needed", "unavailable", "failed"]
    item_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    # None means the producer did not instrument this stage. Never substitute
    # a parser-wide duration or an assumed attempt count for an observation.
    attempt_count: int | None = Field(default=None, ge=0)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    evidence_source: Literal["observed_runtime"] = "observed_runtime"
