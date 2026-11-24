from __future__ import annotations

from typing import Any

from app.models.domain import Citation, LearnerAttachmentRecord
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.study_chat_note_references import (
    STUDY_NOTE_REFERENCE_LIMIT,
    StudyNoteReferenceV1,
)
from app.models.study_chat_tool_contracts import SearchStudyNotesResultV1
from app.persistence.study_note_repository import StudyNoteRepository
from app.models.tool_manifest import resolve_tool_manifest_entry
from app.services.document_layout import DocumentLayoutService
from app.services.plans import LearningPlanService
from app.services.study_chat_effects import StudyChatEffectCollector
from app.services.study_sessions import StudySessionService
from app.services.study_tools.affinity import AffinityTools
from app.services.study_tools.context import StudyToolContext
from app.services.study_tools.follow_up import FollowUpTools
from app.services.study_tools.image_generation import ImageGenerationTools
from app.services.study_tools.memory import SessionMemoryTools
from app.services.study_tools.note_search import StudyNoteSearchTools
from app.services.study_tools.plan_confirmation import PlanConfirmationTools
from app.services.study_tools.projection_read import ProjectionReadTools
from app.services.study_tools.projection_write import ProjectionWriteTools
from app.services.tool_provider_projection import provider_function_for_entry
from fastapi import HTTPException

# Stable provider presentation order; contracts and adapter identities live in the Manifest.
SESSION_CHAT_TOOL_NAMES = (
    "read_system_time",
    "read_session_memory",
    "search_study_notes",
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
    "read_projected_pdf_layout_candidates",
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
        effect_collector: StudyChatEffectCollector | None = None,
        document_layout_service: DocumentLayoutService | None = None,
        study_note_repository: StudyNoteRepository | None = None,
    ) -> None:
        self._context = StudyToolContext(
            sessions=session_service,
            plans=plan_service,
            session_id=session_id,
            plan_id=plan_id.strip() if plan_id else "",
            attachments=list(transient_attachments or []),
            multimodal_enabled=multimodal_enabled,
            model_provider=model_provider,
            effects=effect_collector,
            layout_service=document_layout_service,
        )
        self._note_search = (
            StudyNoteSearchTools(study_note_repository, session_id)
            if study_note_repository is not None
            else None
        )
        self._note_references: dict[str, StudyNoteReferenceV1] = {}
        self._handlers = (
            self._note_search,
            SessionMemoryTools(self._context),
            AffinityTools(self._context),
            FollowUpTools(self._context),
            ProjectionReadTools(self._context),
            ProjectionWriteTools(self._context),
            ImageGenerationTools(self._context),
            PlanConfirmationTools(self._context),
        )

    @property
    def session_id(self) -> str:
        return self._context.session_id

    @property
    def plan_id(self) -> str:
        return self._context.plan_id

    def has_tool(self, tool_name: str) -> bool:
        if tool_name == "search_study_notes":
            return self._note_search is not None
        if tool_name == "update_learning_plan" and not self._context.plan_id:
            return False
        if tool_name == "update_learning_plan_progress" and not self._context.plan_id:
            return False
        if (
            tool_name == "read_projected_pdf_images"
            and not self._context.multimodal_enabled
        ):
            return False
        if tool_name == "read_projected_pdf_layout_candidates":
            return bool(
                self._context.multimodal_enabled
                and self._context.layout_service is not None
                and self._context.layout_service.enabled
            )
        if tool_name == "generate_projected_image":
            return bool(
                self._context.model_provider is not None
                and getattr(
                    self._context.model_provider,
                    "supports_chat_generated_image_tools",
                    lambda: False,
                )()
            )
        return tool_name in SESSION_CHAT_TOOL_NAMES

    def session_context(self) -> str:
        session = self._context.sessions.require_session(self._context.session_id)
        memory_lines = [
            f"- {item.key}: {item.content}" for item in session.session_memory[-6:]
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
        prepared_study_units = ", ".join(session.prepared_study_unit_ids[-6:]) or "无"
        affinity = session.affinity_state
        pdf_attachment_lines = [
            f"- {item.attachment_id} | {item.name} | pages={item.page_count or '?'}"
            for item in self._context.sessions.list_attachments(
                session_id=self._context.session_id,
                kind="pdf",
                transient_attachments=self._context.attachments,
            )[-8:]
        ]
        image_attachment_lines = [
            f"- {item.attachment_id} | {item.name}"
            for item in self._context.sessions.list_attachments(
                session_id=self._context.session_id,
                kind="image",
                transient_attachments=self._context.attachments,
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
            f"已做过预处理的学习单元：{prepared_study_units}\n"
            f"临时记忆：\n{chr(10).join(memory_lines) if memory_lines else '- 无'}\n"
            f"好感度：score={affinity.score} | level={affinity.level} | summary={affinity.summary or '无'}\n"
            f"当前可投射 PDF 附件：\n{chr(10).join(pdf_attachment_lines) if pdf_attachment_lines else '- 无'}\n"
            f"当前可投射图片附件：\n{chr(10).join(image_attachment_lines) if image_attachment_lines else '- 无'}\n"
            f"当前投射 PDF：{projected_pdf_line}\n"
            f"待确认计划操作：\n{chr(10).join(pending_confirmation_lines) if pending_confirmation_lines else '- 无'}\n"
            f"待触发自动续接：\n{chr(10).join(pending_follow_up_lines) if pending_follow_up_lines else '- 无'}"
        )

    def response_citations(self) -> list[Citation]:
        return list(self._context.citations)

    def record_successful_note_search(self, result: SearchStudyNotesResultV1) -> None:
        # Only validated, successfully projected tool results can reach this path.
        for hit in result.hits:
            if len(self._note_references) >= STUDY_NOTE_REFERENCE_LIMIT:
                break
            self._note_references.setdefault(
                hit.note_id,
                StudyNoteReferenceV1(
                    note_id=hit.note_id,
                    note_revision=hit.note_revision,
                    title=hit.title,
                ),
            )

    def response_study_note_references(self) -> list[StudyNoteReferenceV1]:
        return list(self._note_references.values())

    def available_tool_names(self) -> list[str]:
        return [name for name in SESSION_CHAT_TOOL_NAMES if self.has_tool(name)]

    def tool_specs(self) -> list[dict[str, object]]:
        return [
            provider_function_for_entry(
                resolve_tool_manifest_entry(
                    workflow=HarnessWorkflow.STUDY_CHAT,
                    offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
                    transport_name=name,
                )
            ).model_dump(mode="json")
            for name in self.available_tool_names()
        ]

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        # The manifest still owns canonical identity, schemas and budgets. Methods
        # implement its existing adapter suffixes; there is no second tool catalog.
        if tool_name not in SESSION_CHAT_TOOL_NAMES:
            raise HTTPException(status_code=400, detail="session_tool_unknown")
        entry = resolve_tool_manifest_entry(
            workflow=HarnessWorkflow.STUDY_CHAT,
            offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
            transport_name=tool_name,
        )
        if (
            entry.owner_module != __name__
            or entry.runtime_adapter.name != f"study_session_chat_runtime.{tool_name}"
        ):
            raise RuntimeError("session_tool_manifest_binding_mismatch")
        methods = [
            method
            for handler in self._handlers
            if callable(method := getattr(handler, entry.canonical_name, None))
        ]
        if len(methods) != 1:
            raise RuntimeError("session_tool_handler_binding_mismatch")
        return methods[0](arguments)
