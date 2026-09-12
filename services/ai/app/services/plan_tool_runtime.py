from __future__ import annotations

from app.core.diagnostic_tool import observe_tool_call

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.core.harness_component_versions import (
    PLANNING_TOOL_RUNTIME_CONTRACT_VERSION,
    PLANNING_TOOLSET_CONTRACT_VERSION,
)
from app.models.domain import DocumentDebugRecord, PlanningQuestionRecord, StudyUnitRecord
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.tool_manifest import (
    TOOL_MANIFEST_ENTRIES,
    ToolManifestEntryV1,
    resolve_tool_manifest_entry,
)
from app.services.model_tool_config import PLAN_STAGE, TOOL_CATALOG
from app.services.plan_prompt import (
    build_study_unit_detail_map,
    read_page_range_content,
    read_page_range_images,
)
from app.services.tool_provider_projection import (
    ProviderToolCallDecodeError,
    ToolContractViolation,
    ToolExecutionBudgetTracker,
    adapt_tool_runtime_result,
    build_versioned_tool_error,
    decode_provider_tool_call,
    project_tool_arguments_for_observability,
    project_validated_tool_result,
    provider_function_for_entry,
)


@dataclass(frozen=True)
class PlanToolDefinition:
    name: str
    is_available: Callable[["PlanToolRuntimeContext"], bool]
    execute: Callable[[dict[str, Any], "PlanToolRuntimeContext"], "PlanToolResult"]


@dataclass(frozen=True)
class PlanToolRuntimeContext:
    study_units: list[StudyUnitRecord]
    detail_map: dict[str, dict[str, object]]
    debug_report: DocumentDebugRecord | None
    document_path: str | None
    multimodal_enabled: bool
    planning_questions: list[PlanningQuestionRecord]
    progress_callback: Callable[[str, dict[str, object]], None] | None


@dataclass(frozen=True)
class PlanToolResult:
    payload: dict[str, object]
    trace_summary: str
    follow_up_messages: list[dict[str, Any]]


@dataclass(frozen=True)
class PlanToolExecution:
    tool_call_id: str
    tool_name: str
    arguments_json: str
    result: dict[str, object]
    provider_result: dict[str, object]
    trace_result: dict[str, object]
    trace_summary: str
    follow_up_messages: list[dict[str, Any]]
    argument_contract_version: str
    result_contract_version: str


class PlanToolRuntime:
    def __init__(self, *, context: PlanToolRuntimeContext, disabled_tools: set[str] | None = None) -> None:
        self.context = context
        disabled = disabled_tools or set()
        self._definitions = {
            definition.name: definition
            for definition in _registered_plan_tools()
            if definition.is_available(context) and definition.name not in disabled
        }
        self._budget = ToolExecutionBudgetTracker()

    def begin_round(self) -> None:
        self._budget.begin_round()

    def has_tools(self) -> bool:
        return bool(self._definitions)

    def current_study_units(self) -> list[StudyUnitRecord]:
        return list(self.context.study_units)

    def current_planning_questions(self) -> list[PlanningQuestionRecord]:
        return list(self.context.planning_questions)

    def public_specs(self) -> list[dict[str, str]]:
        return [
            {
                "name": definition.name,
                "description": _planning_manifest_entry(definition.name).display.provider_description,
            }
            for definition in self._definitions.values()
        ]

    def openai_tools(self) -> list[dict[str, object]]:
        return [
            provider_function_for_entry(
                _planning_manifest_entry(definition.name)
            ).model_dump(mode="json")
            for definition in self._definitions.values()
        ]

    @observe_tool_call(HarnessWorkflow.PLANNING, HarnessStage.PLAN_GENERATION, method=True)
    def execute_tool_call(self, tool_call: dict[str, Any]) -> PlanToolExecution:
        tool_call_id = tool_call.get("id") if isinstance(tool_call.get("id"), str) else ""
        try:
            decoded = decode_provider_tool_call(
                tool_call,
                workflow=HarnessWorkflow.PLANNING,
                offered_in_stage=HarnessStage.PLAN_GENERATION,
            )
        except ProviderToolCallDecodeError as error:
            function_payload = tool_call.get("function")
            raw_name = function_payload.get("name") if isinstance(function_payload, dict) else ""
            error_path = list(error.path)
            if len(error_path) > 2 and error_path[:2] == [
                "function",
                "arguments",
            ]:
                error_path = error_path[2:]
            return _tool_argument_error_execution(
                tool_call_id=tool_call_id,
                tool_name=raw_name if isinstance(raw_name, str) else "",
                error=_planning_decode_error_code(error.code),
                path=error_path,
                detail=error.detail,
            )
        tool_name = decoded.canonical_name
        definition = self._definitions.get(tool_name)
        entry = TOOL_MANIFEST_ENTRIES[decoded.manifest_key]
        if definition is None:
            return _tool_argument_error_execution(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                error="tool_unavailable",
                path=["function", "name"],
                detail="tool is not available in this planning context",
                entry=entry,
            )
        try:
            self._budget.admit(entry)
        except ToolContractViolation as error:
            return _tool_argument_error_execution(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                error=error.code,
                path=[],
                detail=error.detail,
                entry=entry,
            )
        result = definition.execute(decoded.arguments.model_dump(mode="python"), self.context)
        validated_result = adapt_tool_runtime_result(entry, result.payload)
        canonical = validated_result.model_dump(mode="json")
        return PlanToolExecution(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            arguments_json=project_tool_arguments_for_observability(
                entry,
                decoded.arguments,
            ),
            result=canonical,
            provider_result=project_validated_tool_result(
                entry,
                validated_result,
                audience="provider",
            ),
            trace_result=project_validated_tool_result(
                entry,
                validated_result,
                audience="trace",
            ),
            trace_summary=f"{tool_name}: {'failed' if canonical.get('ok') is False else 'validated'}",
            follow_up_messages=result.follow_up_messages,
            argument_contract_version=entry.input_contract.version,
            result_contract_version=entry.result_contract.version,
        )


def build_plan_tool_runtime(
    *,
    study_units: list[StudyUnitRecord] | None = None,
    detail_map: dict[str, dict[str, object]] | None = None,
    debug_report: DocumentDebugRecord | None = None,
    document_path: str | None = None,
    multimodal_enabled: bool = False,
    planning_questions: list[PlanningQuestionRecord] | None = None,
    progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    disabled_tools: set[str] | None = None,
) -> PlanToolRuntime:
    return PlanToolRuntime(
        context=PlanToolRuntimeContext(
            study_units=list(study_units or []),
            detail_map=detail_map or {},
            debug_report=debug_report,
            document_path=document_path,
            multimodal_enabled=multimodal_enabled,
            planning_questions=list(planning_questions or []),
            progress_callback=progress_callback,
        ),
        disabled_tools=disabled_tools,
    )


def get_learning_plan_tool_specs(
    *,
    study_units: list[StudyUnitRecord] | None = None,
    detail_map: dict[str, dict[str, object]] | None = None,
    debug_report: DocumentDebugRecord | None = None,
    document_path: str | None = None,
    multimodal_enabled: bool = False,
) -> list[dict[str, str]]:
    if study_units is None and detail_map is None and debug_report is None and document_path is None:
        return [
            {
                "name": definition.name,
                "description": _planning_manifest_entry(
                    definition.name
                ).display.provider_description,
            }
            for definition in _registered_plan_tools()
        ]
    runtime = build_plan_tool_runtime(
        study_units=study_units,
        detail_map=detail_map,
        debug_report=debug_report,
        document_path=document_path,
        multimodal_enabled=multimodal_enabled,
    )
    return runtime.public_specs()


def _registered_plan_tools() -> list[PlanToolDefinition]:
    definitions = [
        PlanToolDefinition(
            name="get_study_unit_detail",
            is_available=lambda context: bool(context.detail_map),
            execute=_execute_get_study_unit_detail,
        ),
        PlanToolDefinition(
            name="ask_planning_question",
            is_available=lambda context: True,
            execute=_execute_ask_planning_question,
        ),
        PlanToolDefinition(
            name="estimate_plan_completion",
            is_available=lambda context: True,
            execute=_execute_estimate_plan_completion,
        ),
        PlanToolDefinition(
            name="revise_study_units",
            is_available=lambda context: context.debug_report is not None and bool(context.study_units),
            execute=_execute_revise_study_units,
        ),
        PlanToolDefinition(
            name="read_page_range_content",
            is_available=lambda context: context.debug_report is not None,
            execute=_execute_read_page_range_content,
        ),
        PlanToolDefinition(
            name="read_page_range_images",
            is_available=lambda context: bool(
                context.multimodal_enabled and context.document_path
            ),
            execute=_execute_read_page_range_images,
        ),
    ]
    expected_names = {
        entry.canonical_name
        for entry in TOOL_MANIFEST_ENTRIES.values()
        if entry.workflow == HarnessWorkflow.PLANNING
    }
    actual_names = {definition.name for definition in definitions}
    if actual_names != expected_names:
        raise RuntimeError("planning_tool_availability_manifest_mismatch")
    for definition in definitions:
        catalog_description = TOOL_CATALOG[PLAN_STAGE][definition.name]["description"]
        if catalog_description != _planning_manifest_entry(
            definition.name
        ).display.provider_description:
            raise RuntimeError("planning_tool_description_manifest_mismatch")
    return definitions


def _execute_get_study_unit_detail(
    arguments: dict[str, Any],
    context: PlanToolRuntimeContext,
) -> PlanToolResult:
    target_id = str(arguments.get("study_unit_id") or "").strip()
    if not target_id:
        return PlanToolResult(
            payload={
                "ok": False,
                "error": "missing_study_unit_id",
            },
            trace_summary="缺少 study_unit_id",
            follow_up_messages=[],
        )
    detail = context.detail_map.get(target_id)
    if detail is None:
        return PlanToolResult(
            payload={
                "ok": False,
                "error": "study_unit_not_found",
                "study_unit_id": target_id,
            },
            trace_summary=f"未找到学习单元：{target_id}",
            follow_up_messages=[],
        )
    return PlanToolResult(
        payload={
            "ok": True,
            "tool_name": "get_study_unit_detail",
            "requested_focus": str(arguments.get("focus") or ""),
            "detail": detail,
        },
        trace_summary=f"已读取学习单元详情：{target_id}",
        follow_up_messages=[],
    )


def _execute_ask_planning_question(
    arguments: dict[str, Any],
    context: PlanToolRuntimeContext,
) -> PlanToolResult:
    question = str(arguments.get("question") or "").strip()
    if not question:
        return PlanToolResult(
            payload={
                "ok": False,
                "error": "missing_question",
            },
            trace_summary="缺少需要向学习者确认的问题",
            follow_up_messages=[],
        )
    reason = str(arguments.get("reason") or "").strip()
    assumptions: list[str] = []
    assumptions_raw = arguments.get("assumptions")
    if isinstance(assumptions_raw, list):
        for item in assumptions_raw:
            text = str(item).strip()
            if text:
                assumptions.append(text)
    question_record = PlanningQuestionRecord(
        id=f"planning-question-{uuid4().hex[:10]}",
        question=question,
        reason=reason,
        assumptions=assumptions,
        created_at=_now(),
    )
    context.planning_questions.append(question_record)
    _emit_progress(
        context.progress_callback,
        "planning_question_asked",
        {
            "question_id": question_record.id,
            "question": question,
            "reason": reason,
            "assumptions": assumptions,
        },
    )
    follow_up_text = [f"需要向学习者确认：{question}"]
    if reason:
        follow_up_text.append(f"原因：{reason}")
    if assumptions:
        follow_up_text.append("若暂时无法等待回答，可先按以下保守假设继续：")
        follow_up_text.extend(f"- {item}" for item in assumptions)
    else:
        follow_up_text.append("若暂时无法等待回答，可先按保守假设继续，并在 today_tasks 中保留一个确认项。")
    return PlanToolResult(
        payload={
            "ok": True,
            "tool_name": "ask_planning_question",
            "question_id": question_record.id,
            "question": question,
            "reason": reason,
            "assumptions": assumptions,
        },
        trace_summary=f"已提出待确认问题：{question}",
        follow_up_messages=[
            {
                "role": "assistant",
                "content": "\n".join(follow_up_text),
            }
        ],
    )


def _execute_estimate_plan_completion(
    arguments: dict[str, Any],
    context: PlanToolRuntimeContext,
) -> PlanToolResult:
    focus = str(arguments.get("focus") or "").strip()
    plannable_units = [unit for unit in context.study_units if unit.include_in_plan] or list(context.study_units)
    if not plannable_units:
        return PlanToolResult(
            payload={
                "ok": True,
                "tool_name": "estimate_plan_completion",
                "completion_score": 20,
                "completion_label": "需要补充学习单元",
                "signals": {
                    "plannable_unit_count": 0,
                    "units_with_subsections": 0,
                    "detail_coverage_ratio": 0.0,
                },
                "missing_items": ["study_units"],
                "recommendations": ["先建立最小可执行的章节结构，再生成计划。"],
            },
            trace_summary="学习单元结构估分偏低：当前没有可用的学习单元",
            follow_up_messages=[],
        )

    subsection_counts = [
        len(context.detail_map.get(unit.id, {}).get("subsection_titles", []) or [])
        for unit in plannable_units
    ]
    units_with_subsections = sum(1 for count in subsection_counts if count > 0)
    total_subsections = sum(subsection_counts)
    detail_coverage_ratio = units_with_subsections / max(1, len(plannable_units))
    richness_ratio = min(1.0, total_subsections / max(1, len(plannable_units) * 2))
    span_penalty = 0.0
    # Few units can be a complete short source; only page span implies breadth.
    if any((unit.page_end - unit.page_start + 1) >= 80 for unit in plannable_units):
        span_penalty = 0.18
    score = int(
        max(
            25,
            min(
                96,
                round((0.42 + (detail_coverage_ratio * 0.28) + (richness_ratio * 0.22) - span_penalty) * 100),
            ),
        )
    )
    if score >= 80:
        label = "学习单元结构元数据较充分"
    elif score >= 60:
        label = "学习单元结构仍需补充"
    else:
        label = "建议继续细化学习单元结构"
    missing_items: list[str] = []
    recommendations: list[str] = []
    if detail_coverage_ratio < 0.7:
        missing_items.append("subsection_detail")
        recommendations.append("再读取代表性学习单元详情，补足子章节边界。")
    if richness_ratio < 0.6:
        missing_items.append("page_range_evidence")
        recommendations.append("再读取一段页范围文本，核对目录与正文是否一致。")
    if span_penalty > 0:
        missing_items.append("coarse_segmentation")
        recommendations.append("把过宽的学习单元拆细，再重新估分。")
    if focus:
        recommendations.insert(0, f"当前重点：{focus}。")
    if not recommendations:
        recommendations.append("学习单元结构元数据较充分；仍需依据原文和学习目标核对计划的事实、活动与时长。")
    return PlanToolResult(
        payload={
            "ok": True,
            "tool_name": "estimate_plan_completion",
            "completion_score": score,
            "completion_label": label,
            "focus": focus,
            "signals": {
                "plannable_unit_count": len(plannable_units),
                "units_with_subsections": units_with_subsections,
                "total_subsections": total_subsections,
                "detail_coverage_ratio": round(detail_coverage_ratio, 3),
                "richness_ratio": round(richness_ratio, 3),
            },
            "missing_items": missing_items,
            "recommendations": recommendations,
        },
        trace_summary=f"学习单元结构估分 {score}/100：{label}",
        follow_up_messages=[],
    )


def _execute_revise_study_units(
    arguments: dict[str, Any],
    context: PlanToolRuntimeContext,
) -> PlanToolResult:
    raw_units = arguments.get("study_units")
    if not isinstance(raw_units, list) or not raw_units:
        return PlanToolResult(
            payload={
                "ok": False,
                "error": "missing_study_units",
            },
            trace_summary="缺少 revised study_units 载荷",
            follow_up_messages=[],
        )
    debug_report = context.debug_report
    if debug_report is None:
        return PlanToolResult(
            payload={
                "ok": False,
                "error": "missing_debug_report",
            },
            trace_summary="重编排学习单元时缺少调试报告",
            follow_up_messages=[],
        )
    try:
        revised_units = _validate_revised_study_units(
            raw_units=raw_units,
            base_document_id=debug_report.document_id,
            page_count=debug_report.page_count,
            raw_sections=debug_report.sections,
        )
    except ValueError as exc:
        return PlanToolResult(
            payload={
                "ok": False,
                "error": "invalid_study_unit_revision",
                "detail": str(exc),
                **({"recovery": {
                    "kind": "non_overlapping_physical_pages",
                    "document_page_count": debug_report.page_count,
                }} if str(exc).endswith(("_overlaps_previous", "_page_out_of_range", "_invalid_page_range"))
                    and debug_report.page_count > 0 else {}),
            },
            trace_summary=f"学习单元重编排无效：{exc}",
            follow_up_messages=[],
        )

    context.study_units[:] = revised_units
    next_detail_map = build_study_unit_detail_map(
        study_units=revised_units,
        debug_report=debug_report,
    )
    context.detail_map.clear()
    context.detail_map.update(next_detail_map)
    return PlanToolResult(
        payload={
            "ok": True,
            "tool_name": "revise_study_units",
            "rationale": str(arguments.get("rationale") or ""),
            "study_unit_count": len(revised_units),
            "plannable_count": len([unit for unit in revised_units if unit.include_in_plan]),
            "study_units": [
                {
                    "unit_id": unit.id,
                    "title": unit.title,
                    "page_start": unit.page_start,
                    "page_end": unit.page_end,
                    "include_in_plan": unit.include_in_plan,
                }
                for unit in revised_units
            ],
        },
        trace_summary=_build_study_unit_revision_summary(
            revised_units=revised_units,
            rationale=str(arguments.get("rationale") or ""),
        ),
        follow_up_messages=[],
    )


def _execute_read_page_range_content(
    arguments: dict[str, Any],
    context: PlanToolRuntimeContext,
) -> PlanToolResult:
    page_start = max(1, int(arguments.get("page_start") or 1))
    page_end = max(page_start, int(arguments.get("page_end") or page_start))
    max_chars = max(500, min(6000, int(arguments.get("max_chars") or 3000)))
    return PlanToolResult(
        payload={
            "ok": True,
            "tool_name": "read_page_range_content",
            **read_page_range_content(
                debug_report=context.debug_report,
                page_start=page_start,
                page_end=page_end,
                max_chars=max_chars,
            ),
        },
        trace_summary=f"已读取第 {page_start}-{page_end} 页文本",
        follow_up_messages=[],
    )


def _validate_revised_study_units(
    *,
    raw_units: list[Any],
    base_document_id: str,
    page_count: int,
    raw_sections: list[Any],
) -> list[StudyUnitRecord]:
    if len(raw_units) > 24:
        raise ValueError("too_many_study_units")
    normalized: list[StudyUnitRecord] = []
    previous_end = 0
    for index, raw_unit in enumerate(raw_units, start=1):
        if not isinstance(raw_unit, dict):
            raise ValueError("study_unit_item_must_be_object")
        title = str(raw_unit.get("title") or "").strip()
        if not title:
            raise ValueError(f"study_unit_{index}_missing_title")
        page_start = int(raw_unit.get("page_start") or 0)
        page_end = int(raw_unit.get("page_end") or 0)
        if page_start < 1 or page_end < page_start:
            raise ValueError(f"study_unit_{index}_invalid_page_range")
        if page_end > page_count:
            raise ValueError(f"study_unit_{index}_page_out_of_range")
        if page_start <= previous_end:
            raise ValueError(f"study_unit_{index}_overlaps_previous")
        previous_end = page_end
        include_in_plan = bool(raw_unit.get("include_in_plan", True))
        summary = str(raw_unit.get("summary") or f"覆盖第 {page_start}-{page_end} 页的学习单元。").strip()
        source_section_ids = [
            str(section.id)
            for section in raw_sections
            if getattr(section, "page_start", 0) <= page_end and getattr(section, "page_end", 0) >= page_start
        ]
        normalized.append(
            StudyUnitRecord(
                id=f"{base_document_id}:study-unit:llm:{index}",
                document_id=base_document_id,
                title=title,
                page_start=page_start,
                page_end=page_end,
                unit_kind="chapter" if include_in_plan else "chapter",
                include_in_plan=include_in_plan,
                source_section_ids=source_section_ids,
                summary=summary,
                confidence=0.95,
            )
        )
    return normalized


def _execute_read_page_range_images(
    arguments: dict[str, Any],
    context: PlanToolRuntimeContext,
) -> PlanToolResult:
    page_start = max(1, int(arguments.get("page_start") or 1))
    page_end = max(page_start, int(arguments.get("page_end") or page_start))
    max_images = max(1, min(4, int(arguments.get("max_images") or 3)))
    image_result = read_page_range_images(
        document_path=context.document_path,
        page_start=page_start,
        page_end=page_end,
        max_images=max_images,
    )
    images = image_result.get("images") or []
    page_numbers = [
        int(image["page_number"])
        for image in images
        if isinstance(image, dict) and "page_number" in image
    ]
    follow_up_messages: list[dict[str, Any]] = []
    if images:
        follow_up_messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "已附上教材页图像，可用于查看公式、图表、表格和版式等视觉线索，以辅助学习计划生成。"
                        ),
                    },
                    *[
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": str(image["image_url"]),
                            },
                        }
                        for image in images
                        if isinstance(image, dict) and image.get("image_url")
                    ],
                ],
            }
        )
    return PlanToolResult(
        payload={
            "ok": True,
            "tool_name": "read_page_range_images",
            "page_start": page_start,
            "page_end": page_end,
            "image_count": len(page_numbers),
            "page_numbers": page_numbers,
        },
        trace_summary=f"已渲染第 {page_start}-{page_end} 页图像，共 {len(page_numbers)} 张",
        follow_up_messages=follow_up_messages,
    )


def _build_study_unit_revision_summary(
    *,
    revised_units: list[StudyUnitRecord],
    rationale: str,
) -> str:
    parts = [
        f"{unit.title}（第 {unit.page_start}-{unit.page_end} 页）"
        for unit in revised_units[:4]
    ]
    if len(revised_units) > 4:
        parts.append(f"另有 {len(revised_units) - 4} 个学习单元")
    summary = f"已重编排为 {len(revised_units)} 个学习单元：" + "；".join(parts)
    if rationale:
        summary += f"；原因：{rationale}"
    return summary


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


def _tool_argument_error_execution(
    *,
    tool_call_id: str,
    tool_name: str,
    error: str,
    path: list[str | int],
    detail: str,
    entry: ToolManifestEntryV1 | None = None,
) -> PlanToolExecution:
    result = build_versioned_tool_error(
        workflow=HarnessWorkflow.PLANNING,
        tool_name=tool_name,
        error=error,
        path=path,
        detail=detail,
    )
    canonical = result.model_dump(mode="json")
    if entry is None and tool_name:
        try:
            entry = _planning_manifest_entry(tool_name)
        except ValueError:
            entry = None
    provider_result = (
        project_validated_tool_result(entry, result, audience="provider")
        if entry is not None
        else {
            "schema_version": canonical["schema_version"],
            "ok": False,
            "tool_name": canonical["tool_name"],
            "error": canonical["error"],
        }
    )
    trace_result = (
        project_validated_tool_result(entry, result, audience="trace")
        if entry is not None
        else provider_result
    )
    rendered_path = ".".join(str(item) for item in path) or "$"
    rejection_label = {
        "tool_round_budget_exceeded": "超过同轮调用次数限制",
        "tool_operation_budget_exceeded": "超过本次计划调用次数限制",
    }.get(error, "参数拒绝")
    return PlanToolExecution(
        tool_call_id=tool_call_id,
        tool_name=entry.canonical_name if entry is not None else (tool_name or "unknown_tool"),
        arguments_json=(
            '{"contract_version":"planning-tool-arguments-v1","redacted":true}'
        ),
        result=canonical,
        provider_result=provider_result,
        trace_result=trace_result,
        trace_summary=f"{tool_name or 'tool'}: {rejection_label}（{rendered_path}）",
        follow_up_messages=[],
        argument_contract_version=(
            entry.input_contract.version
            if entry is not None
            else "planning-tool-arguments-v1"
        ),
        result_contract_version=(
            entry.result_contract.version
            if entry is not None
            else "planning-tool-result-v1"
        ),
    )


def _planning_manifest_entry(name: str) -> ToolManifestEntryV1:
    return resolve_tool_manifest_entry(
        workflow=HarnessWorkflow.PLANNING,
        offered_in_stage=HarnessStage.PLAN_GENERATION,
        transport_name=name,
    )


def _planning_decode_error_code(code: str) -> str:
    if code == "tool_arguments_json_invalid":
        return "tool_argument_invalid_json"
    if code in {
        "tool_arguments_object_required",
        "tool_arguments_json_string_required",
        "tool_arguments_contract_invalid",
        "tool_arguments_duplicate_key",
        "tool_arguments_nonfinite",
    }:
        return "tool_argument_schema_invalid"
    if code == "tool_arguments_budget_exceeded":
        return "tool_argument_budget_exceeded"
    if code == "tool_manifest_tool_unknown":
        return "unknown_tool"
    return code
