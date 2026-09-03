from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.models.harness import (
    HarnessContractRef,
    HarnessStage,
    HarnessWorkflow,
    canonical_harness_digest,
)
from app.models.harness_eval import (
    HarnessEvalCaseV1,
    HarnessEvalFailureV1,
    HarnessEvalGraderResultV1,
    HarnessEvalRunV1,
    canonical_harness_eval_case_digest,
    canonical_harness_eval_environment_digest,
    canonical_harness_eval_run_digest,
)
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.persistence.database import Database
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.models import HarnessOperationBindingRow
from app.services.harness_eval_runner import (
    HarnessEvalCandidateResult,
    HarnessEvalFixturePayload,
    HarnessEvalGraderRegistry,
    HarnessEvalModelGraderSpec,
    HarnessEvalProtectedPayload,
    HarnessEvalRouteAdapter,
    HarnessEvalRunner,
    HarnessEvalRunnerError,
    HarnessEvalSuiteRegistration,
    HarnessEvalSuiteRegistry,
    HarnessEvalSyntheticPayload,
)


FIXTURE_ROOT = Path(__file__).parents[3] / "packages" / "shared" / "fixtures" / "harness"
FIXTURE_PAYLOAD = {"fixture": "deterministic"}
SUITE_REGISTRY_CONTRACT = HarnessContractRef(
    name="HarnessEvalFixtureSuiteRegistry",
    version="harness-eval-fixture-suite-registry-v1",
)


def _golden() -> dict[str, object]:
    return json.loads(
        (FIXTURE_ROOT / "eval-contract-golden-v1.json").read_text(encoding="utf-8")
    )


def _fixed_clock() -> datetime:
    return datetime(2026, 8, 31, tzinfo=UTC)


class _PassGrader:
    contract = HarnessContractRef(
        name="tavern_identity_grader",
        version="tavern-identity-grader-v1",
    )
    implementation_contract = HarnessContractRef(
        name="tavern_identity_grader_impl",
        version="tavern-identity-grader-impl-v1",
    )
    configuration_digest = "a" * 64
    kind = "deterministic"

    def grade(self, **_: object) -> HarnessEvalGraderResultV1:
        return HarnessEvalGraderResultV1(
            grader_result_id="grader-result-pass-001",
            grader=self.contract,
            grader_kind="deterministic",
            grader_config_digest=self.configuration_digest,
            execution_status="completed",
            verdict="passed",
            score=1.0,
            metrics=[],
            failure_codes=[],
            evidence_digest="b" * 64,
            duration_ms=0,
        )


class _FailGrader(_PassGrader):
    def grade(self, **_: object) -> HarnessEvalGraderResultV1:
        return HarnessEvalGraderResultV1(
            grader_result_id="grader-result-fail-001",
            grader=self.contract,
            grader_kind="deterministic",
            grader_config_digest=self.configuration_digest,
            execution_status="completed",
            verdict="failed",
            score=0.0,
            metrics=[],
            failure_codes=[],
            evidence_digest="8" * 64,
            duration_ms=0,
        )


class _ErrorGrader(_PassGrader):
    def grade(self, **_: object) -> HarnessEvalGraderResultV1:
        raise RuntimeError("grader unavailable")


class _DurableOperationAuthority:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.repository = HarnessOperationBindingRepository(database)

    def admit(
        self,
        *,
        case: HarnessEvalCaseV1,
        run: HarnessEvalRunV1,
        repetition_index: int,
        seed: int,
    ) -> HarnessOperationBindingV1:
        identity = canonical_harness_digest(
            {
                "run": run.run_id,
                "case": case.case_digest,
                "repetition": repetition_index,
                "seed": seed,
            }
        )
        binding = HarnessOperationBindingV1(
            harness_operation_id=f"harness-operation-{identity[:32]}",
            domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
            domain_operation_id=f"eval-run-{identity[:32]}",
            workflow=HarnessWorkflow.TAVERN,
            entry_stage=HarnessStage.TAVERN_ACTOR_REPLY,
            admitted_at=_fixed_clock(),
        )
        existing = self.repository.resolve_harness_id(
            harness_operation_id=binding.harness_operation_id
        )
        if existing is not None:
            if existing != binding:
                raise RuntimeError("eval operation identity collision")
            return existing
        with self.database.session() as session:
            session.add(
                HarnessOperationBindingRow(
                    **binding.model_dump(mode="json", exclude_none=False)
                )
            )
        return binding

    def resolve_harness_id(
        self,
        *,
        harness_operation_id: str,
    ) -> HarnessOperationBindingV1 | None:
        return self.repository.resolve_harness_id(
            harness_operation_id=harness_operation_id
        )


class _ProtectedResolver:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def resolve(
        self,
        case: HarnessEvalCaseV1,
        operation_binding: HarnessOperationBindingV1,
    ) -> HarnessEvalProtectedPayload:
        source = case.source
        assert source.source_mode == "protected_artifact"
        return HarnessEvalProtectedPayload(
            harness_operation_id=operation_binding.harness_operation_id,
            artifact_type=source.artifact_type,
            artifact_id=source.artifact_id,
            artifact_contract=source.artifact_contract,
            payload_digest=source.payload_digest,
            payload=self.payload,
            authorization_digest="f" * 64,
        )


class HarnessEvalRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{self._tmp.name}/eval.sqlite3")
        self.database.create_schema()
        self.authority = _DurableOperationAuthority(self.database)

    def tearDown(self) -> None:
        self.database.dispose()
        self._tmp.cleanup()

    def _prepared(self):
        payload = _golden()
        case_payload = deepcopy(payload["case"])
        assert isinstance(case_payload, dict)
        source_payload = case_payload["source"]
        assert isinstance(source_payload, dict)
        source_payload["payload_digest"] = canonical_harness_digest(FIXTURE_PAYLOAD)
        case_payload["case_digest"] = canonical_harness_eval_case_digest(case_payload)
        case = HarnessEvalCaseV1.model_validate(case_payload)

        run_payload = deepcopy(payload["run"])
        assert isinstance(run_payload, dict)
        self._bind_run_to_cases(run_payload, [case])
        run = HarnessEvalRunV1.model_validate(run_payload)

        known_values = [
            SUITE_REGISTRY_CONTRACT,
            case.suite,
            *case.grader_refs,
            *(item.invariant for item in case.expected_invariants),
            run.runner_contract,
            run.failure_taxonomy_contract,
            run.grader_registry_contract,
            run.environment.environment_contract,
            run.tested_system.workflow_manifest_contract,
            run.tested_system.harness_contract,
            run.tested_system.provider_adapter_contract,
            run.tested_system.provider_model_contract,
            run.tested_system.input_contract,
            run.tested_system.output_contract,
            *run.tested_system.component_contracts,
            case.source.payload_contract,
        ]
        for item in (
            run.tested_system.prompt_contract,
            run.tested_system.policy_contract,
            run.tested_system.toolset_contract,
        ):
            if item is not None:
                known_values.append(item)
        known = {(item.name, item.version): item for item in known_values}
        registration = HarnessEvalSuiteRegistration(
            registration_contract=SUITE_REGISTRY_CONTRACT,
            suite=case.suite,
            workflow=HarnessWorkflow.TAVERN,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            eval_route=case.eval_route,
            runner_contract=run.runner_contract,
            grader_registry_contract=run.grader_registry_contract,
            tested_system=run.tested_system,
            known_contracts=tuple(known[key] for key in sorted(known)),
            allowed_execution_modes=("fixture", "protected_replay", "synthetic"),
        )
        executions = {"count": 0}

        def execute(**_: object) -> HarnessEvalCandidateResult:
            executions["count"] += 1
            return HarnessEvalCandidateResult(
                candidate_outcome="passed",
                raw_schema_valid=True,
                final_schema_valid=True,
                trace_contract=run.tested_system.harness_contract,
                trace_digest="c" * 64,
                evidence_digest="d" * 64,
            )

        adapter = HarnessEvalRouteAdapter(
            suite=case.suite,
            eval_route=case.eval_route,
            operation_admitter=self.authority.admit,
            fixture_resolver=lambda source_case: HarnessEvalFixturePayload(
                payload=FIXTURE_PAYLOAD,
                payload_digest=source_case.source.payload_digest,
            ),
            synthetic_resolver=None,
            execute=execute,
        )
        graders = HarnessEvalGraderRegistry(run.grader_registry_contract)
        graders.register(_PassGrader())
        return case, run, registration, adapter, graders, executions

    @staticmethod
    def _bind_run_to_cases(
        run_payload: dict[str, object],
        cases: list[HarnessEvalCaseV1],
    ) -> None:
        run_payload["case_set_digest"] = canonical_harness_digest(
            [case.model_dump(mode="json", exclude_none=False) for case in cases]
        )
        suite = cases[0].suite
        run_payload["suite_manifest_digest"] = canonical_harness_digest(
            {
                "suite": suite.model_dump(mode="json"),
                "cases": [case.case_digest for case in cases],
            }
        )
        system = run_payload["tested_system"]
        environment = run_payload["environment"]
        assert isinstance(system, dict) and isinstance(environment, dict)
        run_payload["tested_system_config_digest"] = canonical_harness_digest(
            {
                "contract": {
                    "name": "HarnessEvalSystemConfig",
                    "version": "harness-eval-system-config-v1",
                },
                "payload": system,
            }
        )
        run_payload["environment_digest"] = canonical_harness_eval_environment_digest(
            environment
        )
        run_payload["run_digest"] = canonical_harness_eval_run_digest(run_payload)

    def _runner(
        self,
        registration: HarnessEvalSuiteRegistration,
        adapter: HarnessEvalRouteAdapter,
        graders: HarnessEvalGraderRegistry,
        *,
        protected_resolver: _ProtectedResolver | None = None,
    ) -> HarnessEvalRunner:
        suites = HarnessEvalSuiteRegistry(SUITE_REGISTRY_CONTRACT)
        suites.register(registration)
        return HarnessEvalRunner(
            suite_registry=suites,
            adapters=[adapter],
            graders=graders,
            operation_resolver=self.authority,
            protected_resolver=protected_resolver,
            clock=_fixed_clock,
        )

    def test_runner_emits_stable_ordered_raw_samples_and_aggregate_report(self) -> None:
        case, run, registration, adapter, graders, _ = self._prepared()
        runner = self._runner(registration, adapter, graders)

        result = runner.run(run, [case], deterministic_gate=True)

        self.assertEqual([sample.sample_index for sample in result.raw_samples], [1])
        self.assertEqual(result.report.status, "passed")
        assert result.report.raw_samples_artifact is not None
        self.assertEqual(result.report.raw_samples_artifact.sample_count, 1)
        self.assertEqual(
            result.raw_samples_json()["samples"][0]["sample_id"],
            result.report.sample_refs[0].sample_id,
        )
        resolved = self.authority.resolve_harness_id(
            harness_operation_id=result.raw_samples[0].harness_operation_id
        )
        assert resolved is not None
        self.assertEqual(
            resolved.harness_operation_id,
            result.raw_samples[0].harness_operation_id,
        )

    def test_unknown_contract_is_rejected_before_execution(self) -> None:
        case, run, registration, adapter, graders, executions = self._prepared()
        bad_registration = replace(
            registration,
            known_contracts=tuple(
                item
                for item in registration.known_contracts
                if item != case.source.payload_contract
            ),
        )
        runner = self._runner(bad_registration, adapter, graders)

        with self.assertRaisesRegex(
            HarnessEvalRunnerError,
            "harness_eval_contract_unregistered",
        ):
            runner.run(run, [case])
        self.assertEqual(executions["count"], 0)

    def test_admission_failure_is_reported_without_fabricated_sample(self) -> None:
        case, run, registration, adapter, graders, _ = self._prepared()

        def fail_admission(**_: object) -> HarnessOperationBindingV1:
            raise RuntimeError("database unavailable")

        adapter = replace(adapter, operation_admitter=fail_admission)
        runner = self._runner(registration, adapter, graders)

        result = runner.run(run, [case])

        self.assertEqual(result.raw_samples, ())
        self.assertEqual(result.report.status, "broken")
        self.assertEqual(result.report.expected_sample_count, 1)
        self.assertEqual(result.report.sample_count, 0)
        self.assertIsNone(result.report.raw_samples_artifact)
        self.assertEqual(
            [(item.failure_code, item.count) for item in result.report.failure_counts],
            [("runner_execution_failed", 1)],
        )

    def test_unresolved_protected_case_is_broken_not_candidate_success(self) -> None:
        case, run, registration, adapter, graders, executions = self._prepared()
        protected_bytes = b"held-out protected replay"
        protected_payload = case.model_dump(mode="json", exclude_none=False)
        protected_payload.update(
            {
                "source": {
                    "source_mode": "protected_artifact",
                    "artifact_type": "tavern_transcript",
                    "artifact_id": "private-1",
                    "artifact_contract": {
                        "name": "TavernIdentityFixture",
                        "version": "tavern-identity-fixture-v1",
                    },
                    "payload_digest": hashlib.sha256(protected_bytes).hexdigest(),
                },
                "sensitivity": "protected",
            }
        )
        protected_payload["case_digest"] = canonical_harness_eval_case_digest(
            protected_payload
        )
        protected = HarnessEvalCaseV1.model_validate(protected_payload)
        known = {
            (item.name, item.version): item for item in registration.known_contracts
        }
        known[
            (
                protected.source.artifact_contract.name,
                protected.source.artifact_contract.version,
            )
        ] = protected.source.artifact_contract
        registration = replace(
            registration,
            known_contracts=tuple(known[key] for key in sorted(known)),
        )
        run_payload = run.model_dump(mode="json", exclude_none=False)
        run_payload["execution_mode"] = "protected_replay"
        environment = run_payload["environment"]
        assert isinstance(environment, dict)
        environment["provider_mode"] = "local"
        self._bind_run_to_cases(run_payload, [protected])
        protected_run = HarnessEvalRunV1.model_validate(run_payload)
        registration = replace(registration, tested_system=protected_run.tested_system)
        runner = self._runner(registration, adapter, graders)

        result = runner.run(protected_run, [protected])

        self.assertEqual(result.raw_samples[0].status, "broken")
        self.assertEqual(result.raw_samples[0].candidate_outcome, "unavailable")
        self.assertEqual(
            result.raw_samples[0].failures[0].failure_code,
            "protected_artifact_forbidden",
        )
        self.assertEqual(result.report.status, "broken")
        self.assertEqual(executions["count"], 0)

        authorized_runner = self._runner(
            registration,
            adapter,
            graders,
            protected_resolver=_ProtectedResolver(protected_bytes),
        )
        authorized = authorized_runner.run(protected_run, [protected])
        self.assertEqual(authorized.report.status, "passed")

    def test_pr_gate_rejects_non_deterministic_execution(self) -> None:
        case, run, registration, adapter, graders, _ = self._prepared()
        run_payload = run.model_dump(mode="json", exclude_none=False)
        environment = run_payload["environment"]
        assert isinstance(environment, dict)
        environment["provider_mode"] = "local"
        self._bind_run_to_cases(run_payload, [case])
        local_run = HarnessEvalRunV1.model_validate(run_payload)
        registration = replace(registration, tested_system=local_run.tested_system)
        runner = self._runner(registration, adapter, graders)

        with self.assertRaisesRegex(
            HarnessEvalRunnerError,
            "release_gate_not_deterministic",
        ):
            runner.run(local_run, [case], deterministic_gate=True)

    def test_synthetic_case_uses_case_seed_not_candidate_repetition_seed(self) -> None:
        case, run, registration, adapter, graders, _ = self._prepared()
        synthetic_payload = case.model_dump(mode="json", exclude_none=False)
        generator = HarnessContractRef(
            name="TavernSyntheticGenerator",
            version="tavern-synthetic-generator-v1",
        )
        synthetic_payload["source"] = {
            "source_mode": "synthetic",
            "generator_contract": generator.model_dump(mode="json"),
            "seed": 101,
            "manifest_digest": "7" * 64,
        }
        provenance = synthetic_payload["provenance"]
        assert isinstance(provenance, dict)
        provenance["source_kind"] = "synthetic"
        synthetic_payload["case_digest"] = canonical_harness_eval_case_digest(
            synthetic_payload
        )
        synthetic_case = HarnessEvalCaseV1.model_validate(synthetic_payload)
        run_payload = run.model_dump(mode="json", exclude_none=False)
        run_payload["execution_mode"] = "synthetic"
        self._bind_run_to_cases(run_payload, [synthetic_case])
        synthetic_run = HarnessEvalRunV1.model_validate(run_payload)
        known = {
            (item.name, item.version): item for item in registration.known_contracts
        }
        known[(generator.name, generator.version)] = generator
        registration = replace(
            registration,
            tested_system=synthetic_run.tested_system,
            known_contracts=tuple(known[key] for key in sorted(known)),
        )
        seen_seeds: list[int] = []

        def resolve_synthetic(
            source_case: HarnessEvalCaseV1,
            seed: int,
        ) -> HarnessEvalSyntheticPayload:
            seen_seeds.append(seed)
            payload = {"synthetic": source_case.case_id, "seed": seed}
            return HarnessEvalSyntheticPayload(
                payload=payload,
                payload_digest=canonical_harness_digest(payload),
                manifest_digest="7" * 64,
                seed=seed,
            )

        adapter = replace(
            adapter,
            fixture_resolver=None,
            synthetic_resolver=resolve_synthetic,
        )
        runner = self._runner(registration, adapter, graders)

        result = runner.run(synthetic_run, [synthetic_case], deterministic_gate=True)

        self.assertEqual(result.report.status, "passed")
        self.assertEqual(seen_seeds, [101])
        self.assertEqual(result.raw_samples[0].seed, synthetic_run.seeds[0])

    def test_candidate_and_grader_failures_keep_separate_owners(self) -> None:
        case, run, registration, adapter, _, _ = self._prepared()

        def fail_candidate(**_: object) -> HarnessEvalCandidateResult:
            return HarnessEvalCandidateResult(
                candidate_outcome="failed",
                raw_schema_valid=False,
                final_schema_valid=False,
                trace_contract=run.tested_system.harness_contract,
                trace_digest="5" * 64,
                failures=(
                    HarnessEvalFailureV1(
                        failure_code="candidate_validation_failed",
                        owner="candidate",
                        reason_code="candidate_validation_failed",
                        evidence_digest="6" * 64,
                    ),
                ),
                evidence_digest="4" * 64,
            )

        candidate_graders = HarnessEvalGraderRegistry(run.grader_registry_contract)
        candidate_graders.register(_FailGrader())
        candidate_runner = self._runner(
            registration,
            replace(adapter, execute=fail_candidate),
            candidate_graders,
        )
        candidate_result = candidate_runner.run(run, [case])
        self.assertEqual(candidate_result.raw_samples[0].status, "failed")
        self.assertEqual(candidate_result.raw_samples[0].failures[0].owner, "candidate")

        error_graders = HarnessEvalGraderRegistry(run.grader_registry_contract)
        error_graders.register(_ErrorGrader())
        grader_runner = self._runner(registration, adapter, error_graders)
        grader_result = grader_runner.run(run, [case])
        self.assertEqual(grader_result.raw_samples[0].status, "broken")
        self.assertEqual(
            grader_result.raw_samples[0].failures[0].failure_code,
            "grader_execution_failed",
        )
        self.assertEqual(grader_result.raw_samples[0].failures[0].owner, "grader")

    def test_model_grader_cannot_gate_without_calibration_or_self_grade(self) -> None:
        spec = HarnessEvalModelGraderSpec(
            contract=HarnessContractRef(name="subjective", version="subjective-v1"),
            model_contract=HarnessContractRef(
                name="grader_model",
                version="grader-model-v1",
            ),
            configuration_contract=HarnessContractRef(
                name="grader_config",
                version="grader-config-v1",
            ),
            prompt_contract=HarnessContractRef(
                name="grader_prompt",
                version="grader-prompt-v1",
            ),
            rubric_contract=HarnessContractRef(name="rubric", version="rubric-v1"),
            output_contract=HarnessContractRef(
                name="grader_output",
                version="grader-output-v1",
            ),
            failure_policy_contract=HarnessContractRef(
                name="grader_failure_policy",
                version="grader-failure-policy-v1",
            ),
            configuration_digest="9" * 64,
            subjective_rubric=True,
        )

        class _Model:
            contract = spec.contract
            implementation_contract = HarnessContractRef(
                name="model_grader_adapter",
                version="model-grader-adapter-v1",
            )
            configuration_digest = spec.configuration_digest
            kind = "model"

            def grade(self, **_: object) -> object:
                raise AssertionError("must not execute")

        registry = HarnessEvalGraderRegistry(
            HarnessContractRef(name="registry", version="registry-v1")
        )
        registry.register(_Model(), model_spec=spec)
        with self.assertRaisesRegex(HarnessEvalRunnerError, "not_calibrated"):
            registry.require(spec.contract, release_gate=True)
        with self.assertRaisesRegex(HarnessEvalRunnerError, "self_grading"):
            registry.require(
                spec.contract,
                candidate_model_contract=spec.model_contract,
            )


if __name__ == "__main__":
    unittest.main()
