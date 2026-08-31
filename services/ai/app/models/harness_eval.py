from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
import re
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.harness import (
    HARNESS_OPERATION_STAGE_REGISTRATIONS,
    HarnessContractRef,
    HarnessStage,
    HarnessWorkflow,
    canonical_harness_digest,
    require_versioned_harness_contract,
)
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN


HARNESS_EVAL_CASE_SCHEMA_VERSION = "harness-eval-case-v1"
HARNESS_EVAL_RUN_SCHEMA_VERSION = "harness-eval-run-v1"
HARNESS_EVAL_SAMPLE_SCHEMA_VERSION = "harness-eval-sample-v1"
HARNESS_EVAL_REPORT_SCHEMA_VERSION = "harness-eval-report-v1"
HARNESS_EVAL_METRIC_SCHEMA_VERSION = "harness-eval-metric-v1"
HARNESS_EVAL_GRADER_RESULT_SCHEMA_VERSION = "harness-eval-grader-result-v1"
HARNESS_EVAL_FAILURE_SCHEMA_VERSION = "harness-eval-failure-v1"
HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION = "harness-eval-failure-taxonomy-v1"
HARNESS_EVAL_SYSTEM_CONFIG_SCHEMA_VERSION = "harness-eval-system-config-v1"
HARNESS_EVAL_ENVIRONMENT_SCHEMA_VERSION = "harness-eval-environment-v1"
HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION = "harness-eval-raw-samples-v1"
HARNESS_EVAL_CONTRACT_GOLDEN_SCHEMA_VERSION = "harness-eval-contract-golden-v1"

HARNESS_EVAL_FAILURE_TAXONOMY_CONTRACT = HarnessContractRef(
    name="HarnessEvalFailureTaxonomy",
    version=HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION,
)

_TOKEN_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$"
_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_RUN_ID_PATTERN = r"^harness-eval-run-[0-9a-f]{32}$"
_SAMPLE_ID_PATTERN = r"^harness-eval-sample-[0-9a-f]{32}$"
_REPORT_ID_PATTERN = r"^harness-eval-report-[0-9a-f]{32}$"
_UTC_TIMESTAMP_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


class HarnessEvalModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
        revalidate_instances="always",
    )


HarnessEvalSensitivity: TypeAlias = Literal["public", "internal", "protected"]
HarnessEvalSplit: TypeAlias = Literal[
    "development",
    "validation",
    "held_out",
    "calibration",
    "regression",
]
HarnessEvalSourceMode: TypeAlias = Literal["fixture", "synthetic", "protected_artifact"]
HarnessEvalProvenanceKind: TypeAlias = Literal[
    "developer_authored",
    "independently_reviewed",
    "synthetic",
    "production_derived",
    "imported",
]
HarnessEvalReviewStatus: TypeAlias = Literal[
    "unreviewed",
    "developer_reviewed",
    "independently_reviewed",
]
HarnessEvalExpectedOutcome: TypeAlias = Literal["passed", "failed", "not_applicable"]
HarnessEvalExecutionMode: TypeAlias = Literal["fixture", "synthetic", "protected_replay"]
HarnessEvalReasoningMode: TypeAlias = Literal[
    "not_supported",
    "disabled",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
]
HarnessEvalSeedStrategy: TypeAlias = Literal[
    "provider_unsupported",
    "per_sample",
    "fixed",
]
HarnessEvalWorktreeState: TypeAlias = Literal["clean", "dirty"]
HarnessEvalMetricUnit: TypeAlias = Literal[
    "boolean",
    "ratio",
    "score",
    "count",
    "milliseconds",
    "bytes",
    "tokens",
    "tool_calls",
    "provider_calls",
    "micro_usd",
]
HarnessEvalMetricAggregation: TypeAlias = Literal[
    "count",
    "sum",
    "mean",
    "min",
    "max",
    "rate",
    "p50",
    "p95",
]
HarnessEvalGraderKind: TypeAlias = Literal["deterministic", "model", "human"]
HarnessEvalGraderExecutionStatus: TypeAlias = Literal["completed", "error", "skipped"]
HarnessEvalVerdict: TypeAlias = Literal["passed", "failed", "not_applicable"]
HarnessEvalSampleStatus: TypeAlias = Literal["passed", "failed", "broken", "skipped"]
HarnessEvalCandidateOutcome: TypeAlias = Literal[
    "passed",
    "repaired",
    "failed",
    "skipped",
    "unavailable",
]
HarnessEvalFailureOwner: TypeAlias = Literal[
    "case",
    "runner",
    "candidate",
    "grader",
    "metric",
]
HarnessEvalFailureCategory: TypeAlias = Literal[
    "contract",
    "resolution",
    "configuration",
    "execution",
    "decode",
    "validation",
    "recovery",
    "commit",
    "effect",
    "grading",
    "measurement",
    "sensitivity",
]
HarnessEvalFailureReleaseClass: TypeAlias = Literal[
    "candidate_failure",
    "infrastructure_failure",
    "data_failure",
    "incomparable",
]
HarnessEvalReportStatus: TypeAlias = Literal["passed", "failed", "broken"]


def _validate_contract(contract: HarnessContractRef) -> None:
    require_versioned_harness_contract(
        HarnessContractRef.model_validate(
            contract.model_dump(mode="json", exclude_none=False)
        )
    )


def _require_sorted_unique_tokens(values: list[str], *, error_prefix: str) -> None:
    if values != sorted(values):
        raise ValueError(f"{error_prefix}_not_sorted")
    if len(values) != len(set(values)):
        raise ValueError(f"{error_prefix}_duplicate")
    if any(not re.fullmatch(_TOKEN_PATTERN, item) for item in values):
        raise ValueError(f"{error_prefix}_invalid")


def _require_sorted_unique_contracts(
    values: list[HarnessContractRef],
    *,
    error_prefix: str,
) -> None:
    for contract in values:
        _validate_contract(contract)
    identities = [(item.name, item.version) for item in values]
    if identities != sorted(identities):
        raise ValueError(f"{error_prefix}_not_sorted")
    if len(identities) != len(set(identities)):
        raise ValueError(f"{error_prefix}_duplicate")


def _require_utc_range(started_at: str, completed_at: str, *, error_prefix: str) -> None:
    start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    if start > end:
        raise ValueError(f"{error_prefix}_time_range_invalid")


def _dump_without(payload: BaseModel | dict[str, object], *fields: str) -> dict[str, object]:
    value = (
        payload.model_dump(mode="json", exclude_none=False)
        if isinstance(payload, BaseModel)
        else dict(payload)
    )
    for field in fields:
        value.pop(field, None)
    return value


def _contract_digest(
    *,
    name: str,
    version: str,
    payload: BaseModel | dict[str, object],
    excluded_fields: tuple[str, ...],
) -> str:
    return canonical_harness_digest(
        {
            "contract": {"name": name, "version": version},
            "payload": _dump_without(payload, *excluded_fields),
        }
    )


class HarnessEvalFixtureSourceV1(HarnessEvalModel):
    source_mode: Literal["fixture"] = "fixture"
    fixture_id: str = Field(pattern=_TOKEN_PATTERN)
    payload_contract: HarnessContractRef
    payload_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalFixtureSourceV1":
        _validate_contract(self.payload_contract)
        return self


class HarnessEvalSyntheticSourceV1(HarnessEvalModel):
    source_mode: Literal["synthetic"] = "synthetic"
    generator_contract: HarnessContractRef
    seed: int = Field(ge=0, le=9_007_199_254_740_991)
    manifest_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalSyntheticSourceV1":
        _validate_contract(self.generator_contract)
        return self


class HarnessEvalProtectedArtifactSourceV1(HarnessEvalModel):
    source_mode: Literal["protected_artifact"] = "protected_artifact"
    artifact_type: str = Field(pattern=_TOKEN_PATTERN)
    artifact_id: str = Field(pattern=_TOKEN_PATTERN)
    artifact_contract: HarnessContractRef
    payload_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalProtectedArtifactSourceV1":
        _validate_contract(self.artifact_contract)
        return self


HarnessEvalSourceV1: TypeAlias = Annotated[
    HarnessEvalFixtureSourceV1
    | HarnessEvalSyntheticSourceV1
    | HarnessEvalProtectedArtifactSourceV1,
    Field(discriminator="source_mode"),
]


class HarnessEvalProvenanceV1(HarnessEvalModel):
    source_kind: HarnessEvalProvenanceKind
    review_status: HarnessEvalReviewStatus
    review_contract: HarnessContractRef | None
    attestation_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_review_evidence(self) -> "HarnessEvalProvenanceV1":
        if self.review_contract is not None:
            _validate_contract(self.review_contract)
        requires_attestation = self.review_status == "independently_reviewed"
        if requires_attestation != (
            self.review_contract is not None and self.attestation_digest is not None
        ):
            raise ValueError("harness_eval_independent_review_evidence_mismatch")
        if self.review_status != "independently_reviewed" and (
            self.review_contract is not None or self.attestation_digest is not None
        ):
            raise ValueError("harness_eval_review_evidence_forbidden")
        return self


class HarnessEvalExpectedInvariantV1(HarnessEvalModel):
    invariant: HarnessContractRef
    expected_outcome: HarnessEvalExpectedOutcome

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalExpectedInvariantV1":
        _validate_contract(self.invariant)
        return self


class HarnessEvalCaseRefV1(HarnessEvalModel):
    suite: HarnessContractRef
    case_id: str = Field(pattern=_TOKEN_PATTERN)
    case_version: str = Field(pattern=_TOKEN_PATTERN)
    case_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalCaseRefV1":
        _validate_contract(self.suite)
        if self.case_version.lower() in {"latest", "unknown", "none"} or self.case_version.lower().startswith("pending-"):
            raise ValueError("harness_eval_case_version_not_adopted")
        return self


class HarnessEvalCaseV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalCase"] = "HarnessEvalCase"
    schema_version: Literal["harness-eval-case-v1"] = HARNESS_EVAL_CASE_SCHEMA_VERSION
    case_id: str = Field(pattern=_TOKEN_PATTERN)
    case_version: str = Field(pattern=_TOKEN_PATTERN)
    case_digest: str = Field(pattern=_DIGEST_PATTERN)
    suite: HarnessContractRef
    workflow: str = Field(pattern=_TOKEN_PATTERN)
    stage: str = Field(pattern=_TOKEN_PATTERN)
    eval_route: str = Field(pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")
    source: HarnessEvalSourceV1
    provenance: HarnessEvalProvenanceV1
    sensitivity: HarnessEvalSensitivity
    split: HarnessEvalSplit
    tags: list[str] = Field(default_factory=list, max_length=64)
    expected_invariants: list[HarnessEvalExpectedInvariantV1] = Field(
        default_factory=list,
        max_length=64,
    )
    grader_refs: list[HarnessContractRef] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_case(self) -> "HarnessEvalCaseV1":
        _validate_contract(self.suite)
        HarnessEvalCaseRefV1(
            suite=self.suite,
            case_id=self.case_id,
            case_version=self.case_version,
            case_digest=self.case_digest,
        )
        try:
            workflow = HarnessWorkflow(self.workflow)
            stage = HarnessStage(self.stage)
        except ValueError as error:
            raise ValueError("harness_eval_case_stage_unregistered") from error
        registration = HARNESS_OPERATION_STAGE_REGISTRATIONS.get((workflow, stage))
        if registration is None or registration.eval_route != self.eval_route:
            raise ValueError("harness_eval_case_route_mismatch")
        if (self.sensitivity == "protected") != (
            self.source.source_mode == "protected_artifact"
        ):
            raise ValueError("harness_eval_case_sensitivity_source_mismatch")
        if self.source.source_mode == "synthetic" and self.provenance.source_kind != "synthetic":
            raise ValueError("harness_eval_case_synthetic_provenance_required")
        if self.split in {"held_out", "calibration"} and (
            self.provenance.review_status != "independently_reviewed"
        ):
            raise ValueError("harness_eval_case_independent_review_required")
        _require_sorted_unique_tokens(self.tags, error_prefix="harness_eval_case_tags")
        invariant_identities = [
            (item.invariant.name, item.invariant.version)
            for item in self.expected_invariants
        ]
        if invariant_identities != sorted(invariant_identities):
            raise ValueError("harness_eval_case_invariants_not_sorted")
        if len(invariant_identities) != len(set(invariant_identities)):
            raise ValueError("harness_eval_case_invariant_duplicate")
        _require_sorted_unique_contracts(
            self.grader_refs,
            error_prefix="harness_eval_case_graders",
        )
        if not self.expected_invariants and not self.grader_refs:
            raise ValueError("harness_eval_case_expectation_missing")
        if self.case_digest != canonical_harness_eval_case_digest(self):
            raise ValueError("harness_eval_case_digest_mismatch")
        return self

    def to_ref(self) -> HarnessEvalCaseRefV1:
        return HarnessEvalCaseRefV1(
            suite=self.suite,
            case_id=self.case_id,
            case_version=self.case_version,
            case_digest=self.case_digest,
        )


def canonical_harness_eval_case_digest(
    case: HarnessEvalCaseV1 | dict[str, object],
) -> str:
    return _contract_digest(
        name="HarnessEvalCase",
        version=HARNESS_EVAL_CASE_SCHEMA_VERSION,
        payload=case,
        excluded_fields=("case_digest",),
    )


class HarnessEvalReasoningConfigV1(HarnessEvalModel):
    mode: HarnessEvalReasoningMode
    budget_tokens: int | None = Field(default=None, ge=1, le=10_000_000)

    @model_validator(mode="after")
    def validate_budget(self) -> "HarnessEvalReasoningConfigV1":
        if self.mode in {"not_supported", "disabled"} and self.budget_tokens is not None:
            raise ValueError("harness_eval_reasoning_budget_forbidden")
        return self


class HarnessEvalSamplingConfigV1(HarnessEvalModel):
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    seed_strategy: HarnessEvalSeedStrategy
    fixed_seed: int | None = Field(default=None, ge=0, le=9_007_199_254_740_991)

    @model_validator(mode="after")
    def validate_seed(self) -> "HarnessEvalSamplingConfigV1":
        if (self.seed_strategy == "fixed") != (self.fixed_seed is not None):
            raise ValueError("harness_eval_sampling_fixed_seed_mismatch")
        return self


class HarnessEvalExecutionBudgetV1(HarnessEvalModel):
    max_attempts: int = Field(ge=1, le=128)
    max_repairs: int = Field(ge=0, le=32)
    max_tool_calls: int = Field(ge=0, le=10_000)
    max_provider_calls: int = Field(ge=0, le=10_000)
    max_input_tokens: int = Field(ge=0, le=100_000_000)
    max_output_tokens: int = Field(ge=0, le=100_000_000)
    max_wall_time_ms: int = Field(ge=1, le=86_400_000)
    per_call_timeout_ms: int = Field(ge=1, le=86_400_000)
    max_cost_micro_usd: int = Field(ge=0, le=10_000_000_000)

    @model_validator(mode="after")
    def validate_attempt_budget(self) -> "HarnessEvalExecutionBudgetV1":
        if self.max_repairs >= self.max_attempts:
            raise ValueError("harness_eval_repair_budget_exceeds_attempts")
        if self.per_call_timeout_ms > self.max_wall_time_ms:
            raise ValueError("harness_eval_call_timeout_exceeds_wall_time")
        return self


class HarnessEvalSystemConfigV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalSystemConfig"] = "HarnessEvalSystemConfig"
    schema_version: Literal["harness-eval-system-config-v1"] = (
        HARNESS_EVAL_SYSTEM_CONFIG_SCHEMA_VERSION
    )
    workflow_manifest_contract: HarnessContractRef
    harness_contract: HarnessContractRef
    provider_adapter_contract: HarnessContractRef
    provider_model_contract: HarnessContractRef
    input_contract: HarnessContractRef
    output_contract: HarnessContractRef
    prompt_contract: HarnessContractRef | None
    policy_contract: HarnessContractRef | None
    toolset_contract: HarnessContractRef | None
    component_contracts: list[HarnessContractRef] = Field(min_length=1, max_length=64)
    reasoning: HarnessEvalReasoningConfigV1
    sampling: HarnessEvalSamplingConfigV1
    budgets: HarnessEvalExecutionBudgetV1
    source_revision: str = Field(pattern=_TOKEN_PATTERN)
    worktree_state: HarnessEvalWorktreeState
    source_tree_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_config(self) -> "HarnessEvalSystemConfigV1":
        for contract in (
            self.workflow_manifest_contract,
            self.harness_contract,
            self.provider_adapter_contract,
            self.provider_model_contract,
            self.input_contract,
            self.output_contract,
            self.prompt_contract,
            self.policy_contract,
            self.toolset_contract,
        ):
            if contract is not None:
                _validate_contract(contract)
        _require_sorted_unique_contracts(
            self.component_contracts,
            error_prefix="harness_eval_system_components",
        )
        if (self.worktree_state == "dirty") != (self.source_tree_digest is not None):
            raise ValueError("harness_eval_source_tree_digest_mismatch")
        return self


def canonical_harness_eval_system_config_digest(
    config: HarnessEvalSystemConfigV1 | dict[str, object],
) -> str:
    return _contract_digest(
        name="HarnessEvalSystemConfig",
        version=HARNESS_EVAL_SYSTEM_CONFIG_SCHEMA_VERSION,
        payload=config,
        excluded_fields=(),
    )


class HarnessEvalEnvironmentV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalEnvironment"] = "HarnessEvalEnvironment"
    schema_version: Literal["harness-eval-environment-v1"] = (
        HARNESS_EVAL_ENVIRONMENT_SCHEMA_VERSION
    )
    environment_contract: HarnessContractRef
    platform: str = Field(pattern=_TOKEN_PATTERN)
    architecture: str = Field(pattern=_TOKEN_PATTERN)
    python_version: str = Field(pattern=_TOKEN_PATTERN)
    node_version: str | None = Field(default=None, pattern=_TOKEN_PATTERN)
    database_kind: Literal["none", "sqlite", "postgresql"]
    provider_mode: Literal["mock", "local", "live"]

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalEnvironmentV1":
        _validate_contract(self.environment_contract)
        return self


def canonical_harness_eval_environment_digest(
    environment: HarnessEvalEnvironmentV1 | dict[str, object],
) -> str:
    return _contract_digest(
        name="HarnessEvalEnvironment",
        version=HARNESS_EVAL_ENVIRONMENT_SCHEMA_VERSION,
        payload=environment,
        excluded_fields=(),
    )


class HarnessEvalRunV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalRun"] = "HarnessEvalRun"
    schema_version: Literal["harness-eval-run-v1"] = HARNESS_EVAL_RUN_SCHEMA_VERSION
    run_id: str = Field(pattern=_RUN_ID_PATTERN)
    suite: HarnessContractRef
    suite_manifest_digest: str = Field(pattern=_DIGEST_PATTERN)
    case_set_digest: str = Field(pattern=_DIGEST_PATTERN)
    execution_mode: HarnessEvalExecutionMode
    splits: list[HarnessEvalSplit] = Field(min_length=1, max_length=8)
    repetition_count: int = Field(ge=1, le=1_000)
    seeds: list[int] = Field(min_length=1, max_length=1_000)
    runner_contract: HarnessContractRef
    failure_taxonomy_contract: HarnessContractRef
    grader_registry_contract: HarnessContractRef
    tested_system: HarnessEvalSystemConfigV1
    tested_system_config_digest: str = Field(pattern=_DIGEST_PATTERN)
    environment: HarnessEvalEnvironmentV1
    environment_digest: str = Field(pattern=_DIGEST_PATTERN)
    admitted_at: str = Field(pattern=_UTC_TIMESTAMP_PATTERN)
    run_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_run(self) -> "HarnessEvalRunV1":
        for contract in (
            self.suite,
            self.runner_contract,
            self.failure_taxonomy_contract,
            self.grader_registry_contract,
        ):
            _validate_contract(contract)
        if self.failure_taxonomy_contract != HARNESS_EVAL_FAILURE_TAXONOMY_CONTRACT:
            raise ValueError("harness_eval_failure_taxonomy_contract_mismatch")
        if self.splits != sorted(self.splits) or len(self.splits) != len(set(self.splits)):
            raise ValueError("harness_eval_run_splits_not_canonical")
        if len(self.seeds) != self.repetition_count or len(self.seeds) != len(set(self.seeds)):
            raise ValueError("harness_eval_run_seeds_mismatch")
        if self.execution_mode == "protected_replay" and self.environment.provider_mode == "mock":
            raise ValueError("harness_eval_protected_replay_mock_provider_forbidden")
        if self.tested_system_config_digest != canonical_harness_eval_system_config_digest(
            self.tested_system
        ):
            raise ValueError("harness_eval_system_config_digest_mismatch")
        if self.environment_digest != canonical_harness_eval_environment_digest(
            self.environment
        ):
            raise ValueError("harness_eval_environment_digest_mismatch")
        if self.run_digest != canonical_harness_eval_run_digest(self):
            raise ValueError("harness_eval_run_digest_mismatch")
        return self


def canonical_harness_eval_run_digest(run: HarnessEvalRunV1 | dict[str, object]) -> str:
    return _contract_digest(
        name="HarnessEvalRun",
        version=HARNESS_EVAL_RUN_SCHEMA_VERSION,
        payload=run,
        excluded_fields=("run_digest",),
    )


class HarnessEvalBooleanMetricV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalMetric"] = "HarnessEvalMetric"
    schema_version: Literal["harness-eval-metric-v1"] = HARNESS_EVAL_METRIC_SCHEMA_VERSION
    metric: HarnessContractRef
    value_type: Literal["boolean"] = "boolean"
    unit: Literal["boolean"] = "boolean"
    value: bool
    evidence_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalBooleanMetricV1":
        _validate_contract(self.metric)
        return self


class HarnessEvalIntegerMetricV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalMetric"] = "HarnessEvalMetric"
    schema_version: Literal["harness-eval-metric-v1"] = HARNESS_EVAL_METRIC_SCHEMA_VERSION
    metric: HarnessContractRef
    value_type: Literal["integer"] = "integer"
    unit: Literal[
        "count",
        "milliseconds",
        "bytes",
        "tokens",
        "tool_calls",
        "provider_calls",
        "micro_usd",
    ]
    value: int = Field(ge=0, le=9_007_199_254_740_991)
    evidence_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalIntegerMetricV1":
        _validate_contract(self.metric)
        return self


class HarnessEvalNumberMetricV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalMetric"] = "HarnessEvalMetric"
    schema_version: Literal["harness-eval-metric-v1"] = HARNESS_EVAL_METRIC_SCHEMA_VERSION
    metric: HarnessContractRef
    value_type: Literal["number"] = "number"
    unit: Literal["ratio", "score"]
    value: float = Field(ge=0, le=1)
    evidence_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalNumberMetricV1":
        _validate_contract(self.metric)
        return self


HarnessEvalMetricObservationV1: TypeAlias = Annotated[
    HarnessEvalBooleanMetricV1 | HarnessEvalIntegerMetricV1 | HarnessEvalNumberMetricV1,
    Field(discriminator="value_type"),
]


class HarnessEvalMetricAggregateV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalMetricAggregate"] = "HarnessEvalMetricAggregate"
    schema_version: Literal["harness-eval-metric-v1"] = HARNESS_EVAL_METRIC_SCHEMA_VERSION
    metric: HarnessContractRef
    aggregation: HarnessEvalMetricAggregation
    unit: HarnessEvalMetricUnit
    value: int | float = Field(ge=0)
    population_count: int = Field(ge=1, le=10_000_000)
    excluded_count: int = Field(ge=0, le=10_000_000)
    numerator: int | None = Field(default=None, ge=0, le=10_000_000)
    denominator: int | None = Field(default=None, ge=1, le=10_000_000)
    percentile_method: Literal["nearest_rank"] | None

    @model_validator(mode="after")
    def validate_aggregate(self) -> "HarnessEvalMetricAggregateV1":
        _validate_contract(self.metric)
        is_rate = self.aggregation == "rate"
        if is_rate != (self.numerator is not None and self.denominator is not None):
            raise ValueError("harness_eval_metric_rate_evidence_mismatch")
        if is_rate:
            if self.unit != "ratio" or self.numerator > self.denominator:
                raise ValueError("harness_eval_metric_rate_invalid")
            if abs(float(self.value) - self.numerator / self.denominator) > 1e-12:
                raise ValueError("harness_eval_metric_rate_value_mismatch")
        is_percentile = self.aggregation in {"p50", "p95"}
        if is_percentile != (self.percentile_method is not None):
            raise ValueError("harness_eval_metric_percentile_method_mismatch")
        if self.unit == "boolean":
            raise ValueError("harness_eval_metric_boolean_aggregate_forbidden")
        return self


class HarnessEvalGraderResultV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalGraderResult"] = "HarnessEvalGraderResult"
    schema_version: Literal["harness-eval-grader-result-v1"] = (
        HARNESS_EVAL_GRADER_RESULT_SCHEMA_VERSION
    )
    grader_result_id: str = Field(pattern=_TOKEN_PATTERN)
    grader: HarnessContractRef
    grader_kind: HarnessEvalGraderKind
    grader_config_digest: str = Field(pattern=_DIGEST_PATTERN)
    execution_status: HarnessEvalGraderExecutionStatus
    verdict: HarnessEvalVerdict | None
    score: float | None = Field(default=None, ge=0, le=1)
    metrics: list[HarnessEvalMetricObservationV1] = Field(default_factory=list, max_length=128)
    failure_codes: list[str] = Field(default_factory=list, max_length=32)
    evidence_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    duration_ms: int = Field(ge=0, le=86_400_000)

    @model_validator(mode="after")
    def validate_result(self) -> "HarnessEvalGraderResultV1":
        _validate_contract(self.grader)
        _require_sorted_unique_tokens(
            self.failure_codes,
            error_prefix="harness_eval_grader_failure_codes",
        )
        _require_metric_order(self.metrics, error_prefix="harness_eval_grader_metrics")
        if self.execution_status == "completed":
            if self.verdict is None or self.failure_codes:
                raise ValueError("harness_eval_completed_grader_result_invalid")
            if self.evidence_digest is None:
                raise ValueError("harness_eval_grader_evidence_required")
        elif self.execution_status == "error":
            if self.verdict is not None or self.score is not None or not self.failure_codes:
                raise ValueError("harness_eval_failed_grader_result_invalid")
        elif self.verdict is not None or self.score is not None or self.metrics:
            raise ValueError("harness_eval_skipped_grader_result_invalid")
        return self


class HarnessEvalFailureTaxonomyEntryV1(HarnessEvalModel):
    code: str = Field(pattern=_TOKEN_PATTERN)
    owner: HarnessEvalFailureOwner
    category: HarnessEvalFailureCategory
    release_class: HarnessEvalFailureReleaseClass
    retryable: bool
    counts_as_candidate_failure: bool
    allowed_sample_statuses: list[HarnessEvalSampleStatus] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def validate_entry(self) -> "HarnessEvalFailureTaxonomyEntryV1":
        if self.allowed_sample_statuses != sorted(self.allowed_sample_statuses) or len(
            self.allowed_sample_statuses
        ) != len(set(self.allowed_sample_statuses)):
            raise ValueError("harness_eval_failure_allowed_statuses_not_canonical")
        if self.counts_as_candidate_failure != (self.owner == "candidate"):
            raise ValueError("harness_eval_failure_candidate_blame_mismatch")
        if self.owner == "candidate" and self.release_class != "candidate_failure":
            raise ValueError("harness_eval_candidate_failure_release_class_mismatch")
        if self.owner != "candidate" and self.release_class == "candidate_failure":
            raise ValueError("harness_eval_non_candidate_failure_release_class_invalid")
        return self


_FAILURE_ENTRIES = (
    HarnessEvalFailureTaxonomyEntryV1(code="candidate_commit_failed", owner="candidate", category="commit", release_class="candidate_failure", retryable=False, counts_as_candidate_failure=True, allowed_sample_statuses=["failed"]),
    HarnessEvalFailureTaxonomyEntryV1(code="candidate_decode_failed", owner="candidate", category="decode", release_class="candidate_failure", retryable=False, counts_as_candidate_failure=True, allowed_sample_statuses=["failed", "passed"]),
    HarnessEvalFailureTaxonomyEntryV1(code="candidate_effect_uncertain", owner="candidate", category="effect", release_class="candidate_failure", retryable=False, counts_as_candidate_failure=True, allowed_sample_statuses=["failed"]),
    HarnessEvalFailureTaxonomyEntryV1(code="candidate_execution_failed", owner="candidate", category="execution", release_class="candidate_failure", retryable=False, counts_as_candidate_failure=True, allowed_sample_statuses=["failed", "passed"]),
    HarnessEvalFailureTaxonomyEntryV1(code="candidate_recovery_exhausted", owner="candidate", category="recovery", release_class="candidate_failure", retryable=False, counts_as_candidate_failure=True, allowed_sample_statuses=["failed"]),
    HarnessEvalFailureTaxonomyEntryV1(code="candidate_validation_failed", owner="candidate", category="validation", release_class="candidate_failure", retryable=False, counts_as_candidate_failure=True, allowed_sample_statuses=["failed", "passed"]),
    HarnessEvalFailureTaxonomyEntryV1(code="case_contract_invalid", owner="case", category="contract", release_class="data_failure", retryable=False, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="case_source_unresolved", owner="case", category="resolution", release_class="data_failure", retryable=True, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="eval_route_unregistered", owner="runner", category="configuration", release_class="infrastructure_failure", retryable=False, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="grader_execution_failed", owner="grader", category="grading", release_class="infrastructure_failure", retryable=True, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="grader_output_invalid", owner="grader", category="grading", release_class="infrastructure_failure", retryable=False, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="metric_computation_failed", owner="metric", category="measurement", release_class="infrastructure_failure", retryable=False, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="protected_artifact_forbidden", owner="case", category="resolution", release_class="data_failure", retryable=False, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="runner_configuration_invalid", owner="runner", category="configuration", release_class="incomparable", retryable=False, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="runner_execution_failed", owner="runner", category="execution", release_class="infrastructure_failure", retryable=True, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
    HarnessEvalFailureTaxonomyEntryV1(code="sensitive_material_detected", owner="runner", category="sensitivity", release_class="infrastructure_failure", retryable=False, counts_as_candidate_failure=False, allowed_sample_statuses=["broken"]),
)

HARNESS_EVAL_FAILURE_TAXONOMY = MappingProxyType(
    {item.code: item for item in _FAILURE_ENTRIES}
)


class HarnessEvalFailureTaxonomyRegistryV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalFailureTaxonomy"] = "HarnessEvalFailureTaxonomy"
    schema_version: Literal["harness-eval-failure-taxonomy-v1"] = (
        HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION
    )
    entries: list[HarnessEvalFailureTaxonomyEntryV1] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_entries(self) -> "HarnessEvalFailureTaxonomyRegistryV1":
        codes = [item.code for item in self.entries]
        if codes != sorted(codes) or len(codes) != len(set(codes)):
            raise ValueError("harness_eval_failure_taxonomy_not_canonical")
        return self


def harness_eval_failure_taxonomy_registry_snapshot() -> dict[str, object]:
    return HarnessEvalFailureTaxonomyRegistryV1(
        entries=[HARNESS_EVAL_FAILURE_TAXONOMY[key] for key in sorted(HARNESS_EVAL_FAILURE_TAXONOMY)]
    ).model_dump(mode="json", exclude_none=False)


class HarnessEvalFailureV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalFailure"] = "HarnessEvalFailure"
    schema_version: Literal["harness-eval-failure-v1"] = HARNESS_EVAL_FAILURE_SCHEMA_VERSION
    failure_code: str = Field(pattern=_TOKEN_PATTERN)
    owner: HarnessEvalFailureOwner
    reason_code: str = Field(pattern=_TOKEN_PATTERN)
    evidence_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_taxonomy(self) -> "HarnessEvalFailureV1":
        entry = HARNESS_EVAL_FAILURE_TAXONOMY.get(self.failure_code)
        if entry is None:
            raise ValueError("harness_eval_failure_code_unregistered")
        if entry.owner != self.owner:
            raise ValueError("harness_eval_failure_owner_mismatch")
        return self


def _metric_identity(metric: HarnessEvalMetricObservationV1 | HarnessEvalMetricAggregateV1) -> tuple[str, str]:
    return (metric.metric.name, metric.metric.version)


def _require_metric_order(
    metrics: list[HarnessEvalMetricObservationV1] | list[HarnessEvalMetricAggregateV1],
    *,
    error_prefix: str,
) -> None:
    identities = [_metric_identity(item) for item in metrics]
    if identities != sorted(identities):
        raise ValueError(f"{error_prefix}_not_sorted")
    if len(identities) != len(set(identities)):
        raise ValueError(f"{error_prefix}_duplicate")


def expected_harness_eval_sample_id(
    *,
    run_id: str,
    harness_operation_id: str,
    case_ref: HarnessEvalCaseRefV1 | dict[str, object],
    repetition_index: int,
    seed: int,
) -> str:
    case_payload = (
        case_ref.model_dump(mode="json", exclude_none=False)
        if isinstance(case_ref, HarnessEvalCaseRefV1)
        else dict(case_ref)
    )
    identity_digest = canonical_harness_digest(
        {
            "contract": {
                "name": "HarnessEvalSampleIdentity",
                "version": "harness-eval-sample-identity-v1",
            },
            "payload": {
                "run_id": run_id,
                "harness_operation_id": harness_operation_id,
                "case_ref": case_payload,
                "repetition_index": repetition_index,
                "seed": seed,
            },
        }
    )
    return f"harness-eval-sample-{identity_digest[:32]}"


class HarnessEvalSampleV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalSample"] = "HarnessEvalSample"
    schema_version: Literal["harness-eval-sample-v1"] = HARNESS_EVAL_SAMPLE_SCHEMA_VERSION
    sample_id: str = Field(pattern=_SAMPLE_ID_PATTERN)
    run_id: str = Field(pattern=_RUN_ID_PATTERN)
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    sample_index: int = Field(ge=1, le=10_000_000)
    case_ref: HarnessEvalCaseRefV1
    repetition_index: int = Field(ge=1, le=1_000)
    seed: int = Field(ge=0, le=9_007_199_254_740_991)
    status: HarnessEvalSampleStatus
    candidate_outcome: HarnessEvalCandidateOutcome
    raw_schema_valid: bool | None
    final_schema_valid: bool | None
    trace_contract: HarnessContractRef | None
    trace_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    metrics: list[HarnessEvalMetricObservationV1] = Field(default_factory=list, max_length=256)
    grader_results: list[HarnessEvalGraderResultV1] = Field(default_factory=list, max_length=64)
    failures: list[HarnessEvalFailureV1] = Field(default_factory=list, max_length=64)
    evidence_digest: str = Field(pattern=_DIGEST_PATTERN)
    started_at: str = Field(pattern=_UTC_TIMESTAMP_PATTERN)
    completed_at: str = Field(pattern=_UTC_TIMESTAMP_PATTERN)
    duration_ms: int = Field(ge=0, le=86_400_000)
    sample_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_sample(self) -> "HarnessEvalSampleV1":
        expected_id = expected_harness_eval_sample_id(
            run_id=self.run_id,
            harness_operation_id=self.harness_operation_id,
            case_ref=self.case_ref,
            repetition_index=self.repetition_index,
            seed=self.seed,
        )
        if self.sample_id != expected_id:
            raise ValueError("harness_eval_sample_id_mismatch")
        if (self.trace_contract is None) != (self.trace_digest is None):
            raise ValueError("harness_eval_sample_trace_evidence_incomplete")
        if self.trace_contract is not None:
            _validate_contract(self.trace_contract)
        _require_metric_order(self.metrics, error_prefix="harness_eval_sample_metrics")
        grader_ids = [(item.grader.name, item.grader.version) for item in self.grader_results]
        if grader_ids != sorted(grader_ids) or len(grader_ids) != len(set(grader_ids)):
            raise ValueError("harness_eval_sample_graders_not_canonical")
        failure_codes = [item.failure_code for item in self.failures]
        if failure_codes != sorted(failure_codes) or len(failure_codes) != len(set(failure_codes)):
            raise ValueError("harness_eval_sample_failures_not_canonical")
        for failure in self.failures:
            entry = HARNESS_EVAL_FAILURE_TAXONOMY[failure.failure_code]
            if self.status not in entry.allowed_sample_statuses:
                raise ValueError("harness_eval_sample_failure_status_mismatch")
        grader_error = any(item.execution_status == "error" for item in self.grader_results)
        infrastructure_failure = any(item.owner != "candidate" for item in self.failures)
        if grader_error or infrastructure_failure:
            if self.status != "broken":
                raise ValueError("harness_eval_infrastructure_failure_not_broken")
        if self.status in {"passed", "failed"}:
            if not self.grader_results or any(
                item.execution_status != "completed" for item in self.grader_results
            ):
                raise ValueError("harness_eval_evaluable_sample_grader_missing")
            has_failed_verdict = any(item.verdict == "failed" for item in self.grader_results)
            if (self.status == "failed") != has_failed_verdict:
                raise ValueError("harness_eval_sample_verdict_mismatch")
        elif self.status == "broken":
            if not self.failures and not grader_error:
                raise ValueError("harness_eval_broken_sample_failure_missing")
        else:
            if self.candidate_outcome != "skipped" or self.metrics or self.grader_results:
                raise ValueError("harness_eval_skipped_sample_contains_execution")
        if self.candidate_outcome in {"unavailable", "skipped"}:
            if self.raw_schema_valid is not None or self.final_schema_valid is not None:
                raise ValueError("harness_eval_unavailable_candidate_schema_evidence_forbidden")
        elif self.raw_schema_valid is None or self.final_schema_valid is None:
            raise ValueError("harness_eval_candidate_schema_evidence_required")
        if self.raw_schema_valid is True and self.final_schema_valid is not True:
            raise ValueError("harness_eval_final_schema_regressed")
        _require_utc_range(self.started_at, self.completed_at, error_prefix="harness_eval_sample")
        if self.sample_digest != canonical_harness_eval_sample_digest(self):
            raise ValueError("harness_eval_sample_digest_mismatch")
        return self


def canonical_harness_eval_sample_digest(
    sample: HarnessEvalSampleV1 | dict[str, object],
) -> str:
    return _contract_digest(
        name="HarnessEvalSample",
        version=HARNESS_EVAL_SAMPLE_SCHEMA_VERSION,
        payload=sample,
        excluded_fields=("sample_digest",),
    )


class HarnessEvalSampleRefV1(HarnessEvalModel):
    sample_id: str = Field(pattern=_SAMPLE_ID_PATTERN)
    sample_index: int = Field(ge=1, le=10_000_000)
    case_ref: HarnessEvalCaseRefV1
    sample_digest: str = Field(pattern=_DIGEST_PATTERN)


class HarnessEvalRawSamplesArtifactRefV1(HarnessEvalModel):
    artifact_id: str = Field(pattern=_TOKEN_PATTERN)
    artifact_contract: HarnessContractRef
    payload_digest: str = Field(pattern=_DIGEST_PATTERN)
    sample_count: int = Field(ge=0, le=10_000_000)

    @model_validator(mode="after")
    def validate_contract(self) -> "HarnessEvalRawSamplesArtifactRefV1":
        _validate_contract(self.artifact_contract)
        if self.artifact_contract != HarnessContractRef(
            name="HarnessEvalRawSamples",
            version=HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION,
        ):
            raise ValueError("harness_eval_raw_samples_contract_mismatch")
        return self


class HarnessEvalFailureCountV1(HarnessEvalModel):
    failure_code: str = Field(pattern=_TOKEN_PATTERN)
    count: int = Field(ge=1, le=10_000_000)

    @model_validator(mode="after")
    def validate_code(self) -> "HarnessEvalFailureCountV1":
        if self.failure_code not in HARNESS_EVAL_FAILURE_TAXONOMY:
            raise ValueError("harness_eval_failure_count_code_unregistered")
        return self


def expected_harness_eval_report_id(run_id: str) -> str:
    digest = canonical_harness_digest(
        {
            "contract": {
                "name": "HarnessEvalReportIdentity",
                "version": "harness-eval-report-identity-v1",
            },
            "payload": {"run_id": run_id},
        }
    )
    return f"harness-eval-report-{digest[:32]}"


class HarnessEvalReportV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalReport"] = "HarnessEvalReport"
    schema_version: Literal["harness-eval-report-v1"] = HARNESS_EVAL_REPORT_SCHEMA_VERSION
    report_id: str = Field(pattern=_REPORT_ID_PATTERN)
    run_id: str = Field(pattern=_RUN_ID_PATTERN)
    run_digest: str = Field(pattern=_DIGEST_PATTERN)
    tested_system_config_digest: str = Field(pattern=_DIGEST_PATTERN)
    status: HarnessEvalReportStatus
    expected_sample_count: int = Field(ge=1, le=10_000_000)
    sample_count: int = Field(ge=0, le=10_000_000)
    passed_count: int = Field(ge=0, le=10_000_000)
    failed_count: int = Field(ge=0, le=10_000_000)
    broken_count: int = Field(ge=0, le=10_000_000)
    skipped_count: int = Field(ge=0, le=10_000_000)
    sample_refs: list[HarnessEvalSampleRefV1] = Field(default_factory=list, max_length=10_000)
    raw_samples_artifact: HarnessEvalRawSamplesArtifactRefV1 | None
    aggregate_metrics: list[HarnessEvalMetricAggregateV1] = Field(default_factory=list, max_length=256)
    failure_counts: list[HarnessEvalFailureCountV1] = Field(default_factory=list, max_length=256)
    started_at: str = Field(pattern=_UTC_TIMESTAMP_PATTERN)
    completed_at: str = Field(pattern=_UTC_TIMESTAMP_PATTERN)
    report_digest: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def validate_report(self) -> "HarnessEvalReportV1":
        if self.report_id != expected_harness_eval_report_id(self.run_id):
            raise ValueError("harness_eval_report_id_mismatch")
        if self.sample_count != len(self.sample_refs):
            raise ValueError("harness_eval_report_sample_count_mismatch")
        if self.sample_count != (
            self.passed_count + self.failed_count + self.broken_count + self.skipped_count
        ):
            raise ValueError("harness_eval_report_terminal_counts_mismatch")
        indexes = [item.sample_index for item in self.sample_refs]
        if indexes != list(range(1, len(indexes) + 1)):
            raise ValueError("harness_eval_report_sample_indexes_not_contiguous")
        sample_ids = [item.sample_id for item in self.sample_refs]
        if len(sample_ids) != len(set(sample_ids)):
            raise ValueError("harness_eval_report_sample_id_duplicate")
        if self.sample_count:
            if self.raw_samples_artifact is None or (
                self.raw_samples_artifact.sample_count != self.sample_count
            ):
                raise ValueError("harness_eval_report_raw_samples_mismatch")
        elif self.raw_samples_artifact is not None:
            raise ValueError("harness_eval_empty_report_raw_samples_forbidden")
        incomplete = self.sample_count != self.expected_sample_count
        expected_status = (
            "broken"
            if self.broken_count or incomplete
            else "failed"
            if self.failed_count
            else "passed"
        )
        if self.status != expected_status:
            raise ValueError("harness_eval_report_status_mismatch")
        _require_metric_order(
            self.aggregate_metrics,
            error_prefix="harness_eval_report_metrics",
        )
        failure_codes = [item.failure_code for item in self.failure_counts]
        if failure_codes != sorted(failure_codes) or len(failure_codes) != len(set(failure_codes)):
            raise ValueError("harness_eval_report_failure_counts_not_canonical")
        _require_utc_range(self.started_at, self.completed_at, error_prefix="harness_eval_report")
        if self.report_digest != canonical_harness_eval_report_digest(self):
            raise ValueError("harness_eval_report_digest_mismatch")
        return self


def canonical_harness_eval_report_digest(
    report: HarnessEvalReportV1 | dict[str, object],
) -> str:
    return _contract_digest(
        name="HarnessEvalReport",
        version=HARNESS_EVAL_REPORT_SCHEMA_VERSION,
        payload=report,
        excluded_fields=("report_digest",),
    )


class HarnessEvalContractGoldenV1(HarnessEvalModel):
    schema_name: Literal["HarnessEvalContractGolden"] = "HarnessEvalContractGolden"
    schema_version: Literal["harness-eval-contract-golden-v1"] = (
        HARNESS_EVAL_CONTRACT_GOLDEN_SCHEMA_VERSION
    )
    case: HarnessEvalCaseV1
    run: HarnessEvalRunV1
    sample: HarnessEvalSampleV1
    report: HarnessEvalReportV1

    @model_validator(mode="after")
    def validate_cross_record_identity(self) -> "HarnessEvalContractGoldenV1":
        if self.run.suite != self.case.suite or self.sample.case_ref != self.case.to_ref():
            raise ValueError("harness_eval_golden_case_identity_mismatch")
        if self.sample.run_id != self.run.run_id or self.report.run_id != self.run.run_id:
            raise ValueError("harness_eval_golden_run_identity_mismatch")
        if self.report.run_digest != self.run.run_digest:
            raise ValueError("harness_eval_golden_run_digest_mismatch")
        if self.report.tested_system_config_digest != self.run.tested_system_config_digest:
            raise ValueError("harness_eval_golden_system_config_mismatch")
        if len(self.report.sample_refs) != 1 or self.report.sample_refs[0] != HarnessEvalSampleRefV1(
            sample_id=self.sample.sample_id,
            sample_index=self.sample.sample_index,
            case_ref=self.sample.case_ref,
            sample_digest=self.sample.sample_digest,
        ):
            raise ValueError("harness_eval_golden_sample_ref_mismatch")
        return self
