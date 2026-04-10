from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from typing import Any

from app.core.logging import get_logger
from app.models.domain import (
    DocumentDebugRecord,
    LearningGoalInput,
    PlanGenerationTraceRecord,
    PersonaProfile,
    StudyUnitRecord,
)
from app.services.openai_plan_runner import OpenAIPlanRunner
from app.services.plan_prompt import (
    build_learning_plan_context,
    build_learning_plan_messages,
)
from app.services.plan_tool_runtime import build_plan_tool_runtime

logger = get_logger("gal_learner.model_provider")


@dataclass
class ModelReply:
    text: str
    mood: str
    action: str


@dataclass
class PlanScheduleItem:
    unit_id: str
    title: str
    focus: str
    activity_type: str


@dataclass
class PlanModelReply:
    course_title: str
    overview: str
    weekly_focus: list[str]
    today_tasks: list[str]
    schedule: list[PlanScheduleItem]
    revised_study_units: list[StudyUnitRecord] | None = None
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
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> PlanModelReply:
        raise NotImplementedError

    def supports_page_image_tools(self) -> bool:
        return False


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
        document_path: str | None = None,
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
        for unit in plannable_units[:4]:
            schedule.append(
                PlanScheduleItem(
                    unit_id=unit.id,
                    title=f"{unit.title} 精读",
                    focus=f"在 {unit.title} 中整理概念、例题与疑问。",
                    activity_type="learn",
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
                f"覆盖 {len(plannable_units)} 个学习单元。"
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
        multimodal_enabled: bool = False,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.plan_model = plan_model
        self.timeout_seconds = timeout_seconds
        self.multimodal_enabled = multimodal_enabled

    def supports_page_image_tools(self) -> bool:
        return self.multimodal_enabled

    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> PlanModelReply:
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
        tool_runtime = build_plan_tool_runtime(
            study_units=study_units,
            detail_map=planning_context["detail_map"],
            debug_report=debug_report,
            document_path=document_path,
            multimodal_enabled=self.multimodal_enabled,
        )
        runner = OpenAIPlanRunner(
            model=self.plan_model,
            timeout_seconds=self.timeout_seconds,
            request_chat_completion=self._request_openai_chat_completion,
        )
        run_result = runner.run(
            document_id=goal.document_id,
            messages=messages,
            tool_runtime=tool_runtime,
            progress_callback=progress_callback,
        )
        parsed = _extract_json_payload(run_result.content)
        schedule_items = [
            PlanScheduleItem(
                unit_id=str(item["unit_id"]),
                title=str(item["title"]),
                focus=str(item["focus"]),
                activity_type=str(item["activity_type"]),
            )
            for item in parsed.get("schedule", [])
        ]
        active_study_units = tool_runtime.current_study_units()
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
            revised_study_units=active_study_units if _study_units_changed(study_units, active_study_units) else None,
            debug_trace=run_result.trace,
        )

    def _request_openai_chat_completion(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        tools_enabled = "tools" in payload
        tool_round = len([message for message in payload.get("messages", []) if message.get("role") == "tool"])
        logger.info(
            "model.plan.request provider=openai model=%s tool_round=%s tools_enabled=%s",
            self.plan_model,
            tool_round,
            tools_enabled,
        )
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


def _build_course_title(
    *,
    document_title: str,
    plannable_units: list[StudyUnitRecord],
) -> str:
    lead_titles = [unit.title.strip() for unit in plannable_units[:2] if unit.title.strip()]
    if lead_titles:
        return " / ".join(lead_titles)
    return document_title.strip()


def _study_units_changed(
    original_units: list[StudyUnitRecord],
    current_units: list[StudyUnitRecord],
) -> bool:
    if len(original_units) != len(current_units):
        return True
    for original, current in zip(original_units, current_units):
        if (
            original.id != current.id
            or original.title != current.title
            or original.page_start != current.page_start
            or original.page_end != current.page_end
            or original.include_in_plan != current.include_in_plan
        ):
            return True
    return False


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
