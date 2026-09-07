from __future__ import annotations

import unittest

from app.models.domain import (
    DocumentDebugRecord,
    DocumentPageRecord,
    DocumentRecord,
    DocumentSection,
)
from app.services.study_arrangement import StudyArrangementService


class StudyArrangementAuditTests(unittest.TestCase):
    def test_english_chapter_at_document_end_remains_plannable(self) -> None:
        document = DocumentRecord(
            id="doc-english-chapters",
            title="Discrete Mathematics",
            original_filename="discrete.pdf",
            stored_path="/tmp/discrete.pdf",
            status="processed",
            ocr_status="completed",
            created_at="2026-09-06T00:00:00+00:00",
            updated_at="2026-09-06T00:00:00+00:00",
        )
        report = DocumentDebugRecord(
            document_id=document.id,
            parser_name="audit-fixture",
            processed_at="2026-09-06T00:00:00+00:00",
            page_count=10,
            total_characters=0,
            extraction_method="text",
            pages=[
                DocumentPageRecord(
                    page_number=page,
                    char_count=0,
                    word_count=0,
                    text_preview="",
                    dominant_font_size=0,
                    heading_candidates=[],
                )
                for page in range(1, 11)
            ],
            sections=[
                DocumentSection(
                    id="doc-english-chapters:section:1",
                    document_id=document.id,
                    title="Chapter 4 Graphs",
                    page_start=1,
                    page_end=8,
                    level=1,
                ),
                DocumentSection(
                    id="doc-english-chapters:section:2",
                    document_id=document.id,
                    title="Chapter 5 Trees",
                    page_start=9,
                    page_end=10,
                    level=1,
                ),
            ],
            chunks=[],
            warnings=[],
            dominant_language_hint="en",
        )

        units = StudyArrangementService().build_study_units(
            document=document,
            debug_report=report,
        )

        final_unit = next(unit for unit in units if unit.title == "Chapter 5 Trees")
        self.assertEqual(final_unit.unit_kind, "chapter")
        self.assertTrue(final_unit.include_in_plan)


if __name__ == "__main__":
    unittest.main()
