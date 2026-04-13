from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import (
    Citation,
    LearnerAttachmentRecord,
    PdfRectRecord,
    ProjectedPdfOverlayRecord,
    SessionPlanConfirmationRecord,
    SessionProjectedPdfRecord,
)
from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG
from app.services.plans import LearningPlanService
from app.services.plan_prompt import read_page_range_images
from app.services.study_chat_attachments import extract_pdf_page_range_text, search_pdf_text_rects
from app.services.study_sessions import StudySessionService


SESSION_CHAT_TOOL_NAMES = (
    "read_system_time",
    "read_session_memory",
    "write_session_memory",
    "read_affinity_state",
    "update_affinity_state",
    "schedule_session_follow_up",
    "update_learning_plan",
    "update_learning_plan_progress",
    "project_uploaded_pdf",
    "project_uploaded_image",
    "generate_projected_image",
    "read_projected_pdf_content",
    "read_projected_pdf_images",
    "focus_projected_pdf_page",
    "highlight_projected_pdf_text",
    "annotate_projected_pdf_region",
    "clear_projected_pdf_overlays",
    "annotate_projected_image_region",
    "clear_projected_image_overlays",
)


class StudySessionChatToolRuntime:
    def __init__(
        self,
        *,
        session_service: StudySessionService,
        plan_service: LearningPlanService,
        session_id: str,
        plan_id: str | None = None,
        transient_attachments: list[LearnerAttachmentRecord] | None = None,
        multimodal_enabled: bool = False,
        model_provider: Any | None = None,
    ) -> None:
        self._session_service = session_service
        self._plan_service = plan_service
        self.session_id = session_id
        self.plan_id = plan_id.strip() if plan_id else ""
        self._transient_attachments = list(transient_attachments or [])
        self._multimodal_enabled = multimodal_enabled
        self._model_provider = model_provider
        self._response_citations: list[Citation] = []

    def has_tool(self, tool_name: str) -> bool:
        if tool_name == "update_learning_plan" and not self.plan_id:
            return False
        if tool_name == "update_learning_plan_progress" and not self.plan_id:
            return False
        if tool_name == "read_projected_pdf_images" and not self._multimodal_enabled:
            return False
        if tool_name == "generate_projected_image":
            return bool(
                self._model_provider is not None
                and getattr(self._model_provider, "supports_chat_generated_image_tools", lambda: False)()
            )
        return tool_name in SESSION_CHAT_TOOL_NAMES

    def session_context(self) -> str:
        session = self._session_service.require_session(self.session_id)
        memory_lines = [
            f"- {item.key}: {item.content}"
            for item in session.session_memory[-6:]
        ]
        pending_confirmation_lines = [
            f"- {item.title} | {item.summary or '待用户确认'}"
            for item in session.plan_confirmations
            if item.status == "pending"
        ]
        pending_follow_up_lines = [
            f"- {item.due_at} | {item.reason or '自动续接对话'}"
            for item in session.pending_follow_ups
            if item.status == "pending"
        ]
        prepared_sections = ", ".join(session.prepared_section_ids[-6:]) or "无"
        affinity = session.affinity_state
        pdf_attachment_lines = [
            f"- {item.attachment_id} | {item.name} | pages={item.page_count or '?'}"
            for item in self._session_service.list_attachments(
                session_id=self.session_id,
                kind="pdf",
                transient_attachments=self._transient_attachments,
            )[-8:]
        ]
        image_attachment_lines = [
            f"- {item.attachment_id} | {item.name}"
            for item in self._session_service.list_attachments(
                session_id=self.session_id,
                kind="image",
                transient_attachments=self._transient_attachments,
            )[-8:]
        ]
        projected_pdf = session.projected_pdf
        projected_pdf_line = (
            f"{projected_pdf.title} | source={projected_pdf.source_kind}:{projected_pdf.source_id} | "
            f"page={projected_pdf.page_number}/{projected_pdf.page_count or '?'} | overlays={len(projected_pdf.overlays)}"
            if projected_pdf is not None
            else "无"
        )
        return (
            f"已做过预处理的章节：{prepared_sections}\n"
            f"临时记忆：\n{chr(10).join(memory_lines) if memory_lines else '- 无'}\n"
            f"好感度：score={affinity.score} | level={affinity.level} | summary={affinity.summary or '无'}\n"
            f"当前可投射 PDF 附件：\n{chr(10).join(pdf_attachment_lines) if pdf_attachment_lines else '- 无'}\n"
            f"当前可投射图片附件：\n{chr(10).join(image_attachment_lines) if image_attachment_lines else '- 无'}\n"
            f"当前投射 PDF：{projected_pdf_line}\n"
            f"待确认计划操作：\n{chr(10).join(pending_confirmation_lines) if pending_confirmation_lines else '- 无'}\n"
            f"待触发自动续接：\n{chr(10).join(pending_follow_up_lines) if pending_follow_up_lines else '- 无'}"
        )

    def response_citations(self) -> list[Citation]:
        return list(self._response_citations)

    def tool_specs(self) -> list[dict[str, object]]:
        tools: list[dict[str, object]] = [
            {
                "type": "function",
                "function": {
                    "name": "read_system_time",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_system_time"]["description"],
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
                    "name": "read_session_memory",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_session_memory"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "可选。只读取某个 key 的临时记忆。",
                            },
                            "limit": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 12,
                                "description": "最多返回多少条。",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "write_session_memory",
                    "description": TOOL_CATALOG[CHAT_STAGE]["write_session_memory"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "临时记忆 key，建议使用短而稳定的标签。",
                            },
                            "content": {
                                "type": "string",
                                "description": "要记录的临时记忆内容。",
                            },
                        },
                        "required": ["key", "content"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_affinity_state",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_affinity_state"]["description"],
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
                    "name": "update_affinity_state",
                    "description": TOOL_CATALOG[CHAT_STAGE]["update_affinity_state"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "delta": {
                                "type": "integer",
                                "minimum": -20,
                                "maximum": 20,
                                "description": "本轮对好感度的增减。",
                            },
                            "reason": {
                                "type": "string",
                                "description": "为什么要调整好感度。",
                            },
                        },
                        "required": ["delta"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "schedule_session_follow_up",
                    "description": TOOL_CATALOG[CHAT_STAGE]["schedule_session_follow_up"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "delay_seconds": {
                                "type": "integer",
                                "minimum": 10,
                                "maximum": 1800,
                                "description": "多少秒后自动续接这次对话。",
                            },
                            "prompt": {
                                "type": "string",
                                "description": "到时唤醒时要发送给模型的隐藏提示词。",
                            },
                            "reason": {
                                "type": "string",
                                "description": "可选。为什么要这样安排自动续接。",
                            },
                        },
                        "required": ["delay_seconds", "prompt"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "project_uploaded_pdf",
                    "description": TOOL_CATALOG[CHAT_STAGE]["project_uploaded_pdf"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "attachment_id": {
                                "type": "string",
                                "description": "要投射到预览窗口的 PDF 附件 ID。",
                            },
                            "page_number": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "可选。初始定位页码。",
                            },
                        },
                        "required": ["attachment_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "project_uploaded_image",
                    "description": TOOL_CATALOG[CHAT_STAGE]["project_uploaded_image"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "attachment_id": {
                                "type": "string",
                                "description": "要投射到预览窗口的图片附件 ID。",
                            },
                        },
                        "required": ["attachment_id"],
                        "additionalProperties": False,
                    },
                },
            },
            *(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "generate_projected_image",
                            "description": TOOL_CATALOG[CHAT_STAGE]["generate_projected_image"]["description"],
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "prompt": {
                                        "type": "string",
                                        "description": "要生成并投到预览窗口的图像描述，应明确主题、构图和关键标注。",
                                    },
                                    "title": {
                                        "type": "string",
                                        "description": "可选。预览窗口中的图像标题。",
                                    },
                                    "size": {
                                        "type": "string",
                                        "description": "可选。图像尺寸，例如 1024x1024、1536x1024 或 1024x1536。",
                                    },
                                },
                                "required": ["prompt"],
                                "additionalProperties": False,
                            },
                        },
                    }
                ]
                if self.has_tool("generate_projected_image")
                else []
            ),
            {
                "type": "function",
                "function": {
                    "name": "read_projected_pdf_content",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_projected_pdf_content"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_start": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "要读取的起始页码。",
                            },
                            "page_end": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "要读取的结束页码。",
                            },
                            "max_chars": {
                                "type": "integer",
                                "minimum": 800,
                                "maximum": 8000,
                                "description": "最大字符预算。",
                            },
                        },
                        "required": ["page_start", "page_end"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "focus_projected_pdf_page",
                    "description": TOOL_CATALOG[CHAT_STAGE]["focus_projected_pdf_page"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_number": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "需要聚焦到的页码。",
                            },
                        },
                        "required": ["page_number"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "highlight_projected_pdf_text",
                    "description": TOOL_CATALOG[CHAT_STAGE]["highlight_projected_pdf_text"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_number": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "文字所在页码。",
                            },
                            "quote_text": {
                                "type": "string",
                                "description": "要在 PDF 页面上定位并高亮的文字片段。",
                            },
                            "label": {
                                "type": "string",
                                "description": "可选。给这次高亮附上的简短说明。",
                            },
                            "color": {
                                "type": "string",
                                "description": "可选。高亮颜色，例如 #FACC15。",
                            },
                        },
                        "required": ["page_number", "quote_text"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "annotate_projected_pdf_region",
                    "description": TOOL_CATALOG[CHAT_STAGE]["annotate_projected_pdf_region"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_number": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "要框选的页码。",
                            },
                            "x": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": "框选区域左上角横坐标，使用页面归一化坐标。",
                            },
                            "y": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": "框选区域左上角纵坐标，使用页面归一化坐标。",
                            },
                            "width": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": "框选区域宽度，使用页面归一化坐标。",
                            },
                            "height": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                                "description": "框选区域高度，使用页面归一化坐标。",
                            },
                            "label": {
                                "type": "string",
                                "description": "可选。给框选区域附上的简短说明。",
                            },
                            "color": {
                                "type": "string",
                                "description": "可选。框选颜色，例如 #38BDF8。",
                            },
                        },
                        "required": ["page_number", "x", "y", "width", "height"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "clear_projected_pdf_overlays",
                    "description": TOOL_CATALOG[CHAT_STAGE]["clear_projected_pdf_overlays"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_number": {
                                "type": "integer",
                                "minimum": 1,
                                "description": "可选。只清空某一页标注；不填则清空全部。",
                            },
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "annotate_projected_image_region",
                    "description": TOOL_CATALOG[CHAT_STAGE]["annotate_projected_image_region"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number", "minimum": 0, "maximum": 1},
                            "y": {"type": "number", "minimum": 0, "maximum": 1},
                            "width": {"type": "number", "minimum": 0, "maximum": 1},
                            "height": {"type": "number", "minimum": 0, "maximum": 1},
                            "label": {"type": "string"},
                            "color": {"type": "string"},
                        },
                        "required": ["x", "y", "width", "height"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "clear_projected_image_overlays",
                    "description": TOOL_CATALOG[CHAT_STAGE]["clear_projected_image_overlays"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            },
        ]
        if self._multimodal_enabled:
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": "read_projected_pdf_images",
                        "description": TOOL_CATALOG[CHAT_STAGE]["read_projected_pdf_images"]["description"],
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "page_start": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "description": "要渲染图像的起始页码。",
                                },
                                "page_end": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "description": "要渲染图像的结束页码。",
                                },
                                "max_images": {
                                    "type": "integer",
                                    "minimum": 1,
                                    "maximum": 4,
                                    "description": "最多返回多少页图像。",
                                },
                            },
                            "required": ["page_start", "page_end"],
                            "additionalProperties": False,
                        },
                    },
                }
            )
        if self.plan_id:
            tools.extend(
                [
                    {
                        "type": "function",
                        "function": {
                            "name": "update_learning_plan",
                            "description": TOOL_CATALOG[CHAT_STAGE]["update_learning_plan"]["description"],
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "course_title": {
                                        "type": "string",
                                        "description": "可选。新的课程标题。",
                                    },
                                    "study_chapters": {
                                        "type": "array",
                                        "description": "可选。新的学习章节标题列表。",
                                        "items": {"type": "string"},
                                    },
                                    "note": {
                                        "type": "string",
                                        "description": "为什么要这样调整计划。",
                                    },
                                },
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
                                    "chapter_unit_id": {
                                        "type": "string",
                                        "description": "可选。按章节整体更新时使用。",
                                    },
                                    "chapter_unit_ids": {
                                        "type": "array",
                                        "description": "可选。批量按章节整体更新时使用。",
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
            )
        return tools

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "read_system_time":
            now = datetime.now().astimezone()
            return {
                "ok": True,
                "tool_name": tool_name,
                "iso_datetime": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "timezone": str(now.tzinfo or ""),
                "weekday": now.strftime("%A"),
            }

        if tool_name == "read_session_memory":
            session = self._session_service.require_session(self.session_id)
            requested_key = str(arguments.get("key") or "").strip()
            limit = max(1, min(int(arguments.get("limit") or 6), 12))
            items = session.session_memory
            if requested_key:
                items = [item for item in items if item.key == requested_key]
            return {
                "ok": True,
                "tool_name": tool_name,
                "memory_items": [item.model_dump(mode="json") for item in items[-limit:]],
            }

        if tool_name == "write_session_memory":
            key = str(arguments.get("key") or "").strip()
            content = str(arguments.get("content") or "").strip()
            updated_session = self._session_service.upsert_session_memory(
                session_id=self.session_id,
                key=key,
                content=content,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "saved_key": key,
                "memory_count": len(updated_session.session_memory),
            }

        if tool_name == "read_affinity_state":
            session = self._session_service.require_session(self.session_id)
            affinity = session.affinity_state
            return {
                "ok": True,
                "tool_name": tool_name,
                "score": affinity.score,
                "level": affinity.level,
                "summary": affinity.summary,
                "updated_at": affinity.updated_at,
                "recent_events": [
                    item.model_dump(mode="json")
                    for item in affinity.events[-6:]
                ],
            }

        if tool_name == "update_affinity_state":
            delta = max(-20, min(int(arguments.get("delta") or 0), 20))
            reason = str(arguments.get("reason") or "").strip()
            updated_session = self._session_service.update_affinity(
                session_id=self.session_id,
                delta=delta,
                reason=reason,
            )
            affinity = updated_session.affinity_state
            return {
                "ok": True,
                "tool_name": tool_name,
                "score": affinity.score,
                "level": affinity.level,
                "summary": affinity.summary,
                "updated_at": affinity.updated_at,
            }

        if tool_name == "schedule_session_follow_up":
            delay_seconds = max(10, min(int(arguments.get("delay_seconds") or 30), 1800))
            prompt = str(arguments.get("prompt") or "").strip()
            reason = str(arguments.get("reason") or "").strip()
            if not prompt:
                raise HTTPException(status_code=422, detail="follow_up_prompt_required")
            follow_up = self._session_service.schedule_follow_up(
                session_id=self.session_id,
                delay_seconds=delay_seconds,
                hidden_message=prompt,
                reason=reason,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "requires_client_schedule": True,
                "follow_up": follow_up.model_dump(mode="json"),
            }

        if tool_name == "project_uploaded_pdf":
            attachment_id = str(arguments.get("attachment_id") or "").strip()
            page_number = max(1, int(arguments.get("page_number") or 1))
            attachment = self._require_pdf_attachment(attachment_id)
            projected_pdf = SessionProjectedPdfRecord(
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
                title=attachment.name,
                page_number=min(page_number, max(1, attachment.page_count or page_number)),
                page_count=attachment.page_count,
                overlays=[],
                updated_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.upsert_projected_pdf(
                session_id=self.session_id,
                projected_pdf=projected_pdf,
            )
            citation = self._push_citation(
                title=attachment.name,
                page_start=projected_pdf.page_number,
                page_end=projected_pdf.page_number,
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "projected_pdf": projected_pdf.model_dump(mode="json"),
                "citation": citation.model_dump(mode="json"),
            }

        if tool_name == "project_uploaded_image":
            attachment_id = str(arguments.get("attachment_id") or "").strip()
            attachment = self._require_image_attachment(attachment_id)
            projected_pdf = SessionProjectedPdfRecord(
                source_kind="attachment_image",
                source_id=attachment.attachment_id,
                title=attachment.name,
                page_number=1,
                page_count=1,
                overlays=[],
                updated_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.upsert_projected_pdf(
                session_id=self.session_id,
                projected_pdf=projected_pdf,
            )
            citation = self._push_citation(
                title=attachment.name,
                page_start=1,
                page_end=1,
                source_kind="attachment_image",
                source_id=attachment.attachment_id,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "projected_pdf": projected_pdf.model_dump(mode="json"),
                "citation": citation.model_dump(mode="json"),
            }

        if tool_name == "generate_projected_image":
            if self._model_provider is None:
                raise HTTPException(status_code=422, detail="chat_image_generation_unsupported")
            prompt = str(arguments.get("prompt") or "").strip()
            title = str(arguments.get("title") or "").strip() or "AI 生成图像"
            size = str(arguments.get("size") or "1024x1024").strip() or "1024x1024"
            if not prompt:
                raise HTTPException(status_code=422, detail="chat_image_generation_prompt_required")
            try:
                generated = self._model_provider.generate_projected_image(
                    prompt=prompt,
                    size=size,
                )
            except RuntimeError as exc:
                return {
                    "ok": False,
                    "tool_name": tool_name,
                    "error": str(exc),
                }
            projected_pdf = SessionProjectedPdfRecord(
                source_kind="generated_image",
                source_id=f"generated-image-{uuid4().hex[:10]}",
                title=title,
                page_number=1,
                page_count=1,
                image_url=str(generated.get("image_url") or ""),
                overlays=[],
                updated_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.upsert_projected_pdf(
                session_id=self.session_id,
                projected_pdf=projected_pdf,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "projected_pdf": projected_pdf.model_dump(mode="json"),
                "revised_prompt": str(generated.get("revised_prompt") or ""),
            }

        if tool_name == "read_projected_pdf_content":
            attachment, projected_pdf = self._require_projected_pdf_attachment()
            page_start = max(1, int(arguments.get("page_start") or projected_pdf.page_number or 1))
            page_end = max(page_start, int(arguments.get("page_end") or page_start))
            max_chars = max(800, min(int(arguments.get("max_chars") or 4000), 8000))
            content = extract_pdf_page_range_text(
                pdf_path=attachment.stored_path,
                page_start=page_start,
                page_end=page_end,
                max_chars=max_chars,
            )
            self._push_citation(
                title=attachment.name,
                page_start=page_start,
                page_end=page_end,
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "source_kind": projected_pdf.source_kind,
                "source_id": projected_pdf.source_id,
                **content,
            }

        if tool_name == "read_projected_pdf_images":
            attachment, projected_pdf = self._require_projected_pdf_attachment()
            page_start = max(1, int(arguments.get("page_start") or projected_pdf.page_number or 1))
            page_end = max(page_start, int(arguments.get("page_end") or page_start))
            max_images = max(1, min(int(arguments.get("max_images") or 2), 4))
            payload = read_page_range_images(
                document_path=attachment.stored_path,
                page_start=page_start,
                page_end=page_end,
                max_images=max_images,
            )
            self._push_citation(
                title=attachment.name,
                page_start=page_start,
                page_end=page_end,
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "source_kind": projected_pdf.source_kind,
                "source_id": projected_pdf.source_id,
                **payload,
            }

        if tool_name == "focus_projected_pdf_page":
            attachment, _ = self._require_projected_pdf_attachment()
            page_number = max(1, int(arguments.get("page_number") or 1))
            resolved_page = min(page_number, max(1, attachment.page_count or page_number))
            session = self._session_service.focus_projected_pdf_page(
                session_id=self.session_id,
                page_number=resolved_page,
            )
            citation = self._push_citation(
                title=attachment.name,
                page_start=resolved_page,
                page_end=resolved_page,
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "projected_pdf": session.projected_pdf.model_dump(mode="json") if session.projected_pdf else {},
                "citation": citation.model_dump(mode="json"),
            }

        if tool_name == "highlight_projected_pdf_text":
            attachment, _ = self._require_projected_pdf_attachment()
            page_number = max(1, int(arguments.get("page_number") or 1))
            quote_text = str(arguments.get("quote_text") or "").strip()
            label = str(arguments.get("label") or "").strip()
            color = str(arguments.get("color") or "#FACC15").strip() or "#FACC15"
            rects = search_pdf_text_rects(
                pdf_path=attachment.stored_path,
                page_number=page_number,
                quote_text=quote_text,
            )
            if not rects:
                raise HTTPException(status_code=404, detail="projected_pdf_text_not_found")
            overlay = ProjectedPdfOverlayRecord(
                id=f"pdf-overlay-{uuid4().hex[:10]}",
                kind="text_highlight",
                page_number=page_number,
                rects=rects,
                label=label,
                quote_text=quote_text,
                color=color,
                created_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.append_projected_pdf_overlay(
                session_id=self.session_id,
                overlay=overlay,
                page_number=page_number,
            )
            citation = self._push_citation(
                title=attachment.name,
                page_start=page_number,
                page_end=page_number,
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "overlay": overlay.model_dump(mode="json"),
                "match_count": len(rects),
                "citation": citation.model_dump(mode="json"),
            }

        if tool_name == "annotate_projected_pdf_region":
            attachment, _ = self._require_projected_pdf_attachment()
            page_number = max(1, int(arguments.get("page_number") or 1))
            label = str(arguments.get("label") or "").strip()
            color = str(arguments.get("color") or "#38BDF8").strip() or "#38BDF8"
            rect = PdfRectRecord(
                x=float(arguments.get("x") or 0.0),
                y=float(arguments.get("y") or 0.0),
                width=float(arguments.get("width") or 0.0),
                height=float(arguments.get("height") or 0.0),
            )
            overlay = ProjectedPdfOverlayRecord(
                id=f"pdf-overlay-{uuid4().hex[:10]}",
                kind="region_box",
                page_number=page_number,
                rects=[rect],
                label=label,
                color=color,
                created_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.append_projected_pdf_overlay(
                session_id=self.session_id,
                overlay=overlay,
                page_number=page_number,
            )
            citation = self._push_citation(
                title=attachment.name,
                page_start=page_number,
                page_end=page_number,
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "overlay": overlay.model_dump(mode="json"),
                "citation": citation.model_dump(mode="json"),
            }

        if tool_name == "annotate_projected_image_region":
            projected_pdf = self._require_projected_image_projection()
            label = str(arguments.get("label") or "").strip()
            color = str(arguments.get("color") or "#38BDF8").strip() or "#38BDF8"
            rect = PdfRectRecord(
                x=float(arguments.get("x") or 0.0),
                y=float(arguments.get("y") or 0.0),
                width=float(arguments.get("width") or 0.0),
                height=float(arguments.get("height") or 0.0),
            )
            overlay = ProjectedPdfOverlayRecord(
                id=f"image-overlay-{uuid4().hex[:10]}",
                kind="region_box",
                page_number=1,
                rects=[rect],
                label=label,
                color=color,
                created_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.append_projected_pdf_overlay(
                session_id=self.session_id,
                overlay=overlay,
                page_number=1,
            )
            citation = (
                self._push_citation(
                    title=projected_pdf.title,
                    page_start=1,
                    page_end=1,
                    source_kind="attachment_image",
                    source_id=projected_pdf.source_id,
                )
                if projected_pdf.source_kind == "attachment_image"
                else None
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "overlay": overlay.model_dump(mode="json"),
                "citation": citation.model_dump(mode="json") if citation is not None else None,
            }

        if tool_name == "clear_projected_pdf_overlays":
            page_number = arguments.get("page_number")
            resolved_page = max(1, int(page_number)) if page_number is not None else None
            session = self._session_service.clear_projected_pdf_overlays(
                session_id=self.session_id,
                page_number=resolved_page,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "remaining_overlay_count": (
                    len(session.projected_pdf.overlays)
                    if session.projected_pdf is not None
                    else 0
                ),
            }

        if tool_name == "clear_projected_image_overlays":
            session = self._session_service.clear_projected_pdf_overlays(
                session_id=self.session_id,
                page_number=None,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "remaining_overlay_count": (
                    len(session.projected_pdf.overlays)
                    if session.projected_pdf is not None
                    else 0
                ),
            }

        if tool_name == "update_learning_plan":
            if not self.plan_id:
                raise HTTPException(status_code=400, detail="plan_not_bound")
            course_title = str(arguments.get("course_title") or "").strip()
            raw_chapters = arguments.get("study_chapters")
            study_chapters = (
                [str(item).strip() for item in raw_chapters if str(item).strip()]
                if isinstance(raw_chapters, list)
                else []
            )
            note = str(arguments.get("note") or "").strip()
            if not course_title and not study_chapters:
                raise HTTPException(status_code=422, detail="plan_update_empty")
            plan = self._plan_service.require_plan(self.plan_id)
            preview_lines: list[str] = []
            if course_title:
                preview_lines.append(f"课程标题：{plan.course_title} -> {course_title}")
            if study_chapters:
                preview_lines.append(
                    f"学习章节：{' / '.join(plan.study_chapters[:6]) or '无'} -> {' / '.join(study_chapters[:6])}"
                )
            confirmation = SessionPlanConfirmationRecord(
                id=f"plan-confirm-{uuid4().hex[:10]}",
                tool_name=tool_name,
                action_type="update_plan",
                plan_id=self.plan_id,
                title="待确认的计划修改",
                summary=note or "模型建议调整当前学习计划结构。",
                preview_lines=preview_lines,
                payload={
                    "course_title": course_title,
                    "study_chapters": study_chapters,
                    "note": note,
                },
                created_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.create_plan_confirmation(
                session_id=self.session_id,
                confirmation=confirmation,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "requires_confirmation": True,
                "confirmation": confirmation.model_dump(mode="json"),
            }

        if tool_name == "update_learning_plan_progress":
            if not self.plan_id:
                raise HTTPException(status_code=400, detail="plan_not_bound")
            plan = self._plan_service.require_plan(self.plan_id)
            schedule_ids = _collect_schedule_ids(plan, arguments)
            status = str(arguments.get("status") or "").strip()
            note = str(arguments.get("note") or "").strip()
            if not schedule_ids:
                raise HTTPException(status_code=422, detail="schedule_ids_required")
            if status not in {"planned", "in_progress", "completed", "blocked", "skipped"}:
                raise HTTPException(status_code=422, detail="invalid_schedule_status")
            schedule_map = {item.id: item for item in plan.schedule}
            preview_lines = [
                f"{schedule_id} | {schedule_map[schedule_id].title} -> {status}"
                for schedule_id in schedule_ids
                if schedule_id in schedule_map
            ]
            confirmation = SessionPlanConfirmationRecord(
                id=f"plan-confirm-{uuid4().hex[:10]}",
                tool_name=tool_name,
                action_type="update_plan_progress",
                plan_id=self.plan_id,
                title="待确认的完成度更新",
                summary=note or "模型建议更新当前计划的完成状态。",
                preview_lines=preview_lines,
                payload={
                    "schedule_ids": schedule_ids,
                    "status": status,
                    "note": note,
                },
                created_at=datetime.now().astimezone().isoformat(),
            )
            self._session_service.create_plan_confirmation(
                session_id=self.session_id,
                confirmation=confirmation,
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "requires_confirmation": True,
                "confirmation": confirmation.model_dump(mode="json"),
            }

        raise HTTPException(status_code=400, detail="session_tool_unknown")

    def _require_pdf_attachment(self, attachment_id: str) -> LearnerAttachmentRecord:
        attachment = self._session_service.require_attachment(
            session_id=self.session_id,
            attachment_id=attachment_id,
            transient_attachments=self._transient_attachments,
        )
        if attachment.kind != "pdf" or not attachment.stored_path:
            raise HTTPException(status_code=422, detail="session_attachment_not_pdf")
        return attachment

    def _require_image_attachment(self, attachment_id: str) -> LearnerAttachmentRecord:
        attachment = self._session_service.require_attachment(
            session_id=self.session_id,
            attachment_id=attachment_id,
            transient_attachments=self._transient_attachments,
        )
        if attachment.kind != "image":
            raise HTTPException(status_code=422, detail="session_attachment_not_image")
        return attachment

    def _require_projected_pdf_attachment(self) -> tuple[LearnerAttachmentRecord, SessionProjectedPdfRecord]:
        session = self._session_service.require_session(self.session_id)
        projected_pdf = session.projected_pdf
        if projected_pdf is None:
            raise HTTPException(status_code=409, detail="projected_pdf_not_set")
        if projected_pdf.source_kind != "attachment_pdf":
            raise HTTPException(status_code=422, detail="projected_pdf_source_unsupported")
        attachment = self._require_pdf_attachment(projected_pdf.source_id)
        return attachment, projected_pdf

    def _require_projected_image_projection(self) -> SessionProjectedPdfRecord:
        session = self._session_service.require_session(self.session_id)
        projected_pdf = session.projected_pdf
        if projected_pdf is None:
            raise HTTPException(status_code=409, detail="projected_pdf_not_set")
        if projected_pdf.source_kind not in {"attachment_image", "generated_image"}:
            raise HTTPException(status_code=422, detail="projected_image_source_unsupported")
        return projected_pdf

    def _push_citation(
        self,
        *,
        title: str,
        page_start: int,
        page_end: int,
        source_kind: str,
        source_id: str,
    ) -> Citation:
        citation = Citation(
            section_id=source_id,
            title=title,
            page_start=page_start,
            page_end=page_end,
            source_kind=source_kind,
            source_id=source_id,
        )
        if not any(
            item.source_kind == citation.source_kind
            and item.source_id == citation.source_id
            and item.page_start == citation.page_start
            and item.page_end == citation.page_end
            and item.title == citation.title
            for item in self._response_citations
        ):
            self._response_citations.append(citation)
        return citation


def _collect_schedule_ids(plan, arguments: dict[str, Any]) -> list[str]:
    schedule_ids: list[str] = []
    single_schedule_id = str(arguments.get("schedule_id") or "").strip()
    if single_schedule_id:
        schedule_ids.append(single_schedule_id)
    raw_schedule_ids = arguments.get("schedule_ids")
    if isinstance(raw_schedule_ids, list):
        schedule_ids.extend(str(item).strip() for item in raw_schedule_ids if str(item).strip())
    chapter_unit_ids: list[str] = []
    single_chapter_unit_id = str(arguments.get("chapter_unit_id") or "").strip()
    if single_chapter_unit_id:
        chapter_unit_ids.append(single_chapter_unit_id)
    raw_chapter_unit_ids = arguments.get("chapter_unit_ids")
    if isinstance(raw_chapter_unit_ids, list):
        chapter_unit_ids.extend(str(item).strip() for item in raw_chapter_unit_ids if str(item).strip())
    if chapter_unit_ids:
        for chapter in plan.chapter_progress:
            if chapter.unit_id in chapter_unit_ids:
                schedule_ids.extend(chapter.schedule_ids)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in schedule_ids:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
