from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


PLANNING_TOOL_ARGUMENT_CONTRACT_VERSION = "planning-tool-arguments-v1"
PLANNING_TOOL_RESULT_CONTRACT_VERSION = "planning-tool-result-v1"
LEARNING_PLAN_PROPOSAL_SCHEMA_NAME = "learning-plan-proposal"
LEARNING_PLAN_PROPOSAL_SCHEMA_VERSION = "learning-plan-proposal-v1"


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
