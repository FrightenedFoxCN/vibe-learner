from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from app.models.domain import DocumentDebugRecord, PlanningQuestionRecord, StudyUnitRecord
from app.services.model_tool_config import PLAN_STAGE, TOOL_CATALOG
from app.services.plan_prompt import (
    build_study_unit_detail_map,
    read_page_range_content,
    read_page_range_images,
)


@dataclass(frozen=True)
class PlanToolDefinition:
    name: str
    description: str
    parameters: dict[str, object]
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
    trace_summary: str
    follow_up_messages: list[dict[str, Any]]


class PlanToolRuntime:
    def __init__(self, *, context: PlanToolRuntimeContext, disabled_tools: set[str] | None = None) -> None:
        self.context = context
        disabled = disabled_tools or set()
        self._definitions = {
            definition.name: definition
            for definition in _registered_plan_tools()
            if definition.is_available(context) and definition.name not in disabled
        }

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
                "description": definition.description,
            }
            for definition in self._definitions.values()
        ]

    def openai_tools(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": definition.name,
                    "description": definition.description,
                    "parameters": definition.parameters,
                },
            }
            for definition in self._definitions.values()
        ]

    def execute_tool_call(self, tool_call: dict[str, Any]) -> PlanToolExecution:
        function_payload = tool_call.get("function") or {}
        tool_name = str(function_payload.get("name") or "")
        raw_arguments = str(function_payload.get("arguments") or "{}")
        definition = self._definitions.get(tool_name)
        if definition is None:
            return PlanToolExecution(
                tool_call_id=str(tool_call.get("id") or ""),
                tool_name=tool_name,
                arguments_json=raw_arguments,
                result={
                    "ok": False,
                    "error": "unknown_tool",
                    "tool_name": tool_name,
                },
                trace_summary=f"{tool_name}: 未知工具",
                follow_up_messages=[],
            )
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            arguments = {}
        result = definition.execute(arguments, self.context)
        return PlanToolExecution(
            tool_call_id=str(tool_call.get("id") or ""),
            tool_name=tool_name,
            arguments_json=raw_arguments,
            result=result.payload,
            trace_summary=result.trace_summary,
            follow_up_messages=result.follow_up_messages,
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
                "description": definition.description,
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
    return [
        PlanToolDefinition(
            name="get_study_unit_detail",
            description=TOOL_CATALOG[PLAN_STAGE]["get_study_unit_detail"]["description"],
            parameters={
                "type": "object",
                "properties": {
                    "study_unit_id": {
                        "type": "string",
                        "description": "从当前学习单元列表中选择要查看的学习单元 ID。",
                    },
                    "focus": {
                        "type": "string",
                        "description": "可选。说明查看原因，例如核对子主题覆盖或例题分布。",
                    },
                },
                "required": ["study_unit_id"],
                "additionalProperties": False,
            },
            is_available=lambda context: bool(context.detail_map),
            execute=_execute_get_study_unit_detail,
        ),
        PlanToolDefinition(
            name="ask_planning_question",
            description=TOOL_CATALOG[PLAN_STAGE]["ask_planning_question"]["description"],
            parameters={
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "需要向学习者确认的一个具体问题。",
                    },
                    "reason": {
                        "type": "string",
                        "description": "可选。说明为什么当前需要确认这个问题。",
                    },
                    "assumptions": {
                        "type": "array",
                        "description": "可选。若暂时无法等待回答，先采用的保守假设。",
                        "items": {
                            "type": "string",
                        },
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
            is_available=lambda context: True,
            execute=_execute_ask_planning_question,
        ),
        PlanToolDefinition(
            name="estimate_plan_completion",
            description=TOOL_CATALOG[PLAN_STAGE]["estimate_plan_completion"]["description"],
            parameters={
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "可选。提示当前最需要检查的维度，例如目录细度、目标覆盖或行动可执行性。",
                    },
                },
                "additionalProperties": False,
            },
            is_available=lambda context: True,
            execute=_execute_estimate_plan_completion,
        ),
        PlanToolDefinition(
            name="revise_study_units",
            description=TOOL_CATALOG[PLAN_STAGE]["revise_study_units"]["description"],
            parameters={
                "type": "object",
                "properties": {
                    "study_units": {
                        "type": "array",
                        "description": "当前学习单元切分的完整替换列表。",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "面向学习者展示的章节或学习单元标题。",
                                },
                                "page_start": {
                                    "type": "integer",
                                    "description": "该学习单元的起始页码，包含本页。",
                                },
                                "page_end": {
                                    "type": "integer",
                                    "description": "该学习单元的结束页码，包含本页。",
                                },
                                "include_in_plan": {
                                    "type": "boolean",
                                    "description": "该学习单元是否应纳入学习计划。",
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "可选。该学习单元的简短摘要。",
                                },
                            },
                            "required": ["title", "page_start", "page_end"],
                            "additionalProperties": False,
                        },
                    },
                    "rationale": {
                        "type": "string",
                        "description": "可选。说明为何需要替换原有切分。",
                    },
                },
                "required": ["study_units"],
                "additionalProperties": False,
            },
            is_available=lambda context: context.debug_report is not None and bool(context.study_units),
            execute=_execute_revise_study_units,
        ),
        PlanToolDefinition(
            name="read_page_range_content",
            description=TOOL_CATALOG[PLAN_STAGE]["read_page_range_content"]["description"],
            parameters={
                "type": "object",
                "properties": {
                    "page_start": {
                        "type": "integer",
                        "description": "要查看文本的起始页码。",
                    },
                    "page_end": {
                        "type": "integer",
                        "description": "要查看文本的结束页码。",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "可选。返回文本的最大字符预算。",
                    },
                },
                "required": ["page_start", "page_end"],
                "additionalProperties": False,
            },
            is_available=lambda context: context.debug_report is not None,
            execute=_execute_read_page_range_content,
        ),
        PlanToolDefinition(
            name="read_page_range_images",
            description=TOOL_CATALOG[PLAN_STAGE]["read_page_range_images"]["description"],
            parameters={
                "type": "object",
                "properties": {
                    "page_start": {
                        "type": "integer",
                        "description": "要渲染图像的起始页码。",
                    },
                    "page_end": {
                        "type": "integer",
                        "description": "要渲染图像的结束页码。",
                    },
                    "max_images": {
                        "type": "integer",
                        "description": "可选。最多返回的页图像数量。",
                    },
                },
                "required": ["page_start", "page_end"],
                "additionalProperties": False,
            },
            is_available=lambda context: context.multimodal_enabled and bool(context.document_path),
            execute=_execute_read_page_range_images,
        ),
    ]


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
            trace_summary="计划完成度偏低：当前没有可用的学习单元",
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
    if any((unit.page_end - unit.page_start + 1) >= 80 for unit in plannable_units):
        span_penalty = 0.18
    if len(plannable_units) <= 2:
        span_penalty += 0.08
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
        label = "可以收束成稿"
    elif score >= 60:
        label = "还需要一轮打磨"
    else:
        label = "建议继续细化"
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
        recommendations.append("目录细度和行动性已经足够，可以开始生成最终计划。")
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
        trace_summary=f"计划完成度 {score}/100：{label}",
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
