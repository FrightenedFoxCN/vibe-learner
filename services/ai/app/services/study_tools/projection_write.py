from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.domain import (
    PdfRectRecord,
)
from app.models.study_chat_effect import (
    StudyProjectionEffectAction,
    StudyProjectionEffectProposalV1,
    StudyProjectionRectV1,
)
from app.services.study_chat_attachments import (
    search_pdf_text_rects,
)
from app.services.study_tools.context import StudyToolContext
from fastapi import HTTPException


@dataclass
class ProjectionWriteTools:
    context: StudyToolContext

    def project_uploaded_pdf(self, arguments: dict[str, Any]) -> dict[str, Any]:
        attachment_id = str(arguments.get("attachment_id") or "").strip()
        page_number = max(1, int(arguments.get("page_number") or 1))
        attachment = self.context.require_pdf_attachment(attachment_id)
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.SET,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
            title=attachment.name,
            page_number=min(page_number, max(1, attachment.page_count or page_number)),
            page_count=max(1, attachment.page_count or page_number),
        )
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        citation = self.context.push_citation(
            title=attachment.name,
            page_start=projected_pdf.page_number,
            page_end=projected_pdf.page_number,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "project_uploaded_pdf",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": projected_pdf.model_dump(mode="json"),
            "citation": citation.model_dump(mode="json"),
        }

    def project_uploaded_image(self, arguments: dict[str, Any]) -> dict[str, Any]:
        attachment_id = str(arguments.get("attachment_id") or "").strip()
        attachment = self.context.require_image_attachment(attachment_id)
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.SET,
            source_kind="attachment_image",
            source_id=attachment.attachment_id,
            title=attachment.name,
            page_number=1,
            page_count=1,
        )
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        citation = self.context.push_citation(
            title=attachment.name,
            page_start=1,
            page_end=1,
            source_kind="attachment_image",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "project_uploaded_image",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": projected_pdf.model_dump(mode="json"),
            "citation": citation.model_dump(mode="json"),
        }

    def focus_projected_pdf_page(self, arguments: dict[str, Any]) -> dict[str, Any]:
        attachment, _ = self.context.require_projected_pdf_attachment()
        page_number = max(1, int(arguments.get("page_number") or 1))
        resolved_page = min(page_number, max(1, attachment.page_count or page_number))
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.FOCUS,
            page_number=resolved_page,
        )
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        citation = self.context.push_citation(
            title=attachment.name,
            page_start=resolved_page,
            page_end=resolved_page,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "focus_projected_pdf_page",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": projected_pdf.model_dump(mode="json"),
            "citation": citation.model_dump(mode="json"),
        }

    def highlight_projected_pdf_text(self, arguments: dict[str, Any]) -> dict[str, Any]:
        attachment, _ = self.context.require_projected_pdf_attachment()
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
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
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
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        overlay = projected_pdf.overlays[-1]
        citation = self.context.push_citation(
            title=attachment.name,
            page_start=page_number,
            page_end=page_number,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "highlight_projected_pdf_text",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": overlay.model_dump(mode="json"),
            "match_count": len(rects),
            "citation": citation.model_dump(mode="json"),
        }

    def annotate_projected_pdf_region(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        attachment, _ = self.context.require_projected_pdf_attachment()
        page_number = max(1, int(arguments.get("page_number") or 1))
        label = str(arguments.get("label") or "").strip()
        color = str(arguments.get("color") or "#38BDF8").strip() or "#38BDF8"
        rect = PdfRectRecord(
            x=float(arguments.get("x") or 0.0),
            y=float(arguments.get("y") or 0.0),
            width=float(arguments.get("width") or 0.0),
            height=float(arguments.get("height") or 0.0),
        )
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.APPEND_OVERLAY,
            overlay_kind="region_box",
            page_number=page_number,
            rects=[StudyProjectionRectV1.model_validate(rect.model_dump(mode="json"))],
            label=label,
            color=color,
        )
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        overlay = projected_pdf.overlays[-1]
        citation = self.context.push_citation(
            title=attachment.name,
            page_start=page_number,
            page_end=page_number,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "annotate_projected_pdf_region",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": overlay.model_dump(mode="json"),
            "citation": citation.model_dump(mode="json"),
        }

    def clear_projected_pdf_overlays(self, arguments: dict[str, Any]) -> dict[str, Any]:
        page_number = arguments.get("page_number")
        resolved_page = max(1, int(page_number)) if page_number is not None else None
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.CLEAR_OVERLAYS,
            page_number=resolved_page or 0,
        )
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        return {
            "ok": True,
            "tool_name": "clear_projected_pdf_overlays",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": projected_pdf.model_dump(mode="json"),
        }

    def annotate_projected_image_region(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        projected_pdf = self.context.require_projected_image_projection()
        label = str(arguments.get("label") or "").strip()
        color = str(arguments.get("color") or "#38BDF8").strip() or "#38BDF8"
        rect = PdfRectRecord(
            x=float(arguments.get("x") or 0.0),
            y=float(arguments.get("y") or 0.0),
            width=float(arguments.get("width") or 0.0),
            height=float(arguments.get("height") or 0.0),
        )
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.APPEND_OVERLAY,
            overlay_kind="region_box",
            page_number=1,
            rects=[StudyProjectionRectV1.model_validate(rect.model_dump(mode="json"))],
            label=label,
            color=color,
        )
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        next_projected = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert next_projected is not None
        overlay = next_projected.overlays[-1]
        citation = (
            self.context.push_citation(
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
            "tool_name": "annotate_projected_image_region",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": overlay.model_dump(mode="json"),
            "citation": citation.model_dump(mode="json")
            if citation is not None
            else None,
        }

    def clear_projected_image_overlays(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        self.context.require_projected_image_projection()
        proposal = StudyProjectionEffectProposalV1(
            action=StudyProjectionEffectAction.CLEAR_OVERLAYS,
        )
        effect = self.context.effects.prepare_projection(proposal)
        session = self.context.sessions.require_session(self.context.session_id)
        projected_pdf = self.context.effects.preview_projected_state(
            session.projected_pdf
        )
        assert projected_pdf is not None
        return {
            "ok": True,
            "tool_name": "clear_projected_image_overlays",
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": proposal.model_dump(mode="json"),
            "predicted_state": projected_pdf.model_dump(mode="json"),
        }
