"""Model-owned unit suggestions and the application-owned confirmation boundary."""

from __future__ import annotations

from collections import Counter
from typing import ClassVar, Literal, Self

from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    DocumentSection,
    StudyUnitRecord,
)
from app.models.harness import (
    HarnessContractRef,
    HarnessSafeManifest,
    canonical_harness_digest,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StudyUnitSuggestionV1(_Strict):
    title: str = Field(min_length=1, max_length=500)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    unit_kind: Literal["chapter", "front_matter", "solutions", "back_matter"] = (
        "chapter"
    )
    include_in_plan: bool = True
    summary: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if not self.title.strip() or self.page_end < self.page_start:
            raise ValueError("study_unit_suggestion_invalid")
        return self


class StudyUnitSuggestionsV1(_Strict):
    study_units: list[StudyUnitSuggestionV1] = Field(min_length=1, max_length=24)
    rationale: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_units(self) -> Self:
        previous_end = 0
        for unit in self.study_units:
            if unit.page_start <= previous_end:
                raise ValueError("study_unit_suggestions_overlap_or_unordered")
            previous_end = unit.page_end
        if not any(unit.include_in_plan for unit in self.study_units):
            raise ValueError("study_unit_suggestions_no_plannable_unit")
        return self


class StudyUnitRevisionPreviewV1(_Strict):
    schema_version: Literal["study-unit-revision-preview-v1"] = (
        "study-unit-revision-preview-v1"
    )
    operation_id: str = Field(min_length=1, max_length=80)
    plan_id: str = Field(min_length=1, max_length=64)
    parent_operation_id: str = Field(min_length=1, max_length=64)
    base_document: DocumentRecord
    base_debug_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    suggestions: StudyUnitSuggestionsV1

    @model_validator(mode="after")
    def scope(self) -> Self:
        if any(
            unit.page_end > self.base_document.page_count
            for unit in self.suggestions.study_units
        ):
            raise ValueError("study_unit_revision_page_out_of_range")
        return self


class StudyUnitRevisionInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"operation_id", "document_id", "base_revision"}
    )
    operation_id: str
    document_id: str
    base_revision: int


class StudyUnitRevisionOutputV1(_Strict):
    document: DocumentRecord
    debug_report: DocumentDebugRecord


class StudyUnitRevisionCommittedProjectionV1(_Strict):
    schema_version: Literal["study-unit-revision-commit-v1"] = (
        "study-unit-revision-commit-v1"
    )
    operation_id: str
    preview: StudyUnitRevisionPreviewV1
    base_debug_report: DocumentDebugRecord
    document: DocumentRecord
    debug_report: DocumentDebugRecord
    planning_context_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def scope(self) -> Self:
        if self.operation_id != self.preview.operation_id:
            raise ValueError("study_unit_revision_commit_identity_mismatch")
        if self.planning_context_revision != self.document.revision:
            raise ValueError("study_unit_revision_context_revision_mismatch")
        if (
            canonical_harness_digest(self.base_debug_report)
            != self.preview.base_debug_digest
        ):
            raise ValueError("study_unit_revision_base_debug_digest_mismatch")
        expected = apply_unit_suggestions(
            self.preview, self.base_debug_report, self.document.updated_at
        )
        if (
            expected.document != self.document
            or expected.debug_report != self.debug_report
        ):
            raise ValueError("study_unit_revision_commit_projection_mismatch")
        return self


class StudyUnitRevisionDecisionV1(_Strict):
    decision: Literal["accept", "reject"]


class StudyUnitRevisionResponseV1(_Strict):
    preview: StudyUnitRevisionPreviewV1
    status: Literal["ready", "applying", "accepted", "rejected", "conflict", "failed"]
    result: DocumentRecord | None = None
    planning_context_revision: int | None = None
    error_code: str = ""


def apply_unit_suggestions(
    preview: StudyUnitRevisionPreviewV1,
    debug: DocumentDebugRecord,
    updated_at: str,
) -> StudyUnitRevisionOutputV1:
    """Allocate identity only in the application projection after confirmation."""
    if (
        debug.document_id != preview.base_document.id
        or debug.page_count != preview.base_document.page_count
    ):
        raise ValueError("study_unit_revision_debug_identity_mismatch")
    document = preview.base_document.model_copy(deep=True)
    ranges = Counter((unit.page_start, unit.page_end) for unit in document.study_units)
    existing = {(unit.page_start, unit.page_end): unit for unit in document.study_units}
    units = []
    for index, suggestion in enumerate(preview.suggestions.study_units, start=1):
        key = suggestion.page_start, suggestion.page_end
        before = existing.get(key) if ranges[key] == 1 else None
        units.append(
            StudyUnitRecord(
                id=before.id
                if before is not None
                else f"{document.id}:unit:{preview.operation_id}:{index}",
                document_id=document.id,
                title=suggestion.title.strip(),
                page_start=suggestion.page_start,
                page_end=suggestion.page_end,
                unit_kind=suggestion.unit_kind,
                include_in_plan=suggestion.include_in_plan,
                source_section_ids=[
                    section.id
                    for section in debug.sections
                    if section.page_start <= suggestion.page_end
                    and section.page_end >= suggestion.page_start
                ],
                summary=suggestion.summary,
                confidence=before.confidence if before is not None else 0.95,
            )
        )
    document.study_units = units
    document.study_unit_count = len(units)
    document.sections = [
        DocumentSection(
            id=unit.id,
            document_id=document.id,
            title=unit.title,
            page_start=unit.page_start,
            page_end=unit.page_end,
            level=1,
        )
        for unit in units
        if unit.include_in_plan
    ]
    document.revision += 1
    document.updated_at = updated_at
    report = debug.model_copy(deep=True)
    report.study_units = units
    return StudyUnitRevisionOutputV1(document=document, debug_report=report)


UNIT_REVISION_INPUT = HarnessContractRef(
    name="StudyUnitRevisionInputManifest", version="study-unit-revision-input-v1"
)
UNIT_REVISION_SNAPSHOT = HarnessContractRef(
    name="StudyUnitRevisionSnapshot", version="study-unit-revision-snapshot-v1"
)
UNIT_REVISION_PROMPT = HarnessContractRef(
    name="StudyUnitRevisionPrompt", version="study-unit-revision-prompt-v1"
)
UNIT_REVISION_POLICY = HarnessContractRef(
    name="StudyUnitRevisionPolicy", version="study-unit-revision-policy-v1"
)
UNIT_REVISION_ADAPTER = HarnessContractRef(
    name="StudyUnitRevisionAdapter", version="study-unit-revision-adapter-v1"
)
UNIT_REVISION_OUTPUT = HarnessContractRef(
    name="StudyUnitRevisionOutput", version="study-unit-revision-output-v1"
)
UNIT_REVISION_COMMIT = HarnessContractRef(
    name="StudyUnitRevisionCommittedProjection", version="study-unit-revision-commit-v1"
)
