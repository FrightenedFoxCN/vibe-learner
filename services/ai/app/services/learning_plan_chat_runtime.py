from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG
from app.services.plans import LearningPlanService


PLAN_CHAT_TOOL_NAMES = (
    "read_learning_plan_progress",
    "update_learning_plan_progress",
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
            {
                "type": "function",
                "function": {
                    "name": "update_learning_plan_progress",
                    "description": TOOL_CATALOG[CHAT_STAGE]["update_learning_plan_progress"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "schedule_id": {
                                "type": "string",
                                "description": "单个排期项 ID；与 schedule_ids 二选一即可。",
                            },
                            "schedule_ids": {
                                "type": "array",
                                "description": "一组需要更新状态的排期项 ID。",
                                "items": {"type": "string"},
                            },
                            "status": {
                                "type": "string",
                                "enum": ["planned", "in_progress", "completed", "blocked", "skipped"],
                                "description": "新的计划状态。",
                            },
                            "note": {
                                "type": "string",
                                "description": "可选。记录为什么要更新这次状态。",
                            },
                        },
                        "required": ["status"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "read_learning_plan_progress":
            return self._service.describe_progress(self.plan_id)
        if tool_name == "update_learning_plan_progress":
            schedule_ids = []
            single_schedule_id = str(arguments.get("schedule_id") or "").strip()
            if single_schedule_id:
                schedule_ids.append(single_schedule_id)
            raw_schedule_ids = arguments.get("schedule_ids")
            if isinstance(raw_schedule_ids, list):
                schedule_ids.extend(str(item).strip() for item in raw_schedule_ids if str(item).strip())
            updated = self._service.update_progress(
                plan_id=self.plan_id,
                schedule_ids=schedule_ids,
                status=str(arguments.get("status") or ""),
                note=str(arguments.get("note") or ""),
                actor="assistant",
                source="chat_tool",
            )
            payload = self._service.describe_progress(self.plan_id)
            payload["tool_name"] = "update_learning_plan_progress"
            payload["updated_schedule_ids"] = schedule_ids
            payload["updated_status"] = str(arguments.get("status") or "")
            payload["note"] = str(arguments.get("note") or "")
            payload["progress_event_id"] = updated.progress_events[-1].id if updated.progress_events else ""
            return payload
        raise HTTPException(status_code=400, detail="plan_tool_unknown")
