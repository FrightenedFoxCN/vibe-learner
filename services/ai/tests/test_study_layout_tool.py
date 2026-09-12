from __future__ import annotations

import base64
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from app.models.domain import LearnerAttachmentRecord, SessionProjectedPdfRecord
from app.services.document_layout import DocumentLayoutService
from app.services.provider_study import _chat_tool_image_parts
from app.services.study_session_chat_runtime import StudySessionChatToolRuntime


def _png_data_url() -> str:
    output = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(output, format="PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode()


class StudyLayoutToolTests(unittest.TestCase):
    def _runtime(self, service: DocumentLayoutService | None, *, multimodal: bool) -> StudySessionChatToolRuntime:
        attachment = LearnerAttachmentRecord(
            attachment_id="attachment-1",
            name="book.pdf",
            mime_type="application/pdf",
            kind="pdf",
            stored_path="/tmp/book.pdf",
            page_count=3,
            previewable=True,
        )
        projected = SessionProjectedPdfRecord(
            source_kind="attachment_pdf",
            source_id=attachment.attachment_id,
            title=attachment.name,
            page_number=2,
            page_count=3,
            updated_at="2026-09-12T00:00:00Z",
        )
        session_service = SimpleNamespace(
            require_session=lambda _session_id: SimpleNamespace(projected_pdf=projected),
            require_attachment=lambda **_kwargs: attachment,
        )
        return StudySessionChatToolRuntime(
            session_service=session_service,
            plan_service=SimpleNamespace(),
            session_id="session-1",
            multimodal_enabled=multimodal,
            document_layout_service=service,
        )

    def test_tool_is_only_offered_when_multimodal_layout_is_enabled(self) -> None:
        enabled = DocumentLayoutService(engine="doclayout-yolo", runner=lambda *_: {})
        self.assertNotIn(
            "read_projected_pdf_layout_candidates",
            self._runtime(None, multimodal=True).available_tool_names(),
        )
        self.assertNotIn(
            "read_projected_pdf_layout_candidates",
            self._runtime(enabled, multimodal=False).available_tool_names(),
        )
        self.assertIn(
            "read_projected_pdf_layout_candidates",
            self._runtime(enabled, multimodal=True).available_tool_names(),
        )

    def test_tool_returns_candidates_but_keeps_images_provider_only(self) -> None:
        service = DocumentLayoutService(
            engine="doclayout-yolo",
            runner=lambda *_: {
                "width": 200,
                "height": 100,
                "detections": [
                    {"label": "Picture", "confidence": 0.91, "box_px": [20, 10, 180, 90], "depth": 0, "parent_index": None}
                ],
            },
        )
        runtime = self._runtime(service, multimodal=True)
        with patch(
            "app.services.study_session_chat_runtime.read_page_range_images",
            return_value={"images": [{"image_url": _png_data_url()}]},
        ):
            result = runtime.execute_tool(
                "read_projected_pdf_layout_candidates",
                {
                    "page_number": 2,
                    "target": "the commutative diagram",
                    "labels": ["Picture"],
                    "recursive_picture": True,
                    "max_candidates": 8,
                },
            )

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["label"], "Picture")
        self.assertEqual(len(result["images"]), 3)
        self.assertNotIn("image_url", result["candidates"][0])
        self.assertEqual(runtime.response_citations()[0].page_start, 2)

    def test_provider_follow_up_caps_layout_evidence_at_three_images(self) -> None:
        images = [
            {"role": f"evidence-{index}", "image_url": _png_data_url()}
            for index in range(5)
        ]
        parts = _chat_tool_image_parts(
            {
                "tool_name": "read_projected_pdf_layout_candidates",
                "application_result": {"ok": True, "page_number": 1, "images": images},
            }
        )
        image_parts = [item for item in parts if item.get("type") == "image_url"]
        self.assertEqual(len(image_parts), 3)


if __name__ == "__main__":
    unittest.main()
