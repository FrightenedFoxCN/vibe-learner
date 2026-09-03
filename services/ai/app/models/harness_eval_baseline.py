from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.harness import HarnessContractRef, canonical_harness_digest
from app.models.harness_eval import (
    HARNESS_EVAL_REPORT_SCHEMA_VERSION,
    HarnessEvalMetricAggregateV1,
    HarnessEvalRawSamplesArtifactRefV1,
    HarnessEvalReportV1,
    HarnessEvalRunV1,
)


HARNESS_EVAL_BASELINE_SCHEMA_VERSION = "harness-eval-baseline-v1"
HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION = "harness-eval-gate-decision-v1"

_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_TOKEN_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$"


class _BaselineModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
        revalidate_instances="always",
    )


class HarnessEvalMetricThresholdV1(_BaselineModel):
    metric: HarnessContractRef
    direction: Literal["minimum", "maximum"]
    absolute_value: int | float = Field(ge=0)
    max_regression_ratio: float | None = Field(default=None, ge=0, le=1)


class HarnessEvalBaselineV1(_BaselineModel):
    """Reviewed release comparison point for one exact, reproducible eval run."""

    schema_name: Literal["HarnessEvalBaseline"] = "HarnessEvalBaseline"
    schema_version: Literal["harness-eval-baseline-v1"] = (
        HARNESS_EVAL_BASELINE_SCHEMA_VERSION
    )
    baseline_id: str = Field(pattern=r"^harness-eval-baseline-[0-9a-f]{32}$")
    baseline_version: str = Field(pattern=_TOKEN_PATTERN)
    suite: HarnessContractRef
    suite_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    case_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    tested_system_config_digest: str = Field(pattern=_DIGEST_PATTERN)
    environment_digest: str = Field(pattern=_DIGEST_PATTERN)
    execution_mode: Literal["fixture", "synthetic", "protected_replay"]
    splits: list[str] = Field(min_length=1, max_length=8)
    repetition_count: int = Field(ge=1, le=1_000)
    seeds: list[int] = Field(min_length=1, max_length=1_000)
    minimum_sample_count: int = Field(ge=1, le=10_000_000)
    report_contract: HarnessContractRef
    report_id: str = Field(pattern=r"^harness-eval-report-[0-9a-f]{32}$")
    report_digest: str = Field(pattern=_DIGEST_PATTERN)
    raw_samples_artifact: HarnessEvalRawSamplesArtifactRefV1
    metrics: list[HarnessEvalMetricAggregateV1] = Field(min_length=1, max_length=256)
    thresholds: list[HarnessEvalMetricThresholdV1] = Field(
        min_length=1,
        max_length=256,
    )
    review_contract: HarnessContractRef
    review_attestation_digest: str = Field(pattern=_DIGEST_PATTERN)
    baseline_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_baseline(self) -> "HarnessEvalBaselineV1":
        if self.report_contract != HarnessContractRef(
            name="HarnessEvalReport",
            version=HARNESS_EVAL_REPORT_SCHEMA_VERSION,
        ):
            raise ValueError("harness_eval_baseline_report_contract_mismatch")
        if self.splits != sorted(self.splits) or len(self.splits) != len(
            set(self.splits)
        ):
            raise ValueError("harness_eval_baseline_splits_not_canonical")
        if len(self.seeds) != self.repetition_count or len(self.seeds) != len(
            set(self.seeds)
        ):
            raise ValueError("harness_eval_baseline_seeds_mismatch")
        metric_ids = [(item.metric.name, item.metric.version) for item in self.metrics]
        if metric_ids != sorted(metric_ids) or len(metric_ids) != len(set(metric_ids)):
            raise ValueError("harness_eval_baseline_metrics_not_canonical")
        threshold_ids = [
            (item.metric.name, item.metric.version) for item in self.thresholds
        ]
        if threshold_ids != sorted(threshold_ids) or len(threshold_ids) != len(
            set(threshold_ids)
        ):
            raise ValueError("harness_eval_baseline_thresholds_not_canonical")
        if not set(threshold_ids) <= set(metric_ids):
            raise ValueError("harness_eval_baseline_threshold_metric_missing")
        if self.raw_samples_artifact.sample_count < self.minimum_sample_count:
            raise ValueError("harness_eval_baseline_sample_count_insufficient")
        if self.baseline_digest != canonical_harness_eval_baseline_digest(self):
            raise ValueError("harness_eval_baseline_digest_mismatch")
        return self


class HarnessEvalGateMetricResultV1(_BaselineModel):
    metric: HarnessContractRef
    baseline_value: int | float = Field(ge=0)
    candidate_value: int | float = Field(ge=0)
    passed: bool
    failure_code: str | None = Field(default=None, pattern=_TOKEN_PATTERN)

    @model_validator(mode="after")
    def validate_result(self) -> "HarnessEvalGateMetricResultV1":
        if self.passed == (self.failure_code is not None):
            raise ValueError("harness_eval_gate_metric_failure_shape_invalid")
        return self


class HarnessEvalGateDecisionV1(_BaselineModel):
    schema_name: Literal["HarnessEvalGateDecision"] = "HarnessEvalGateDecision"
    schema_version: Literal["harness-eval-gate-decision-v1"] = (
        HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION
    )
    baseline_id: str = Field(pattern=r"^harness-eval-baseline-[0-9a-f]{32}$")
    candidate_report_id: str = Field(pattern=r"^harness-eval-report-[0-9a-f]{32}$")
    status: Literal["passed", "failed", "blocked"]
    comparable: bool
    failure_codes: list[str] = Field(default_factory=list, max_length=64)
    metric_results: list[HarnessEvalGateMetricResultV1] = Field(
        default_factory=list,
        max_length=256,
    )
    decision_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_decision(self) -> "HarnessEvalGateDecisionV1":
        if self.failure_codes != sorted(self.failure_codes) or len(
            self.failure_codes
        ) != len(set(self.failure_codes)):
            raise ValueError("harness_eval_gate_failures_not_canonical")
        metric_ids = [
            (item.metric.name, item.metric.version) for item in self.metric_results
        ]
        if metric_ids != sorted(metric_ids) or len(metric_ids) != len(set(metric_ids)):
            raise ValueError("harness_eval_gate_metrics_not_canonical")
        expected = (
            "blocked"
            if not self.comparable
            else "failed"
            if self.failure_codes
            else "passed"
        )
        if self.status != expected:
            raise ValueError("harness_eval_gate_status_mismatch")
        if self.decision_digest != canonical_harness_eval_gate_decision_digest(self):
            raise ValueError("harness_eval_gate_decision_digest_mismatch")
        return self


def canonical_harness_eval_baseline_digest(
    baseline: HarnessEvalBaselineV1 | dict[str, object],
) -> str:
    payload = (
        baseline.model_dump(mode="json", exclude_none=False)
        if isinstance(baseline, HarnessEvalBaselineV1)
        else dict(baseline)
    )
    payload.pop("baseline_digest", None)
    return canonical_harness_digest(
        {
            "contract": {
                "name": "HarnessEvalBaseline",
                "version": HARNESS_EVAL_BASELINE_SCHEMA_VERSION,
            },
            "payload": payload,
        }
    )


def canonical_harness_eval_gate_decision_digest(
    decision: HarnessEvalGateDecisionV1 | dict[str, object],
) -> str:
    payload = (
        decision.model_dump(mode="json", exclude_none=False)
        if isinstance(decision, HarnessEvalGateDecisionV1)
        else dict(decision)
    )
    payload.pop("decision_digest", None)
    return canonical_harness_digest(
        {
            "contract": {
                "name": "HarnessEvalGateDecision",
                "version": HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION,
            },
            "payload": payload,
        }
    )


def build_harness_eval_baseline(
    *,
    baseline_version: str,
    run: HarnessEvalRunV1,
    report: HarnessEvalReportV1,
    minimum_sample_count: int,
    thresholds: list[HarnessEvalMetricThresholdV1],
    review_contract: HarnessContractRef,
    review_attestation_digest: str,
) -> HarnessEvalBaselineV1:
    if report.status != "passed":
        raise ValueError("harness_eval_baseline_report_not_passed")
    if report.run_id != run.run_id or report.run_digest != run.run_digest:
        raise ValueError("harness_eval_baseline_run_report_mismatch")
    if report.raw_samples_artifact is None:
        raise ValueError("harness_eval_baseline_raw_samples_required")
    identity_payload = {
        "suite": run.suite.model_dump(mode="json"),
        "baseline_version": baseline_version,
        "case_set_digest": run.case_set_digest,
        "tested_system_config_digest": run.tested_system_config_digest,
        "report_digest": report.report_digest,
    }
    baseline_id = (
        "harness-eval-baseline-"
        f"{canonical_harness_digest(identity_payload)[:32]}"
    )
    payload = {
        "schema_name": "HarnessEvalBaseline",
        "schema_version": HARNESS_EVAL_BASELINE_SCHEMA_VERSION,
        "baseline_id": baseline_id,
        "baseline_version": baseline_version,
        "suite": run.suite.model_dump(mode="json"),
        "suite_manifest_digest": run.suite_manifest_digest,
        "case_set_digest": run.case_set_digest,
        "tested_system_config_digest": run.tested_system_config_digest,
        "environment_digest": run.environment_digest,
        "execution_mode": run.execution_mode,
        "splits": list(run.splits),
        "repetition_count": run.repetition_count,
        "seeds": list(run.seeds),
        "minimum_sample_count": minimum_sample_count,
        "report_contract": {
            "name": "HarnessEvalReport",
            "version": HARNESS_EVAL_REPORT_SCHEMA_VERSION,
        },
        "report_id": report.report_id,
        "report_digest": report.report_digest,
        "raw_samples_artifact": report.raw_samples_artifact.model_dump(mode="json"),
        "metrics": [item.model_dump(mode="json") for item in report.aggregate_metrics],
        "thresholds": [item.model_dump(mode="json") for item in thresholds],
        "review_contract": review_contract.model_dump(mode="json"),
        "review_attestation_digest": review_attestation_digest,
        "baseline_digest": "0" * 64,
    }
    payload["baseline_digest"] = canonical_harness_eval_baseline_digest(payload)
    return HarnessEvalBaselineV1.model_validate(payload)


def evaluate_harness_eval_baseline(
    *,
    baseline: HarnessEvalBaselineV1,
    candidate_run: HarnessEvalRunV1,
    candidate_report: HarnessEvalReportV1,
) -> HarnessEvalGateDecisionV1:
    comparability_failures: list[str] = []
    comparisons = (
        (candidate_run.suite == baseline.suite, "harness_eval_gate_suite_mismatch"),
        (
            candidate_run.suite_manifest_digest == baseline.suite_manifest_digest,
            "harness_eval_gate_suite_manifest_drift",
        ),
        (
            candidate_run.case_set_digest == baseline.case_set_digest,
            "harness_eval_gate_case_data_drift",
        ),
        (
            candidate_run.tested_system_config_digest
            == baseline.tested_system_config_digest,
            "harness_eval_gate_system_configuration_drift",
        ),
        (
            candidate_run.environment_digest == baseline.environment_digest,
            "harness_eval_gate_environment_drift",
        ),
        (
            candidate_run.execution_mode == baseline.execution_mode,
            "harness_eval_gate_execution_mode_drift",
        ),
        (
            candidate_run.splits == baseline.splits,
            "harness_eval_gate_split_drift",
        ),
        (
            candidate_run.seeds == baseline.seeds
            and candidate_run.repetition_count == baseline.repetition_count,
            "harness_eval_gate_sampling_drift",
        ),
        (
            candidate_report.run_id == candidate_run.run_id
            and candidate_report.run_digest == candidate_run.run_digest,
            "harness_eval_gate_run_report_mismatch",
        ),
    )
    comparability_failures.extend(code for passed, code in comparisons if not passed)
    if (
        candidate_report.sample_count < baseline.minimum_sample_count
        or candidate_report.expected_sample_count < baseline.minimum_sample_count
    ):
        comparability_failures.append("harness_eval_gate_insufficient_samples")
    if candidate_report.broken_count or candidate_report.skipped_count:
        comparability_failures.append("harness_eval_gate_broken_samples")

    metric_results: list[HarnessEvalGateMetricResultV1] = []
    metric_failures: list[str] = []
    baseline_metrics = {
        (item.metric.name, item.metric.version): item for item in baseline.metrics
    }
    candidate_metrics = {
        (item.metric.name, item.metric.version): item
        for item in candidate_report.aggregate_metrics
    }
    if not comparability_failures:
        for threshold in baseline.thresholds:
            identity = (threshold.metric.name, threshold.metric.version)
            baseline_metric = baseline_metrics[identity]
            candidate_metric = candidate_metrics.get(identity)
            failure_code: str | None = None
            candidate_value: int | float = 0
            if candidate_metric is None:
                failure_code = "harness_eval_gate_metric_missing"
            else:
                candidate_value = candidate_metric.value
                baseline_value = float(baseline_metric.value)
                candidate_number = float(candidate_metric.value)
                if threshold.direction == "minimum":
                    regression_floor = (
                        baseline_value * (1 - threshold.max_regression_ratio)
                        if threshold.max_regression_ratio is not None
                        else 0
                    )
                    passed = candidate_number >= max(
                        float(threshold.absolute_value),
                        regression_floor,
                    )
                else:
                    regression_ceiling = (
                        baseline_value * (1 + threshold.max_regression_ratio)
                        if threshold.max_regression_ratio is not None
                        else float("inf")
                    )
                    passed = candidate_number <= min(
                        float(threshold.absolute_value),
                        regression_ceiling,
                    )
                if not passed:
                    failure_code = "harness_eval_gate_metric_regression"
            if failure_code is not None:
                metric_failures.append(failure_code)
            metric_results.append(
                HarnessEvalGateMetricResultV1(
                    metric=threshold.metric,
                    baseline_value=baseline_metric.value,
                    candidate_value=candidate_value,
                    passed=failure_code is None,
                    failure_code=failure_code,
                )
            )

    failures = sorted(set(comparability_failures or metric_failures))
    draft = {
        "schema_name": "HarnessEvalGateDecision",
        "schema_version": HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION,
        "baseline_id": baseline.baseline_id,
        "candidate_report_id": candidate_report.report_id,
        "status": (
            "blocked"
            if comparability_failures
            else "failed"
            if metric_failures
            else "passed"
        ),
        "comparable": not comparability_failures,
        "failure_codes": failures,
        "metric_results": [
            item.model_dump(mode="json")
            for item in sorted(
                metric_results,
                key=lambda item: (item.metric.name, item.metric.version),
            )
        ],
        "decision_digest": "0" * 64,
    }
    draft["decision_digest"] = canonical_harness_eval_gate_decision_digest(draft)
    return HarnessEvalGateDecisionV1.model_validate(draft)
