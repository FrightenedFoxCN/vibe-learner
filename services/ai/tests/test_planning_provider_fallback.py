from unittest import TestCase
from unittest.mock import Mock

from app.api._shared import _map_plan_generation_error
from app.models.domain import LearningGoalInput
from app.models.planning import LearningPlanOperationStatus
from app.services.plans import _learning_plan_failure_status
from app.services.provider_planning import RemotePlanningProvider
from tests.support.planning_operations import planning_document
from tests.support.planning_samples import planning_persona


class PlanProviderFallbackTests(TestCase):
    def test_tool_exhaustion_is_not_empty_without_distinct_fallback(self):
        for fallback in ("", "primary"):
            with self.subTest(fallback=fallback):
                self.check_failure(fallback, ["plan_model_tool_loop_exhausted"])

    def test_distinct_fallback_runs_once_and_reports_its_terminal_error(self):
        self.check_failure(
            "backup", ["plan_model_empty_response", "plan_model_tool_loop_exhausted"]
        )

    def test_budget_and_transport_failures_do_not_switch_models(self):
        for error, mapped_detail in (
            ("harness_budget_attempt_count_exceeded", "plan_generation_failed"),
            ("openai_plan_request_rate_limit", "plan_model_rate_limited"),
            ("openai_plan_request_unsupported_params", "plan_model_unsupported_params"),
        ):
            with self.subTest(error=error):
                self.check_failure(
                    "backup",
                    [error],
                    mapped_detail=mapped_detail,
                    status=LearningPlanOperationStatus.UNCERTAIN,
                )

    def check_failure(
        self,
        fallback,
        errors,
        *,
        mapped_detail=None,
        status=LearningPlanOperationStatus.NOT_COMMITTED,
    ):
        runner = Mock()
        runner.run.side_effect = [RuntimeError(error) for error in errors]
        runner_factory = Mock(return_value=runner)
        provider = RemotePlanningProvider(
            plan_model="primary",
            plan_tools_enabled=False,
            fallback_plan_model=fallback,
            fallback_disable_tools=True,
            multimodal_enabled=False,
            timeout_seconds=2,
            disabled_tools=frozenset(),
            request=Mock(side_effect=AssertionError("provider I/O is forbidden")),
            runner_factory=runner_factory,
        )
        doc = planning_document()
        with self.assertRaisesRegex(RuntimeError, f"^{errors[-1]}$") as error:
            provider.generate_learning_plan(
                persona=planning_persona(),
                document_title=doc.title,
                goal=LearningGoalInput(
                    document_id=doc.id,
                    persona_id="persona-1",
                    objective="Learn vectors",
                ),
                study_units=doc.study_units,
            )
        self.assertEqual(
            [call.kwargs["model"] for call in runner_factory.call_args_list],
            ["primary", "backup"] if len(errors) > 1 else ["primary"],
        )
        self.assertEqual(
            _map_plan_generation_error(error.exception).detail,
            mapped_detail or errors[-1],
        )
        self.assertEqual(
            _learning_plan_failure_status(
                error.exception, provider_started=True, candidate_built=False
            ),
            status,
        )
