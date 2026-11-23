from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.models.domain import LearningGoalInput, StudyUnitRecord
from app.services.model_provider import OpenAIModelProvider
from tests.support.planning_samples import (
    planning_persona as _persona,
    valid_proposal_payload as _valid_proposal_payload,
)


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


class PlanningNoRepairTests(unittest.TestCase):
    """Guard the planning contract repair retry stays removed.

    A proposal that fails strict contract validation must fail closed after the
    free local JSON salvage attempt. It must never spend a second provider call
    on a "repair this JSON" round trip: evaluation showed that round trip never
    changed the outcome while every failed attempt still billed the provider.
    """

    def test_invalid_proposal_does_not_retry_the_model(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
            plan_tools_enabled=False,
        )
        invalid_payload = _valid_proposal_payload()
        invalid_payload["schedule"][0]["schedule_chapters"][0]["id"] = "forged-id"

        with patch.object(
            provider.sdk,
            "completion",
            side_effect=lambda **_: _FakeLiteLLMResult(_chat_payload(invalid_payload)),
        ) as completion:
            with self.assertRaises(RuntimeError) as raised:
                provider.generate_learning_plan(
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

        self.assertEqual(completion.call_count, 1)
        self.assertIn("plan_proposal_schema_invalid", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
