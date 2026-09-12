"""A short single unit is not evidence of overly broad source segmentation."""
import unittest

from app.models.domain import StudyUnitRecord
from app.services.openai_plan_runner import _looks_coarse_grained
from app.services.plan_prompt import _build_segmentation_hints


def unit(pages):
    return StudyUnitRecord(id='unit', document_id='doc', title='Reading',
        page_start=1, page_end=pages, unit_kind='chapter', include_in_plan=True,
        source_section_ids=[], summary='', confidence=1)


class PlanningScopeClassificationTests(unittest.TestCase):
    def test_detailed_single_page_does_not_trigger_coarse_repair_advice(self):
        units = [unit(1)]
        hints = _build_segmentation_hints(study_units=units,
            detail_map={'unit': {'subsection_titles': ['Dialogue', 'Commentary']}})
        self.assertFalse(hints['is_coarse_grained'])
        self.assertNotIn('plannable_units_too_coarse', hints['reason'])
        self.assertFalse(hints['recommend_revise_study_units'])
        self.assertFalse(_looks_coarse_grained(units))

    def test_sparse_short_source_keeps_detail_warning_without_false_scope_claim(self):
        units = [unit(2)]
        hints = _build_segmentation_hints(study_units=units, detail_map={})
        self.assertFalse(hints['is_coarse_grained'])
        self.assertIn('subsections_too_sparse', hints['reason'])
        self.assertTrue(hints['recommend_detail_tool_call'])
        self.assertTrue(hints['recommend_revise_study_units'])
        self.assertFalse(_looks_coarse_grained(units))

    def test_existing_wide_span_threshold_agrees_between_prompt_and_runner(self):
        for pages, expected in [(79, False), (80, True), (736, True)]:
            with self.subTest(pages=pages):
                units = [unit(pages)]
                hints = _build_segmentation_hints(study_units=units,
                    detail_map={'unit': {'subsection_titles': ['A', 'B']}})
                self.assertEqual(hints['is_coarse_grained'], expected)
                self.assertEqual(_looks_coarse_grained(units), expected)
