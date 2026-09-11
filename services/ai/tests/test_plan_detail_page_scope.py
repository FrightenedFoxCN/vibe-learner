"""A shared source chapter must not redirect a revised unit to the book's start."""
from types import SimpleNamespace
import unittest

from app.models.domain import StudyUnitRecord
from app.services.plan_prompt import build_study_unit_detail_map


def chunk(identifier, section_id, start, end):
    return SimpleNamespace(id=identifier, section_id=section_id, page_start=start,
        page_end=end, char_count=10, content="fixture " + identifier, text_preview="")


class PlanDetailPageScopeTests(unittest.TestCase):
    def detail(self, chunks, start=80, end=85):
        unit = StudyUnitRecord(id="later-unit", document_id="doc", title="Later subchapter",
            page_start=start, page_end=end, source_section_ids=["parent"])
        parent = SimpleNamespace(id="parent", title="Whole chapter", level=1, page_start=1, page_end=100)
        debug = SimpleNamespace(sections=[parent], chunks=chunks)
        return build_study_unit_detail_map(study_units=[unit], debug_report=debug)[unit.id]

    def test_later_subchapter_does_not_receive_first_six_parent_excerpts(self):
        chunks = [chunk(f"early-{i}", "parent", 10+i, 10+i) for i in range(6)]
        chunks += [chunk("actual-later", "parent", 80, 81)]
        detail = self.detail(chunks)
        self.assertEqual(detail["chunk_count"], 1)
        self.assertEqual([c["chunk_id"] for c in detail["chunk_excerpts"]], ["actual-later"])

    def test_page_overlap_fallback_is_used_when_source_metadata_has_no_local_match(self):
        detail = self.detail([chunk("old-parent", "parent", 10, 11), chunk("local", "other", 82, 83)])
        self.assertEqual([c["chunk_id"] for c in detail["chunk_excerpts"]], ["local"])

    def test_shared_boundary_is_inclusive_but_missing_page_evidence_is_empty(self):
        detail = self.detail([chunk("boundary", "parent", 79, 80), chunk("after", "parent", 86, 87)])
        self.assertEqual([c["chunk_id"] for c in detail["chunk_excerpts"]], ["boundary"])
        self.assertEqual(self.detail([chunk("unrelated-page", "parent", 1, 2)])["chunk_excerpts"], [])
