from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from app.services.plan_prompt import read_page_range_images
from app.services.study_chat_attachments import (
    extract_pdf_page_range_text,
)
from app.services.study_tools.context import StudyToolContext
from fastapi import HTTPException


@dataclass
class ProjectionReadTools:
    context: StudyToolContext

    def read_projected_pdf_content(self, arguments: dict[str, Any]) -> dict[str, Any]:
        attachment, projected_pdf = self.context.require_projected_pdf_attachment()
        page_start = max(
            1, int(arguments.get("page_start") or projected_pdf.page_number or 1)
        )
        page_end = max(page_start, int(arguments.get("page_end") or page_start))
        max_chars = max(800, min(int(arguments.get("max_chars") or 4000), 8000))
        content = extract_pdf_page_range_text(
            pdf_path=attachment.stored_path,
            page_start=page_start,
            page_end=page_end,
            max_chars=max_chars,
        )
        self.context.push_citation(
            title=attachment.name,
            page_start=page_start,
            page_end=page_end,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "read_projected_pdf_content",
            "source_kind": projected_pdf.source_kind,
            "source_id": projected_pdf.source_id,
            **content,
        }

    def read_projected_pdf_images(self, arguments: dict[str, Any]) -> dict[str, Any]:
        attachment, projected_pdf = self.context.require_projected_pdf_attachment()
        page_start = max(
            1, int(arguments.get("page_start") or projected_pdf.page_number or 1)
        )
        page_end = max(page_start, int(arguments.get("page_end") or page_start))
        max_images = max(1, min(int(arguments.get("max_images") or 2), 4))
        payload = read_page_range_images(
            document_path=attachment.stored_path,
            page_start=page_start,
            page_end=page_end,
            max_images=max_images,
        )
        self.context.push_citation(
            title=attachment.name,
            page_start=page_start,
            page_end=page_end,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "read_projected_pdf_images",
            "source_kind": projected_pdf.source_kind,
            "source_id": projected_pdf.source_id,
            **payload,
        }

    def read_projected_pdf_layout_candidates(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        attachment, projected_pdf = self.context.require_projected_pdf_attachment()
        page_number = max(
            1, int(arguments.get("page_number") or projected_pdf.page_number or 1)
        )
        page_number = min(page_number, max(1, attachment.page_count or page_number))
        labels = list(arguments.get("labels") or [])
        target = str(arguments.get("target") or "").strip()
        recursive_picture = bool(arguments.get("recursive_picture", True))
        max_candidates = max(1, min(int(arguments.get("max_candidates") or 24), 32))
        rendered = read_page_range_images(
            document_path=attachment.stored_path,
            page_start=page_number,
            page_end=page_number,
            max_images=1,
        )
        images = rendered.get("images") or []
        if not images or not str(images[0].get("image_url") or "").startswith(
            "data:image/png;base64,"
        ):
            raise HTTPException(
                status_code=503, detail="projected_pdf_page_render_unavailable"
            )
        png = base64.b64decode(
            str(images[0]["image_url"]).split(",", 1)[1], validate=True
        )
        assert self.context.layout_service is not None
        detection = self.context.layout_service.detect_png(
            png,
            labels=labels,
            recursive_picture=recursive_picture,
        )
        candidates = list(detection.candidates[:max_candidates])
        evidence_images = self.context.layout_service.evidence_images(png, detection)
        self.context.push_citation(
            title=attachment.name,
            page_start=page_number,
            page_end=page_number,
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
        )
        return {
            "ok": True,
            "tool_name": "read_projected_pdf_layout_candidates",
            "source_kind": projected_pdf.source_kind,
            "source_id": projected_pdf.source_id,
            "page_number": page_number,
            "target": target,
            "labels": labels,
            "recursive_picture": recursive_picture,
            "engine_status": detection.status,
            "candidate_count": len(candidates),
            "candidates": [
                candidate.model_dump(mode="json") for candidate in candidates
            ],
            "images": evidence_images,
            "warning": detection.warning,
        }
