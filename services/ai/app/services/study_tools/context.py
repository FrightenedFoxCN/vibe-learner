"""Shared operation-scoped services, overlays and citations; never commits effects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.models.domain import (
    Citation,
    LearnerAttachmentRecord,
    SessionProjectedPdfRecord,
)
from app.services.study_grounding import StudyVerbatimMemorySourceV1
from fastapi import HTTPException

if TYPE_CHECKING:
    from app.services.document_layout import DocumentLayoutService
    from app.services.plans import LearningPlanService
    from app.services.study_chat_effects import StudyChatEffectCollector
    from app.services.study_sessions import StudySessionService


@dataclass
class StudyToolContext:
    sessions: StudySessionService
    plans: LearningPlanService
    session_id: str
    plan_id: str
    attachments: list[LearnerAttachmentRecord]
    multimodal_enabled: bool
    model_provider: Any | None
    effects: StudyChatEffectCollector | None
    layout_service: DocumentLayoutService | None
    citations: list[Citation] = field(default_factory=list)
    verbatim_memory_source: StudyVerbatimMemorySourceV1 | None = None

    def require_pdf_attachment(self, attachment_id: str) -> LearnerAttachmentRecord:
        attachment = self.sessions.require_attachment(
            session_id=self.session_id,
            attachment_id=attachment_id,
            transient_attachments=self.attachments,
        )
        if attachment.kind != "pdf" or not attachment.stored_path:
            raise HTTPException(status_code=422, detail="session_attachment_not_pdf")
        return attachment

    def require_image_attachment(self, attachment_id: str) -> LearnerAttachmentRecord:
        attachment = self.sessions.require_attachment(
            session_id=self.session_id,
            attachment_id=attachment_id,
            transient_attachments=self.attachments,
        )
        if attachment.kind != "image":
            raise HTTPException(status_code=422, detail="session_attachment_not_image")
        return attachment

    def require_projected_pdf_attachment(
        self,
    ) -> tuple[LearnerAttachmentRecord, SessionProjectedPdfRecord]:
        session = self.sessions.require_session(self.session_id)
        projected_pdf = (
            self.effects.preview_projected_state(session.projected_pdf)
            if self.effects is not None
            else session.projected_pdf
        )
        if projected_pdf is None:
            raise HTTPException(status_code=409, detail="projected_pdf_not_set")
        if projected_pdf.source_kind != "attachment_pdf":
            raise HTTPException(
                status_code=422, detail="projected_pdf_source_unsupported"
            )
        attachment = self.require_pdf_attachment(projected_pdf.source_id)
        return attachment, projected_pdf

    def require_projected_image_projection(self) -> SessionProjectedPdfRecord:
        session = self.sessions.require_session(self.session_id)
        projected_pdf = (
            self.effects.preview_projected_state(session.projected_pdf)
            if self.effects is not None
            else session.projected_pdf
        )
        if projected_pdf is None:
            raise HTTPException(status_code=409, detail="projected_pdf_not_set")
        if projected_pdf.source_kind not in {"attachment_image", "generated_image"}:
            raise HTTPException(
                status_code=422, detail="projected_image_source_unsupported"
            )
        return projected_pdf

    def push_citation(
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
            for item in self.citations
        ):
            self.citations.append(citation)
        return citation
