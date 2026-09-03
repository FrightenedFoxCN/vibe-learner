from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from app.models.harness import HarnessContractRef
from app.models.harness_eval import (
    HarnessEvalReportV1,
    HarnessEvalRunV1,
    canonical_harness_eval_report_digest,
    canonical_harness_eval_run_digest,
)
from app.models.harness_eval_baseline import (
    HarnessEvalMetricThresholdV1,
    build_harness_eval_baseline,
    evaluate_harness_eval_baseline,
)


FIXTURE = (
    Path(__file__).parents[3]
    / "packages"
    / "shared"
    / "fixtures"
    / "harness"
    / "eval-contract-golden-v1.json"
)


class HarnessEvalBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.run = HarnessEvalRunV1.model_validate(payload["run"])
        self.report = HarnessEvalReportV1.model_validate(payload["report"])
        metric = self.report.aggregate_metrics[0].metric
        self.baseline = build_harness_eval_baseline(
            baseline_version="tavern-identity-baseline-v1",
            run=self.run,
            report=self.report,
            minimum_sample_count=1,
            thresholds=[
                HarnessEvalMetricThresholdV1(
                    metric=metric,
                    direction="minimum",
                    absolute_value=1.0,
                    max_regression_ratio=0.0,
                )
            ],
            review_contract=HarnessContractRef(
                name="HarnessEvalBaselineReview",
                version="harness-eval-baseline-review-v1",
            ),
            review_attestation_digest="a" * 64,
        )

    def test_equal_replay_passes_gate(self) -> None:
        decision = evaluate_harness_eval_baseline(
            baseline=self.baseline,
            candidate_run=self.run,
            candidate_report=self.report,
        )
        self.assertEqual(decision.status, "passed")
        self.assertTrue(decision.comparable)

    def test_metric_regression_fails_without_changing_comparability(self) -> None:
        payload = self.report.model_dump(mode="json", exclude_none=False)
        payload["aggregate_metrics"][0]["value"] = 0.0
        payload["aggregate_metrics"][0]["numerator"] = 0
        payload["report_digest"] = canonical_harness_eval_report_digest(payload)
        report = HarnessEvalReportV1.model_validate(payload)

        decision = evaluate_harness_eval_baseline(
            baseline=self.baseline,
            candidate_run=self.run,
            candidate_report=report,
        )
        self.assertEqual(decision.status, "failed")
        self.assertTrue(decision.comparable)
        self.assertEqual(
            decision.failure_codes,
            ["harness_eval_gate_metric_regression"],
        )

    def test_case_data_or_configuration_drift_blocks_comparison(self) -> None:
        run_payload = deepcopy(self.run.model_dump(mode="json", exclude_none=False))
        run_payload["case_set_digest"] = "b" * 64
        run_payload["run_digest"] = canonical_harness_eval_run_digest(run_payload)
        changed_run = HarnessEvalRunV1.model_validate(run_payload)
        report_payload = self.report.model_dump(mode="json", exclude_none=False)
        report_payload["run_digest"] = changed_run.run_digest
        report_payload["report_digest"] = canonical_harness_eval_report_digest(
            report_payload
        )
        changed_report = HarnessEvalReportV1.model_validate(report_payload)

        decision = evaluate_harness_eval_baseline(
            baseline=self.baseline,
            candidate_run=changed_run,
            candidate_report=changed_report,
        )
        self.assertEqual(decision.status, "blocked")
        self.assertFalse(decision.comparable)
        self.assertIn("harness_eval_gate_case_data_drift", decision.failure_codes)

    def test_broken_or_insufficient_samples_cannot_form_a_baseline(self) -> None:
        broken_payload = self.report.model_dump(mode="json", exclude_none=False)
        broken_payload.update(
            {
                "status": "broken",
                "passed_count": 0,
                "broken_count": 1,
            }
        )
        broken_payload["report_digest"] = canonical_harness_eval_report_digest(
            broken_payload
        )
        broken = HarnessEvalReportV1.model_validate(broken_payload)
        with self.assertRaisesRegex(ValueError, "report_not_passed"):
            build_harness_eval_baseline(
                baseline_version="invalid-v1",
                run=self.run,
                report=broken,
                minimum_sample_count=1,
                thresholds=list(self.baseline.thresholds),
                review_contract=self.baseline.review_contract,
                review_attestation_digest="a" * 64,
            )


if __name__ == "__main__":
    unittest.main()
