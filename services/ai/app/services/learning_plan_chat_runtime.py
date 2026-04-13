from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG
from app.services.plans import LearningPlanService


PLAN_CHAT_TOOL_NAMES = (
    "read_learning_plan_progress",
)


class LearningPlanChatToolRuntime:
    def __init__(self, service: LearningPlanService, plan_id: str) -> None:
        self._service = service
        self.plan_id = plan_id

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in PLAN_CHAT_TOOL_NAMES

    def plan_context(self) -> str:
        payload = self._service.describe_progress(self.plan_id)
        progress = payload["progress_summary"]
        chapter_lines = [
            (
                f"- {item['unit_id']} | {item['status']} | {item['title']} | "
                f"{item['completed_schedule_count']}/{item['total_schedule_count']} "
                f"({item['completion_percent']}%) | {item['objective_fragment'] or '无'}"
            )
            for item in payload.get("chapter_progress", [])[:6]
        ]
        schedule_lines = [
            (
                f"- {item['id']} | {item['status']} | {item['title']} | "
                f"{item['focus']}"
            )
            for item in payload["schedule"][:8]
        ]
        question_lines = [
            f"- {item['id']} | {item['question']}"
            for item in payload["pending_planning_questions"][:4]
        ]
        return (
            f"当前计划：{payload['course_title']}\n"
            f"计划模式：{payload['creation_mode']}\n"
            f"学习目标：{payload['objective'] or '未填写'}\n"
            f"完成度：{progress['completed_schedule_count']}/{progress['total_schedule_count']} "
            f"（{progress['completion_percent']}%）\n"
            f"进行中：{progress['in_progress_schedule_count']}，待处理：{progress['pending_schedule_count']}，"
            f"阻塞：{progress['blocked_schedule_count']}\n"
            f"章节完成度：\n{chr(10).join(chapter_lines) if chapter_lines else '- 暂无章节进度'}\n"
            f"排期项：\n{chr(10).join(schedule_lines) if schedule_lines else '- 暂无排期项'}\n"
            f"待补充规划问题：\n{chr(10).join(question_lines) if question_lines else '- 无'}"
        )

    def tool_specs(self) -> list[dict[str, object]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_learning_plan_progress",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_learning_plan_progress"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "read_learning_plan_progress":
            return self._service.describe_progress(self.plan_id)
        raise HTTPException(status_code=400, detail="plan_tool_unknown")
