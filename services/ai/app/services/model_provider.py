from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable
from typing import Any

from app.core.logging import get_logger
from app.models.domain import (
    DocumentDebugRecord,
    LearningGoalInput,
    PlanGenerationRoundRecord,
    PlanGenerationTraceRecord,
    PlanToolCallTraceRecord,
    PersonaProfile,
    StudyUnitRecord,
)
from app.services.plan_prompt import (
    build_learning_plan_context,
    build_learning_plan_messages,
    read_page_range_content,
)

logger = get_logger("gal_learner.model_provider")


PLAN_TOOL_SPECS = [
    {
        "name": "get_study_unit_detail",
        "description": (
            "Read the detailed subsection structure and chunk excerpts for one study unit "
            "before finalizing the learning plan."
        ),
    },
    {
        "name": "read_page_range_content",
        "description": (
            "Read longer textbook content for a specific page range when the planner needs "
            "more detail than the chunk excerpts."
        ),
    },
]


@dataclass
class ModelReply:
    text: str
    mood: str
    action: str


@dataclass
class PlanScheduleItem:
    unit_id: str
    title: str
    scheduled_date: str
    focus: str
    activity_type: str
    estimated_minutes: int


@dataclass
class PlanModelReply:
    course_title: str
    overview: str
    weekly_focus: list[str]
    today_tasks: list[str]
    schedule: list[PlanScheduleItem]
    debug_trace: PlanGenerationTraceRecord | None = None


class ModelProvider:
    def generate_chat(
        self, *, persona: PersonaProfile, section_id: str, message: str
    ) -> ModelReply:
        raise NotImplementedError

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ModelReply:
        raise NotImplementedError

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> ModelReply:
        raise NotImplementedError

    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> PlanModelReply:
        raise NotImplementedError


class MockModelProvider(ModelProvider):
    def generate_chat(
        self, *, persona: PersonaProfile, section_id: str, message: str
    ) -> ModelReply:
        style = persona.teaching_style[0] if persona.teaching_style else "structured"
        text = (
            f"{persona.name} 正在结合章节 {section_id} 讲解。"
            f" 当前提问是：{message}。"
            f" 我会用 {style} 的方式先解释核心概念，再给你一个复述任务。"
        )
        mood = "playful" if persona.narrative_mode == "light_story" else "calm"
        return ModelReply(text=text, mood=mood, action="explain")

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ModelReply:
        text = (
            f"围绕 {section_id} 的 {topic}，请你先用三句话概括概念，"
            "再举一个教材中的例子。"
        )
        return ModelReply(text=text, mood="encouraging", action="prompt")

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> ModelReply:
        quality = "完整" if len(answer.strip()) > 24 else "偏短"
        text = (
            f"针对练习 {exercise_id}，你的回答{quality}。"
            " 我会指出遗漏点，并给出下一步复习建议。"
        )
        mood = "excited" if quality == "完整" else "concerned"
        action = "celebrate" if quality == "完整" else "reflect"
        return ModelReply(text=text, mood=mood, action=action)

    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> PlanModelReply:
        plannable_units = [unit for unit in study_units if unit.include_in_plan] or study_units
        today_tasks = [
            f"阅读 {unit.title}，提取 2 条定义或结论。"
            for unit in plannable_units[:2]
        ]
        if not today_tasks:
            today_tasks = [f"阅读 {document_title}，确认本周目标。"]
        schedule: list[PlanScheduleItem] = []
        for index, unit in enumerate(plannable_units[:4], start=1):
            schedule.append(
                PlanScheduleItem(
                    unit_id=unit.id,
                    title=f"{unit.title} 精读",
                    scheduled_date=goal.deadline,
                    focus=f"在 {unit.title} 中整理概念、例题与疑问。",
                    activity_type="learn",
                    estimated_minutes=goal.session_minutes,
                )
            )
        # course_title is the generated textbook-grounded title; objective remains learner-authored goal text.
        return PlanModelReply(
            course_title=_build_course_title(
                document_title=document_title,
                plannable_units=plannable_units,
            ),
            overview=(
                f"{persona.name} 将围绕 {document_title} 生成首轮学习计划，"
                f"在 {goal.deadline} 前完成 {len(plannable_units)} 个学习单元。"
            ),
            weekly_focus=[unit.title for unit in plannable_units[:4]],
            today_tasks=today_tasks,
            schedule=schedule,
        )


class OpenAIModelProvider(MockModelProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        plan_model: str,
        timeout_seconds: int = 30,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.plan_model = plan_model
        self.timeout_seconds = timeout_seconds
        self._last_plan_trace: PlanGenerationTraceRecord | None = None

    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> PlanModelReply:
        self._last_plan_trace = None
        planning_context = build_learning_plan_context(
            study_units=study_units,
            debug_report=debug_report,
        )
        messages = build_learning_plan_messages(
            persona=persona,
            document_title=document_title,
            goal=goal,
            study_units=study_units,
            debug_report=debug_report,
        )
        content = self._complete_learning_plan(
            messages=messages,
            detail_map=planning_context["detail_map"],
            debug_report=debug_report,
            document_id=goal.document_id,
            study_unit_count=len(study_units),
            deadline=goal.deadline,
            progress_callback=progress_callback,
        )
        trace = self._last_plan_trace
        parsed = _extract_json_payload(content)
        schedule_items = [
            PlanScheduleItem(
                unit_id=str(item["unit_id"]),
                title=str(item["title"]),
                scheduled_date=str(item["scheduled_date"]),
                focus=str(item["focus"]),
                activity_type=str(item["activity_type"]),
                estimated_minutes=int(item["estimated_minutes"]),
            )
            for item in parsed.get("schedule", [])
        ]
        return PlanModelReply(
            course_title=str(
                parsed.get("course_title")
                or _build_course_title(
                    document_title=document_title,
                    plannable_units=study_units,
                )
            ),
            overview=str(parsed["overview"]),
            weekly_focus=[str(item) for item in parsed.get("weekly_focus", [])],
            today_tasks=[str(item) for item in parsed.get("today_tasks", [])],
            schedule=schedule_items,
            debug_trace=trace,
        )

    def _complete_learning_plan(
        self,
        *,
        messages: list[dict[str, Any]],
        detail_map: dict[str, dict[str, object]],
        debug_report: DocumentDebugRecord | None,
        document_id: str,
        study_unit_count: int,
        deadline: str,
        progress_callback: Callable[[str, dict[str, object]], None] | None,
    ) -> str:
        current_messages: list[dict[str, Any]] = [*messages]
        tools = _build_plan_tools()
        trace = PlanGenerationTraceRecord(
            document_id=document_id,
            model=self.plan_model,
            created_at=_now(),
            rounds=[],
        )
        max_rounds = 4
        for round_index in range(max_rounds):
            _emit_progress(
                progress_callback,
                "model_round_started",
                {
                    "round_index": round_index,
                    "timeout_seconds": self.timeout_seconds,
                    "tools_enabled": bool(detail_map),
                },
            )
            payload: dict[str, Any] = {
                "model": self.plan_model,
                "messages": current_messages,
                "temperature": 0.2,
            }
            if detail_map:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
            else:
                payload["response_format"] = {"type": "json_object"}
            logger.info(
                "model.plan.request provider=openai model=%s study_units=%s deadline=%s tool_round=%s tools_enabled=%s",
                self.plan_model,
                study_unit_count,
                deadline,
                round_index,
                bool(detail_map),
            )
            raw_payload, elapsed_ms = self._request_openai_chat_completion(payload)
            choice = raw_payload["choices"][0]
            message = choice["message"]
            thinking = _extract_reasoning_text(raw_payload=raw_payload, choice=choice, message=message)
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                round_tool_calls: list[PlanToolCallTraceRecord] = []
                current_messages.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                )
                for tool_call in tool_calls:
                    tool_result = self._execute_plan_tool_call(
                        tool_call=tool_call,
                        detail_map=detail_map,
                        debug_report=debug_report,
                    )
                    _emit_progress(
                        progress_callback,
                        "model_tool_call",
                        {
                            "round_index": round_index,
                            "tool_call_id": str(tool_call.get("id") or ""),
                            "tool_name": str(tool_call.get("function", {}).get("name") or ""),
                        },
                    )
                    round_tool_calls.append(
                        PlanToolCallTraceRecord(
                            tool_call_id=str(tool_call.get("id") or ""),
                            tool_name=str(tool_call.get("function", {}).get("name") or ""),
                            arguments_json=str(tool_call.get("function", {}).get("arguments") or "{}"),
                            result_json=json.dumps(tool_result, ensure_ascii=False),
                        )
                    )
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call["id"],
                            "name": tool_call["function"]["name"],
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        }
                    )
                trace.rounds.append(
                    PlanGenerationRoundRecord(
                        round_index=round_index,
                        finish_reason=str(choice.get("finish_reason") or ""),
                        assistant_content=_coerce_text_content(message.get("content")),
                        thinking=thinking,
                        elapsed_ms=elapsed_ms,
                        timeout_seconds=self.timeout_seconds,
                        tool_calls=round_tool_calls,
                    )
                )
                _emit_progress(
                    progress_callback,
                    "model_round_completed",
                    {
                        "round_index": round_index,
                        "elapsed_ms": elapsed_ms,
                        "finish_reason": str(choice.get("finish_reason") or ""),
                        "tool_call_count": len(tool_calls),
                    },
                )
                continue

            content = _coerce_text_content(message.get("content"))
            if content.strip():
                trace.rounds.append(
                    PlanGenerationRoundRecord(
                        round_index=round_index,
                        finish_reason=str(choice.get("finish_reason") or ""),
                        assistant_content=content,
                        thinking=thinking,
                        elapsed_ms=elapsed_ms,
                        timeout_seconds=self.timeout_seconds,
                        tool_calls=[],
                    )
                )
                self._last_plan_trace = trace
                _emit_progress(
                    progress_callback,
                    "model_round_completed",
                    {
                        "round_index": round_index,
                        "elapsed_ms": elapsed_ms,
                        "finish_reason": str(choice.get("finish_reason") or ""),
                        "tool_call_count": 0,
                        "has_content": True,
                    },
                )
                return content
            raise RuntimeError("plan_model_empty_response")
        raise RuntimeError("plan_model_tool_loop_exhausted")

    def _execute_plan_tool_call(
        self,
        *,
        tool_call: dict[str, Any],
        detail_map: dict[str, dict[str, object]],
        debug_report: DocumentDebugRecord | None,
    ) -> dict[str, object]:
        function_payload = tool_call.get("function") or {}
        tool_name = str(function_payload.get("name") or "")
        raw_arguments = function_payload.get("arguments") or "{}"
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            arguments = {}

        if tool_name != "get_study_unit_detail":
            if tool_name == "read_page_range_content":
                page_start = max(1, int(arguments.get("page_start") or 1))
                page_end = max(page_start, int(arguments.get("page_end") or page_start))
                max_chars = max(500, min(6000, int(arguments.get("max_chars") or 3000)))
                return {
                    "ok": True,
                    "tool_name": tool_name,
                    **read_page_range_content(
                        debug_report=debug_report,
                        page_start=page_start,
                        page_end=page_end,
                        max_chars=max_chars,
                    ),
                }
            return {
                "ok": False,
                "error": "unknown_tool",
                "tool_name": tool_name,
            }

        target_id = str(arguments.get("study_unit_id") or "").strip()
        if not target_id:
            return {
                "ok": False,
                "error": "missing_study_unit_id",
            }
        detail = detail_map.get(target_id)
        if detail is None:
            return {
                "ok": False,
                "error": "study_unit_not_found",
                "study_unit_id": target_id,
            }
        logger.info(
            "model.plan.tool_call tool=%s study_unit_id=%s",
            tool_name,
            target_id,
        )
        return {
            "ok": True,
            "tool_name": tool_name,
            "requested_focus": str(arguments.get("focus") or ""),
            "detail": detail,
        }

    def _request_openai_chat_completion(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started_at = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_payload = json.loads(response.read().decode("utf-8"))
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            return raw_payload, elapsed_ms
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            error_code, error_message = _extract_upstream_error(body)
            logger.exception(
                "model.plan.http_error status=%s upstream_code=%s upstream_message=%s body=%s",
                exc.code,
                error_code,
                error_message,
                body,
            )
            if error_code == "rate_limit":
                raise RuntimeError("openai_plan_request_rate_limit") from exc
            raise RuntimeError(
                f"openai_plan_request_failed:{exc.code}:{error_code or 'unknown'}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.exception("model.plan.network_error reason=%s", exc.reason)
            raise RuntimeError("openai_plan_request_network_error") from exc
        except (TimeoutError, socket.timeout) as exc:
            logger.exception("model.plan.timeout timeout_seconds=%s", self.timeout_seconds)
            raise RuntimeError("openai_plan_request_timeout") from exc


def _extract_json_payload(content: str) -> dict[str, object]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("plan_model_invalid_json")
        payload = json.loads(content[start : end + 1])
    if not isinstance(payload, dict):
        raise RuntimeError("plan_model_invalid_payload")
    return payload


def get_learning_plan_tool_specs() -> list[dict[str, str]]:
    return PLAN_TOOL_SPECS


def _build_plan_tools() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "get_study_unit_detail",
                "description": PLAN_TOOL_SPECS[0]["description"],
                "parameters": {
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
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_page_range_content",
                "description": PLAN_TOOL_SPECS[1]["description"],
                "parameters": {
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
            },
        },
    ]


def _extract_reasoning_text(
    *,
    raw_payload: dict[str, Any],
    choice: dict[str, Any],
    message: dict[str, Any],
) -> str:
    candidates = [
        message.get("reasoning_content"),
        message.get("reasoning"),
        message.get("thinking"),
        choice.get("reasoning_content"),
        choice.get("reasoning"),
        raw_payload.get("reasoning_content"),
        raw_payload.get("reasoning"),
    ]
    parts = [_coerce_text_content(candidate) for candidate in candidates]
    text = "\n\n".join(part for part in parts if part)
    return text[:12000]


def _coerce_text_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_coerce_text_content(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        return json.dumps(value, ensure_ascii=False)
    return str(value)


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


def _build_course_title(
    *,
    document_title: str,
    plannable_units: list[StudyUnitRecord],
) -> str:
    lead_titles = [unit.title.strip() for unit in plannable_units[:2] if unit.title.strip()]
    if lead_titles:
        return " / ".join(lead_titles)
    return document_title.strip()


def _extract_upstream_error(body: str) -> tuple[str, str]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return "", body[:200]
    if not isinstance(payload, dict):
        return "", body[:200]
    error = payload.get("error")
    if not isinstance(error, dict):
        return "", body[:200]
    return str(error.get("code", "")), str(error.get("message", ""))
