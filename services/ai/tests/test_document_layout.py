from __future__ import annotations

import io
import unittest

from PIL import Image
from pydantic import ValidationError

from app.models.document_layout import DocumentLayoutCandidateV1
from app.services.document_layout import DocumentLayoutService


def _png(width: int = 200, height: int = 100) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(output, format="PNG")
    return output.getvalue()


class DocumentLayoutServiceTests(unittest.TestCase):
    def test_disabled_engine_returns_typed_content_free_result(self) -> None:
        result = DocumentLayoutService().detect_png(_png(), labels=["Picture"])

        self.assertEqual(result.status, "disabled")
        self.assertEqual(result.engine, "disabled")
        self.assertEqual(result.width, 200)
        self.assertEqual(result.height, 100)
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.warning, "document_layout_disabled")

    def test_runner_maps_recursive_candidates_and_suppresses_duplicates(self) -> None:
        def runner(_png, labels, recursive_picture):
            self.assertEqual(labels, ("Picture", "Formula"))
            self.assertTrue(recursive_picture)
            return {
                "width": 200,
                "height": 100,
                "detections": [
                    {"label": "Picture", "confidence": 0.9, "box_px": [20, 10, 180, 90], "depth": 0, "parent_index": None},
                    {"label": "Picture", "confidence": 0.8, "box_px": [21, 10, 180, 90], "depth": 0, "parent_index": None},
                    {"label": "Picture", "confidence": 0.7, "box_px": [40, 20, 100, 70], "depth": 1, "parent_index": 0},
                    {"label": "Formula", "confidence": 0.6, "box_px": [120, 30, 170, 50], "depth": 1, "parent_index": 0},
                ],
            }

        service = DocumentLayoutService(engine="doclayout-yolo", runner=runner)
        result = service.detect_png(_png(), labels=["Picture", "Formula"])

        self.assertEqual(result.status, "completed")
        self.assertEqual(len(result.candidates), 3)
        parent = result.candidates[0]
        self.assertEqual(parent.candidate_id, "layout-001")
        self.assertEqual(parent.box.model_dump(), {"x": 0.1, "y": 0.1, "width": 0.8, "height": 0.8})
        self.assertEqual(
            {candidate.parent_candidate_id for candidate in result.candidates[1:]},
            {parent.candidate_id},
        )

    def test_worker_contract_violation_fails_closed(self) -> None:
        service = DocumentLayoutService(
            engine="doclayout-yolo",
            runner=lambda *_: {
                "width": 200,
                "height": 100,
                "detections": [
                    {"label": "Text", "confidence": 0.9, "box_px": [1, 1, 20, 20], "depth": 0, "parent_index": None}
                ],
            },
        )

        result = service.detect_png(_png(), labels=["Picture"])

        self.assertEqual(result.status, "unavailable")
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.warning, "document_layout_unavailable:ValueError")

    def test_labels_are_limited_to_picture_and_formula(self) -> None:
        service = DocumentLayoutService(engine="doclayout-yolo", runner=lambda *_: {})
        with self.assertRaisesRegex(ValueError, "document_layout_labels_invalid"):
            service.detect_png(_png(), labels=[])
        with self.assertRaisesRegex(ValueError, "document_layout_labels_invalid"):
            service.detect_png(_png(), labels=["Text"])  # type: ignore[list-item]

    def test_model_rejects_recursive_candidate_without_parent(self) -> None:
        with self.assertRaises(ValidationError):
            DocumentLayoutCandidateV1.model_validate(
                {
                    "candidate_id": "layout-001",
                    "label": "Picture",
                    "confidence": 0.8,
                    "box": {"x": 0.1, "y": 0.1, "width": 0.5, "height": 0.5},
                    "depth": 1,
                    "parent_candidate_id": None,
                }
            )

    def test_provider_evidence_is_separate_from_detection_dto(self) -> None:
        service = DocumentLayoutService(
            engine="doclayout-yolo",
            runner=lambda *_: {
                "width": 200,
                "height": 100,
                "detections": [
                    {"label": "Picture", "confidence": 0.9, "box_px": [20, 10, 180, 90], "depth": 0, "parent_index": None}
                ],
            },
        )
        png = _png()
        result = service.detect_png(png, labels=["Picture"])
        evidence = service.evidence_images(png, result)

        self.assertEqual(len(evidence), 3)
        self.assertTrue(all(item["image_url"].startswith("data:image/png;base64,") for item in evidence))
        self.assertNotIn("image_url", result.model_dump_json())
        self.assertNotIn("base64", result.model_dump_json())


if __name__ == "__main__":
    unittest.main()
