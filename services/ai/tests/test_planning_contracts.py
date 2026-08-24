from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pydantic import ValidationError

from app.models.domain import LearningGoalInput, PersonaProfile, StudyUnitRecord
from app.models.planning import (
    LEARNING_PLAN_PROPOSAL_SCHEMA_NAME,
    LEARNING_PLAN_PROPOSAL_SCHEMA_VERSION,
    LearningPlanProposalV1,
    PlanContentSliceProposalV1,
    PlanScheduleChapterProposalV1,
)
from app.services.local_store import LocalJsonStore
from app.services.model_provider import (
    MockModelProvider,
    OpenAIModelProvider,
    PlanScheduleItem,
    PlanningProposalDecodeError,
    _decode_learning_plan_proposal,
)
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.plans import LearningPlanService
from app.services.study_arrangement import StudyArrangementService


class PlanningContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_malformed_tool_arguments_are_typed_and_never_become_empty_object(self) -> None:
        runtime = build_plan_tool_runtime()

        execution = runtime.execute_tool_call(
            {
                "id": "call-invalid-json",
                "type": "function",
                "function": {
                    "name": "ask_planning_question",
                    "arguments": '{"question":',
                },
            }
        )

        self.assertFalse(execution.result["ok"])
        self.assertEqual(execution.result["error"], "tool_argument_invalid_json")
        self.assertEqual(execution.result["schema_version"], "planning-tool-result-v1")
        self.assertEqual(execution.result["path"][:2], ["function", "arguments"])
        self.assertEqual(runtime.current_planning_questions(), [])

    def test_tool_argument_extra_field_reports_exact_path_and_skips_execution(self) -> None:
        runtime = build_plan_tool_runtime()

        execution = runtime.execute_tool_call(
            {
                "id": "call-extra-field",
                "type": "function",
                "function": {
                    "name": "ask_planning_question",
                    "arguments": json.dumps(
                        {
                            "question": "需要确认目标吗？",
                            "application_owned_id": "planning-question-forged",
                        }
                    ),
                },
            }
        )

        self.assertFalse(execution.result["ok"])
        self.assertEqual(execution.result["error"], "tool_argument_schema_invalid")
        self.assertEqual(execution.result["path"], ["application_owned_id"])
        self.assertEqual(runtime.current_planning_questions(), [])

    def test_tool_success_is_projected_through_versioned_result_contract(self) -> None:
        runtime = build_plan_tool_runtime()

        execution = runtime.execute_tool_call(
            {
                "id": "call-estimate",
                "type": "function",
                "function": {
                    "name": "estimate_plan_completion",
                    "arguments": json.dumps({"focus": "目录覆盖"}),
                },
            }
        )

        self.assertTrue(execution.result["ok"])
        self.assertEqual(execution.argument_contract_version, "planning-tool-arguments-v1")
        self.assertEqual(execution.result_contract_version, "planning-tool-result-v1")
        self.assertEqual(execution.result["schema_name"], "planning-tool-result")
        self.assertEqual(execution.result["tool_name"], "estimate_plan_completion")

    def test_plan_proposal_rejects_application_ids_and_coerced_numbers(self) -> None:
        payload = _valid_proposal_payload()
        payload["schedule"][0]["schedule_chapters"][0]["id"] = "forged-id"

        with self.assertRaises(ValidationError) as forged:
            LearningPlanProposalV1.model_validate(payload)

        self.assertEqual(
            forged.exception.errors(include_url=False)[0]["loc"],
            ("schedule", 0, "schedule_chapters", 0, "id"),
        )

        payload = _valid_proposal_payload()
        payload["schedule"][0]["schedule_chapters"][0]["anchor_page_start"] = "1"
        with self.assertRaises(ValidationError) as coerced:
            LearningPlanProposalV1.model_validate(payload)
        self.assertEqual(
            coerced.exception.errors(include_url=False)[0]["loc"],
            ("schedule", 0, "schedule_chapters", 0, "anchor_page_start"),
        )

    def test_model_proposal_decode_preserves_typed_failure_path(self) -> None:
        payload = _valid_proposal_payload()
        payload["schedule"][0]["unit_id"] = 123

        with self.assertRaises(PlanningProposalDecodeError) as raised:
            _decode_learning_plan_proposal(json.dumps(payload))

        self.assertEqual(raised.exception.path, "schedule.0.unit_id")
        self.assertEqual(raised.exception.reason, "string_type")

    def test_model_proposal_repair_is_bounded_to_one_retry(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
            plan_tools_enabled=False,
        )
        invalid_payload = _valid_proposal_payload()
        invalid_payload["schedule"][0]["schedule_chapters"][0]["id"] = "forged-id"
        responses = [
            _FakeLiteLLMResult(_chat_payload(invalid_payload)),
            _FakeLiteLLMResult(_chat_payload(_valid_proposal_payload())),
        ]

        with patch(
            "app.services.model_provider.litellm_completion",
            side_effect=responses,
        ) as completion:
            reply = provider.generate_learning_plan(
                persona=_persona(),
                document_title="Discrete Mathematics",
                goal=LearningGoalInput(
                    document_id="doc-1",
                    persona_id="persona-1",
                    objective="掌握集合基础",
                ),
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Foundations",
                        page_start=1,
                        page_end=5,
                        source_section_ids=["section-1"],
                    )
                ],
            )

        self.assertEqual(completion.call_count, 2)
        self.assertEqual(reply.course_title, "离散数学基础")
        self.assertIsNotNone(reply.debug_trace)
        assert reply.debug_trace is not None
        self.assertEqual([item.round_index for item in reply.debug_trace.rounds], [0, 1])
        self.assertEqual(
            reply.debug_trace.rounds[1].recoveries[0].strategy,
            "strict_contract_repair",
        )

    def test_application_assigns_chapter_id_after_proposal_validation(self) -> None:
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            MockModelProvider(),
        )
        unit = StudyUnitRecord(
            id="doc-1:study-unit:1",
            document_id="doc-1",
            title="Foundations",
            page_start=1,
            page_end=5,
            source_section_ids=["section-1"],
        )
        item = PlanScheduleItem(
            unit_id=unit.id,
            title="精读",
            focus="掌握基础概念",
            activity_type="learn",
            schedule_chapters=[
                PlanScheduleChapterProposalV1(
                    title="1.1 基础",
                    anchor_page_start=1,
                    anchor_page_end=5,
                    source_section_ids=["section-1"],
                    content_slices=[
                        PlanContentSliceProposalV1(
                            page_start=1,
                            page_end=5,
                            source_section_ids=["section-1"],
                        )
                    ],
                )
            ],
        )

        committed = service._build_schedule_record(index=0, item=item, unit=unit)

        self.assertEqual(committed.id, "schedule-1")
        self.assertEqual(
            committed.schedule_chapters[0].id,
            "doc-1:study-unit:1:schedule-chapter:1",
        )

    def test_out_of_unit_chapter_fails_instead_of_silently_disappearing(self) -> None:
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            MockModelProvider(),
        )
        unit = StudyUnitRecord(
            id="unit-1",
            document_id="doc-1",
            title="Foundations",
            page_start=1,
            page_end=5,
        )
        item = PlanScheduleItem(
            unit_id=unit.id,
            title="精读",
            focus="掌握基础概念",
            activity_type="learn",
            schedule_chapters=[
                PlanScheduleChapterProposalV1(
                    title="越界章节",
                    anchor_page_start=4,
                    anchor_page_end=6,
                    content_slices=[
                        PlanContentSliceProposalV1(page_start=4, page_end=6)
                    ],
                )
            ],
        )

        with self.assertRaisesRegex(RuntimeError, "outside_unit"):
            service._build_schedule_record(index=0, item=item, unit=unit)


class _FakeLiteLLMResult:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return self.payload


def _chat_payload(content: dict) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {"content": json.dumps(content)},
                "finish_reason": "stop",
            }
        ]
    }


def _persona() -> PersonaProfile:
    return PersonaProfile(
        id="persona-1",
        name="Test Mentor",
        source="user",
        summary="A deterministic planning test persona.",
        system_prompt="Help the learner build a grounded plan.",
        available_emotions=["focused"],
        available_actions=["explain"],
        default_speech_style="clear",
    )


def _valid_proposal_payload() -> dict:
    return {
        "schema_name": LEARNING_PLAN_PROPOSAL_SCHEMA_NAME,
        "schema_version": LEARNING_PLAN_PROPOSAL_SCHEMA_VERSION,
        "course_title": "离散数学基础",
        "overview": "先建立命题逻辑与集合的知识结构。",
        "today_tasks": ["阅读第一章并整理定义。"],
        "schedule": [
            {
                "unit_id": "unit-1",
                "title": "第一章精读",
                "focus": "理解集合与命题逻辑。",
                "activity_type": "learn",
                "schedule_chapters": [
                    {
                        "title": "1.1 集合",
                        "anchor_page_start": 1,
                        "anchor_page_end": 5,
                        "source_section_ids": ["section-1"],
                        "content_slices": [
                            {
                                "page_start": 1,
                                "page_end": 5,
                                "source_section_ids": ["section-1"],
                            }
                        ],
                    }
                ],
            }
        ],
    }


if __name__ == "__main__":
    unittest.main()
