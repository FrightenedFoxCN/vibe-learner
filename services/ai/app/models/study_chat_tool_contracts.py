from __future__ import annotations

from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


STUDY_CHAT_TOOL_ARGUMENT_CONTRACT_VERSION = "study-chat-tool-arguments-v1"
STUDY_CHAT_TOOL_RESULT_CONTRACT_VERSION = "study-chat-tool-result-v1"


class StudyChatToolContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
    )


ShortText = Annotated[str, Field(min_length=1, max_length=500)]
OptionalShortText = Annotated[str, Field(max_length=500)]
LongText = Annotated[str, Field(min_length=1, max_length=20_000)]


class EmptyToolArgumentsV1(StudyChatToolContractModel):
    pass


class ReadSystemTimeArgumentsV1(EmptyToolArgumentsV1):
    pass


class ReadAffinityStateArgumentsV1(EmptyToolArgumentsV1):
    pass


class ReadLearningPlanProgressArgumentsV1(EmptyToolArgumentsV1):
    pass


class AskMultipleChoiceQuestionArgumentsV1(StudyChatToolContractModel):
    topic: OptionalShortText = ""
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    focus_mode: Literal["detail", "deep_understanding"] = "deep_understanding"
    option_count: int = Field(default=4, ge=3, le=5)


class AskFillBlankQuestionArgumentsV1(StudyChatToolContractModel):
    topic: OptionalShortText = ""
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    focus_mode: Literal["detail", "deep_understanding"] = "deep_understanding"
    blank_count: int = Field(default=1, ge=1, le=3)


class RetrieveMemoryContextArgumentsV1(StudyChatToolContractModel):
    top_k: int = Field(default=4, ge=1, le=8)


class ReadSessionMemoryArgumentsV1(StudyChatToolContractModel):
    key: Annotated[str, Field(max_length=120)] = ""
    limit: int = Field(default=6, ge=1, le=12)


class WriteSessionMemoryArgumentsV1(StudyChatToolContractModel):
    key: Annotated[str, Field(min_length=1, max_length=120)]
    content: Annotated[str, Field(min_length=1, max_length=4_000)]


class ScheduleSessionFollowUpArgumentsV1(StudyChatToolContractModel):
    delay_seconds: int = Field(ge=10, le=1800)
    prompt: LongText
    reason: Annotated[str, Field(max_length=1_200)] = ""


class UpdateAffinityStateArgumentsV1(StudyChatToolContractModel):
    delta: int = Field(ge=-20, le=20)
    reason: Annotated[str, Field(max_length=1_200)] = ""


class UpdateLearningPlanArgumentsV1(StudyChatToolContractModel):
    course_title: ShortText
    note: Annotated[str, Field(max_length=1_200)] = ""


class UpdateLearningPlanProgressArgumentsV1(StudyChatToolContractModel):
    schedule_id: Annotated[str, Field(max_length=160)] = ""
    schedule_ids: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
        default_factory=list,
        max_length=64,
    )
    study_unit_id: Annotated[str, Field(max_length=160)] = ""
    study_unit_ids: list[Annotated[str, Field(min_length=1, max_length=160)]] = Field(
        default_factory=list,
        max_length=24,
    )
    status: Literal["planned", "in_progress", "completed", "blocked", "skipped"]
    note: Annotated[str, Field(max_length=1_200)] = ""

    @model_validator(mode="after")
    def validate_targets(self) -> "UpdateLearningPlanProgressArgumentsV1":
        targets = [
            *([self.schedule_id] if self.schedule_id else []),
            *self.schedule_ids,
            *([self.study_unit_id] if self.study_unit_id else []),
            *self.study_unit_ids,
        ]
        if not targets:
            raise ValueError("study_plan_progress_target_required")
        if len(targets) != len(set(targets)):
            raise ValueError("study_plan_progress_target_duplicate")
        return self


class PageRangeArgumentsV1(StudyChatToolContractModel):
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_page_range(self) -> "PageRangeArgumentsV1":
        if self.page_end < self.page_start:
            raise ValueError("page_end_before_page_start")
        return self


class ReadPageRangeContentArgumentsV1(PageRangeArgumentsV1):
    max_chars: int = Field(default=4_000, ge=800, le=8_000)


class ReadPageRangeImagesArgumentsV1(PageRangeArgumentsV1):
    max_images: int = Field(default=2, ge=1, le=4)


class ReadProjectedPdfContentArgumentsV1(ReadPageRangeContentArgumentsV1):
    pass


class ReadProjectedPdfImagesArgumentsV1(ReadPageRangeImagesArgumentsV1):
    pass


class ProjectUploadedPdfArgumentsV1(StudyChatToolContractModel):
    attachment_id: Annotated[str, Field(min_length=1, max_length=160)]
    page_number: int = Field(default=1, ge=1, le=100_000)


class ProjectUploadedImageArgumentsV1(StudyChatToolContractModel):
    attachment_id: Annotated[str, Field(min_length=1, max_length=160)]


class GenerateProjectedImageArgumentsV1(StudyChatToolContractModel):
    prompt: Annotated[str, Field(min_length=1, max_length=20_000)]
    title: Annotated[str, Field(max_length=500)] = ""
    size: Literal["1024x1024", "1536x1024", "1024x1536", "auto"] = "1024x1024"


class FocusProjectedPdfPageArgumentsV1(StudyChatToolContractModel):
    page_number: int = Field(ge=1, le=100_000)


class HighlightProjectedPdfTextArgumentsV1(FocusProjectedPdfPageArgumentsV1):
    quote_text: Annotated[str, Field(min_length=1, max_length=8_000)]
    label: Annotated[str, Field(max_length=1_200)] = ""
    color: Annotated[str, Field(max_length=32)] = ""


class RegionArgumentsV1(StudyChatToolContractModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)
    label: Annotated[str, Field(max_length=1_200)] = ""
    color: Annotated[str, Field(max_length=32)] = ""


class AnnotateProjectedPdfRegionArgumentsV1(RegionArgumentsV1):
    page_number: int = Field(ge=1, le=100_000)


class AnnotateProjectedImageRegionArgumentsV1(RegionArgumentsV1):
    pass


class ClearProjectedPdfOverlaysArgumentsV1(StudyChatToolContractModel):
    page_number: int | None = Field(default=None, ge=1, le=100_000)


class ClearProjectedImageOverlaysArgumentsV1(EmptyToolArgumentsV1):
    pass


class ReadSceneOverviewArgumentsV1(EmptyToolArgumentsV1):
    pass


class AddSceneArgumentsV1(StudyChatToolContractModel):
    parent_scene_id: Annotated[str, Field(max_length=160)] = ""
    title: ShortText
    scope_label: Annotated[str, Field(min_length=1, max_length=160)]
    summary: Annotated[str, Field(max_length=2_000)] = ""
    atmosphere: Annotated[str, Field(max_length=2_000)] = ""
    rules: Annotated[str, Field(max_length=4_000)] = ""
    entrance: Annotated[str, Field(max_length=2_000)] = ""


class MoveToSceneArgumentsV1(StudyChatToolContractModel):
    scene_id: Annotated[str, Field(min_length=1, max_length=160)]


class AddObjectArgumentsV1(StudyChatToolContractModel):
    scene_id: Annotated[str, Field(max_length=160)] = ""
    name: ShortText
    description: Annotated[str, Field(max_length=4_000)] = ""
    interaction: Annotated[str, Field(max_length=4_000)] = ""
    tags: Annotated[str, Field(max_length=2_000)] = ""


class UpdateObjectDescriptionArgumentsV1(StudyChatToolContractModel):
    object_id: Annotated[str, Field(min_length=1, max_length=160)]
    description: Annotated[str, Field(min_length=1, max_length=4_000)]


class DeleteObjectArgumentsV1(StudyChatToolContractModel):
    object_id: Annotated[str, Field(min_length=1, max_length=160)]


class StudyChatToolResultBaseV1(StudyChatToolContractModel):
    schema_name: Literal["study-chat-tool-result"] = "study-chat-tool-result"
    schema_version: Literal["study-chat-tool-result-v1"] = STUDY_CHAT_TOOL_RESULT_CONTRACT_VERSION
    ok: Literal[True] = True
    summary: Annotated[str, Field(max_length=2_000)] = ""


class StudyChatToolErrorResultV1(StudyChatToolContractModel):
    schema_name: Literal["study-chat-tool-result"] = "study-chat-tool-result"
    schema_version: Literal["study-chat-tool-result-v1"] = STUDY_CHAT_TOOL_RESULT_CONTRACT_VERSION
    ok: Literal[False] = False
    tool_name: Annotated[str, Field(min_length=1, max_length=80)]
    error: Annotated[str, Field(min_length=1, max_length=128)]
    path: list[str | int] = Field(default_factory=list, max_length=16)
    detail: Annotated[str, Field(max_length=1_000)] = ""


class QuestionOptionResultV1(StudyChatToolContractModel):
    key: Annotated[str, Field(min_length=1, max_length=16)]
    text: Annotated[str, Field(min_length=1, max_length=2_000)]


class AskMultipleChoiceQuestionResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["ask_multiple_choice_question"] = "ask_multiple_choice_question"
    question_type: Literal["multiple_choice"] = "multiple_choice"
    difficulty: Literal["easy", "medium", "hard"]
    topic: OptionalShortText = ""
    question: Annotated[str, Field(min_length=1, max_length=8_000)]
    options: list[QuestionOptionResultV1] = Field(min_length=3, max_length=5)
    call_back: bool = True
    answer_key: Annotated[str, Field(min_length=1, max_length=16)]
    explanation: Annotated[str, Field(max_length=8_000)] = ""
    source_context: Annotated[str, Field(max_length=8_000)] = ""


class AskFillBlankQuestionResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["ask_fill_blank_question"] = "ask_fill_blank_question"
    question_type: Literal["fill_blank"] = "fill_blank"
    difficulty: Literal["easy", "medium", "hard"]
    topic: OptionalShortText = ""
    question: Annotated[str, Field(min_length=1, max_length=8_000)]
    call_back: bool = True
    answer: Annotated[str, Field(min_length=1, max_length=8_000)]
    explanation: Annotated[str, Field(max_length=8_000)] = ""
    source_context: Annotated[str, Field(max_length=8_000)] = ""


class MemoryHitResultV1(StudyChatToolContractModel):
    memory_id: Annotated[str, Field(max_length=160)] = ""
    content: Annotated[str, Field(min_length=1, max_length=8_000)]
    source: Annotated[str, Field(max_length=64)] = ""
    # Time of the source record, not an inferred event/effective date.
    created_at: Annotated[str, Field(max_length=64)] = ""


class RetrieveMemoryContextResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["retrieve_memory_context"] = "retrieve_memory_context"
    hit_count: int = Field(ge=0, le=8)
    hits: list[MemoryHitResultV1] = Field(max_length=8)


class SessionMemoryItemResultV1(StudyChatToolContractModel):
    memory_id: Annotated[str, Field(max_length=160)] = ""
    key: Annotated[str, Field(min_length=1, max_length=120)]
    content: Annotated[str, Field(min_length=1, max_length=4_000)]
    committed: bool


class ReadSessionMemoryResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["read_session_memory"] = "read_session_memory"
    memory_items: list[SessionMemoryItemResultV1] = Field(max_length=12)


class PreparedEffectResultV1(StudyChatToolResultBaseV1):
    effect_state: Literal["prepared"] = "prepared"
    committed: Literal[False] = False
    prepared_effect_id: Annotated[str, Field(min_length=1, max_length=160)]


class WriteSessionMemoryResultV1(PreparedEffectResultV1):
    tool_name: Literal["write_session_memory"] = "write_session_memory"
    key: Annotated[str, Field(min_length=1, max_length=120)]


class ReadSystemTimeResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["read_system_time"] = "read_system_time"
    iso_datetime: Annotated[str, Field(min_length=1, max_length=64)]
    date: Annotated[str, Field(min_length=1, max_length=32)]
    time: Annotated[str, Field(min_length=1, max_length=32)]
    timezone: Annotated[str, Field(max_length=64)] = ""
    weekday: Annotated[str, Field(max_length=32)] = ""


class ScheduleSessionFollowUpResultV1(PreparedEffectResultV1):
    tool_name: Literal["schedule_session_follow_up"] = "schedule_session_follow_up"
    requires_client_schedule: Literal[True] = True
    delay_seconds: int = Field(ge=10, le=1800)


class ReadAffinityStateResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["read_affinity_state"] = "read_affinity_state"
    score: int = Field(ge=0, le=100)
    level: Annotated[str, Field(min_length=1, max_length=80)]
    state_summary: Annotated[str, Field(max_length=1_200)] = ""
    committed: bool


class UpdateAffinityStateResultV1(PreparedEffectResultV1):
    tool_name: Literal["update_affinity_state"] = "update_affinity_state"
    score: int = Field(ge=0, le=100)
    level: Annotated[str, Field(min_length=1, max_length=80)]


class PlanProgressItemResultV1(StudyChatToolContractModel):
    item_id: Annotated[str, Field(min_length=1, max_length=160)]
    title: ShortText
    status: Literal["planned", "in_progress", "completed", "blocked", "skipped"]


class ReadLearningPlanProgressResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["read_learning_plan_progress"] = "read_learning_plan_progress"
    course_title: ShortText
    completion_percent: float = Field(ge=0.0, le=100.0)
    schedule: list[PlanProgressItemResultV1] = Field(max_length=64)


class PlanConfirmationResultV1(PreparedEffectResultV1):
    requires_confirmation: Literal[True] = True
    plan_id: Annotated[str, Field(min_length=1, max_length=160)]
    preview_lines: list[Annotated[str, Field(min_length=1, max_length=1_000)]] = Field(
        max_length=64
    )


class UpdateLearningPlanResultV1(PlanConfirmationResultV1):
    tool_name: Literal["update_learning_plan"] = "update_learning_plan"


class UpdateLearningPlanProgressResultV1(PlanConfirmationResultV1):
    tool_name: Literal["update_learning_plan_progress"] = "update_learning_plan_progress"


class ReadPageRangeContentResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["read_page_range_content"] = "read_page_range_content"
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    chunk_count: int = Field(ge=0)
    content: Annotated[str, Field(max_length=8_000)]


class ReadPageRangeImagesResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["read_page_range_images"] = "read_page_range_images"
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    image_count: int = Field(ge=0, le=4)
    page_numbers: list[int] = Field(max_length=4)


class ProjectionPreparedResultV1(PreparedEffectResultV1):
    source_kind: Literal["attachment_pdf", "attachment_image", "generated_image", ""] = ""
    source_id: Annotated[str, Field(max_length=160)] = ""
    page_number: int = Field(default=0, ge=0, le=100_000)


class ProjectUploadedPdfResultV1(ProjectionPreparedResultV1):
    tool_name: Literal["project_uploaded_pdf"] = "project_uploaded_pdf"
    source_kind: Literal["attachment_pdf"] = "attachment_pdf"


class ProjectUploadedImageResultV1(ProjectionPreparedResultV1):
    tool_name: Literal["project_uploaded_image"] = "project_uploaded_image"
    source_kind: Literal["attachment_image"] = "attachment_image"


class GenerateProjectedImageResultV1(ProjectionPreparedResultV1):
    tool_name: Literal["generate_projected_image"] = "generate_projected_image"
    source_kind: Literal["generated_image"] = "generated_image"
    external_effect_state: Literal["completed_uncommitted"] = "completed_uncommitted"
    external_effect_id: Annotated[str, Field(min_length=1, max_length=160)]
    external_effect_read_back: Literal["unsupported"] = "unsupported"
    revised_prompt: Annotated[str, Field(max_length=20_000)] = ""


class ReadProjectedPdfContentResultV1(ReadPageRangeContentResultV1):
    tool_name: Literal["read_projected_pdf_content"] = "read_projected_pdf_content"
    source_kind: Literal["attachment_pdf"] = "attachment_pdf"
    source_id: Annotated[str, Field(min_length=1, max_length=160)]


class ReadProjectedPdfImagesResultV1(ReadPageRangeImagesResultV1):
    tool_name: Literal["read_projected_pdf_images"] = "read_projected_pdf_images"
    source_kind: Literal["attachment_pdf"] = "attachment_pdf"
    source_id: Annotated[str, Field(min_length=1, max_length=160)]


class FocusProjectedPdfPageResultV1(ProjectionPreparedResultV1):
    tool_name: Literal["focus_projected_pdf_page"] = "focus_projected_pdf_page"
    source_kind: Literal["attachment_pdf"] = "attachment_pdf"


class HighlightProjectedPdfTextResultV1(FocusProjectedPdfPageResultV1):
    tool_name: Literal["highlight_projected_pdf_text"] = "highlight_projected_pdf_text"
    match_count: int = Field(ge=1, le=128)


class AnnotateProjectedPdfRegionResultV1(FocusProjectedPdfPageResultV1):
    tool_name: Literal["annotate_projected_pdf_region"] = "annotate_projected_pdf_region"


class ClearProjectedPdfOverlaysResultV1(FocusProjectedPdfPageResultV1):
    tool_name: Literal["clear_projected_pdf_overlays"] = "clear_projected_pdf_overlays"


class AnnotateProjectedImageRegionResultV1(ProjectionPreparedResultV1):
    tool_name: Literal["annotate_projected_image_region"] = "annotate_projected_image_region"


class ClearProjectedImageOverlaysResultV1(ProjectionPreparedResultV1):
    tool_name: Literal["clear_projected_image_overlays"] = "clear_projected_image_overlays"


class SceneToolNodeV1(StudyChatToolContractModel):
    scene_id: Annotated[str, Field(min_length=1, max_length=160)]
    parent_scene_id: Annotated[str, Field(max_length=160)] = ""
    title: ShortText


class SceneToolObjectV1(StudyChatToolContractModel):
    object_id: Annotated[str, Field(min_length=1, max_length=160)]
    scene_id: Annotated[str, Field(min_length=1, max_length=160)]
    name: ShortText
    description: Annotated[str, Field(max_length=4000)] = ""


class ReadSceneOverviewResultV1(StudyChatToolResultBaseV1):
    tool_name: Literal["read_scene_overview"] = "read_scene_overview"
    scene_instance_id: Annotated[str, Field(min_length=1, max_length=160)]
    scene_title: Annotated[str, Field(max_length=500)] = ""
    selected_path: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        max_length=8
    )
    object_names: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        max_length=128
    )
    selected_scene_id: Annotated[str, Field(max_length=160)] = ""
    scenes: list[SceneToolNodeV1] = Field(default_factory=list, max_length=128)
    objects: list[SceneToolObjectV1] = Field(default_factory=list, max_length=128)
    truncated: bool = False


class ScenePreparedResultV1(PreparedEffectResultV1):
    scene_instance_id: Annotated[str, Field(min_length=1, max_length=160)]
    selected_scene_id: Annotated[str, Field(max_length=160)] = ""
    added_scene_id: Annotated[str, Field(max_length=160)] = ""
    object_id: Annotated[str, Field(max_length=160)] = ""


class AddSceneResultV1(ScenePreparedResultV1):
    tool_name: Literal["add_scene"] = "add_scene"


class MoveToSceneResultV1(ScenePreparedResultV1):
    tool_name: Literal["move_to_scene"] = "move_to_scene"


class AddObjectResultV1(ScenePreparedResultV1):
    tool_name: Literal["add_object"] = "add_object"


class UpdateObjectDescriptionResultV1(ScenePreparedResultV1):
    tool_name: Literal["update_object_description"] = "update_object_description"


class DeleteObjectResultV1(ScenePreparedResultV1):
    tool_name: Literal["delete_object"] = "delete_object"


StudyChatToolArguments: TypeAlias = (
    AskMultipleChoiceQuestionArgumentsV1
    | AskFillBlankQuestionArgumentsV1
    | RetrieveMemoryContextArgumentsV1
    | ReadSessionMemoryArgumentsV1
    | WriteSessionMemoryArgumentsV1
    | ReadSystemTimeArgumentsV1
    | ScheduleSessionFollowUpArgumentsV1
    | ReadAffinityStateArgumentsV1
    | UpdateAffinityStateArgumentsV1
    | ReadLearningPlanProgressArgumentsV1
    | UpdateLearningPlanArgumentsV1
    | UpdateLearningPlanProgressArgumentsV1
    | ReadPageRangeContentArgumentsV1
    | ReadPageRangeImagesArgumentsV1
    | ReadProjectedPdfContentArgumentsV1
    | ReadProjectedPdfImagesArgumentsV1
    | ProjectUploadedPdfArgumentsV1
    | ProjectUploadedImageArgumentsV1
    | GenerateProjectedImageArgumentsV1
    | FocusProjectedPdfPageArgumentsV1
    | HighlightProjectedPdfTextArgumentsV1
    | AnnotateProjectedPdfRegionArgumentsV1
    | ClearProjectedPdfOverlaysArgumentsV1
    | AnnotateProjectedImageRegionArgumentsV1
    | ClearProjectedImageOverlaysArgumentsV1
    | ReadSceneOverviewArgumentsV1
    | AddSceneArgumentsV1
    | MoveToSceneArgumentsV1
    | AddObjectArgumentsV1
    | UpdateObjectDescriptionArgumentsV1
    | DeleteObjectArgumentsV1
)


STUDY_CHAT_TOOL_ARGUMENT_MODELS: dict[str, type[StudyChatToolContractModel]] = {
    "ask_multiple_choice_question": AskMultipleChoiceQuestionArgumentsV1,
    "ask_fill_blank_question": AskFillBlankQuestionArgumentsV1,
    "retrieve_memory_context": RetrieveMemoryContextArgumentsV1,
    "read_session_memory": ReadSessionMemoryArgumentsV1,
    "write_session_memory": WriteSessionMemoryArgumentsV1,
    "read_system_time": ReadSystemTimeArgumentsV1,
    "schedule_session_follow_up": ScheduleSessionFollowUpArgumentsV1,
    "read_affinity_state": ReadAffinityStateArgumentsV1,
    "update_affinity_state": UpdateAffinityStateArgumentsV1,
    "read_learning_plan_progress": ReadLearningPlanProgressArgumentsV1,
    "update_learning_plan": UpdateLearningPlanArgumentsV1,
    "update_learning_plan_progress": UpdateLearningPlanProgressArgumentsV1,
    "read_page_range_content": ReadPageRangeContentArgumentsV1,
    "read_page_range_images": ReadPageRangeImagesArgumentsV1,
    "project_uploaded_pdf": ProjectUploadedPdfArgumentsV1,
    "project_uploaded_image": ProjectUploadedImageArgumentsV1,
    "generate_projected_image": GenerateProjectedImageArgumentsV1,
    "read_projected_pdf_content": ReadProjectedPdfContentArgumentsV1,
    "read_projected_pdf_images": ReadProjectedPdfImagesArgumentsV1,
    "focus_projected_pdf_page": FocusProjectedPdfPageArgumentsV1,
    "highlight_projected_pdf_text": HighlightProjectedPdfTextArgumentsV1,
    "annotate_projected_pdf_region": AnnotateProjectedPdfRegionArgumentsV1,
    "clear_projected_pdf_overlays": ClearProjectedPdfOverlaysArgumentsV1,
    "annotate_projected_image_region": AnnotateProjectedImageRegionArgumentsV1,
    "clear_projected_image_overlays": ClearProjectedImageOverlaysArgumentsV1,
    "read_scene_overview": ReadSceneOverviewArgumentsV1,
    "add_scene": AddSceneArgumentsV1,
    "move_to_scene": MoveToSceneArgumentsV1,
    "add_object": AddObjectArgumentsV1,
    "update_object_description": UpdateObjectDescriptionArgumentsV1,
    "delete_object": DeleteObjectArgumentsV1,
}


STUDY_CHAT_TOOL_RESULT_MODELS: dict[str, type[StudyChatToolContractModel]] = {
    "ask_multiple_choice_question": AskMultipleChoiceQuestionResultV1,
    "ask_fill_blank_question": AskFillBlankQuestionResultV1,
    "retrieve_memory_context": RetrieveMemoryContextResultV1,
    "read_session_memory": ReadSessionMemoryResultV1,
    "write_session_memory": WriteSessionMemoryResultV1,
    "read_system_time": ReadSystemTimeResultV1,
    "schedule_session_follow_up": ScheduleSessionFollowUpResultV1,
    "read_affinity_state": ReadAffinityStateResultV1,
    "update_affinity_state": UpdateAffinityStateResultV1,
    "read_learning_plan_progress": ReadLearningPlanProgressResultV1,
    "update_learning_plan": UpdateLearningPlanResultV1,
    "update_learning_plan_progress": UpdateLearningPlanProgressResultV1,
    "read_page_range_content": ReadPageRangeContentResultV1,
    "read_page_range_images": ReadPageRangeImagesResultV1,
    "project_uploaded_pdf": ProjectUploadedPdfResultV1,
    "project_uploaded_image": ProjectUploadedImageResultV1,
    "generate_projected_image": GenerateProjectedImageResultV1,
    "read_projected_pdf_content": ReadProjectedPdfContentResultV1,
    "read_projected_pdf_images": ReadProjectedPdfImagesResultV1,
    "focus_projected_pdf_page": FocusProjectedPdfPageResultV1,
    "highlight_projected_pdf_text": HighlightProjectedPdfTextResultV1,
    "annotate_projected_pdf_region": AnnotateProjectedPdfRegionResultV1,
    "clear_projected_pdf_overlays": ClearProjectedPdfOverlaysResultV1,
    "annotate_projected_image_region": AnnotateProjectedImageRegionResultV1,
    "clear_projected_image_overlays": ClearProjectedImageOverlaysResultV1,
    "read_scene_overview": ReadSceneOverviewResultV1,
    "add_scene": AddSceneResultV1,
    "move_to_scene": MoveToSceneResultV1,
    "add_object": AddObjectResultV1,
    "update_object_description": UpdateObjectDescriptionResultV1,
    "delete_object": DeleteObjectResultV1,
}
