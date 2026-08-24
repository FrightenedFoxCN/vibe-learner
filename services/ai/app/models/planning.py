from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    LearningPlanRecord,
    PlanGenerationTraceRecord,
    SceneProfileRecord,
)


PLANNING_TOOL_ARGUMENT_CONTRACT_VERSION = "planning-tool-arguments-v1"
PLANNING_TOOL_RESULT_CONTRACT_VERSION = "planning-tool-result-v1"
LEARNING_PLAN_PROPOSAL_SCHEMA_NAME = "learning-plan-proposal"
LEARNING_PLAN_PROPOSAL_SCHEMA_VERSION = "learning-plan-proposal-v1"
LEARNING_PLAN_OPERATION_REQUEST_SCHEMA_VERSION = "learning-plan-operation-request-v1"
LEARNING_PLAN_OPERATION_FINGERPRINT_VERSION = "learning-plan-operation-fingerprint-v1"
LEARNING_PLAN_COMMITTED_PROJECTION_VERSION = "learning-plan-committed-projection-v1"
LEARNING_PLAN_COMMIT_CONTRACT_VERSION = "learning-plan-commit-v1"


class _StrictPlanningModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


ShortText = Annotated[str, Field(min_length=1, max_length=500)]
LongText = Annotated[str, Field(min_length=1, max_length=4000)]
OptionalShortText = Annotated[str, Field(max_length=500)]
TypedPathPart: TypeAlias = str | int


class GetStudyUnitDetailArgumentsV1(_StrictPlanningModel):
    study_unit_id: ShortText
    focus: OptionalShortText = ""


class AskPlanningQuestionArgumentsV1(_StrictPlanningModel):
    question: ShortText
    reason: Annotated[str, Field(max_length=1000)] = ""
    assumptions: list[ShortText] = Field(default_factory=list, max_length=8)


class EstimatePlanCompletionArgumentsV1(_StrictPlanningModel):
    focus: OptionalShortText = ""


class StudyUnitRevisionProposalV1(_StrictPlanningModel):
    title: ShortText
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    include_in_plan: bool = True
    summary: Annotated[str, Field(max_length=2000)] = ""

    @model_validator(mode="after")
    def validate_range(self) -> "StudyUnitRevisionProposalV1":
        if self.page_end < self.page_start:
            raise ValueError("page_end_before_page_start")
        return self


class ReviseStudyUnitsArgumentsV1(_StrictPlanningModel):
    study_units: list[StudyUnitRevisionProposalV1] = Field(min_length=1, max_length=24)
    rationale: Annotated[str, Field(max_length=2000)] = ""


class ReadPageRangeContentArgumentsV1(_StrictPlanningModel):
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    max_chars: int = Field(default=3000, ge=500, le=6000)

    @model_validator(mode="after")
    def validate_range(self) -> "ReadPageRangeContentArgumentsV1":
        if self.page_end < self.page_start:
            raise ValueError("page_end_before_page_start")
        return self


class ReadPageRangeImagesArgumentsV1(_StrictPlanningModel):
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    max_images: int = Field(default=3, ge=1, le=4)

    @model_validator(mode="after")
    def validate_range(self) -> "ReadPageRangeImagesArgumentsV1":
        if self.page_end < self.page_start:
            raise ValueError("page_end_before_page_start")
        return self


PlanningToolArguments: TypeAlias = (
    GetStudyUnitDetailArgumentsV1
    | AskPlanningQuestionArgumentsV1
    | EstimatePlanCompletionArgumentsV1
    | ReviseStudyUnitsArgumentsV1
    | ReadPageRangeContentArgumentsV1
    | ReadPageRangeImagesArgumentsV1
)


class PlanningToolResultBaseV1(_StrictPlanningModel):
    schema_name: Literal["planning-tool-result"] = "planning-tool-result"
    schema_version: Literal["planning-tool-result-v1"] = PLANNING_TOOL_RESULT_CONTRACT_VERSION
    ok: Literal[True] = True


class PlanningToolErrorResultV1(_StrictPlanningModel):
    schema_name: Literal["planning-tool-result"] = "planning-tool-result"
    schema_version: Literal["planning-tool-result-v1"] = PLANNING_TOOL_RESULT_CONTRACT_VERSION
    ok: Literal[False] = False
    tool_name: str = Field(max_length=80)
    error: str = Field(min_length=1, max_length=128)
    path: list[TypedPathPart] = Field(default_factory=list, max_length=16)
    detail: str = Field(default="", max_length=1000)
    study_unit_id: str = Field(default="", max_length=128)


class RelatedSectionResultV1(_StrictPlanningModel):
    section_id: str
    title: str
    level: int
    page_start: int
    page_end: int


class ChunkExcerptResultV1(_StrictPlanningModel):
    chunk_id: str
    section_id: str
    page_start: int
    page_end: int
    char_count: int
    content: str


class StudyUnitDetailResultV1(_StrictPlanningModel):
    unit_id: str
    title: str
    page_start: int
    page_end: int
    summary: str
    unit_kind: str
    include_in_plan: bool
    related_section_ids: list[str]
    subsection_titles: list[str]
    related_sections: list[RelatedSectionResultV1]
    chunk_count: int
    chunk_excerpts: list[ChunkExcerptResultV1]


class GetStudyUnitDetailResultV1(PlanningToolResultBaseV1):
    tool_name: Literal["get_study_unit_detail"] = "get_study_unit_detail"
    requested_focus: str
    detail: StudyUnitDetailResultV1


class AskPlanningQuestionResultV1(PlanningToolResultBaseV1):
    tool_name: Literal["ask_planning_question"] = "ask_planning_question"
    question_id: str
    question: str
    reason: str
    assumptions: list[str]


class PlanCompletionSignalsV1(_StrictPlanningModel):
    plannable_unit_count: int = Field(ge=0)
    units_with_subsections: int = Field(ge=0)
    total_subsections: int = Field(default=0, ge=0)
    detail_coverage_ratio: float = Field(ge=0, le=1)
    richness_ratio: float = Field(default=0, ge=0, le=1)


class EstimatePlanCompletionResultV1(PlanningToolResultBaseV1):
    tool_name: Literal["estimate_plan_completion"] = "estimate_plan_completion"
    completion_score: int = Field(ge=0, le=100)
    completion_label: str
    focus: str = ""
    signals: PlanCompletionSignalsV1
    missing_items: list[str]
    recommendations: list[str]


class RevisedStudyUnitResultV1(_StrictPlanningModel):
    unit_id: str
    title: str
    page_start: int
    page_end: int
    include_in_plan: bool


class ReviseStudyUnitsResultV1(PlanningToolResultBaseV1):
    tool_name: Literal["revise_study_units"] = "revise_study_units"
    rationale: str
    study_unit_count: int = Field(ge=1, le=24)
    plannable_count: int = Field(ge=0, le=24)
    study_units: list[RevisedStudyUnitResultV1] = Field(min_length=1, max_length=24)


class ReadPageRangeContentResultV1(PlanningToolResultBaseV1):
    tool_name: Literal["read_page_range_content"] = "read_page_range_content"
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    chunk_count: int = Field(ge=0)
    content: str


class ReadPageRangeImagesResultV1(PlanningToolResultBaseV1):
    tool_name: Literal["read_page_range_images"] = "read_page_range_images"
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    image_count: int = Field(ge=0, le=4)
    page_numbers: list[int] = Field(max_length=4)


PlanningToolSuccessResult: TypeAlias = (
    GetStudyUnitDetailResultV1
    | AskPlanningQuestionResultV1
    | EstimatePlanCompletionResultV1
    | ReviseStudyUnitsResultV1
    | ReadPageRangeContentResultV1
    | ReadPageRangeImagesResultV1
)
PlanningToolWireResult: TypeAlias = PlanningToolSuccessResult | PlanningToolErrorResultV1


class PlanContentSliceProposalV1(_StrictPlanningModel):
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    source_section_ids: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_range_and_refs(self) -> "PlanContentSliceProposalV1":
        if self.page_end < self.page_start:
            raise ValueError("page_end_before_page_start")
        if len(set(self.source_section_ids)) != len(self.source_section_ids):
            raise ValueError("duplicate_source_section_id")
        return self


class PlanScheduleChapterProposalV1(_StrictPlanningModel):
    title: ShortText
    anchor_page_start: int = Field(ge=1)
    anchor_page_end: int = Field(ge=1)
    source_section_ids: list[str] = Field(default_factory=list, max_length=32)
    content_slices: list[PlanContentSliceProposalV1] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_range_and_refs(self) -> "PlanScheduleChapterProposalV1":
        if self.anchor_page_end < self.anchor_page_start:
            raise ValueError("anchor_page_end_before_start")
        if len(set(self.source_section_ids)) != len(self.source_section_ids):
            raise ValueError("duplicate_source_section_id")
        return self


class PlanScheduleItemProposalV1(_StrictPlanningModel):
    unit_id: str = Field(min_length=1, max_length=128)
    title: ShortText
    focus: Annotated[str, Field(min_length=1, max_length=2000)]
    activity_type: Literal["learn", "review"]
    schedule_chapters: list[PlanScheduleChapterProposalV1] = Field(min_length=1, max_length=24)


class LearningPlanProposalV1(_StrictPlanningModel):
    schema_name: Literal["learning-plan-proposal"]
    schema_version: Literal["learning-plan-proposal-v1"]
    course_title: ShortText
    overview: LongText
    today_tasks: list[ShortText] = Field(min_length=1, max_length=12)
    schedule: list[PlanScheduleItemProposalV1] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def validate_unique_unit_refs(self) -> "LearningPlanProposalV1":
        unit_ids = [item.unit_id for item in self.schedule]
        if len(set(unit_ids)) != len(unit_ids):
            raise ValueError("duplicate_schedule_unit_ref")
        return self


PLANNING_TOOL_ARGUMENT_MODELS: dict[str, type[_StrictPlanningModel]] = {
    "get_study_unit_detail": GetStudyUnitDetailArgumentsV1,
    "ask_planning_question": AskPlanningQuestionArgumentsV1,
    "estimate_plan_completion": EstimatePlanCompletionArgumentsV1,
    "revise_study_units": ReviseStudyUnitsArgumentsV1,
    "read_page_range_content": ReadPageRangeContentArgumentsV1,
    "read_page_range_images": ReadPageRangeImagesArgumentsV1,
}

PLANNING_TOOL_RESULT_MODELS: dict[str, type[_StrictPlanningModel]] = {
    "get_study_unit_detail": GetStudyUnitDetailResultV1,
    "ask_planning_question": AskPlanningQuestionResultV1,
    "estimate_plan_completion": EstimatePlanCompletionResultV1,
    "revise_study_units": ReviseStudyUnitsResultV1,
    "read_page_range_content": ReadPageRangeContentResultV1,
    "read_page_range_images": ReadPageRangeImagesResultV1,
}


class LearningPlanOperationStatus(str, Enum):
    RUNNING = "running"
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"
    INTERRUPTED = "interrupted"
    UNCERTAIN = "uncertain"


class LearningPlanProjectionState(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"


class LearningPlanOperationRequestV1(_StrictPlanningModel):
    schema_version: Literal["learning-plan-operation-request-v1"] = (
        LEARNING_PLAN_OPERATION_REQUEST_SCHEMA_VERSION
    )
    client_request_id: str = Field(min_length=1, max_length=80)
    document_id: str = Field(default="", max_length=64)
    persona_id: str = Field(min_length=1, max_length=64)
    objective: str = Field(min_length=1, max_length=12000)
    scene_profile_summary: str = Field(default="", max_length=4000)
    scene_profile: SceneProfileRecord | None = None
    expected_document_updated_at: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def validate_document_revision(self) -> "LearningPlanOperationRequestV1":
        if self.document_id and not self.expected_document_updated_at:
            raise ValueError("expected_document_updated_at_required")
        if not self.document_id and self.expected_document_updated_at:
            raise ValueError("goal_only_request_has_document_revision")
        return self


class LearningPlanCommittedProjectionV1(_StrictPlanningModel):
    schema_version: Literal["learning-plan-committed-projection-v1"] = (
        LEARNING_PLAN_COMMITTED_PROJECTION_VERSION
    )
    operation_id: str
    client_request_id: str
    plan_id: str
    document_id: str
    plan: LearningPlanRecord
    document: DocumentRecord | None = None
    debug_report: DocumentDebugRecord | None = None
    trace: PlanGenerationTraceRecord | None = None
    plan_digest: str
    document_digest: str = ""
    debug_digest: str = ""
    trace_digest: str = ""

    @model_validator(mode="after")
    def validate_projection(self) -> "LearningPlanCommittedProjectionV1":
        if self.plan.id != self.plan_id:
            raise ValueError("committed_plan_identity_mismatch")
        if self.plan.document_id != self.document_id:
            raise ValueError("committed_plan_document_identity_mismatch")
        if (
            planning_projection_digest(self.plan.model_dump(mode="json"))
            != self.plan_digest
        ):
            raise ValueError("committed_plan_digest_mismatch")
        if self.document_id:
            if self.document is None:
                raise ValueError("committed_document_projection_required")
            if self.document.id != self.document_id:
                raise ValueError("committed_document_identity_mismatch")
            if (
                planning_projection_digest(self.document.model_dump(mode="json"))
                != self.document_digest
            ):
                raise ValueError("committed_document_digest_mismatch")
            if self.debug_report is not None:
                if self.debug_report.document_id != self.document_id:
                    raise ValueError("committed_debug_identity_mismatch")
                if planning_projection_digest(
                    self.debug_report.model_dump(mode="json")
                ) != self.debug_digest:
                    raise ValueError("committed_debug_digest_mismatch")
            elif self.debug_digest:
                raise ValueError("committed_debug_digest_without_projection")
        elif self.document is not None or self.debug_report is not None:
            raise ValueError("goal_only_commit_has_document_projection")
        if self.trace is not None:
            if self.trace.plan_id != self.plan_id:
                raise ValueError("committed_trace_plan_identity_mismatch")
            if (
                planning_projection_digest(self.trace.model_dump(mode="json"))
                != self.trace_digest
            ):
                raise ValueError("committed_trace_digest_mismatch")
        elif self.trace_digest:
            raise ValueError("committed_trace_digest_without_projection")
        return self


class LearningPlanOperationRecord(_StrictPlanningModel):
    operation_id: str
    client_request_id: str
    document_id: str
    persona_id: str
    request_schema_version: str
    fingerprint_contract_version: str
    request_fingerprint: str
    request_payload: LearningPlanOperationRequestV1
    base_document_updated_at: str = ""
    base_document_digest: str = ""
    base_debug_digest: str = ""
    status: LearningPlanOperationStatus
    projection_state: LearningPlanProjectionState
    provider_started_at: str = ""
    plan_id: str = ""
    commit_contract_version: str = ""
    committed_projection_digest: str = ""
    committed_projection: LearningPlanCommittedProjectionV1 | None = None
    error_code: str = ""
    created_at: str
    updated_at: str
    completed_at: str = ""

    @model_validator(mode="after")
    def validate_operation(self) -> "LearningPlanOperationRecord":
        if self.request_schema_version != LEARNING_PLAN_OPERATION_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported_learning_plan_request_schema")
        if self.fingerprint_contract_version != LEARNING_PLAN_OPERATION_FINGERPRINT_VERSION:
            raise ValueError("unsupported_learning_plan_fingerprint_contract")
        if self.request_payload.client_request_id != self.client_request_id:
            raise ValueError("learning_plan_request_identity_mismatch")
        if self.request_payload.document_id != self.document_id:
            raise ValueError("learning_plan_document_identity_mismatch")
        if self.request_payload.persona_id != self.persona_id:
            raise ValueError("learning_plan_persona_identity_mismatch")
        if learning_plan_request_fingerprint(self.request_payload) != self.request_fingerprint:
            raise ValueError("learning_plan_request_fingerprint_mismatch")
        if self.document_id:
            if not self.base_document_updated_at or not self.base_document_digest:
                raise ValueError("learning_plan_document_base_evidence_missing")
        elif (
            self.base_document_updated_at
            or self.base_document_digest
            or self.base_debug_digest
        ):
            raise ValueError("goal_only_plan_has_document_base_evidence")
        if self.status == LearningPlanOperationStatus.RUNNING:
            if self.projection_state != LearningPlanProjectionState.PENDING:
                raise ValueError("running_plan_projection_must_be_pending")
            if self.completed_at or self.error_code or self.committed_projection is not None:
                raise ValueError("running_plan_operation_has_terminal_evidence")
        elif self.status == LearningPlanOperationStatus.COMMITTED:
            if self.projection_state != LearningPlanProjectionState.COMMITTED:
                raise ValueError("committed_plan_projection_required")
            if (
                not self.completed_at
                or not self.plan_id
                or self.commit_contract_version != LEARNING_PLAN_COMMIT_CONTRACT_VERSION
                or not self.committed_projection_digest
                or self.committed_projection is None
                or self.error_code
            ):
                raise ValueError("committed_plan_operation_evidence_incomplete")
            projection_digest = planning_projection_digest(
                self.committed_projection.model_dump(mode="json")
            )
            if projection_digest != self.committed_projection_digest:
                raise ValueError("committed_plan_projection_digest_mismatch")
        else:
            if self.projection_state != LearningPlanProjectionState.NOT_COMMITTED:
                raise ValueError("terminal_plan_failure_must_be_not_committed")
            if (
                not self.completed_at
                or not self.error_code
                or self.plan_id
                or self.commit_contract_version
                or self.committed_projection_digest
                or self.committed_projection is not None
            ):
                raise ValueError("failed_plan_operation_evidence_invalid")
        return self


def learning_plan_request_fingerprint(payload: LearningPlanOperationRequestV1) -> str:
    return planning_projection_digest(payload.model_dump(mode="json"))


def planning_projection_digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
