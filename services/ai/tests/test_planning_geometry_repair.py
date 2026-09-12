"""The bounded provider repair must see the same chapter geometry rules as commit."""
import copy
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.models.domain import LearningGoalInput, PlanGenerationTraceRecord, StudyUnitRecord
from app.models.planning import LearningPlanProposalV1
from app.services.plans import LearningPlanService
from app.services.provider_planning import (RemotePlanningProvider, PlanningProposalDecodeError,
                                            _validate_learning_plan_proposal_refs)
from tests.support.planning_samples import planning_persona, valid_proposal_payload


def unit():
    return StudyUnitRecord(id='unit-1', document_id='doc-1', title='Basics',
                           page_start=1, page_end=5, source_section_ids=['section-1'])


def two_chapters(starts):
    payload = valid_proposal_payload()
    template = payload['schedule'][0]['schedule_chapters'][0]
    chapters = []
    for start in starts:
        chapter = copy.deepcopy(template)
        chapter.update(anchor_page_start=start, anchor_page_end=start)
        chapter['content_slices'][0].update(page_start=start, page_end=start)
        chapters.append(chapter)
    payload['schedule'][0]['schedule_chapters'] = chapters
    return payload


class PlanningGeometryRepairTests(unittest.TestCase):
    def test_provider_and_commit_reject_same_geometry(self):
        cases = []
        cases.append((two_chapters([3, 1]), 'not_ordered'))
        outside = valid_proposal_payload()
        outside['schedule'][0]['schedule_chapters'][0]['anchor_page_end'] = 6
        cases.append((outside, 'outside_unit'))
        outside_slice = valid_proposal_payload()
        outside_slice['schedule'][0]['schedule_chapters'][0]['content_slices'][0]['page_end'] = 6
        cases.append((outside_slice, 'outside_chapter'))
        reversed_slices = valid_proposal_payload()
        reversed_slices['schedule'][0]['schedule_chapters'][0]['content_slices'] = [
            {'page_start':3,'page_end':4,'source_section_ids':['section-1']},
            {'page_start':1,'page_end':2,'source_section_ids':['section-1']}]
        cases.append((reversed_slices, 'not_ordered'))
        service = object.__new__(LearningPlanService)
        for raw, reason in cases:
            with self.subTest(reason=reason, payload=raw):
                proposal = LearningPlanProposalV1.model_validate(raw)
                with self.assertRaises(PlanningProposalDecodeError) as error:
                    _validate_learning_plan_proposal_refs(proposal, [unit()])
                self.assertEqual(error.exception.reason, reason)
                with self.assertRaisesRegex(RuntimeError, reason):
                    service._normalize_schedule_chapters(raw_schedule_chapters=proposal.schedule[0].schedule_chapters, unit=unit())

    def test_same_page_chapters_remain_allowed(self):
        proposal = LearningPlanProposalV1.model_validate(two_chapters([1,1]))
        _validate_learning_plan_proposal_refs(proposal, [unit()])
        service = object.__new__(LearningPlanService)
        chapters = service._normalize_schedule_chapters(
            raw_schedule_chapters=proposal.schedule[0].schedule_chapters, unit=unit())
        self.assertEqual([c.anchor_page_start for c in chapters], [1,1])

    def generate(self, responses):
        calls = []
        def run(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(content=json.dumps(responses[len(calls)-1]), tool_messages=[],
                trace=PlanGenerationTraceRecord(document_id='doc-1', model='test', created_at='2026-09-12T00:00:00+00:00'))
        provider = RemotePlanningProvider(plan_model='test', plan_tools_enabled=True,
            fallback_plan_model='', fallback_disable_tools=False, multimodal_enabled=False,
            timeout_seconds=30, disabled_tools=frozenset(), request=Mock(),
            runner_factory=lambda **_: SimpleNamespace(run=run))
        def invoke():
            return provider.generate_learning_plan(persona=planning_persona(), document_title='Basics',
                goal=LearningGoalInput(document_id='doc-1', persona_id='persona-1', objective='Learn'), study_units=[unit()])
        return invoke, calls

    def test_unordered_chapters_enter_one_repair_without_tools(self):
        invoke, calls = self.generate([two_chapters([3,1]), two_chapters([1,3])])
        result = invoke()
        self.assertEqual(len(calls), 2)
        self.assertFalse(calls[1]['tool_runtime'].has_tools())
        self.assertIn('not_ordered', calls[1]['messages'][-1]['content'])
        self.assertEqual([c.anchor_page_start for c in result.schedule[0].schedule_chapters], [1,3])

    def test_repeated_geometry_failure_does_not_add_more_repairs(self):
        invoke, calls = self.generate([two_chapters([3,1]), two_chapters([3,1])])
        with self.assertRaisesRegex(RuntimeError, 'not_ordered'):
            invoke()
        self.assertEqual(len(calls), 2)
