import unittest
from unittest.mock import patch
from app.services.plan_revision_evals import build_plan_revision_runner, SUITE
from app.services.harness_stage_evals import close_stage_runner, gate_execution


class PlanRevisionEvalTests(unittest.TestCase):
    def test_registered_suite_runs_seven_real_admissions(self):
        runner = build_plan_revision_runner()
        try:
            result = runner.run(runner.stage_runs[SUITE.name], runner.stage_cases[SUITE.name],
                selected_suites=[SUITE], release_gate=True, deterministic_gate=True)
            self.assertTrue(gate_execution(result, 7), result.report)
        finally:
            close_stage_runner(runner)

    def test_patch_regression_cannot_pass_gate(self):
        runner = build_plan_revision_runner()
        try:
            with patch('app.services.plan_revision_evals.apply_patch', side_effect=ValueError('broken patch')):
                result = runner.run(runner.stage_runs[SUITE.name], runner.stage_cases[SUITE.name],
                    selected_suites=[SUITE], release_gate=True, deterministic_gate=True)
            self.assertEqual(result.report.status, 'failed')
            self.assertFalse(gate_execution(result, 7))
        finally:
            close_stage_runner(runner)
