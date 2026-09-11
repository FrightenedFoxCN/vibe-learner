"""Measurement regressions: classify envelopes without retaining response content."""
import json
import unittest
from tests.acceptance.planning_payload_observation import observe_planning_content


class PlanningPayloadObservationTests(unittest.TestCase):
    def test_strict_object_and_recoverable_fence_remain_distinct(self):
        valid = observe_planning_content('{"overview":"PRIVATE-CONTENT"}')
        fenced = observe_planning_content('```json\n{"overview":"PRIVATE-CONTENT"}\n```')
        self.assertTrue(valid['strict_json_object'])
        self.assertFalse(fenced['strict_json_object'])
        self.assertTrue(fenced['starts_with_code_fence'])
        for result in (valid, fenced):
            self.assertEqual(result['provider_object_decode'], 'accepted_object')
            self.assertNotIn('PRIVATE-CONTENT', json.dumps(result))

    def test_empty_truncated_and_array_are_not_equated(self):
        empty = observe_planning_content(' ')
        truncated = observe_planning_content('{"overview":')
        array = observe_planning_content('[]')
        self.assertTrue(empty['empty'])
        self.assertEqual(empty['provider_object_decode'], 'plan_model_invalid_json')
        self.assertFalse(truncated['empty'])
        self.assertEqual(truncated['json_error_offset'], 12)
        self.assertEqual(array['provider_object_decode'], 'plan_model_invalid_payload')

    def test_non_string_content_is_only_typed(self):
        self.assertEqual(observe_planning_content(None), {'content_type': 'NoneType'})
        self.assertEqual(observe_planning_content([{'text': 'PRIVATE-CONTENT'}]), {'content_type': 'list'})
