"""Planning model orchestration tests using an explicit runner dependency."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app.models.domain import LearningGoalInput, PlanGenerationTraceRecord, StudyUnitRecord
from app.services.provider_planning import RemotePlanningProvider
from tests.support.planning_samples import planning_persona, valid_proposal_payload


class PlanningProviderTests(unittest.TestCase):
    def provider(self, **overrides):
        args = dict(plan_model="primary", plan_tools_enabled=True, fallback_plan_model="fallback",
                    fallback_disable_tools=False, multimodal_enabled=False, timeout_seconds=30,
                    disabled_tools=frozenset({"ask_planning_question"}), request=Mock())
        return RemotePlanningProvider(**{**args, **overrides})

    def generate(self, provider, **kwargs):
        return provider.generate_learning_plan(persona=planning_persona(), document_title="Basics",
            goal=LearningGoalInput(document_id="doc-1", persona_id="persona-1", objective="Learn"),
            study_units=[StudyUnitRecord(id="unit-1", document_id="doc-1", title="Basics",
                page_start=1, page_end=5, source_section_ids=["section-1"])], **kwargs)

    def test_repair_uses_post_tool_units_and_cannot_mutate_them_again(self) -> None:
        from types import SimpleNamespace
        from app.models.domain import PlanGenerationTraceRecord

        unit = StudyUnitRecord(id="unit-1", document_id="doc-1", title="Basics",
            page_start=1, page_end=5, source_section_ids=["section-1"])
        revised = unit.model_copy(update={"id": "unit-revised"})
        calls = []

        def run(**kwargs):
            calls.append(kwargs)
            payload = valid_proposal_payload()
            if len(calls) == 1:
                kwargs["tool_runtime"].context.study_units[:] = [revised]
            else:
                context = json.loads(kwargs["messages"][1]["content"])
                self.assertEqual(context["study_units"][0]["unit_id"], revised.id)
                self.assertFalse(kwargs["tool_runtime"].has_tools())
                payload["schedule"][0]["unit_id"] = revised.id
            return SimpleNamespace(content=json.dumps(payload), trace=PlanGenerationTraceRecord(
                document_id="doc-1", model="test", created_at="2026-09-09T00:00:00+00:00"))

        provider = self.provider(runner_factory=lambda **_: SimpleNamespace(run=run))
        result = provider.generate_learning_plan(persona=planning_persona(), document_title="Basics",
            goal=LearningGoalInput(document_id="doc-1", persona_id="persona-1", objective="Learn"),
            study_units=[unit])
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.schedule[0].unit_id, revised.id)
        self.assertEqual(result.revised_study_units[0].id, revised.id)


    def test_fallback_retains_tool_policy_and_only_runs_once(self):
        calls = []
        def factory(**config):
            def run(**kwargs):
                calls.append((config, kwargs))
                self.assertNotIn("ask_planning_question", [spec["name"] for spec in kwargs["tool_runtime"].public_specs()])
                raise RuntimeError("plan_model_tool_loop_exhausted")
            return SimpleNamespace(run=run)
        with self.assertRaisesRegex(RuntimeError, "plan_model_tool_loop_exhausted"):
            self.generate(self.provider(runner_factory=factory))
        self.assertEqual([config["model"] for config, _ in calls], ["primary", "fallback"])

    def test_transport_error_does_not_switch_models(self):
        run = Mock(side_effect=RuntimeError("openai_plan_request_timeout"))
        with self.assertRaisesRegex(RuntimeError, "openai_plan_request_timeout"):
            self.generate(self.provider(runner_factory=lambda **_: SimpleNamespace(run=run)))
        self.assertEqual(run.call_count, 1)

    def test_cancellation_reaches_real_runner_before_any_request(self):
        request = Mock()
        interrupt = Mock(side_effect=RuntimeError("canceled"))
        with self.assertRaisesRegex(RuntimeError, "canceled"):
            self.generate(self.provider(request=request), interrupt_check=interrupt)
        request.assert_not_called()
