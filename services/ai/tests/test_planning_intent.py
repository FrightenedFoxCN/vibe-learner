from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from app.models.domain import LearningGoalInput, PlanningIntentV1, StudyUnitRecord
from app.models.planning import (
    LEARNING_PLAN_OPERATION_FINGERPRINT_LEGACY_VERSION,
    LearningPlanOperationRequestV1,
    learning_plan_request_fingerprint,
)
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.plans import LearningPlanService
from app.services.planning_intent import select_study_units_for_intent
from app.services.study_arrangement import StudyArrangementService
from app.services.provider_planning import (
    PlanningProposalDecodeError,
    _decode_learning_plan_proposal,
    _validate_learning_plan_proposal_refs,
)
from tests.support.planning_samples import valid_proposal_payload
from tests.support.planning_operations import planning_debug, planning_document
from tests.support.planning_samples import planning_persona


def _explicit_intent(**overrides: object) -> PlanningIntentV1:
    payload: dict[str, object] = {
        "pdf_page_ranges": {
            "status": "user_explicit",
            "value": [{"page_start": 1, "page_end": 5}],
        },
        "session_count": {"status": "user_explicit", "value": 1},
        "minutes_per_session": {"status": "user_explicit", "value": 45},
    }
    payload.update(overrides)
    return PlanningIntentV1.model_validate(payload)


class PlanningIntentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp_dir.name))

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_omitted_fields_are_explicitly_unknown(self) -> None:
        intent = LearningGoalInput(
            document_id="doc-1", persona_id="persona-1", objective="Learn"
        ).planning_intent
        self.assertEqual(intent.pdf_page_ranges.status, "unknown")
        self.assertIsNone(intent.pdf_page_ranges.value)
        self.assertEqual(intent.outline_targets.status, "unknown")
        self.assertEqual(intent.session_count.status, "unknown")
        self.assertEqual(intent.minutes_per_session.status, "unknown")
        self.assertEqual(intent.output_language.status, "unknown")

    def test_unknown_cannot_smuggle_a_value_and_explicit_requires_one(self) -> None:
        with self.assertRaises(ValidationError):
            PlanningIntentV1.model_validate(
                {"session_count": {"status": "unknown", "value": 4}}
            )
        with self.assertRaises(ValidationError):
            PlanningIntentV1.model_validate(
                {"minutes_per_session": {"status": "user_explicit", "value": None}}
            )

    def test_intent_is_in_current_fingerprint_but_legacy_unknown_replays(self) -> None:
        base = LearningPlanOperationRequestV1(
            client_request_id="request-1",
            document_id="doc-1",
            persona_id="persona-1",
            objective="Learn",
            expected_document_updated_at="2026-09-13T00:00:00Z",
        )
        explicit = base.model_copy(update={"planning_intent": _explicit_intent()})
        self.assertNotEqual(
            learning_plan_request_fingerprint(base),
            learning_plan_request_fingerprint(explicit),
        )
        legacy_payload = base.model_dump(mode="json")
        legacy_payload.pop("planning_intent")
        from app.models.planning import planning_projection_digest
        self.assertEqual(
            learning_plan_request_fingerprint(
                base,
                contract_version=LEARNING_PLAN_OPERATION_FINGERPRINT_LEGACY_VERSION,
            ),
            planning_projection_digest(legacy_payload),
        )

    def test_page_tool_rejects_user_explicit_out_of_scope_read(self) -> None:
        runtime = build_plan_tool_runtime(
            debug_report=SimpleNamespace(chunks=[]),
            planning_intent=_explicit_intent(),
        )
        execution = runtime.execute_tool_call({
            "id": "call-outside",
            "type": "function",
            "function": {
                "name": "read_page_range_content",
                "arguments": json.dumps({"page_start": 70, "page_end": 73}),
            },
        })
        self.assertFalse(execution.result["ok"])
        self.assertEqual(execution.result["error"], "outside_explicit_scope")

    def test_final_proposal_enforces_page_count_and_duration(self) -> None:
        proposal = _decode_learning_plan_proposal(json.dumps(valid_proposal_payload()))
        units = [StudyUnitRecord(
            id="unit-1", document_id="doc-1", title="Unit", page_start=1,
            page_end=10, source_section_ids=["section-1"],
        )]
        _validate_learning_plan_proposal_refs(proposal, units, _explicit_intent())

        outside = valid_proposal_payload()
        outside["schedule"][0]["schedule_chapters"][0]["anchor_page_start"] = 6
        outside["schedule"][0]["schedule_chapters"][0]["anchor_page_end"] = 7
        outside["schedule"][0]["schedule_chapters"][0]["content_slices"][0]["page_start"] = 6
        outside["schedule"][0]["schedule_chapters"][0]["content_slices"][0]["page_end"] = 7
        with self.assertRaises(PlanningProposalDecodeError) as raised:
            _validate_learning_plan_proposal_refs(
                _decode_learning_plan_proposal(json.dumps(outside)),
                units,
                _explicit_intent(),
            )
        self.assertEqual(raised.exception.reason, "outside_explicit_scope")

        wrong_duration = valid_proposal_payload()
        wrong_duration["schedule"][0]["duration_minutes"] = 30
        with self.assertRaises(PlanningProposalDecodeError) as raised:
            _validate_learning_plan_proposal_refs(
                _decode_learning_plan_proposal(json.dumps(wrong_duration)),
                units,
                _explicit_intent(),
            )
        self.assertEqual(raised.exception.reason, "explicit_minutes_mismatch")

        french_intent = _explicit_intent(
            output_language={"status": "user_explicit", "value": "fr"}
        )
        with self.assertRaises(PlanningProposalDecodeError) as raised:
            _validate_learning_plan_proposal_refs(proposal, units, french_intent)
        self.assertEqual(raised.exception.reason, "explicit_language_mismatch")

    def test_explicit_outline_target_scopes_units_while_unknown_keeps_all(self) -> None:
        units = [
            StudyUnitRecord(
                id=f"unit-{index}", document_id="doc-1", title=f"Unit {index}",
                page_start=index, page_end=index, source_section_ids=[section_id],
            )
            for index, section_id in ((1, "section-a"), (2, "section-b"))
        ]
        self.assertEqual(
            select_study_units_for_intent(
                study_units=units, intent=PlanningIntentV1()
            ),
            units,
        )
        selected = select_study_units_for_intent(
            study_units=units,
            intent=PlanningIntentV1.model_validate({
                "outline_targets": {
                    "status": "user_explicit", "value": ["section-b"],
                }
            }),
        )
        self.assertEqual([unit.id for unit in selected], ["unit-2"])

    def test_committed_candidate_preserves_four_by_forty_five_and_page_scope(self) -> None:
        document = planning_document()
        document.debug_ready = False
        goal = LearningGoalInput(
            document_id=document.id,
            persona_id="persona-1",
            objective="Study the selected pages",
            planning_intent=PlanningIntentV1.model_validate({
                "pdf_page_ranges": {
                    "status": "user_explicit",
                    "value": [{"page_start": 1, "page_end": 5}],
                },
                "session_count": {"status": "user_explicit", "value": 4},
                "minutes_per_session": {"status": "user_explicit", "value": 45},
            }),
        )
        service = LearningPlanService(
            self.store, StudyArrangementService(), MockModelProvider()
        )
        plan, _, _, _ = service._build_plan_candidate(
            goal=goal,
            document=document,
            persona_name="Test Mentor",
            persona=planning_persona(),
            debug_report=planning_debug(document),
        )
        self.assertEqual(len(plan.schedule), 4)
        self.assertEqual({item.unit_id for item in plan.schedule}, {document.study_units[0].id})
        self.assertEqual([item.duration_minutes for item in plan.schedule], [45] * 4)
        self.assertEqual(
            {
                (chapter.anchor_page_start, chapter.anchor_page_end)
                for item in plan.schedule
                for chapter in item.schedule_chapters
            },
            {(1, 5)},
        )
        self.assertEqual(plan.planning_intent.session_count.status, "user_explicit")


if __name__ == "__main__":
    unittest.main()
