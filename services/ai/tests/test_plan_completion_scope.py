"""Short source material must not be mistaken for overly broad segmentation."""
import unittest

from app.models.domain import StudyUnitRecord
from app.services.plan_tool_runtime import PlanToolRuntimeContext, _execute_estimate_plan_completion


def estimate(spans, detailed=True):
    units = [StudyUnitRecord(id=f'u-{i}', document_id='d', title='Reading',
                             page_start=start, page_end=end)
             for i, (start, end) in enumerate(spans)]
    context = PlanToolRuntimeContext(study_units=units,
        detail_map={u.id: {'subsection_titles': ['First', 'Second'] if detailed else []} for u in units},
        debug_report=None, document_path=None, multimodal_enabled=False,
        planning_questions=[], progress_callback=None)
    return _execute_estimate_plan_completion({}, context).payload


class PlanCompletionScopeTests(unittest.TestCase):
    def test_short_sources_do_not_request_segmentation(self):
        for spans in [[(1, 2)], [(1, 1), (2, 2)]]:
            with self.subTest(spans=spans):
                result = estimate(spans)
                self.assertNotIn('coarse_segmentation', result['missing_items'])
                self.assertFalse(any('拆细' in item for item in result['recommendations']))

    def test_same_detail_density_is_not_penalized_for_fewer_units(self):
        self.assertEqual(estimate([(1, 2)])['completion_score'],
                         estimate([(1, 2), (3, 4), (5, 6)])['completion_score'])

    def test_actual_wide_span_still_requests_segmentation(self):
        for spans in [[(1, 80)], [(1, 2), (3, 82), (83, 84)]]:
            with self.subTest(spans=spans):
                result = estimate(spans)
                self.assertIn('coarse_segmentation', result['missing_items'])
                self.assertLess(result['completion_score'], estimate([(1, 2)])['completion_score'])

    def test_missing_details_are_still_reported_for_short_source(self):
        result = estimate([(1, 2)], detailed=False)
        self.assertIn('subsection_detail', result['missing_items'])
        self.assertIn('page_range_evidence', result['missing_items'])
        self.assertNotIn('coarse_segmentation', result['missing_items'])
