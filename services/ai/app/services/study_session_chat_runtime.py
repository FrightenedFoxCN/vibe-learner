from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import HTTPException

from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.domain import (
    Citation,
    LearnerAttachmentRecord,
    PdfRectRecord,
    SessionProjectedPdfRecord,
)
from app.models.harness_effect import HARNESS_EFFECT_ADAPTER_POLICIES
from app.models.study_chat_operation import study_chat_provider_effect_id
from app.models.study_chat_effect import (
    StudyAffinityDeltaEffectProposalV1,
    StudyFollowUpEffectAction,
    StudyFollowUpEffectProposalV1,
    StudyMemoryUpsertEffectProposalV1,
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
    StudyProjectionEffectAction,
    StudyProjectionEffectProposalV1,
    StudyProjectionRectV1,
)
from app.services.study_grounding import StudyVerbatimMemorySourceV1
from app.models.study_chat_tool_contracts import WriteSessionMemoryArgumentsV1
from app.services.plans import LearningPlanService
from app.services.plan_prompt import read_page_range_images
from app.services.study_chat_attachments import extract_pdf_page_range_text, search_pdf_text_rects
from app.services.study_sessions import StudySessionService
from app.services.study_chat_effects import StudyChatEffectCollector
from app.models.tool_manifest import resolve_tool_manifest_entry
from app.services.tool_provider_projection import provider_function_for_entry


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
        effect_collector: StudyChatEffectCollector | None = None,
    ) -> None:
        self._session_service = session_service
        self._plan_service = plan_service
        self.session_id = session_id
        self.plan_id = plan_id.strip() if plan_id else ""
        self._transient_attachments = list(transient_attachments or [])
        self._multimodal_enabled = multimodal_enabled
        self._model_provider = model_provider
        self._effect_collector = effect_collector
        self._response_citations: list[Citation] = []
        self.verbatim_memory_source: StudyVerbatimMemorySourceV1 | None = None

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
        prepared_study_units = ", ".join(session.prepared_study_unit_ids[-6:]) or "无"
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
        return list(self._response_citations)

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
            items = (
                self._effect_collector.preview_session_memory(session.session_memory)
                if self._effect_collector is not None
                else [item.model_dump(mode="json") for item in session.session_memory]
            )
            if requested_key:
                items = [item for item in items if item.get("key") == requested_key]
            return {
                "ok": True,
                "tool_name": tool_name,
                "memory_items": items[-limit:],
            }

        if tool_name == "write_session_memory":
            validated = WriteSessionMemoryArgumentsV1.model_validate(arguments)
            key = validated.key.strip()
            content = validated.content.strip()
            if self.verbatim_memory_source is not None:
                if validated.key != self.verbatim_memory_source.key:
                    raise HTTPException(status_code=422, detail="verbatim_memory_key_mismatch")
                content = self.verbatim_memory_source.content
            if not key or not content:
                raise HTTPException(status_code=422, detail="session_memory_invalid")
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyMemoryUpsertEffectProposalV1(key=key, content=content)
            effect = self._effect_collector.prepare_memory_upsert(proposal)
            session = self._session_service.require_session(self.session_id)
            predicted = next(
                item
                for item in reversed(
                    self._effect_collector.preview_session_memory(session.session_memory)
                )
                if item.get("key") == key
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": {
                    "memory": predicted,
                    "memory_count": len(
                        self._effect_collector.preview_session_memory(
                            session.session_memory
                        )
                    ),
                },
            }

        if tool_name == "read_affinity_state":
            session = self._session_service.require_session(self.session_id)
            affinity = (
                self._effect_collector.preview_affinity_state(session.affinity_state)
                if self._effect_collector is not None
                else session.affinity_state.model_dump(mode="json")
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "score": affinity["score"],
                "level": affinity["level"],
                "summary": affinity["summary"],
                "updated_at": affinity["updated_at"],
                "effect_state": affinity.get("effect_state", "committed"),
                "committed": affinity.get("committed", True),
                "recent_events": list(affinity.get("events") or [])[-6:],
            }

        if tool_name == "update_affinity_state":
            delta = int(arguments.get("delta") or 0)
            if delta < -20 or delta > 20:
                raise HTTPException(status_code=422, detail="affinity_delta_invalid")
            reason = str(arguments.get("reason") or "").strip()
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyAffinityDeltaEffectProposalV1(
                delta=delta,
                reason=reason,
            )
            effect = self._effect_collector.prepare_affinity_delta(proposal)
            session = self._session_service.require_session(self.session_id)
            affinity = self._effect_collector.preview_affinity_state(
                session.affinity_state
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": {
                    "score": affinity["score"],
                    "level": affinity["level"],
                    "summary": affinity["summary"],
                },
            }

        if tool_name == "schedule_session_follow_up":
            delay_seconds = int(arguments.get("delay_seconds") or 30)
            if delay_seconds < 10 or delay_seconds > 1800:
                raise HTTPException(status_code=422, detail="follow_up_delay_invalid")
            prompt = str(arguments.get("prompt") or "").strip()
            reason = str(arguments.get("reason") or "").strip()
            if not prompt:
                raise HTTPException(status_code=422, detail="follow_up_prompt_required")
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyFollowUpEffectProposalV1(
                action=StudyFollowUpEffectAction.SCHEDULE,
                delay_seconds=delay_seconds,
                hidden_message=prompt,
                reason=reason,
            )
            effect = self._effect_collector.prepare_follow_up(proposal)
            session = self._session_service.require_session(self.session_id)
            predicted = self._effect_collector.preview_follow_ups(
                session.pending_follow_ups
            )[-1]
            return {
                "ok": True,
                "tool_name": tool_name,
                "requires_client_schedule": True,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": predicted,
            }

        if tool_name == "project_uploaded_pdf":
            attachment_id = str(arguments.get("attachment_id") or "").strip()
            page_number = max(1, int(arguments.get("page_number") or 1))
            attachment = self._require_pdf_attachment(attachment_id)
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.SET,
                source_kind="attachment_pdf",
                source_id=attachment.attachment_id,
                title=attachment.name,
                page_number=min(page_number, max(1, attachment.page_count or page_number)),
                page_count=max(1, attachment.page_count or page_number),
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
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
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": projected_pdf.model_dump(mode="json"),
                "citation": citation.model_dump(mode="json"),
            }

        if tool_name == "project_uploaded_image":
            attachment_id = str(arguments.get("attachment_id") or "").strip()
            attachment = self._require_image_attachment(attachment_id)
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.SET,
                source_kind="attachment_image",
                source_id=attachment.attachment_id,
                title=attachment.name,
                page_number=1,
                page_count=1,
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
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
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": projected_pdf.model_dump(mode="json"),
                "citation": citation.model_dump(mode="json"),
            }

        if tool_name == "generate_projected_image":
            if self._model_provider is None:
                raise HTTPException(status_code=422, detail="chat_image_generation_unsupported")
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            prompt = str(arguments.get("prompt") or "").strip()
            title = str(arguments.get("title") or "").strip() or "AI 生成图像"
            size = str(arguments.get("size") or "1024x1024").strip() or "1024x1024"
            if not prompt:
                raise HTTPException(status_code=422, detail="chat_image_generation_prompt_required")
            expected_projection_effect_id = self._effect_collector.next_effect_id()
            external_effect_id = study_chat_provider_effect_id(
                operation_id=self._effect_collector.operation_id,
                source_effect_id=expected_projection_effect_id,
            )
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
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.SET,
                source_kind="generated_image",
                title=title,
                page_number=1,
                page_count=1,
                image_url=str(generated.get("image_url") or ""),
            )
            effect = self._effect_collector.prepare_projection(proposal)
            if effect.effect_id != expected_projection_effect_id:
                raise RuntimeError("study_provider_effect_slot_drift")
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
            return {
                "ok": True,
                "tool_name": tool_name,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": projected_pdf.model_dump(mode="json"),
                "external_effect_state": "completed_uncommitted",
                "external_effect_id": external_effect_id,
                "external_effect_adapter": HARNESS_EFFECT_ADAPTER_POLICIES[
                    "study_provider_execution"
                ].model_dump(mode="json"),
                "external_effect_read_back": "unsupported",
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
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.FOCUS,
                page_number=resolved_page,
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
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
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": projected_pdf.model_dump(mode="json"),
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
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.APPEND_OVERLAY,
                overlay_kind="text_highlight",
                page_number=page_number,
                rects=[
                    StudyProjectionRectV1.model_validate(item.model_dump(mode="json"))
                    for item in rects
                ],
                label=label,
                quote_text=quote_text,
                color=color,
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
            overlay = projected_pdf.overlays[-1]
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
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": overlay.model_dump(mode="json"),
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
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.APPEND_OVERLAY,
                overlay_kind="region_box",
                page_number=page_number,
                rects=[StudyProjectionRectV1.model_validate(rect.model_dump(mode="json"))],
                label=label,
                color=color,
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
            overlay = projected_pdf.overlays[-1]
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
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": overlay.model_dump(mode="json"),
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
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.APPEND_OVERLAY,
                overlay_kind="region_box",
                page_number=1,
                rects=[StudyProjectionRectV1.model_validate(rect.model_dump(mode="json"))],
                label=label,
                color=color,
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            next_projected = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert next_projected is not None
            overlay = next_projected.overlays[-1]
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
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": overlay.model_dump(mode="json"),
                "citation": citation.model_dump(mode="json") if citation is not None else None,
            }

        if tool_name == "clear_projected_pdf_overlays":
            page_number = arguments.get("page_number")
            resolved_page = max(1, int(page_number)) if page_number is not None else None
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.CLEAR_OVERLAYS,
                page_number=resolved_page or 0,
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
            return {
                "ok": True,
                "tool_name": tool_name,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": projected_pdf.model_dump(mode="json"),
            }

        if tool_name == "clear_projected_image_overlays":
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            self._require_projected_image_projection()
            proposal = StudyProjectionEffectProposalV1(
                action=StudyProjectionEffectAction.CLEAR_OVERLAYS,
            )
            effect = self._effect_collector.prepare_projection(proposal)
            session = self._session_service.require_session(self.session_id)
            projected_pdf = self._effect_collector.preview_projected_state(
                session.projected_pdf
            )
            assert projected_pdf is not None
            return {
                "ok": True,
                "tool_name": tool_name,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": proposal.model_dump(mode="json"),
                "predicted_state": projected_pdf.model_dump(mode="json"),
            }

        if tool_name == "update_learning_plan":
            if not self.plan_id:
                raise HTTPException(status_code=400, detail="plan_not_bound")
            course_title = str(arguments.get("course_title") or "").strip()
            note = str(arguments.get("note") or "").strip()
            if not course_title:
                raise HTTPException(status_code=422, detail="plan_update_empty")
            plan = self._plan_service.require_plan(self.plan_id)
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            effect = self._effect_collector.prepare_plan_confirmation(
                StudyPlanConfirmationEffectProposalV1(
                    action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
                    course_title=course_title,
                    note=note,
                )
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "requires_confirmation": True,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": effect.proposal.model_dump(mode="json"),
                "predicted_state": {
                    "slot": effect.slot,
                    "plan_id": self.plan_id,
                    "preview_lines": [
                        f"课程标题：{plan.course_title} -> {course_title}"
                    ],
                },
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
            if self._effect_collector is None:
                raise HTTPException(status_code=409, detail="study_chat_effect_collector_required")
            effect = self._effect_collector.prepare_plan_confirmation(
                StudyPlanConfirmationEffectProposalV1(
                    action=StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS,
                    schedule_ids=schedule_ids,
                    schedule_status=status,
                    note=note,
                )
            )
            return {
                "ok": True,
                "tool_name": tool_name,
                "requires_confirmation": True,
                "effect_state": "prepared",
                "committed": False,
                "prepared_effect_id": effect.effect_id,
                "prepared_proposal": effect.proposal.model_dump(mode="json"),
                "predicted_state": {
                    "slot": effect.slot,
                    "plan_id": self.plan_id,
                    "preview_lines": [
                        f"{schedule_id} | {schedule_map[schedule_id].title} -> {status}"
                        for schedule_id in schedule_ids
                        if schedule_id in schedule_map
                    ],
                },
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
        projected_pdf = (
            self._effect_collector.preview_projected_state(session.projected_pdf)
            if self._effect_collector is not None
            else session.projected_pdf
        )
        if projected_pdf is None:
            raise HTTPException(status_code=409, detail="projected_pdf_not_set")
        if projected_pdf.source_kind != "attachment_pdf":
            raise HTTPException(status_code=422, detail="projected_pdf_source_unsupported")
        attachment = self._require_pdf_attachment(projected_pdf.source_id)
        return attachment, projected_pdf

    def _require_projected_image_projection(self) -> SessionProjectedPdfRecord:
        session = self._session_service.require_session(self.session_id)
        projected_pdf = (
            self._effect_collector.preview_projected_state(session.projected_pdf)
            if self._effect_collector is not None
            else session.projected_pdf
        )
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
    study_unit_ids: list[str] = []
    single_study_unit_id = str(arguments.get("study_unit_id") or "").strip()
    if single_study_unit_id:
        study_unit_ids.append(single_study_unit_id)
    raw_study_unit_ids = arguments.get("study_unit_ids")
    if isinstance(raw_study_unit_ids, list):
        study_unit_ids.extend(str(item).strip() for item in raw_study_unit_ids if str(item).strip())
    if study_unit_ids:
        for progress in plan.study_unit_progress:
            if progress.unit_id in study_unit_ids:
                schedule_ids.extend(progress.schedule_ids)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in schedule_ids:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
