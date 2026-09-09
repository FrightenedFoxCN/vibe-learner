"""Closed, deterministic execution core for Harness evaluation suites.

The eval wire models deliberately contain evidence only.  This module owns the
runtime boundary: a suite and its route adapter must be explicitly registered
before a case can execute, and protected case payloads are available only from
an authorized resolver.  It intentionally has no default suites or provider
adapters; a manifest route is not an implicit permission to evaluate it.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import importlib
import json
from pathlib import Path
import re
from typing import Protocol

from app.models.harness import (
    HarnessArtifactType,
    HarnessContractRef,
    HarnessStage,
    HarnessWorkflow,
    canonical_harness_digest,
)
from app.models.harness_artifact_access import (
    HarnessArtifactPermission,
    HarnessArtifactResolveRequestV1,
)
from app.models.harness_eval import (
    HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION,
    HARNESS_EVAL_FAILURE_TAXONOMY,
    HarnessEvalCaseV1,
    HarnessEvalBooleanMetricV1,
    HarnessEvalFailureV1,
    HarnessEvalFailureCountV1,
    HarnessEvalGraderResultV1,
    HarnessEvalMetricAggregateV1,
    HarnessEvalIntegerMetricV1,
    HarnessEvalMetricObservationV1,
    HarnessEvalNumberMetricV1,
    HarnessEvalRawSamplesArtifactRefV1,
    HarnessEvalReportV1,
    HarnessEvalRunV1,
    HarnessEvalSampleRefV1,
    HarnessEvalSampleV1,
    HarnessEvalSystemConfigV1,
    canonical_harness_eval_report_digest,
    canonical_harness_eval_sample_digest,
    expected_harness_eval_report_id,
    expected_harness_eval_sample_id,
)
from app.models.harness_manifest import (
    HARNESS_WORKFLOW_MANIFEST_ENTRIES,
    HarnessManifestRegisteredContractListSlotV1,
    HarnessManifestRegisteredContractSlotV1,
    HarnessManifestRegisteredStringSlotV1,
)
from app.models.harness_operation import HarnessOperationBindingV1
from app.persistence.harness_artifact_repository import HarnessArtifactRepository


RAW_SAMPLES_CONTRACT = HarnessContractRef(
    name="HarnessEvalRawSamples",
    version=HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION,
)
FINAL_SCHEMA_VALID_RATE = HarnessContractRef(
    name="schema_valid_final_rate", version="schema-valid-final-rate-v1"
)
CANDIDATE_PASS_RATE = HarnessContractRef(
    name="candidate_pass_rate", version="candidate-pass-rate-v1"
)
RAW_SCHEMA_VALID_RATE = HarnessContractRef(
    name="schema_valid_raw_rate", version="schema-valid-raw-rate-v1"
)
REPAIR_RATE = HarnessContractRef(name="repair_rate", version="repair-rate-v1")
FAILURE_RATE = HarnessContractRef(name="failure_rate", version="failure-rate-v1")
DURATION_P50_MS = HarnessContractRef(
    name="duration_p50_ms", version="duration-p50-ms-v1"
)
DURATION_P95_MS = HarnessContractRef(
    name="duration_p95_ms", version="duration-p95-ms-v1"
)


class HarnessEvalRunnerError(ValueError):
    """A fail-closed registration or execution boundary violation."""


def _identity(contract: HarnessContractRef) -> tuple[str, str]:
    return (contract.name, contract.version)


def _digest(value: object) -> str:
    return canonical_harness_digest(value)


def _utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class HarnessEvalCandidateResult:
    """Content-free result returned by one registered workflow adapter."""

    candidate_outcome: str
    raw_schema_valid: bool | None
    final_schema_valid: bool | None
    trace_contract: HarnessContractRef | None
    trace_digest: str | None
    metrics: tuple[HarnessEvalMetricObservationV1, ...] = ()
    failures: tuple[HarnessEvalFailureV1, ...] = ()
    evidence_digest: str | None = None
    duration_ms: int = 0
    grader_evidence: Mapping[str, str | int | float | bool | None] | None = None

    def validate(self) -> None:
        if self.candidate_outcome not in {
            "passed", "repaired", "failed", "skipped", "unavailable"
        }:
            raise HarnessEvalRunnerError("harness_eval_candidate_outcome_invalid")
        if (self.trace_contract is None) != (self.trace_digest is None):
            raise HarnessEvalRunnerError("harness_eval_candidate_trace_evidence_incomplete")
        if self.duration_ms < 0:
            raise HarnessEvalRunnerError("harness_eval_candidate_duration_invalid")
        for digest in (self.trace_digest, self.evidence_digest):
            if digest is not None and re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise HarnessEvalRunnerError("harness_eval_candidate_digest_invalid")
        if self.candidate_outcome in {"unavailable", "skipped"}:
            if self.raw_schema_valid is not None or self.final_schema_valid is not None:
                raise HarnessEvalRunnerError("harness_eval_candidate_schema_evidence_forbidden")
        elif self.raw_schema_valid is None or self.final_schema_valid is None:
            raise HarnessEvalRunnerError("harness_eval_candidate_schema_evidence_required")
        for failure in self.failures:
            if failure.owner != "candidate":
                raise HarnessEvalRunnerError("harness_eval_candidate_failure_owner_invalid")
        metric_ids = [(item.metric.name, item.metric.version) for item in self.metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise HarnessEvalRunnerError("harness_eval_candidate_metric_duplicate")
        failure_codes = [item.failure_code for item in self.failures]
        if len(failure_codes) != len(set(failure_codes)):
            raise HarnessEvalRunnerError("harness_eval_candidate_failure_duplicate")
        if self.candidate_outcome == "unavailable" and not self.failures:
            raise HarnessEvalRunnerError("harness_eval_candidate_unavailable_failure_missing")
        if self.grader_evidence is not None:
            forbidden = {
                "prompt",
                "content",
                "transcript",
                "guidance",
                "raw_output",
                "api_key",
                "token",
                "secret",
            }
            if any(
                any(marker in key.lower() for marker in forbidden)
                for key in self.grader_evidence
            ):
                raise HarnessEvalRunnerError(
                    "harness_eval_candidate_grader_evidence_sensitive"
                )


@dataclass(frozen=True)
class HarnessEvalProtectedPayload:
    """A resolver result that proves an authorized protected replay read."""

    harness_operation_id: str
    artifact_type: str
    artifact_id: str
    artifact_contract: HarnessContractRef
    payload_digest: str
    payload: bytes
    authorization_digest: str
    resolution_status: str = "resolved"

    def validate_for(
        self,
        case: HarnessEvalCaseV1,
        operation_binding: HarnessOperationBindingV1,
    ) -> None:
        source = case.source
        if source.source_mode != "protected_artifact":
            raise HarnessEvalRunnerError("harness_eval_protected_source_expected")
        if self.resolution_status == "forbidden":
            raise HarnessEvalRunnerError("protected_artifact_forbidden")
        if self.resolution_status != "resolved":
            raise HarnessEvalRunnerError("case_source_unresolved")
        if re.fullmatch(r"[0-9a-f]{64}", self.authorization_digest) is None:
            raise HarnessEvalRunnerError("protected_artifact_forbidden")
        if (
            self.harness_operation_id != operation_binding.harness_operation_id
            or self.artifact_type != source.artifact_type
            or self.artifact_id != source.artifact_id
            or self.artifact_contract != source.artifact_contract
            or self.payload_digest != source.payload_digest
            or hashlib.sha256(self.payload).hexdigest() != self.payload_digest
        ):
            raise HarnessEvalRunnerError("case_source_unresolved")


@dataclass(frozen=True)
class HarnessEvalFixturePayload:
    """Fixture data paired with the digest pinned in a public/internal case."""

    payload: object
    payload_digest: str


@dataclass(frozen=True)
class HarnessEvalSyntheticPayload:
    """Synthetic data tied to the registered generator manifest and seed."""

    payload: object
    payload_digest: str
    manifest_digest: str
    seed: int


class HarnessEvalProtectedResolver(Protocol):
    def resolve(
        self,
        case: HarnessEvalCaseV1,
        operation_binding: HarnessOperationBindingV1,
    ) -> HarnessEvalProtectedPayload: ...


class HarnessEvalGrantResolver(Protocol):
    def __call__(
        self,
        case: HarnessEvalCaseV1,
        operation_binding: HarnessOperationBindingV1,
    ) -> str: ...


class HarnessArtifactEvalResolver:
    """Concrete protected replay bridge through the authorized artifact store."""

    def __init__(
        self,
        repository: HarnessArtifactRepository,
        grant_resolver: HarnessEvalGrantResolver,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._grant_resolver = grant_resolver
        self._now = now or (lambda: datetime.now(UTC))

    def resolve(
        self,
        case: HarnessEvalCaseV1,
        operation_binding: HarnessOperationBindingV1,
    ) -> HarnessEvalProtectedPayload:
        source = case.source
        if source.source_mode != "protected_artifact":
            raise HarnessEvalRunnerError("harness_eval_protected_source_expected")
        request = HarnessArtifactResolveRequestV1(
            grant_id=self._grant_resolver(case, operation_binding),
            harness_operation_id=operation_binding.harness_operation_id,
            artifact_id=source.artifact_id,
            artifact_type=HarnessArtifactType(source.artifact_type),
            artifact_contract=source.artifact_contract,
            permission=HarnessArtifactPermission.READ,
        )
        resolution = self._repository.resolve(request, now=self._now())
        authorization_digest = _digest(
            {
                "request": request.model_dump(mode="json", exclude_none=False),
                "resolution": resolution.model_dump(
                    mode="json",
                    exclude={"content"},
                    exclude_none=False,
                ),
            }
        )
        return HarnessEvalProtectedPayload(
            harness_operation_id=operation_binding.harness_operation_id,
            artifact_type=source.artifact_type,
            artifact_id=source.artifact_id,
            artifact_contract=source.artifact_contract,
            payload_digest=resolution.payload_digest or source.payload_digest,
            payload=resolution.content or b"",
            authorization_digest=authorization_digest,
            resolution_status=resolution.status.value,
        )


class HarnessEvalOperationAdmitter(Protocol):
    def __call__(
        self,
        *,
        case: HarnessEvalCaseV1,
        run: HarnessEvalRunV1,
        repetition_index: int,
        seed: int,
    ) -> HarnessOperationBindingV1: ...


class HarnessEvalOperationResolver(Protocol):
    def resolve_harness_id(
        self,
        *,
        harness_operation_id: str,
    ) -> HarnessOperationBindingV1 | None: ...


class HarnessEvalRouteExecutor(Protocol):
    def __call__(
        self,
        *,
        case: HarnessEvalCaseV1,
        payload: object,
        operation_binding: HarnessOperationBindingV1,
        run: HarnessEvalRunV1,
        repetition_index: int,
        seed: int,
    ) -> HarnessEvalCandidateResult: ...


class HarnessEvalFixtureResolver(Protocol):
    def __call__(self, case: HarnessEvalCaseV1) -> HarnessEvalFixturePayload: ...


class HarnessEvalSyntheticResolver(Protocol):
    def __call__(self, case: HarnessEvalCaseV1, seed: int) -> HarnessEvalSyntheticPayload: ...


@dataclass(frozen=True)
class HarnessEvalRouteAdapter:
    """Executable functions for one separately registered suite route."""

    suite: HarnessContractRef
    eval_route: str
    operation_admitter: HarnessEvalOperationAdmitter
    fixture_resolver: HarnessEvalFixtureResolver | None
    synthetic_resolver: HarnessEvalSyntheticResolver | None
    execute: HarnessEvalRouteExecutor


@dataclass(frozen=True)
class HarnessEvalSuiteRegistration:
    """Closed, versioned execution registration independent of adapter code."""

    registration_contract: HarnessContractRef
    suite: HarnessContractRef
    workflow: HarnessWorkflow
    stage: HarnessStage
    eval_route: str
    runner_contract: HarnessContractRef
    grader_registry_contract: HarnessContractRef
    tested_system: HarnessEvalSystemConfigV1
    known_contracts: tuple[HarnessContractRef, ...]
    allowed_execution_modes: tuple[str, ...]

    def validate_registration(self) -> None:
        entry = HARNESS_WORKFLOW_MANIFEST_ENTRIES.get(
            f"{self.workflow.value}:{self.stage.value}"
        )
        if entry is None:
            raise HarnessEvalRunnerError("eval_route_unregistered")
        if not isinstance(entry.eval_route, HarnessManifestRegisteredStringSlotV1):
            raise HarnessEvalRunnerError("eval_route_unregistered")
        if entry.eval_route.value != self.eval_route:
            raise HarnessEvalRunnerError("harness_eval_route_manifest_mismatch")
        if not isinstance(
            entry.eval_suites,
            HarnessManifestRegisteredContractListSlotV1,
        ) or _identity(self.suite) not in {
            (item.name, item.version)
            for item in entry.eval_suites.contracts
        }:
            raise HarnessEvalRunnerError("harness_eval_suite_manifest_unregistered")
        identities = [_identity(item) for item in self.known_contracts]
        if identities != sorted(identities) or len(identities) != len(set(identities)):
            raise HarnessEvalRunnerError("harness_eval_known_contracts_not_canonical")
        required = {
            _identity(self.registration_contract),
            _identity(self.suite),
            _identity(self.runner_contract),
            _identity(self.grader_registry_contract),
        }
        if not required <= set(identities):
            raise HarnessEvalRunnerError("harness_eval_suite_contract_unregistered")
        if self.allowed_execution_modes != tuple(sorted(set(self.allowed_execution_modes))):
            raise HarnessEvalRunnerError("harness_eval_execution_modes_not_canonical")
        if not self.allowed_execution_modes or any(
            item not in {"fixture", "synthetic", "protected_replay"}
            for item in self.allowed_execution_modes
        ):
            raise HarnessEvalRunnerError("harness_eval_execution_mode_unregistered")

    def validate_case_and_run(self, case: HarnessEvalCaseV1, run: HarnessEvalRunV1) -> None:
        self.validate_registration()
        if case.suite != self.suite or run.suite != self.suite:
            raise HarnessEvalRunnerError("harness_eval_suite_unregistered")
        if (
            case.workflow != self.workflow.value
            or case.stage != self.stage.value
            or case.eval_route != self.eval_route
        ):
            raise HarnessEvalRunnerError("eval_route_unregistered")
        if run.tested_system != self.tested_system:
            raise HarnessEvalRunnerError("harness_eval_system_configuration_unregistered")
        if run.runner_contract != self.runner_contract:
            raise HarnessEvalRunnerError("harness_eval_runner_contract_unregistered")
        if run.grader_registry_contract != self.grader_registry_contract:
            raise HarnessEvalRunnerError("harness_eval_grader_registry_unregistered")
        if run.execution_mode not in self.allowed_execution_modes:
            raise HarnessEvalRunnerError("harness_eval_execution_mode_unregistered")
        known = {_identity(item) for item in self.known_contracts}
        contracts = [
            self.registration_contract,
            case.suite,
            *case.grader_refs,
            *(item.invariant for item in case.expected_invariants),
            run.runner_contract,
            run.failure_taxonomy_contract,
            run.grader_registry_contract,
            run.tested_system.workflow_manifest_contract,
            run.tested_system.harness_contract,
            run.tested_system.provider_adapter_contract,
            run.tested_system.provider_model_contract,
            run.tested_system.input_contract,
            run.tested_system.output_contract,
            *run.tested_system.component_contracts,
            run.environment.environment_contract,
        ]
        for optional in (
            run.tested_system.prompt_contract,
            run.tested_system.policy_contract,
            run.tested_system.toolset_contract,
        ):
            if optional is not None:
                contracts.append(optional)
        source = case.source
        if source.source_mode == "fixture":
            contracts.append(source.payload_contract)
        elif source.source_mode == "synthetic":
            contracts.append(source.generator_contract)
        else:
            contracts.append(source.artifact_contract)
        unknown = [item for item in contracts if _identity(item) not in known]
        if unknown:
            identities = ",".join(
                f"{item.name}@{item.version}" for item in unknown
            )
            raise HarnessEvalRunnerError(
                f"harness_eval_contract_unregistered:{identities}"
            )


class HarnessEvalSuiteRegistry:
    """Immutable-by-construction suite authority used by the runner."""

    def __init__(self, contract: HarnessContractRef) -> None:
        self.contract = contract
        self._registrations: dict[tuple[str, str], HarnessEvalSuiteRegistration] = {}

    def register(self, registration: HarnessEvalSuiteRegistration) -> None:
        if registration.registration_contract != self.contract:
            raise HarnessEvalRunnerError(
                "harness_eval_suite_registry_contract_mismatch"
            )
        registration.validate_registration()
        key = _identity(registration.suite)
        if key in self._registrations:
            raise HarnessEvalRunnerError("harness_eval_suite_registration_duplicate")
        self._registrations[key] = registration

    def require(self, suite: HarnessContractRef) -> HarnessEvalSuiteRegistration:
        registration = self._registrations.get(_identity(suite))
        if registration is None:
            raise HarnessEvalRunnerError("harness_eval_suite_unregistered")
        return registration

    def registered_suites(self) -> tuple[HarnessContractRef, ...]:
        return tuple(self._registrations[key].suite for key in sorted(self._registrations))


class HarnessEvalGrader(Protocol):
    contract: HarnessContractRef
    implementation_contract: HarnessContractRef
    configuration_digest: str
    kind: str

    def grade(
        self,
        *,
        case: HarnessEvalCaseV1,
        candidate: HarnessEvalCandidateResult,
        payload: object,
        candidate_evidence: Mapping[str, str | int | float | bool | None] | None,
        run: HarnessEvalRunV1,
    ) -> object: ...


@dataclass(frozen=True)
class HarnessEvalModelGraderCalibration:
    """Immutable evidence for one held-out, human-reviewed calibration run."""

    suite: HarnessContractRef
    case_set_digest: str
    report_digest: str
    human_review_contract: HarnessContractRef
    attestation_digest: str
    sample_count: int
    agreement_rate: float
    false_positive_rate: float
    false_negative_rate: float

    def validate(self) -> None:
        contracts = (self.suite, self.human_review_contract)
        if any(not item.name or not item.version for item in contracts):
            raise HarnessEvalRunnerError("harness_eval_model_grader_calibration_contract_invalid")
        for digest in (
            self.case_set_digest,
            self.report_digest,
            self.attestation_digest,
        ):
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise HarnessEvalRunnerError("harness_eval_model_grader_calibration_digest_invalid")
        if self.sample_count < 1:
            raise HarnessEvalRunnerError("harness_eval_model_grader_calibration_empty")
        if any(
            not 0 <= value <= 1
            for value in (
                self.agreement_rate,
                self.false_positive_rate,
                self.false_negative_rate,
            )
        ):
            raise HarnessEvalRunnerError("harness_eval_model_grader_calibration_invalid")


@dataclass(frozen=True)
class HarnessEvalModelGraderSpec:
    """The complete contract binding required before any model grader runs."""

    contract: HarnessContractRef
    model_contract: HarnessContractRef
    configuration_contract: HarnessContractRef
    prompt_contract: HarnessContractRef
    rubric_contract: HarnessContractRef
    output_contract: HarnessContractRef
    failure_policy_contract: HarnessContractRef
    configuration_digest: str
    subjective_rubric: bool
    calibration: HarnessEvalModelGraderCalibration | None = None

    @property
    def gate_eligible(self) -> bool:
        return self.calibration is not None

    def validate(self) -> None:
        values = (
            self.contract,
            self.model_contract,
            self.configuration_contract,
            self.prompt_contract,
            self.rubric_contract,
            self.output_contract,
            self.failure_policy_contract,
        )
        if any(not item.name or not item.version for item in values):
            raise HarnessEvalRunnerError("harness_eval_model_grader_contract_invalid")
        if re.fullmatch(r"[0-9a-f]{64}", self.configuration_digest) is None:
            raise HarnessEvalRunnerError("harness_eval_model_grader_configuration_digest_invalid")
        if not self.subjective_rubric:
            raise HarnessEvalRunnerError("harness_eval_model_grader_subjective_rubric_required")
        if self.calibration is not None:
            self.calibration.validate()


class HarnessEvalGraderRegistry:
    """Registry that prefers deterministic graders and never accepts self-grading."""

    def __init__(self, contract: HarnessContractRef) -> None:
        self.contract = contract
        self._graders: dict[tuple[str, str], HarnessEvalGrader] = {}
        self._model_specs: dict[tuple[str, str], HarnessEvalModelGraderSpec] = {}

    def register(
        self,
        grader: HarnessEvalGrader,
        *,
        model_spec: HarnessEvalModelGraderSpec | None = None,
    ) -> None:
        identity = _identity(grader.contract)
        if identity in self._graders:
            raise HarnessEvalRunnerError("harness_eval_grader_duplicate")
        if grader.kind not in {"deterministic", "model", "human"}:
            raise HarnessEvalRunnerError("harness_eval_grader_kind_invalid")
        if not grader.implementation_contract.name or not grader.implementation_contract.version:
            raise HarnessEvalRunnerError("harness_eval_grader_implementation_contract_invalid")
        if re.fullmatch(r"[0-9a-f]{64}", grader.configuration_digest) is None:
            raise HarnessEvalRunnerError("harness_eval_grader_configuration_digest_invalid")
        if grader.kind == "model":
            if model_spec is None or model_spec.contract != grader.contract:
                raise HarnessEvalRunnerError("harness_eval_model_grader_binding_missing")
            model_spec.validate()
            if model_spec.configuration_digest != grader.configuration_digest:
                raise HarnessEvalRunnerError("harness_eval_model_grader_configuration_mismatch")
            self._model_specs[identity] = model_spec
        elif model_spec is not None:
            raise HarnessEvalRunnerError("harness_eval_non_model_grader_binding_forbidden")
        self._graders[identity] = grader

    def require(
        self,
        contract: HarnessContractRef,
        *,
        release_gate: bool = False,
        deterministic_gate: bool = False,
        suite: HarnessContractRef | None = None,
        candidate_model_contract: HarnessContractRef | None = None,
        candidate_adapter_contract: HarnessContractRef | None = None,
    ) -> HarnessEvalGrader:
        grader = self._graders.get(_identity(contract))
        if grader is None:
            raise HarnessEvalRunnerError("harness_eval_grader_unregistered")
        if deterministic_gate and grader.kind != "deterministic":
            raise HarnessEvalRunnerError("harness_eval_nondeterministic_grader_forbidden")
        if release_gate and grader.kind == "model" and not self._model_specs[_identity(contract)].gate_eligible:
            raise HarnessEvalRunnerError("harness_eval_model_grader_not_calibrated")
        if release_gate and grader.kind == "model":
            calibration = self._model_specs[_identity(contract)].calibration
            if suite is None or calibration is None or calibration.suite != suite:
                raise HarnessEvalRunnerError("harness_eval_model_grader_calibration_suite_mismatch")
        if candidate_adapter_contract == grader.implementation_contract:
            raise HarnessEvalRunnerError("harness_eval_candidate_self_grading_forbidden")
        if grader.kind == "model" and (
            candidate_model_contract
            == self._model_specs[_identity(contract)].model_contract
        ):
            raise HarnessEvalRunnerError("harness_eval_candidate_self_grading_forbidden")
        return grader

    def known_contracts(self) -> tuple[HarnessContractRef, ...]:
        return tuple(self._graders[key].contract for key in sorted(self._graders))


@dataclass(frozen=True)
class HarnessEvalExecution:
    raw_samples: tuple[HarnessEvalSampleV1, ...]
    report: HarnessEvalReportV1

    def raw_samples_json(self) -> dict[str, object]:
        payload = [sample.model_dump(mode="json", exclude_none=False) for sample in self.raw_samples]
        return {
            "schema_name": "HarnessEvalRawSamples",
            "schema_version": HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION,
            "samples": payload,
        }

    def aggregate_json(self) -> dict[str, object]:
        return self.report.model_dump(mode="json", exclude_none=False)


class HarnessEvalRunner:
    def __init__(
        self,
        *,
        suite_registry: HarnessEvalSuiteRegistry,
        adapters: Iterable[HarnessEvalRouteAdapter],
        graders: HarnessEvalGraderRegistry,
        operation_resolver: HarnessEvalOperationResolver,
        protected_resolver: HarnessEvalProtectedResolver | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._suite_registry = suite_registry
        self._adapters: dict[tuple[str, str], HarnessEvalRouteAdapter] = {}
        for adapter in adapters:
            registration = suite_registry.require(adapter.suite)
            if adapter.eval_route != registration.eval_route:
                raise HarnessEvalRunnerError("harness_eval_route_manifest_mismatch")
            key = (_identity(adapter.suite), adapter.eval_route)
            if key in self._adapters:
                raise HarnessEvalRunnerError("harness_eval_route_adapter_duplicate")
            self._adapters[key] = adapter
        for suite in suite_registry.registered_suites():
            registration = suite_registry.require(suite)
            if (_identity(suite), registration.eval_route) not in self._adapters:
                raise HarnessEvalRunnerError("eval_route_unregistered")
        self._graders = graders
        self._operation_resolver = operation_resolver
        self._protected_resolver = protected_resolver
        self._clock = clock or (lambda: datetime.now(UTC))

    def registered_suites(self) -> tuple[HarnessContractRef, ...]:
        return self._suite_registry.registered_suites()

    def run(
        self,
        run: HarnessEvalRunV1,
        cases: Iterable[HarnessEvalCaseV1],
        *,
        selected_suites: Iterable[HarnessContractRef] | None = None,
        release_gate: bool = False,
        deterministic_gate: bool = False,
        live_provider_approved: bool = False,
    ) -> HarnessEvalExecution:
        if run.grader_registry_contract != self._graders.contract:
            raise HarnessEvalRunnerError("harness_eval_grader_registry_unregistered")
        if run.environment.provider_mode == "live" and not live_provider_approved:
            raise HarnessEvalRunnerError(
                "harness_eval_live_provider_explicit_approval_required"
            )
        if deterministic_gate and (
            run.execution_mode not in {"fixture", "synthetic"}
            or run.environment.provider_mode != "mock"
        ):
            raise HarnessEvalRunnerError("harness_eval_release_gate_not_deterministic")
        all_cases = tuple(cases)
        selected = {_identity(item) for item in (selected_suites or (run.suite,))}
        if selected != {_identity(run.suite)}:
            raise HarnessEvalRunnerError("harness_eval_selected_suite_mismatch")
        if any(_identity(case.suite) not in selected for case in all_cases):
            raise HarnessEvalRunnerError("harness_eval_suite_unregistered")
        selected_cases = sorted(
            (case for case in all_cases if case.split in run.splits),
            key=lambda case: (_identity(case.suite), case.case_id, case.case_version),
        )
        if not selected_cases:
            raise HarnessEvalRunnerError("harness_eval_selected_suite_empty")
        expected_case_digest = _digest(
            [case.model_dump(mode="json", exclude_none=False) for case in selected_cases]
        )
        if run.case_set_digest != expected_case_digest:
            raise HarnessEvalRunnerError("harness_eval_case_set_digest_mismatch")
        if run.suite_manifest_digest != _digest(
            {"suite": run.suite.model_dump(mode="json"), "cases": [case.case_digest for case in selected_cases]}
        ):
            raise HarnessEvalRunnerError("harness_eval_suite_manifest_digest_mismatch")
        samples: list[HarnessEvalSampleV1] = []
        unadmitted_failures: Counter[str] = Counter()
        seen_operation_ids: set[str] = set()
        expected_sample_count = len(selected_cases) * len(run.seeds)
        started_at = _utc(self._clock())
        sample_index = 1
        for case in selected_cases:
            registration = self._suite_registry.require(case.suite)
            adapter = self._adapters.get((_identity(case.suite), case.eval_route))
            if adapter is None:
                raise HarnessEvalRunnerError("eval_route_unregistered")
            registration.validate_case_and_run(case, run)
            for repetition_index, seed in enumerate(run.seeds, start=1):
                operation_binding, admission_failure = self._admit_operation(
                    run=run,
                    case=case,
                    adapter=adapter,
                    registration=registration,
                    repetition_index=repetition_index,
                    seed=seed,
                )
                if admission_failure is not None:
                    unadmitted_failures[admission_failure] += 1
                    continue
                assert operation_binding is not None
                if operation_binding.harness_operation_id in seen_operation_ids:
                    unadmitted_failures["runner_configuration_invalid"] += 1
                    continue
                seen_operation_ids.add(operation_binding.harness_operation_id)
                samples.append(
                    self._run_sample(
                        run=run,
                        case=case,
                        adapter=adapter,
                        registration=registration,
                        operation_binding=operation_binding,
                        sample_index=sample_index,
                        repetition_index=repetition_index,
                        seed=seed,
                        release_gate=release_gate,
                        deterministic_gate=deterministic_gate,
                    )
                )
                sample_index += 1
        completed_at = _utc(self._clock())
        report = self._build_report(
            run,
            samples,
            started_at,
            completed_at,
            expected_sample_count=expected_sample_count,
            extra_failure_counts=unadmitted_failures,
        )
        return HarnessEvalExecution(raw_samples=tuple(samples), report=report)

    def _admit_operation(
        self,
        *,
        run: HarnessEvalRunV1,
        case: HarnessEvalCaseV1,
        adapter: HarnessEvalRouteAdapter,
        registration: HarnessEvalSuiteRegistration,
        repetition_index: int,
        seed: int,
    ) -> tuple[HarnessOperationBindingV1 | None, str | None]:
        try:
            binding = adapter.operation_admitter(
                case=case,
                run=run,
                repetition_index=repetition_index,
                seed=seed,
            )
        except Exception:
            return None, "runner_execution_failed"
        if not isinstance(binding, HarnessOperationBindingV1):
            return None, "runner_configuration_invalid"
        if (
            binding.workflow != registration.workflow
        ):
            return None, "runner_configuration_invalid"
        try:
            entry = HARNESS_WORKFLOW_MANIFEST_ENTRIES.get(
                f"{registration.workflow.value}:{registration.stage.value}"
            )
            if entry is None or not isinstance(
                entry.eval_suites,
                HarnessManifestRegisteredContractListSlotV1,
            ):
                return None, "runner_configuration_invalid"
            authoritative = self._operation_resolver.resolve_harness_id(
                harness_operation_id=binding.harness_operation_id
            )
        except Exception:
            return None, "runner_execution_failed"
        if authoritative != binding:
            return None, "runner_configuration_invalid"
        return binding, None

    def _payload(
        self,
        case: HarnessEvalCaseV1,
        adapter: HarnessEvalRouteAdapter,
        operation_binding: HarnessOperationBindingV1,
        seed: int,
    ) -> tuple[object, str]:
        source = case.source
        if source.source_mode == "fixture":
            if adapter.fixture_resolver is None:
                raise HarnessEvalRunnerError("case_source_unresolved")
            resolved = adapter.fixture_resolver(case)
            if (
                not isinstance(resolved, HarnessEvalFixturePayload)
                or resolved.payload_digest != source.payload_digest
                or _digest(resolved.payload) != resolved.payload_digest
            ):
                raise HarnessEvalRunnerError("case_source_unresolved")
            return resolved.payload, resolved.payload_digest
        if source.source_mode == "synthetic":
            if adapter.synthetic_resolver is None:
                raise HarnessEvalRunnerError("case_source_unresolved")
            # The case owns the deterministic data-generation seed.  The run
            # seed remains available to the candidate for repeated sampling;
            # conflating the two would silently change the case data between
            # repetitions.
            resolved = adapter.synthetic_resolver(case, source.seed)
            if (
                not isinstance(resolved, HarnessEvalSyntheticPayload)
                or resolved.manifest_digest != source.manifest_digest
                or resolved.seed != source.seed
                or _digest(resolved.payload) != resolved.payload_digest
            ):
                raise HarnessEvalRunnerError("case_source_unresolved")
            return resolved.payload, resolved.payload_digest
        if self._protected_resolver is None:
            raise HarnessEvalRunnerError("protected_artifact_forbidden")
        resolved = self._protected_resolver.resolve(case, operation_binding)
        if not isinstance(resolved, HarnessEvalProtectedPayload):
            raise HarnessEvalRunnerError("case_source_unresolved")
        resolved.validate_for(case, operation_binding)
        return resolved.payload, resolved.payload_digest

    def _run_sample(
        self,
        *,
        run: HarnessEvalRunV1,
        case: HarnessEvalCaseV1,
        adapter: HarnessEvalRouteAdapter,
        registration: HarnessEvalSuiteRegistration,
        operation_binding: HarnessOperationBindingV1,
        sample_index: int,
        repetition_index: int,
        seed: int,
        release_gate: bool,
        deterministic_gate: bool,
    ) -> HarnessEvalSampleV1:
        started_at = _utc(self._clock())
        try:
            if (
                (run.execution_mode == "fixture" and case.source.source_mode != "fixture")
                or (run.execution_mode == "synthetic" and case.source.source_mode != "synthetic")
                or (run.execution_mode == "protected_replay" and case.source.source_mode != "protected_artifact")
            ):
                raise HarnessEvalRunnerError("harness_eval_execution_source_mode_mismatch")
            payload, source_evidence_digest = self._payload(
                case,
                adapter,
                operation_binding,
                seed,
            )
        except HarnessEvalRunnerError as error:
            failure_code = str(error)
            if failure_code not in HARNESS_EVAL_FAILURE_TAXONOMY:
                failure_code = "runner_configuration_invalid"
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                failure_code,
                started_at,
            )
        except Exception:
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                "runner_execution_failed",
                started_at,
            )
        try:
            candidate = adapter.execute(
                case=case,
                payload=payload,
                operation_binding=operation_binding,
                run=run,
                repetition_index=repetition_index,
                seed=seed,
            )
            if not isinstance(candidate, HarnessEvalCandidateResult):
                raise HarnessEvalRunnerError("harness_eval_candidate_result_invalid")
            candidate.validate()
            if (
                candidate.trace_contract is not None
                and candidate.trace_contract != run.tested_system.harness_contract
            ):
                raise HarnessEvalRunnerError(
                    "harness_eval_candidate_trace_contract_mismatch"
                )
        except Exception:  # Adapter exceptions are infrastructure failures, never candidate evidence.
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                "runner_execution_failed",
                started_at,
            )
        try:
            results = []
            for contract in case.grader_refs:
                grader = self._graders.require(
                    contract,
                    release_gate=release_gate,
                    deterministic_gate=deterministic_gate,
                    suite=case.suite,
                    candidate_model_contract=run.tested_system.provider_model_contract,
                    candidate_adapter_contract=run.tested_system.provider_adapter_contract,
                )
                result = grader.grade(
                    case=case,
                    candidate=candidate,
                    payload=payload,
                    candidate_evidence=candidate.grader_evidence,
                    run=run,
                )
                if (
                    not isinstance(result, HarnessEvalGraderResultV1)
                    or result.grader != contract
                    or result.grader_kind != grader.kind
                    or result.grader_config_digest != grader.configuration_digest
                ):
                    raise HarnessEvalRunnerError("grader_output_invalid")
                results.append(result)
        except HarnessEvalRunnerError as error:
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                "grader_output_invalid"
                if str(error) == "grader_output_invalid"
                else "grader_execution_failed",
                started_at,
                candidate=candidate,
                grader_results=results,
            )
        except Exception:
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                "grader_execution_failed",
                started_at,
                candidate=candidate,
                grader_results=results,
            )
        if any(item.execution_status != "completed" for item in results):
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                "grader_execution_failed",
                started_at,
                candidate=candidate,
                grader_results=results,
            )
        completed_at = _utc(self._clock())
        failures = tuple(sorted(candidate.failures, key=lambda item: item.failure_code))
        failed_verdict = any(item.verdict == "failed" for item in results)
        if candidate.candidate_outcome == "skipped" and release_gate:
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                "runner_configuration_invalid",
                started_at,
                candidate=candidate,
            )
        if candidate.candidate_outcome == "skipped":
            status = "skipped"
        elif candidate.candidate_outcome in {"failed", "unavailable"} and not failed_verdict:
            # A candidate cannot declare itself failed and then let a passing grader
            # promote that failure into success.
            return self._broken_sample(
                run,
                case,
                operation_binding,
                sample_index,
                repetition_index,
                seed,
                "runner_configuration_invalid",
                started_at,
                candidate=candidate,
            )
        else:
            status = "failed" if failed_verdict else "passed"
        payload_evidence = {
            "case_digest": case.case_digest,
            "operation": operation_binding.harness_operation_id,
            "source_evidence": source_evidence_digest,
            "candidate_evidence": candidate.evidence_digest,
            "grader_evidence": [item.evidence_digest for item in results],
        }
        sample = HarnessEvalSampleV1.model_construct(
            sample_id=expected_harness_eval_sample_id(run_id=run.run_id, harness_operation_id=operation_binding.harness_operation_id, case_ref=case.to_ref(), repetition_index=repetition_index, seed=seed),
            run_id=run.run_id,
            harness_operation_id=operation_binding.harness_operation_id,
            sample_index=sample_index,
            case_ref=case.to_ref(),
            repetition_index=repetition_index,
            seed=seed,
            status=status,
            candidate_outcome=candidate.candidate_outcome,
            raw_schema_valid=candidate.raw_schema_valid,
            final_schema_valid=candidate.final_schema_valid,
            trace_contract=candidate.trace_contract,
            trace_digest=candidate.trace_digest,
            metrics=sorted(candidate.metrics, key=lambda item: (item.metric.name, item.metric.version)),
            grader_results=sorted(results, key=lambda item: (item.grader.name, item.grader.version)),
            failures=list(failures),
            evidence_digest=_digest(payload_evidence),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=candidate.duration_ms,
            sample_digest="0" * 64,
        )
        sample_payload = sample.model_dump(mode="json", exclude_none=False)
        sample_payload["sample_digest"] = canonical_harness_eval_sample_digest(sample_payload)
        return HarnessEvalSampleV1.model_validate(sample_payload)

    def _broken_sample(
        self,
        run: HarnessEvalRunV1,
        case: HarnessEvalCaseV1,
        operation_binding: HarnessOperationBindingV1,
        sample_index: int,
        repetition_index: int,
        seed: int,
        failure_code: str,
        started_at: str,
        *,
        candidate: HarnessEvalCandidateResult | None = None,
        grader_results: Iterable[HarnessEvalGraderResultV1] = (),
    ) -> HarnessEvalSampleV1:
        entry = HARNESS_EVAL_FAILURE_TAXONOMY[failure_code]
        failure = HarnessEvalFailureV1(failure_code=failure_code, owner=entry.owner, reason_code=failure_code, evidence_digest=None)
        operation_id = operation_binding.harness_operation_id
        completed_at = _utc(self._clock())
        sample = HarnessEvalSampleV1.model_construct(
            sample_id=expected_harness_eval_sample_id(run_id=run.run_id, harness_operation_id=operation_id, case_ref=case.to_ref(), repetition_index=repetition_index, seed=seed),
            run_id=run.run_id, harness_operation_id=operation_id, sample_index=sample_index,
            case_ref=case.to_ref(), repetition_index=repetition_index, seed=seed,
            status="broken", candidate_outcome=(candidate.candidate_outcome if candidate else "unavailable"),
            raw_schema_valid=(candidate.raw_schema_valid if candidate else None),
            final_schema_valid=(candidate.final_schema_valid if candidate else None),
            trace_contract=(candidate.trace_contract if candidate else None), trace_digest=(candidate.trace_digest if candidate else None),
            metrics=(sorted(candidate.metrics, key=lambda item: (item.metric.name, item.metric.version)) if candidate else []),
            grader_results=sorted(
                grader_results,
                key=lambda item: (item.grader.name, item.grader.version),
            ),
            failures=[failure], evidence_digest=_digest({"case": case.case_digest, "operation": operation_id, "failure": failure_code}),
            started_at=started_at, completed_at=completed_at, duration_ms=(candidate.duration_ms if candidate else 0), sample_digest="0" * 64,
        )
        sample_payload = sample.model_dump(mode="json", exclude_none=False)
        sample_payload["sample_digest"] = canonical_harness_eval_sample_digest(sample_payload)
        return HarnessEvalSampleV1.model_validate(sample_payload)

    def _build_report(
        self,
        run: HarnessEvalRunV1,
        samples: list[HarnessEvalSampleV1],
        started_at: str,
        completed_at: str,
        *,
        expected_sample_count: int,
        extra_failure_counts: Mapping[str, int],
    ) -> HarnessEvalReportV1:
        counts = Counter(sample.status for sample in samples)
        failure_counts = Counter(failure.failure_code for sample in samples for failure in sample.failures)
        failure_counts.update(extra_failure_counts)
        evaluable = [sample for sample in samples if sample.status in {"passed", "failed"}]
        aggregate_metrics: list[HarnessEvalMetricAggregateV1] = []
        if evaluable:
            raw_valid = sum(sample.raw_schema_valid is True for sample in evaluable)
            final_valid = sum(sample.final_schema_valid is True for sample in evaluable)
            candidate_passed = sum(sample.candidate_outcome in {"passed", "repaired"} for sample in evaluable)
            repaired = sum(sample.candidate_outcome == "repaired" for sample in evaluable)
            failed = sum(sample.status == "failed" for sample in evaluable)
            for metric, numerator in (
                (CANDIDATE_PASS_RATE, candidate_passed),
                (FAILURE_RATE, failed),
                (FINAL_SCHEMA_VALID_RATE, final_valid),
                (RAW_SCHEMA_VALID_RATE, raw_valid),
                (REPAIR_RATE, repaired),
            ):
                aggregate_metrics.append(HarnessEvalMetricAggregateV1(metric=metric, aggregation="rate", unit="ratio", value=numerator / len(evaluable), population_count=len(evaluable), excluded_count=expected_sample_count - len(evaluable), numerator=numerator, denominator=len(evaluable), percentile_method=None))
            durations = sorted(sample.duration_ms for sample in evaluable)
            for metric, percentile in (
                (DURATION_P50_MS, 0.50),
                (DURATION_P95_MS, 0.95),
            ):
                aggregate_metrics.append(
                    HarnessEvalMetricAggregateV1(
                        metric=metric,
                        aggregation="p50" if percentile == 0.50 else "p95",
                        unit="milliseconds",
                        value=_nearest_rank(durations, percentile),
                        population_count=len(durations),
                        excluded_count=expected_sample_count - len(durations),
                        numerator=None,
                        denominator=None,
                        percentile_method="nearest_rank",
                    )
                )
            aggregate_metrics.extend(
                _aggregate_observed_metrics(
                    samples=evaluable,
                    expected_sample_count=expected_sample_count,
                )
            )
        raw_payload = {"schema_name": "HarnessEvalRawSamples", "schema_version": HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION, "samples": [sample.model_dump(mode="json", exclude_none=False) for sample in samples]}
        raw_digest = _digest(raw_payload)
        raw = (
            HarnessEvalRawSamplesArtifactRefV1(artifact_id=f"harness-eval-raw-samples-{raw_digest[:32]}", artifact_contract=RAW_SAMPLES_CONTRACT, payload_digest=raw_digest, sample_count=len(samples))
            if samples
            else None
        )
        report = HarnessEvalReportV1.model_construct(
            report_id=expected_harness_eval_report_id(run.run_id), run_id=run.run_id, run_digest=run.run_digest,
            tested_system_config_digest=run.tested_system_config_digest,
            status=(
                "broken"
                if counts["broken"] or len(samples) != expected_sample_count
                else "failed"
                if counts["failed"]
                else "passed"
            ),
            expected_sample_count=expected_sample_count, sample_count=len(samples), passed_count=counts["passed"], failed_count=counts["failed"], broken_count=counts["broken"], skipped_count=counts["skipped"],
            sample_refs=[HarnessEvalSampleRefV1(sample_id=sample.sample_id, sample_index=sample.sample_index, case_ref=sample.case_ref, sample_digest=sample.sample_digest) for sample in samples],
            raw_samples_artifact=raw,
            aggregate_metrics=sorted(aggregate_metrics, key=lambda item: (item.metric.name, item.metric.version)),
            failure_counts=[HarnessEvalFailureCountV1(failure_code=key, count=value) for key, value in sorted(failure_counts.items())],
            started_at=started_at, completed_at=completed_at, report_digest="0" * 64,
        )
        report_payload = report.model_dump(mode="json", exclude_none=False)
        report_payload["report_digest"] = canonical_harness_eval_report_digest(report_payload)
        return HarnessEvalReportV1.model_validate(report_payload)


def _nearest_rank(values: list[int | float], percentile: float) -> int | float:
    if not values:
        raise ValueError("harness_eval_percentile_population_empty")
    index = max(0, min(len(values) - 1, int(percentile * len(values) + 0.999999) - 1))
    return values[index]


def _aggregate_observed_metrics(
    *,
    samples: list[HarnessEvalSampleV1],
    expected_sample_count: int,
) -> list[HarnessEvalMetricAggregateV1]:
    observations: dict[
        tuple[str, str],
        list[HarnessEvalMetricObservationV1],
    ] = {}
    for sample in samples:
        for observation in sample.metrics:
            observations.setdefault(_identity(observation.metric), []).append(observation)
        for grader in sample.grader_results:
            for observation in grader.metrics:
                observations.setdefault(_identity(observation.metric), []).append(
                    observation
                )

    aggregates: list[HarnessEvalMetricAggregateV1] = []
    for identity in sorted(observations):
        values = observations[identity]
        value_types = {item.value_type for item in values}
        units = {item.unit for item in values}
        if len(value_types) != 1 or len(units) != 1:
            raise HarnessEvalRunnerError("harness_eval_metric_contract_shape_drift")
        contract = values[0].metric
        excluded = expected_sample_count - len(values)
        if isinstance(values[0], HarnessEvalBooleanMetricV1):
            numerator = sum(item.value is True for item in values)
            aggregates.append(
                HarnessEvalMetricAggregateV1(
                    metric=contract,
                    aggregation="rate",
                    unit="ratio",
                    value=numerator / len(values),
                    population_count=len(values),
                    excluded_count=excluded,
                    numerator=numerator,
                    denominator=len(values),
                    percentile_method=None,
                )
            )
        elif isinstance(values[0], HarnessEvalNumberMetricV1):
            aggregates.append(
                HarnessEvalMetricAggregateV1(
                    metric=contract,
                    aggregation="mean",
                    unit=values[0].unit,
                    value=sum(float(item.value) for item in values) / len(values),
                    population_count=len(values),
                    excluded_count=excluded,
                    numerator=None,
                    denominator=None,
                    percentile_method=None,
                )
            )
        elif isinstance(values[0], HarnessEvalIntegerMetricV1):
            numeric = sorted(item.value for item in values)
            aggregates.append(
                HarnessEvalMetricAggregateV1(
                    metric=contract,
                    aggregation="mean",
                    unit=values[0].unit,
                    value=sum(numeric) / len(numeric),
                    population_count=len(numeric),
                    excluded_count=excluded,
                    numerator=None,
                    denominator=None,
                    percentile_method=None,
                )
            )
            if values[0].unit == "milliseconds":
                for aggregation, percentile in (("p50", 0.50), ("p95", 0.95)):
                    aggregates.append(
                        HarnessEvalMetricAggregateV1(
                            metric=HarnessContractRef(
                                name=f"{contract.name}_{aggregation}",
                                version=(
                                    f"{contract.version.rsplit('-v', 1)[0]}-"
                                    f"{aggregation}-v1"
                                ),
                            ),
                            aggregation=aggregation,
                            unit=values[0].unit,
                            value=_nearest_rank(numeric, percentile),
                            population_count=len(numeric),
                            excluded_count=excluded,
                            numerator=None,
                            denominator=None,
                            percentile_method="nearest_rank",
                        )
                    )
    return aggregates


def _load_factory(value: str) -> HarnessEvalRunner:
    module_name, separator, name = value.partition(":")
    if not separator or not module_name or not name:
        raise HarnessEvalRunnerError("harness_eval_cli_registry_factory_invalid")
    factory = getattr(importlib.import_module(module_name), name)
    runner = factory()
    if not isinstance(runner, HarnessEvalRunner):
        raise HarnessEvalRunnerError("harness_eval_cli_registry_factory_invalid")
    return runner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run explicitly registered Harness evaluation suites.")
    parser.add_argument("--registry", help="module:function returning a HarnessEvalRunner")
    parser.add_argument("--list-suites", action="store_true")
    parser.add_argument("--suite", action="append", default=[])
    parser.add_argument("--input", type=Path, help="JSON object containing run and cases")
    parser.add_argument("--output-dir", type=Path, help="directory for raw-samples.json and aggregate.json")
    parser.add_argument("--profile", choices=("pr", "manual", "nightly"), default="pr")
    parser.add_argument("--live-provider", action="store_true", help="required for manual/nightly live-provider suites")
    args = parser.parse_args(argv)
    if not args.registry:
        parser.error("--registry is required; the shared core ships no implicit suites")
    runner = _load_factory(args.registry)
    suites = runner.registered_suites()
    if args.list_suites:
        print(json.dumps([item.model_dump(mode="json") for item in suites], sort_keys=True))
        return 0
    if not args.suite:
        parser.error("select at least one suite with --suite")
    requested = set(args.suite)
    available = {f"{item.name}@{item.version}" for item in suites}
    if not requested <= available:
        raise HarnessEvalRunnerError("harness_eval_selected_suite_unregistered")
    if args.input is None or args.output_dir is None:
        parser.error("--input and --output-dir are required for execution")
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping) or set(payload) != {"run", "cases"}:
        raise HarnessEvalRunnerError("harness_eval_cli_input_invalid")
    run = HarnessEvalRunV1.model_validate(payload["run"])
    cases_payload = payload["cases"]
    if not isinstance(cases_payload, list):
        raise HarnessEvalRunnerError("harness_eval_cli_cases_invalid")
    cases = [HarnessEvalCaseV1.model_validate(item) for item in cases_payload]
    if run.environment.provider_mode == "live" and (
        not args.live_provider or args.profile not in {"manual", "nightly"}
    ):
        raise HarnessEvalRunnerError("harness_eval_live_provider_explicit_approval_required")
    selected_contracts = []
    for value in args.suite:
        name, separator, version = value.partition("@")
        if not separator:
            raise HarnessEvalRunnerError("harness_eval_cli_suite_identifier_invalid")
        selected_contracts.append(HarnessContractRef(name=name, version=version))
    result = runner.run(
        run,
        cases,
        selected_suites=selected_contracts,
        release_gate=args.profile == "pr",
        deterministic_gate=args.profile == "pr",
        live_provider_approved=(
            args.live_provider and args.profile in {"manual", "nightly"}
        ),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "raw-samples.json").write_text(
        json.dumps(result.raw_samples_json(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "aggregate.json").write_text(
        json.dumps(result.aggregate_json(), sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    return 0 if result.report.status == "passed" else 1


if __name__ == "__main__":  # pragma: no cover - exercised through the module entry point.
    raise SystemExit(main())
