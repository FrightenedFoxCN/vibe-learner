from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from app.models.domain import DocumentDebugRecord, StudyUnitRecord
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
                trace_summary=f"{tool_name}: unknown tool",
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
    disabled_tools: set[str] | None = None,
) -> PlanToolRuntime:
    return PlanToolRuntime(
        context=PlanToolRuntimeContext(
            study_units=list(study_units or []),
            detail_map=detail_map or {},
            debug_report=debug_report,
            document_path=document_path,
            multimodal_enabled=multimodal_enabled,
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
            description=(
                "Read the detailed subsection structure and chunk excerpts for one study unit "
                "before finalizing the learning plan."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "study_unit_id": {
                        "type": "string",
                        "description": "The target study unit id from the provided study_units list.",
                    },
                    "focus": {
                        "type": "string",
                        "description": "Optional reason for inspection, such as subsection coverage or examples.",
                    },
                },
                "required": ["study_unit_id"],
                "additionalProperties": False,
            },
            is_available=lambda context: bool(context.detail_map),
            execute=_execute_get_study_unit_detail,
        ),
        PlanToolDefinition(
            name="revise_study_units",
            description=(
                "Replace the current study-unit segmentation when the cleaned chapter split is clearly wrong. "
                "Return a full revised unit list with page ranges."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "study_units": {
                        "type": "array",
                        "description": "Full replacement list for the active study-unit segmentation.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "Learner-facing chapter or unit title.",
                                },
                                "page_start": {
                                    "type": "integer",
                                    "description": "Inclusive start page for the revised unit.",
                                },
                                "page_end": {
                                    "type": "integer",
                                    "description": "Inclusive end page for the revised unit.",
                                },
                                "include_in_plan": {
                                    "type": "boolean",
                                    "description": "Whether this unit should be scheduled in the learning plan.",
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "Optional short summary for the revised unit.",
                                },
                            },
                            "required": ["title", "page_start", "page_end"],
                            "additionalProperties": False,
                        },
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Optional reason for why the original segmentation should be replaced.",
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
            description=(
                "Read longer textbook content for a specific page range when the planner needs "
                "more detail than the chunk excerpts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "page_start": {
                        "type": "integer",
                        "description": "Start page of the content to inspect.",
                    },
                    "page_end": {
                        "type": "integer",
                        "description": "End page of the content to inspect.",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": "Optional output budget for returned content.",
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
            description=(
                "Render textbook pages as images for multimodal inspection when the planner needs "
                "formulas, diagrams, tables, or layout cues."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "page_start": {
                        "type": "integer",
                        "description": "Start page of the page images to inspect.",
                    },
                    "page_end": {
                        "type": "integer",
                        "description": "End page of the page images to inspect.",
                    },
                    "max_images": {
                        "type": "integer",
                        "description": "Optional cap on the number of rendered page images.",
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
            trace_summary="missing study_unit_id",
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
            trace_summary=f"study unit not found: {target_id}",
            follow_up_messages=[],
        )
    return PlanToolResult(
        payload={
            "ok": True,
            "tool_name": "get_study_unit_detail",
            "requested_focus": str(arguments.get("focus") or ""),
            "detail": detail,
        },
        trace_summary=f"loaded detail for {target_id}",
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
            trace_summary="missing revised study_units payload",
            follow_up_messages=[],
        )
    debug_report = context.debug_report
    if debug_report is None:
        return PlanToolResult(
            payload={
                "ok": False,
                "error": "missing_debug_report",
            },
            trace_summary="missing debug report for segmentation revision",
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
            trace_summary=f"invalid study-unit revision: {exc}",
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
        trace_summary=f"read pages {page_start}-{page_end} as text",
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
                            "Rendered textbook page images are attached for visual inspection. "
                            "Use them to inspect formulas, diagrams, tables, or layout when planning."
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
        trace_summary=f"rendered {len(page_numbers)} page image(s) for pages {page_start}-{page_end}",
        follow_up_messages=follow_up_messages,
    )


def _build_study_unit_revision_summary(
    *,
    revised_units: list[StudyUnitRecord],
    rationale: str,
) -> str:
    parts = [
        f"{unit.title} (p.{unit.page_start}-{unit.page_end})"
        for unit in revised_units[:4]
    ]
    if len(revised_units) > 4:
        parts.append(f"+{len(revised_units) - 4} more")
    summary = f"revised to {len(revised_units)} unit(s): " + "; ".join(parts)
    if rationale:
        summary += f" | rationale: {rationale}"
    return summary
