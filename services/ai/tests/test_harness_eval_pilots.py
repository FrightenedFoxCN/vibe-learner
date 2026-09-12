from __future__ import annotations

import json
from pathlib import Path
import unittest

from app.services.harness_eval_pilots import execute_harness_pilot_bundle, _load_fixtures, _current_planning_cases


class HarnessEvalPilotTests(unittest.TestCase):
    def test_prompt_v1_study_baseline_remains_archived_separately(self):
        root = (
            Path(__file__).parents[3]
            / "packages"
            / "shared"
            / "fixtures"
            / "harness"
            / "eval-pilots"
        )
        legacy = json.loads(
            (root / "study_chat_eval" / "baseline.json").read_text(encoding="utf-8")
        )
        current = json.loads(
            (root / "study_chat_eval_prompt_v2" / "baseline.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(legacy["baseline_version"], "study-chat-eval-v1-baseline-v1")
        self.assertEqual(current["baseline_version"], "study-chat-eval-v1-baseline-v2")
        self.assertNotEqual(
            legacy["tested_system_config_digest"],
            current["tested_system_config_digest"],
        )

    def test_budget_revision_preserves_reviewed_book_and_held_out_cases(self):
        historical = _load_fixtures()
        original = next(case for case in historical.planning_cases if case.case_id == "planning-tool-duplicate-call-001")
        self.assertEqual(original.repeat_count, 2)
        current = _current_planning_cases(historical)
        replacement = next(case for case in current if case.case_id == "planning-tool-detail-round-limit-002")
        self.assertEqual((replacement.split, replacement.repeat_count), ("regression", 4))
        page_read = next(case for case in current if case.case_id == "planning-tool-page-read-round-limit-003")
        self.assertEqual((page_read.split, page_read.repeat_count), ("regression", 4))
        self.assertEqual([case for case in current if case.split == "held_out"],
            [case for case in historical.planning_cases if case.split == "held_out"])

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
