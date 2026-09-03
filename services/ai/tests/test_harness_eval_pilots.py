from __future__ import annotations

import unittest

from app.services.harness_eval_pilots import execute_harness_pilot_bundle


class HarnessEvalPilotTests(unittest.TestCase):
    def test_checked_in_pilots_pass_against_checked_in_baselines(self) -> None:
        bundle = execute_harness_pilot_bundle(refresh_baselines=False)
        self.assertEqual(
            {key[0] for key in bundle.executions},
            {"planning_tool_eval", "study_chat_eval", "tavern_identity_eval"},
        )
        for execution in bundle.executions.values():
            self.assertEqual(execution.report.status, "passed")
            self.assertGreaterEqual(execution.report.sample_count, 8)
        for decision in bundle.decisions.values():
            self.assertEqual(decision.status, "passed")
        planning = next(
            execution
            for key, execution in bundle.executions.items()
            if key[0] == "planning_tool_eval"
        )
        latency_aggregates = {
            (item.metric.name, item.aggregation)
            for item in planning.report.aggregate_metrics
            if "_latency_ms" in item.metric.name
        }
        for tool_name in ("get_study_unit_detail", "invent_study_unit"):
            base = f"planning_{tool_name}_latency_ms"
            self.assertIn((base, "mean"), latency_aggregates)
            self.assertIn((f"{base}_p50", "p50"), latency_aggregates)
            self.assertIn((f"{base}_p95", "p95"), latency_aggregates)


if __name__ == "__main__":
    unittest.main()
