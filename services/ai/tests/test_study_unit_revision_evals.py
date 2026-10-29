import unittest
from unittest.mock import patch

from app.services.harness_stage_evals import close_stage_runner, gate_execution
from app.services.study_unit_revision_evals import (
    SUITE,
    build_study_unit_revision_runner,
)


class StudyUnitRevisionEvalTests(unittest.TestCase):
    def test_registered_suite_admits_real_preview_operations_and_detects_regression(
        self,
    ):
        runner = build_study_unit_revision_runner()
        try:
            run, cases = runner.stage_runs[SUITE.name], runner.stage_cases[SUITE.name]
            result = runner.run(
                run,
                cases,
                selected_suites=[SUITE],
                release_gate=True,
                deterministic_gate=True,
            )
            self.assertTrue(gate_execution(result, 8), result.report)
            with patch(
                "app.services.study_unit_revision_evals.apply_unit_suggestions",
                side_effect=ValueError("broken patch"),
            ):
                broken = runner.run(
                    run,
                    cases,
                    selected_suites=[SUITE],
                    release_gate=True,
                    deterministic_gate=True,
                )
            self.assertFalse(gate_execution(broken, 8))
        finally:
            close_stage_runner(runner)
