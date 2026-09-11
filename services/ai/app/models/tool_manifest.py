from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.harness import (
    HarnessContractRef,
    HarnessStage,
    HarnessWorkflow,
    require_versioned_harness_contract,
)
from app.models.planning import (
    PLANNING_TOOL_ARGUMENT_CONTRACT_VERSION,
    PLANNING_TOOL_ARGUMENT_MODELS,
    PLANNING_TOOL_RESULT_CONTRACT_VERSION,
    PLANNING_TOOL_RESULT_MODELS,
)
from app.models.study_chat_tool_contracts import (
    STUDY_CHAT_TOOL_ARGUMENT_CONTRACT_VERSION,
    STUDY_CHAT_TOOL_ARGUMENT_MODELS,
    STUDY_CHAT_TOOL_RESULT_CONTRACT_VERSION,
    STUDY_CHAT_TOOL_RESULT_MODELS,
)


TOOL_MANIFEST_SCHEMA_VERSION = "tool-manifest-v1"
TOOL_PROVIDER_PROJECTION_CONTRACT_VERSION = "openai-function-projection-v1"
TOOL_RUNTIME_ADAPTER_CONTRACT_VERSION = "tool-runtime-adapter-v1"


class ToolManifestModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


class ToolLifecycleStatus(StrEnum):
    ACTIVE = "active"
    RETIRED = "retired"


class ToolEffectBoundaryKind(StrEnum):
    PURE_READ = "pure_read"
    DATABASE_WRITE = "database_write"
    FILE_STAGING = "file_staging"
    EXTERNAL_CALL = "external_call"


class ToolEffectCommitScope(StrEnum):
    NONE = "none"
    PARENT_OPERATION = "parent_operation"
    PREPARED_EFFECT = "prepared_effect"
    IMMEDIATE_EXTERNAL = "immediate_external"


class ToolSensitivityLevel(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    PROTECTED = "protected"
    SERVER_PRIVATE = "server_private"


class ToolResultProjectionMode(StrEnum):
    FULL = "full"
    REDACTED = "redacted"
    CONTENT_FREE = "content_free"
    OMITTED = "omitted"


class ToolRuntimeMode(StrEnum):
    SERIAL = "serial"


class ToolDependency(StrEnum):
    PLANNING_CONTEXT = "planning_context"
    PLANNING_DETAIL_MAP = "planning_detail_map"
    DOCUMENT_DEBUG = "document_debug"
    DOCUMENT_FILE = "document_file"
    MEMORY_HITS = "memory_hits"
    STUDY_SESSION = "study_session"
    EFFECT_COLLECTOR = "effect_collector"
    LEARNING_PLAN = "learning_plan"
    LEARNER_ATTACHMENTS = "learner_attachments"
    PROJECTED_PDF = "projected_pdf"
    PROJECTED_IMAGE = "projected_image"
    SESSION_SCENE = "session_scene"
    IMAGE_PROVIDER = "image_provider"


class ToolProviderCapability(StrEnum):
    FUNCTION_CALLING = "function_calling"
    MULTIMODAL_INPUT = "multimodal_input"
    IMAGE_GENERATION = "image_generation"


class ToolEffectStepV1(ToolManifestModel):
    sequence: int = Field(ge=0, le=7)
    boundary_kind: ToolEffectBoundaryKind
    commit_scope: ToolEffectCommitScope
    adapter: HarnessContractRef | None = None

    @model_validator(mode="after")
    def validate_boundary(self) -> "ToolEffectStepV1":
        if self.boundary_kind == ToolEffectBoundaryKind.PURE_READ:
            if self.commit_scope != ToolEffectCommitScope.NONE or self.adapter is not None:
                raise ValueError("tool_manifest_pure_read_effect_invalid")
        elif self.adapter is None or self.commit_scope == ToolEffectCommitScope.NONE:
            raise ValueError("tool_manifest_effect_adapter_required")
        if (
            self.boundary_kind == ToolEffectBoundaryKind.EXTERNAL_CALL
            and self.commit_scope != ToolEffectCommitScope.IMMEDIATE_EXTERNAL
        ):
            raise ValueError("tool_manifest_external_commit_scope_invalid")
        if self.adapter is not None:
            require_versioned_harness_contract(self.adapter)
        return self


class ToolSensitivityPolicyV1(ToolManifestModel):
    arguments: ToolSensitivityLevel
    internal_result: ToolSensitivityLevel
    provider_result: ToolSensitivityLevel
    trace_projection: ToolResultProjectionMode
    public_projection: ToolResultProjectionMode


class ToolExecutionBudgetV1(ToolManifestModel):
    max_calls_per_operation: int = Field(ge=1, le=64)
    max_calls_per_round: int = Field(ge=1, le=8)
    timeout_ms: int = Field(ge=100, le=120_000)
    max_argument_bytes: int = Field(ge=128, le=1_000_000)
    max_internal_result_bytes: int = Field(ge=128, le=4_000_000)
    max_provider_result_bytes: int = Field(ge=128, le=1_000_000)
    max_public_result_bytes: int = Field(ge=128, le=1_000_000)

    @model_validator(mode="after")
    def validate_call_budget(self) -> "ToolExecutionBudgetV1":
        if self.max_calls_per_round > self.max_calls_per_operation:
            raise ValueError("tool_manifest_round_budget_exceeds_operation")
        return self


class ToolParallelPolicyV1(ToolManifestModel):
    runtime_mode: Literal[ToolRuntimeMode.SERIAL] = ToolRuntimeMode.SERIAL
    parallel_safe: Literal[False] = False
    stable_result_order: Literal["provider_call_order"] = "provider_call_order"
    conflicts: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_conflicts(self) -> "ToolParallelPolicyV1":
        if self.conflicts != tuple(sorted(self.conflicts)) or len(
            self.conflicts
        ) != len(set(self.conflicts)):
            raise ValueError("tool_manifest_parallel_conflicts_not_canonical")
        if any(
            not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", conflict)
            for conflict in self.conflicts
        ):
            raise ValueError("tool_manifest_parallel_conflict_invalid")
        return self


class ToolDisplayV1(ToolManifestModel):
    label: str = Field(min_length=1, max_length=120)
    category: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    category_label: str = Field(min_length=1, max_length=120)
    provider_description: str = Field(min_length=1, max_length=1_000)


class ToolManifestEntryV1(ToolManifestModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$")
    workflow: HarnessWorkflow
    offered_in_stage: HarnessStage
    execution_stage: HarnessStage
    canonical_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    status: ToolLifecycleStatus = ToolLifecycleStatus.ACTIVE
    aliases: tuple[str, ...] = ()
    replacement_key: str | None = None
    owner_module: str = Field(pattern=r"^[A-Za-z0-9_.]+$")
    runtime_adapter: HarnessContractRef
    display: ToolDisplayV1
    input_contract: HarnessContractRef
    result_contract: HarnessContractRef
    provider_projection_contract: HarnessContractRef
    provider_parameters_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    effect_steps: tuple[ToolEffectStepV1, ...] = Field(min_length=1, max_length=8)
    sensitivity: ToolSensitivityPolicyV1
    budget: ToolExecutionBudgetV1
    parallel: ToolParallelPolicyV1
    dependencies: tuple[ToolDependency, ...] = ()
    provider_capabilities: tuple[ToolProviderCapability, ...] = (
        ToolProviderCapability.FUNCTION_CALLING,
    )

    @model_validator(mode="after")
    def validate_entry(self) -> "ToolManifestEntryV1":
        expected_key = f"{self.workflow.value}:{self.execution_stage.value}:{self.canonical_name}"
        if self.key != expected_key:
            raise ValueError("tool_manifest_key_mismatch")
        expected_route = {
            HarnessWorkflow.PLANNING: (
                HarnessStage.PLAN_GENERATION,
                HarnessStage.PLANNING_TOOL_EXECUTION,
            ),
            HarnessWorkflow.STUDY_CHAT: (
                HarnessStage.STUDY_CHAT_REPLY,
                HarnessStage.STUDY_CHAT_REPLY,
            ),
        }.get(self.workflow)
        if expected_route != (self.offered_in_stage, self.execution_stage):
            raise ValueError("tool_manifest_workflow_stage_mismatch")
        for contract in (
            self.runtime_adapter,
            self.input_contract,
            self.result_contract,
            self.provider_projection_contract,
        ):
            require_versioned_harness_contract(contract)
        if self.status == ToolLifecycleStatus.ACTIVE and self.replacement_key is not None:
            raise ValueError("tool_manifest_active_replacement_forbidden")
        if self.status == ToolLifecycleStatus.RETIRED and not self.replacement_key:
            raise ValueError("tool_manifest_retired_replacement_required")
        if len(self.aliases) != len(set(self.aliases)) or self.canonical_name in self.aliases:
            raise ValueError("tool_manifest_alias_invalid")
        if any(not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", alias) for alias in self.aliases):
            raise ValueError("tool_manifest_alias_invalid")
        if tuple(sorted(self.aliases)) != self.aliases:
            raise ValueError("tool_manifest_aliases_not_sorted")
        if [step.sequence for step in self.effect_steps] != list(range(len(self.effect_steps))):
            raise ValueError("tool_manifest_effect_sequence_invalid")
        if len(self.dependencies) != len(set(self.dependencies)):
            raise ValueError("tool_manifest_dependency_duplicate")
        if tuple(sorted(self.dependencies, key=lambda item: item.value)) != self.dependencies:
            raise ValueError("tool_manifest_dependencies_not_sorted")
        if len(self.provider_capabilities) != len(set(self.provider_capabilities)):
            raise ValueError("tool_manifest_provider_capability_duplicate")
        if (
            tuple(sorted(self.provider_capabilities, key=lambda item: item.value))
            != self.provider_capabilities
        ):
            raise ValueError("tool_manifest_provider_capabilities_not_sorted")
        if ToolProviderCapability.FUNCTION_CALLING not in self.provider_capabilities:
            raise ValueError("tool_manifest_function_calling_capability_required")
        return self


class ToolManifestRegistryV1(ToolManifestModel):
    schema_name: Literal["ToolManifestRegistry"] = "ToolManifestRegistry"
    schema_version: Literal["tool-manifest-v1"] = TOOL_MANIFEST_SCHEMA_VERSION
    tools: tuple[ToolManifestEntryV1, ...]

    @model_validator(mode="after")
    def validate_registry(self) -> "ToolManifestRegistryV1":
        keys = [entry.key for entry in self.tools]
        if keys != sorted(keys) or len(keys) != len(set(keys)):
            raise ValueError("tool_manifest_registry_keys_invalid")
        active_names: dict[tuple[HarnessWorkflow, HarnessStage, str], str] = {}
        for entry in self.tools:
            for name in (entry.canonical_name, *entry.aliases):
                scoped = (entry.workflow, entry.offered_in_stage, name)
                if scoped in active_names:
                    raise ValueError("tool_manifest_stage_name_collision")
                active_names[scoped] = entry.key
        replacements = {entry.key: entry for entry in self.tools}
        for entry in self.tools:
            if entry.replacement_key is None:
                continue
            replacement = replacements.get(entry.replacement_key)
            if replacement is None:
                raise ValueError("tool_manifest_replacement_unknown")
            if replacement.key == entry.key:
                raise ValueError("tool_manifest_replacement_self_reference")
            if replacement.status != ToolLifecycleStatus.ACTIVE:
                raise ValueError("tool_manifest_replacement_not_active")
            if (
                replacement.workflow != entry.workflow
                or replacement.offered_in_stage != entry.offered_in_stage
            ):
                raise ValueError("tool_manifest_replacement_scope_mismatch")
        return self


def _inline_schema_refs(value: Any, definitions: Mapping[str, Any]) -> Any:
    if isinstance(value, list):
        return [_inline_schema_refs(item, definitions) for item in value]
    if not isinstance(value, dict):
        return value
    if set(value) == {"$ref"}:
        prefix = "#/$defs/"
        reference = value["$ref"]
        if not isinstance(reference, str) or not reference.startswith(prefix):
            raise ValueError("tool_provider_schema_reference_unsupported")
        name = reference[len(prefix) :]
        target = definitions.get(name)
        if not isinstance(target, dict):
            raise ValueError("tool_provider_schema_reference_unknown")
        return _inline_schema_refs(target, definitions)
    projected: dict[str, Any] = {}
    for key, child in value.items():
        if key in {"$defs", "title", "default"}:
            continue
        if key == "properties" and isinstance(child, dict):
            projected[key] = {
                property_name: _inline_schema_refs(property_schema, definitions)
                for property_name, property_schema in child.items()
            }
            continue
        projected[key] = _inline_schema_refs(child, definitions)
    return projected


def provider_parameters_for_model(model: type[BaseModel]) -> dict[str, Any]:
    raw = model.model_json_schema(mode="validation")
    definitions = raw.get("$defs")
    schema = _inline_schema_refs(raw, definitions if isinstance(definitions, dict) else {})
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("tool_provider_schema_object_required")
    _validate_closed_provider_schema(schema)
    return schema


def _validate_closed_provider_schema(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _validate_closed_provider_schema(item)
        return
    if not isinstance(value, dict):
        return
    if value.get("type") == "object" and value.get("additionalProperties") is not False:
        raise ValueError("tool_provider_schema_open_object_forbidden")
    for child in value.values():
        _validate_closed_provider_schema(child)


def provider_parameters_digest(model: type[BaseModel]) -> str:
    encoded = json.dumps(
        provider_parameters_for_model(model),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contract(model: type[BaseModel], version: str) -> HarnessContractRef:
    return HarnessContractRef(name=model.__name__, version=version)


def _adapter(name: str, version: str = TOOL_RUNTIME_ADAPTER_CONTRACT_VERSION) -> HarnessContractRef:
    return HarnessContractRef(name=name, version=version)


PURE_READ = (ToolEffectStepV1(
    sequence=0,
    boundary_kind=ToolEffectBoundaryKind.PURE_READ,
    commit_scope=ToolEffectCommitScope.NONE,
),)


def _db_effect(name: str, version: str) -> tuple[ToolEffectStepV1, ...]:
    return (ToolEffectStepV1(
        sequence=0,
        boundary_kind=ToolEffectBoundaryKind.DATABASE_WRITE,
        commit_scope=ToolEffectCommitScope.PREPARED_EFFECT,
        adapter=_adapter(name, version),
    ),)


PLANNING_PARENT_EFFECT = (ToolEffectStepV1(
    sequence=0,
    boundary_kind=ToolEffectBoundaryKind.DATABASE_WRITE,
    commit_scope=ToolEffectCommitScope.PARENT_OPERATION,
    adapter=_adapter("planning_parent_state", "planning-parent-state-v1"),
),)


GENERATED_IMAGE_EFFECTS = (
    ToolEffectStepV1(
        sequence=0,
        boundary_kind=ToolEffectBoundaryKind.EXTERNAL_CALL,
        commit_scope=ToolEffectCommitScope.IMMEDIATE_EXTERNAL,
        adapter=_adapter("study_provider_execution", "study-provider-execution-v1"),
    ),
    ToolEffectStepV1(
        sequence=1,
        boundary_kind=ToolEffectBoundaryKind.DATABASE_WRITE,
        commit_scope=ToolEffectCommitScope.PREPARED_EFFECT,
        adapter=_adapter("study_projection_mutation", "study-projection-mutation-v1"),
    ),
)


PUBLIC_SENSITIVITY = ToolSensitivityPolicyV1(
    arguments=ToolSensitivityLevel.PUBLIC,
    internal_result=ToolSensitivityLevel.PUBLIC,
    provider_result=ToolSensitivityLevel.PUBLIC,
    trace_projection=ToolResultProjectionMode.FULL,
    public_projection=ToolResultProjectionMode.FULL,
)
INTERNAL_SENSITIVITY = ToolSensitivityPolicyV1(
    arguments=ToolSensitivityLevel.INTERNAL,
    internal_result=ToolSensitivityLevel.INTERNAL,
    provider_result=ToolSensitivityLevel.INTERNAL,
    trace_projection=ToolResultProjectionMode.CONTENT_FREE,
    public_projection=ToolResultProjectionMode.REDACTED,
)
PROTECTED_SENSITIVITY = ToolSensitivityPolicyV1(
    arguments=ToolSensitivityLevel.PROTECTED,
    internal_result=ToolSensitivityLevel.PROTECTED,
    provider_result=ToolSensitivityLevel.PROTECTED,
    trace_projection=ToolResultProjectionMode.CONTENT_FREE,
    public_projection=ToolResultProjectionMode.REDACTED,
)
PRIVATE_SENSITIVITY = ToolSensitivityPolicyV1(
    arguments=ToolSensitivityLevel.SERVER_PRIVATE,
    internal_result=ToolSensitivityLevel.SERVER_PRIVATE,
    provider_result=ToolSensitivityLevel.SERVER_PRIVATE,
    trace_projection=ToolResultProjectionMode.CONTENT_FREE,
    public_projection=ToolResultProjectionMode.OMITTED,
)


DEFAULT_BUDGET = ToolExecutionBudgetV1(
    max_calls_per_operation=4,
    max_calls_per_round=1,
    timeout_ms=30_000,
    max_argument_bytes=32_000,
    max_internal_result_bytes=256_000,
    max_provider_result_bytes=128_000,
    max_public_result_bytes=32_000,
)
IMAGE_BUDGET = ToolExecutionBudgetV1(
    max_calls_per_operation=4,
    max_calls_per_round=1,
    timeout_ms=60_000,
    max_argument_bytes=32_000,
    max_internal_result_bytes=4_000_000,
    max_provider_result_bytes=128_000,
    max_public_result_bytes=16_000,
)


def _sorted_dependencies(*items: ToolDependency) -> tuple[ToolDependency, ...]:
    return tuple(sorted(items, key=lambda item: item.value))


def _sorted_capabilities(*items: ToolProviderCapability) -> tuple[ToolProviderCapability, ...]:
    return tuple(sorted(items, key=lambda item: item.value))


_PLANNING_META: dict[str, tuple[str, str, str, str]] = {
    "get_study_unit_detail": ("学习单元详情", "planning", "规划分析", "读取单个学习单元的细节结构与切块摘录，用于精细规划。"),
    "ask_planning_question": ("计划澄清提问", "planning", "规划分析", "在目标或边界不清时，向学习者提出一个具体确认问题，并保留保守假设。"),
    "estimate_plan_completion": ("计划完成度评估", "planning", "规划分析", "根据当前学习单元与目录细度估计计划完成度，判断是否还需要继续打磨。"),
    "revise_study_units": ("学习单元重编排", "planning", "规划分析", "在章节切分明显错误时，允许模型重写完整学习单元列表。"),
    "read_page_range_content": ("页范围文本读取", "sensory", "感官工具", "读取教材页范围文本，补充计划生成需要的上下文细节。"),
    "read_page_range_images": ("页范围图像读取", "sensory", "感官工具", "渲染教材页图像，用于公式、图表、版式等视觉线索判断。"),
}


_STUDY_META: dict[str, tuple[str, str, str, str]] = {
    "ask_multiple_choice_question": ("选择题生成", "assessment", "练习评测", "生成章节上下文驱动的选择题。"),
    "ask_fill_blank_question": ("填空题生成", "assessment", "练习评测", "生成章节上下文驱动的填空题。"),
    "retrieve_memory_context": ("跨会话记忆检索", "memory", "记忆工具", "读取历史学习片段，为当前回答补充长期记忆。"),
    "read_session_memory": ("临时记忆读取", "memory", "记忆工具", "读取当前会话内暂存的临时记忆条目。"),
    "write_session_memory": ("临时记忆写入", "memory", "记忆工具", "向当前会话写入一条临时记忆，供后续对话直接调用。"),
    "read_system_time": ("系统时间读取", "session", "会话工具", "读取当前系统时间、日期和时区信息。"),
    "schedule_session_follow_up": ("自动续接调度", "session", "会话工具", "安排在若干秒后自动唤醒一次隐藏对话，继续当前章节互动。"),
    "read_affinity_state": ("好感度读取", "relationship", "关系工具", "读取当前会话的好感度分数、等级和近期变化。"),
    "update_affinity_state": ("好感度更新", "relationship", "关系工具", "调整当前会话的好感度分数，并记录原因。"),
    "read_learning_plan_progress": ("计划进度读取", "planning", "计划工具", "读取当前学习计划的整体完成度、章节完成度和排期状态。"),
    "update_learning_plan": ("计划修改提案", "planning", "计划工具", "提出对当前学习计划标题的修改建议；需要用户确认后才会应用。"),
    "update_learning_plan_progress": ("计划进度更新", "planning", "计划工具", "提出当前学习计划排期状态修改建议；需要用户确认后才会应用。"),
    "read_page_range_content": ("页范围文本读取", "sensory", "感官工具", "读取教材页范围文本，增强章节讲解的教材依据。"),
    "read_page_range_images": ("页范围图像读取", "sensory", "感官工具", "渲染教材页图像，辅助解释公式、图表与布局细节。"),
    "project_uploaded_pdf": ("投射上传 PDF", "sensory", "感官工具", "把当前会话里的某个 PDF 附件投到预览窗口，并切到指定页。"),
    "project_uploaded_image": ("投射上传图片", "sensory", "感官工具", "把当前会话里的某个图片附件投到预览窗口，作为当前视觉焦点。"),
    "generate_projected_image": ("生成并投射图片", "sensory", "感官工具", "生成一张教学用图片并投到预览窗口。"),
    "read_projected_pdf_content": ("投射 PDF 文本读取", "sensory", "感官工具", "读取当前投射 PDF 的指定页文字内容。"),
    "read_projected_pdf_images": ("投射 PDF 图像读取", "sensory", "感官工具", "渲染当前投射 PDF 的指定页图像。"),
    "focus_projected_pdf_page": ("投射 PDF 切页", "sensory", "感官工具", "把当前投射 PDF 的预览焦点移动到某一页。"),
    "highlight_projected_pdf_text": ("投射 PDF 文字高亮", "sensory", "感官工具", "在当前投射 PDF 某一页定位指定文字并生成高亮框。"),
    "annotate_projected_pdf_region": ("投射 PDF 区域框选", "sensory", "感官工具", "在当前投射 PDF 某一页按归一化坐标添加框选。"),
    "clear_projected_pdf_overlays": ("清空投射 PDF 标注", "sensory", "感官工具", "清空当前投射 PDF 的全部或某一页标注。"),
    "annotate_projected_image_region": ("投射图片区域框选", "sensory", "感官工具", "在当前投射图片上按归一化坐标添加框选。"),
    "clear_projected_image_overlays": ("清空投射图片标注", "sensory", "感官工具", "清空当前投射图片上的全部标注。"),
    "read_scene_overview": ("会话场景读取", "scene", "场景工具", "读取当前会话绑定场景的整体状态、路径与物体信息。"),
    "add_scene": ("新增场景", "scene", "场景工具", "在当前会话绑定场景中新增一个子场景并切换过去。"),
    "move_to_scene": ("转移至场景", "scene", "场景工具", "将当前会话焦点转移到绑定场景树中的另一处。"),
    "add_object": ("新增物体", "scene", "场景工具", "向当前场景或指定场景加入新的物体。"),
    "update_object_description": ("修改物体描述", "scene", "场景工具", "更新当前会话场景内某个物体的描述。"),
    "delete_object": ("删除物体", "scene", "场景工具", "从当前会话绑定场景中删除一个物体。"),
}


def _display(meta: tuple[str, str, str, str]) -> ToolDisplayV1:
    return ToolDisplayV1(
        label=meta[0],
        category=meta[1],
        category_label=meta[2],
        provider_description=meta[3],
    )


def _planning_entry(
    name: str,
    *,
    effects: tuple[ToolEffectStepV1, ...] = PURE_READ,
    sensitivity: ToolSensitivityPolicyV1 = INTERNAL_SENSITIVITY,
    dependencies: tuple[ToolDependency, ...] = (),
    capabilities: tuple[ToolProviderCapability, ...] = (
        ToolProviderCapability.FUNCTION_CALLING,
    ),
    budget: ToolExecutionBudgetV1 = DEFAULT_BUDGET,
) -> ToolManifestEntryV1:
    input_model = PLANNING_TOOL_ARGUMENT_MODELS[name]
    result_model = PLANNING_TOOL_RESULT_MODELS[name]
    return ToolManifestEntryV1(
        key=f"planning:{HarnessStage.PLANNING_TOOL_EXECUTION.value}:{name}",
        workflow=HarnessWorkflow.PLANNING,
        offered_in_stage=HarnessStage.PLAN_GENERATION,
        execution_stage=HarnessStage.PLANNING_TOOL_EXECUTION,
        canonical_name=name,
        owner_module="app.services.plan_tool_runtime",
        runtime_adapter=_adapter(f"plan_tool_runtime.{name}"),
        display=_display(_PLANNING_META[name]),
        input_contract=_contract(input_model, PLANNING_TOOL_ARGUMENT_CONTRACT_VERSION),
        result_contract=_contract(result_model, PLANNING_TOOL_RESULT_CONTRACT_VERSION),
        provider_projection_contract=_adapter(
            "openai_function_projection",
            TOOL_PROVIDER_PROJECTION_CONTRACT_VERSION,
        ),
        provider_parameters_digest=provider_parameters_digest(input_model),
        effect_steps=effects,
        sensitivity=sensitivity,
        budget=budget,
        parallel=ToolParallelPolicyV1(),
        dependencies=dependencies,
        provider_capabilities=capabilities,
    )


def _study_owner(name: str) -> str:
    if name in {
        "ask_multiple_choice_question",
        "ask_fill_blank_question",
        "retrieve_memory_context",
        "read_page_range_content",
        "read_page_range_images",
    }:
        return "app.services.model_provider"
    if name == "read_learning_plan_progress":
        return "app.services.learning_plan_chat_runtime"
    if name in {"read_scene_overview", "add_scene", "move_to_scene", "add_object", "update_object_description", "delete_object"}:
        return "app.services.session_scene"
    return "app.services.study_session_chat_runtime"


def _study_entry(
    name: str,
    *,
    effects: tuple[ToolEffectStepV1, ...] = PURE_READ,
    sensitivity: ToolSensitivityPolicyV1 = INTERNAL_SENSITIVITY,
    dependencies: tuple[ToolDependency, ...] = (),
    capabilities: tuple[ToolProviderCapability, ...] = (
        ToolProviderCapability.FUNCTION_CALLING,
    ),
    budget: ToolExecutionBudgetV1 = DEFAULT_BUDGET,
) -> ToolManifestEntryV1:
    input_model = STUDY_CHAT_TOOL_ARGUMENT_MODELS[name]
    result_model = STUDY_CHAT_TOOL_RESULT_MODELS[name]
    owner = _study_owner(name)
    adapter_prefix = owner.rsplit(".", 1)[-1]
    return ToolManifestEntryV1(
        key=f"study_chat:{HarnessStage.STUDY_CHAT_REPLY.value}:{name}",
        workflow=HarnessWorkflow.STUDY_CHAT,
        offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
        execution_stage=HarnessStage.STUDY_CHAT_REPLY,
        canonical_name=name,
        owner_module=owner,
        runtime_adapter=_adapter(f"{adapter_prefix}.{name}"),
        display=_display(_STUDY_META[name]),
        input_contract=_contract(input_model, STUDY_CHAT_TOOL_ARGUMENT_CONTRACT_VERSION),
        result_contract=_contract(result_model, STUDY_CHAT_TOOL_RESULT_CONTRACT_VERSION),
        provider_projection_contract=_adapter(
            "openai_function_projection",
            TOOL_PROVIDER_PROJECTION_CONTRACT_VERSION,
        ),
        provider_parameters_digest=provider_parameters_digest(input_model),
        effect_steps=effects,
        sensitivity=sensitivity,
        budget=budget,
        parallel=ToolParallelPolicyV1(),
        dependencies=dependencies,
        provider_capabilities=capabilities,
    )


_PLANNING_ENTRIES = (
    _planning_entry("get_study_unit_detail", dependencies=_sorted_dependencies(ToolDependency.PLANNING_DETAIL_MAP),
        budget=DEFAULT_BUDGET.model_copy(update={"max_calls_per_round": 3})),
    _planning_entry("ask_planning_question", effects=PLANNING_PARENT_EFFECT, dependencies=_sorted_dependencies(ToolDependency.PLANNING_CONTEXT)),
    _planning_entry("estimate_plan_completion", dependencies=_sorted_dependencies(ToolDependency.PLANNING_CONTEXT)),
    _planning_entry("revise_study_units", effects=PLANNING_PARENT_EFFECT, sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.DOCUMENT_DEBUG, ToolDependency.PLANNING_CONTEXT)),
    _planning_entry("read_page_range_content", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.DOCUMENT_DEBUG)),
    _planning_entry("read_page_range_images", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.DOCUMENT_FILE), capabilities=_sorted_capabilities(ToolProviderCapability.FUNCTION_CALLING, ToolProviderCapability.MULTIMODAL_INPUT), budget=IMAGE_BUDGET),
)


_STUDY_ENTRIES = (
    _study_entry("ask_multiple_choice_question", sensitivity=PRIVATE_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.STUDY_SESSION)),
    _study_entry("ask_fill_blank_question", sensitivity=PRIVATE_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.STUDY_SESSION)),
    _study_entry("retrieve_memory_context", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.MEMORY_HITS)),
    _study_entry("read_session_memory", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.STUDY_SESSION)),
    _study_entry("write_session_memory", effects=_db_effect("study_memory_upsert", "study-memory-upsert-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.STUDY_SESSION)),
    _study_entry("read_system_time", sensitivity=PUBLIC_SENSITIVITY),
    _study_entry("schedule_session_follow_up", effects=_db_effect("study_follow_up_mutation", "study-follow-up-mutation-v1"), sensitivity=PRIVATE_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.STUDY_SESSION)),
    _study_entry("read_affinity_state", dependencies=_sorted_dependencies(ToolDependency.STUDY_SESSION)),
    _study_entry("update_affinity_state", effects=_db_effect("study_affinity_delta", "study-affinity-delta-v1"), dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.STUDY_SESSION)),
    _study_entry("read_learning_plan_progress", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.LEARNING_PLAN)),
    _study_entry("update_learning_plan", effects=_db_effect("study_plan_confirmation_create", "study-plan-confirmation-create-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.LEARNING_PLAN)),
    _study_entry("update_learning_plan_progress", effects=_db_effect("study_plan_confirmation_create", "study-plan-confirmation-create-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.LEARNING_PLAN)),
    _study_entry("read_page_range_content", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.DOCUMENT_DEBUG)),
    _study_entry("read_page_range_images", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.DOCUMENT_FILE), capabilities=_sorted_capabilities(ToolProviderCapability.FUNCTION_CALLING, ToolProviderCapability.MULTIMODAL_INPUT), budget=IMAGE_BUDGET),
    _study_entry("project_uploaded_pdf", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.LEARNER_ATTACHMENTS, ToolDependency.STUDY_SESSION)),
    _study_entry("project_uploaded_image", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.LEARNER_ATTACHMENTS, ToolDependency.STUDY_SESSION)),
    _study_entry("generate_projected_image", effects=GENERATED_IMAGE_EFFECTS, sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.IMAGE_PROVIDER, ToolDependency.STUDY_SESSION), capabilities=_sorted_capabilities(ToolProviderCapability.FUNCTION_CALLING, ToolProviderCapability.IMAGE_GENERATION), budget=IMAGE_BUDGET),
    _study_entry("read_projected_pdf_content", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.PROJECTED_PDF)),
    _study_entry("read_projected_pdf_images", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.DOCUMENT_FILE, ToolDependency.PROJECTED_PDF), capabilities=_sorted_capabilities(ToolProviderCapability.FUNCTION_CALLING, ToolProviderCapability.MULTIMODAL_INPUT), budget=IMAGE_BUDGET),
    _study_entry("focus_projected_pdf_page", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.PROJECTED_PDF, ToolDependency.STUDY_SESSION)),
    _study_entry("highlight_projected_pdf_text", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.DOCUMENT_FILE, ToolDependency.EFFECT_COLLECTOR, ToolDependency.PROJECTED_PDF, ToolDependency.STUDY_SESSION)),
    _study_entry("annotate_projected_pdf_region", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.PROJECTED_PDF, ToolDependency.STUDY_SESSION)),
    _study_entry("clear_projected_pdf_overlays", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.PROJECTED_PDF, ToolDependency.STUDY_SESSION)),
    _study_entry("annotate_projected_image_region", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.PROJECTED_IMAGE, ToolDependency.STUDY_SESSION)),
    _study_entry("clear_projected_image_overlays", effects=_db_effect("study_projection_mutation", "study-projection-mutation-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.PROJECTED_IMAGE, ToolDependency.STUDY_SESSION)),
    _study_entry("read_scene_overview", sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.SESSION_SCENE)),
    _study_entry("add_scene", effects=_db_effect("study_scene_replace", "study-scene-replace-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.SESSION_SCENE)),
    _study_entry("move_to_scene", effects=_db_effect("study_scene_replace", "study-scene-replace-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.SESSION_SCENE)),
    _study_entry("add_object", effects=_db_effect("study_scene_replace", "study-scene-replace-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.SESSION_SCENE)),
    _study_entry("update_object_description", effects=_db_effect("study_scene_replace", "study-scene-replace-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.SESSION_SCENE)),
    _study_entry("delete_object", effects=_db_effect("study_scene_replace", "study-scene-replace-v1"), sensitivity=PROTECTED_SENSITIVITY, dependencies=_sorted_dependencies(ToolDependency.EFFECT_COLLECTOR, ToolDependency.SESSION_SCENE)),
)


TOOL_MANIFEST_REGISTRY = ToolManifestRegistryV1(
    tools=tuple(sorted((*_PLANNING_ENTRIES, *_STUDY_ENTRIES), key=lambda item: item.key))
)
TOOL_MANIFEST_ENTRIES = MappingProxyType(
    {entry.key: entry for entry in TOOL_MANIFEST_REGISTRY.tools}
)
TOOL_INPUT_MODELS = MappingProxyType({
    **{
        f"planning:{HarnessStage.PLANNING_TOOL_EXECUTION.value}:{name}": model
        for name, model in PLANNING_TOOL_ARGUMENT_MODELS.items()
    },
    **{
        f"study_chat:{HarnessStage.STUDY_CHAT_REPLY.value}:{name}": model
        for name, model in STUDY_CHAT_TOOL_ARGUMENT_MODELS.items()
    },
})
TOOL_RESULT_MODELS = MappingProxyType({
    **{
        f"planning:{HarnessStage.PLANNING_TOOL_EXECUTION.value}:{name}": model
        for name, model in PLANNING_TOOL_RESULT_MODELS.items()
    },
    **{
        f"study_chat:{HarnessStage.STUDY_CHAT_REPLY.value}:{name}": model
        for name, model in STUDY_CHAT_TOOL_RESULT_MODELS.items()
    },
})


def resolve_tool_manifest_entry(
    *,
    workflow: HarnessWorkflow,
    offered_in_stage: HarnessStage,
    transport_name: str,
    registry: ToolManifestRegistryV1 = TOOL_MANIFEST_REGISTRY,
) -> ToolManifestEntryV1:
    entry = resolve_tool_manifest_reference(
        workflow=workflow,
        offered_in_stage=offered_in_stage,
        transport_name=transport_name,
        registry=registry,
    )
    if entry.status == ToolLifecycleStatus.RETIRED:
        raise ValueError("tool_manifest_tool_retired")
    return entry


def resolve_tool_manifest_reference(
    *,
    workflow: HarnessWorkflow,
    offered_in_stage: HarnessStage,
    transport_name: str,
    registry: ToolManifestRegistryV1 = TOOL_MANIFEST_REGISTRY,
) -> ToolManifestEntryV1:
    """Resolve legacy config/trace names without authorizing execution."""
    matches = [
        entry
        for entry in registry.tools
        if entry.workflow == workflow
        and entry.offered_in_stage == offered_in_stage
        and transport_name in (entry.canonical_name, *entry.aliases)
    ]
    if not matches:
        raise ValueError("tool_manifest_tool_unknown")
    if len(matches) != 1:
        raise ValueError("tool_manifest_tool_ambiguous")
    return matches[0]


def tool_manifest_registry_snapshot() -> dict[str, object]:
    return TOOL_MANIFEST_REGISTRY.model_dump(mode="json")


def validate_tool_manifest_registry() -> None:
    expected_keys = set(TOOL_INPUT_MODELS)
    if expected_keys != set(TOOL_RESULT_MODELS) or expected_keys != set(TOOL_MANIFEST_ENTRIES):
        raise ValueError("tool_manifest_contract_registry_incomplete")
    planning_count = sum(
        entry.workflow == HarnessWorkflow.PLANNING
        for entry in TOOL_MANIFEST_REGISTRY.tools
    )
    study_count = sum(
        entry.workflow == HarnessWorkflow.STUDY_CHAT
        for entry in TOOL_MANIFEST_REGISTRY.tools
    )
    if (planning_count, study_count) != (6, 31):
        raise ValueError("tool_manifest_tool_count_invalid")
    for key, entry in TOOL_MANIFEST_ENTRIES.items():
        input_model = TOOL_INPUT_MODELS[key]
        result_model = TOOL_RESULT_MODELS[key]
        if input_model.model_config.get("extra") != "forbid":
            raise ValueError("tool_manifest_input_not_strict")
        if result_model.model_config.get("extra") != "forbid":
            raise ValueError("tool_manifest_result_not_strict")
        if entry.input_contract.name != input_model.__name__:
            raise ValueError("tool_manifest_input_contract_mismatch")
        if entry.result_contract.name != result_model.__name__:
            raise ValueError("tool_manifest_result_contract_mismatch")
        if entry.provider_parameters_digest != provider_parameters_digest(input_model):
            raise ValueError("tool_manifest_provider_schema_digest_mismatch")
    generated = TOOL_MANIFEST_ENTRIES[
        "study_chat:study_chat_reply:generate_projected_image"
    ]
    if [step.boundary_kind for step in generated.effect_steps] != [
        ToolEffectBoundaryKind.EXTERNAL_CALL,
        ToolEffectBoundaryKind.DATABASE_WRITE,
    ]:
        raise ValueError("tool_manifest_generated_image_effects_invalid")


validate_tool_manifest_registry()
