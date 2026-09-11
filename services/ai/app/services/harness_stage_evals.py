"""Executable developer-regression suites for all ten Wave 4 stage routes.

This registry uses the shared eval runner and durable domain admission. Its
absolute regression gate is not an independently reviewed held-out baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from app.models.harness import (
    HarnessContractRef,
    HarnessWorkflow,
    canonical_harness_digest,
)
from app.models.harness_eval import (
    HARNESS_EVAL_FAILURE_TAXONOMY_CONTRACT,
    HarnessEvalCaseV1,
    HarnessEvalEnvironmentV1,
    HarnessEvalRunV1,
    HarnessEvalSystemConfigV1,
    canonical_harness_eval_case_digest,
    canonical_harness_eval_environment_digest,
    canonical_harness_eval_run_digest,
    canonical_harness_eval_system_config_digest,
)
from app.models.harness_manifest import (
    HARNESS_WORKFLOW_MANIFEST_ENTRIES,
    HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION,
)
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.harness_stage_eval_contracts import STAGE_EVAL_SUITES
from app.models.planning import (
    LearningPlanOperationRequestV1,
    LearningPlanOperationStatus,
)
from app.persistence.document_process_operation_repository import (
    DocumentProcessOperationRepository,
)
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.harness_workflow_operation_repository import (
    HarnessWorkflowOperationRepository,
)
from app.persistence.learning_plan_operation_repository import (
    LearningPlanOperationRepository,
)
from app.services.harness_eval_pilots import _boolean_metric, _grader_result
from app.services.harness_eval_runner import (
    HarnessEvalCandidateResult,
    HarnessEvalFixturePayload,
    HarnessEvalGraderRegistry,
    HarnessEvalRouteAdapter,
    HarnessEvalRunner,
    HarnessEvalSuiteRegistration,
    HarnessEvalSuiteRegistry,
)
from app.services.harness_stage_eval_adapters import ROOT, document, execute_stage
from app.services.local_store import LocalJsonStore
from pydantic import BaseModel, ConfigDict, Field


def _ref(name):
    return HarnessContractRef(name=name, version=name.replace("_", "-") + "-v1")


RUNNER = _ref("StageRegressionRunner")
REGISTRY = _ref("StageRegressionRegistry")
GRADERS = _ref("StageRegressionGraders")
FIXTURE = _ref("StageRegressionFixture")
OBSERVATION = _ref("StageRegressionObservation")
ENVIRONMENT = _ref("StageRegressionEnvironment")
INVARIANT = _ref("stage_expected_behavior")
CORRECT = _ref("stage_behavior_correct")
FIXTURE_PATH = ROOT / "packages/shared/fixtures/harness/stage-regression-cases-v1.json"
GATE_PATH = FIXTURE_PATH.with_name("stage-regression-gates-v1.json")


class StageCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str
    stage: str
    scenario: str
    input: dict | None
    expected: dict[str, bool | int | str] = Field(min_length=1)


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    values: dict[str, bool | int | str] = Field(min_length=1)


class StageGrader:
    kind = "deterministic"
    contract = _ref("StageBehaviorGrader")
    implementation_contract = _ref("StageExpectedFieldComparison")
    configuration_digest = canonical_harness_digest(
        {"comparison": "exact_type_and_value", "missing": "fail"}
    )

    def grade(self, *, case, payload, candidate_evidence, **_):
        expected = StageCase.model_validate(payload).expected
        actual = candidate_evidence or {}
        correct = all(
            k in actual and type(actual[k]) is type(v) and actual[k] == v
            for k, v in expected.items()
        )
        return _grader_result(
            grader=self,
            case=case,
            passed=correct,
            metrics=[_boolean_metric(CORRECT, correct, case.case_digest)],
            evidence={"expected": expected, "actual": actual},
        )


class StageAuthority:
    def __init__(self, store):
        self.store = store
        self.bindings = HarnessOperationBindingRepository(store.database)
        self.generic = HarnessWorkflowOperationRepository(store.database)
        self.documents = DocumentProcessOperationRepository(store.database)
        self.plans = LearningPlanOperationRepository(store.database)

    def admit(self, *, case, run, repetition_index, seed):
        # A real domain admission and binding share one transaction. No
        # producer binding is borrowed for the Frontend Decode workflow.
        if case.workflow == "document_parse":
            doc = document("eval-doc-" + uuid4().hex[:16])
            self.store.save_list(
                "documents", [*self.store.load_list("documents", type(doc)), doc]
            )
            op, _ = self.documents.admit(document_id=doc.id, force_ocr=False)
            return self.documents.require_harness_operation(op.operation_id)
        if case.workflow == "planning":
            op, _ = self.plans.admit(
                request=LearningPlanOperationRequestV1(
                    client_request_id="eval-" + uuid4().hex,
                    persona_id="eval-persona",
                    objective="Evaluate synthetic plan stage.",
                )
            )
            return self.plans.require_harness_operation(op.operation_id)
        kind = {
            "ocr": HarnessDomainOperationKind.DOCUMENT_OCR,
            "study_unit_cleanup": HarnessDomainOperationKind.STUDY_UNIT_CLEANUP,
            "persona": HarnessDomainOperationKind.PERSONA_GENERATION,
            "scene": HarnessDomainOperationKind.SCENE_GENERATION,
            "frontend_decode": HarnessDomainOperationKind.FRONTEND_DECODE,
        }[case.workflow]
        return self.generic.admit(
            kind=kind,
            request_manifest={
                "case_digest": case.case_digest,
                "run_id": run.run_id,
                "repetition": repetition_index,
                "seed": seed,
            },
        )

    def resolve_harness_id(self, **kwargs):
        return self.bindings.resolve_harness_id(**kwargs)

    def finish(self, binding, success):
        # The eval executes a stage, never commits a document or learning plan.
        if binding.workflow == HarnessWorkflow.DOCUMENT_PARSE:
            self.documents.mark_interrupted(
                operation_id=binding.domain_operation_id,
                error_code="eval_stage_only_no_commit",
            )
        elif binding.workflow == HarnessWorkflow.PLANNING:
            self.plans.mark_terminal(
                operation_id=binding.domain_operation_id,
                status=LearningPlanOperationStatus.NOT_COMMITTED,
                error_code="eval_stage_only_no_commit",
            )
        else:
            self.generic.terminalize(
                binding=binding,
                success=success,
                error_code="eval_stage_execution_failed",
            )


def _source_identity():
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    files = []
    for folder in [
        "services/ai/app",
        "apps/web/lib",
        "apps/web/scripts",
        "packages/shared/src",
        "packages/shared/fixtures/harness",
        "packages/shared/fixtures/adversarial",
    ]:
        files.extend(
            p
            for p in (ROOT / folder).rglob("*")
            if p.is_file()
            and p.suffix in {".py", ".ts", ".json"}
            and "__pycache__" not in p.parts
        )
    files.extend(
        ROOT / f
        for f in [
            "services/ai/uv.lock",
            "services/ai/pyproject.toml",
            "package-lock.json",
            "package.json",
            ".node-version",
        ]
    )
    digest = canonical_harness_digest(
        {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(files))
        }
    )
    return revision, "dirty" if dirty else "clean", digest


def build_harness_stage_runner(*, catalog_path=FIXTURE_PATH, suites=STAGE_EVAL_SUITES,
                               authority_factory=StageAuthority, execute_case=None) -> HarnessEvalRunner:
    catalog = json.loads(catalog_path.read_text())
    if (
        set(catalog) != {"schema_version", "provenance", "cases"}
        or catalog["schema_version"] != "stage-regression-cases-v1"
        or catalog["provenance"] != "developer_authored"
    ):
        raise ValueError("stage_eval_catalog_invalid")
    payloads = [StageCase.model_validate(p) for p in catalog["cases"]]
    if len({p.case_id for p in payloads}) != len(payloads):
        raise ValueError("stage_eval_case_duplicate")
    if {p.stage for p in payloads} != {key.split(":")[1] for key in suites}:
        raise ValueError("stage_eval_coverage_mismatch")
    temporary = TemporaryDirectory(prefix="harness-stage-eval-")
    store = LocalJsonStore(Path(temporary.name))
    authority = authority_factory(store)
    registry = HarnessEvalSuiteRegistry(REGISTRY)
    graders = HarnessEvalGraderRegistry(GRADERS)
    graders.register(StageGrader())
    cases_by_suite = {}
    runs = {}
    adapters = []
    revision, state, tree_digest = _source_identity()
    environment = HarnessEvalEnvironmentV1(
        environment_contract=ENVIRONMENT,
        platform=platform.system().lower(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        node_version=subprocess.check_output(["node", "--version"], text=True).strip(),
        database_kind="sqlite",
        provider_mode="mock",
    )
    payload_by_id = {p.case_id: p.model_dump(mode="json") for p in payloads}

    def resolve(case):
        p = payload_by_id[case.source.fixture_id]
        return HarnessEvalFixturePayload(
            payload=p, payload_digest=canonical_harness_digest(p)
        )

    def execute(*, case, payload, operation_binding, **_):
        started = time.perf_counter()
        success = False
        try:
            StageCase.model_validate(payload)
            observed = Observation(values=(execute_case or execute_stage)(case.stage, payload))
            success = True
            # Schema metrics refer to the versioned observation DTO (including
            # typed rejection), not to validity of deliberately bad input.
            return HarnessEvalCandidateResult(
                candidate_outcome="passed",
                raw_schema_valid=True,
                final_schema_valid=True,
                trace_contract=None,
                trace_digest=None,
                evidence_digest=canonical_harness_digest(
                    observed.model_dump(mode="json")
                ),
                duration_ms=int((time.perf_counter() - started) * 1000),
                grader_evidence=observed.values,
            )
        finally:
            authority.finish(operation_binding, success)

    for key, suite in suites.items():
        entry = HARNESS_WORKFLOW_MANIFEST_ENTRIES[key]
        cases = []
        for p in sorted(
            (p for p in payloads if p.stage == entry.stage.value),
            key=lambda p: p.case_id,
        ):
            draft = dict(
                schema_name="HarnessEvalCase",
                schema_version="harness-eval-case-v1",
                case_id=p.case_id,
                case_version=p.case_id + "-v1",
                case_digest="0" * 64,
                suite=suite.model_dump(mode="json"),
                workflow=entry.workflow.value,
                stage=entry.stage.value,
                eval_route=entry.eval_route.value,
                source={
                    "source_mode": "fixture",
                    "fixture_id": p.case_id,
                    "payload_contract": FIXTURE.model_dump(mode="json"),
                    "payload_digest": canonical_harness_digest(
                        p.model_dump(mode="json")
                    ),
                },
                provenance={
                    "source_kind": "developer_authored",
                    "review_status": "developer_reviewed",
                    "review_contract": None,
                    "attestation_digest": None,
                },
                sensitivity="internal",
                split="regression",
                tags=["stage_regression"],
                expected_invariants=[
                    {
                        "invariant": INVARIANT.model_dump(mode="json"),
                        "expected_outcome": "passed",
                    }
                ],
                grader_refs=[StageGrader.contract.model_dump(mode="json")],
            )
            draft["case_digest"] = canonical_harness_eval_case_digest(draft)
            cases.append(HarnessEvalCaseV1.model_validate(draft))

        def optional(slot):
            value = getattr(slot, "contract", None)
            return value.to_harness_ref() if value is not None else None

        system = HarnessEvalSystemConfigV1(
            workflow_manifest_contract=HarnessContractRef(
                name="HarnessWorkflowManifest",
                version=HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION,
            ),
            harness_contract=OBSERVATION,
            provider_adapter_contract=_ref(suite.name + "_adapter"),
            provider_model_contract=_ref("DeterministicStageFixture"),
            input_contract=FIXTURE,
            output_contract=OBSERVATION,
            prompt_contract=optional(entry.prompt_contract),
            policy_contract=optional(entry.policy_contract),
            toolset_contract=optional(entry.toolset_contract),
            component_contracts=sorted(
                [
                    x.contract.contract.to_harness_ref()
                    for x in entry.component_contracts
                ],
                key=lambda x: (x.name, x.version),
            ),
            reasoning={"mode": "not_supported", "budget_tokens": None},
            sampling={
                "temperature": 0.0,
                "top_p": 1.0,
                "seed_strategy": "per_sample",
                "fixed_seed": None,
            },
            budgets={
                "max_attempts": 2 if entry.workflow == HarnessWorkflow.PERSONA else 1,
                "max_repairs": 1 if entry.workflow == HarnessWorkflow.PERSONA else 0,
                "max_tool_calls": 0,
                "max_provider_calls": 2
                if entry.workflow == HarnessWorkflow.PERSONA
                else 0,
                "max_input_tokens": 64000,
                "max_output_tokens": 2048,
                "max_wall_time_ms": 30000,
                "per_call_timeout_ms": 10000,
                "max_cost_micro_usd": 0,
            },
            source_revision=revision,
            worktree_state=state,
            source_tree_digest=tree_digest if state == "dirty" else None,
        )
        draft = dict(
            schema_name="HarnessEvalRun",
            schema_version="harness-eval-run-v1",
            run_id="harness-eval-run-" + uuid4().hex,
            suite=suite.model_dump(mode="json"),
            suite_manifest_digest=canonical_harness_digest(
                {
                    "suite": suite.model_dump(mode="json"),
                    "cases": [c.case_digest for c in cases],
                }
            ),
            case_set_digest=canonical_harness_digest(
                [c.model_dump(mode="json", exclude_none=False) for c in cases]
            ),
            execution_mode="fixture",
            splits=["regression"],
            repetition_count=1,
            seeds=[17],
            runner_contract=RUNNER.model_dump(mode="json"),
            failure_taxonomy_contract=HARNESS_EVAL_FAILURE_TAXONOMY_CONTRACT.model_dump(
                mode="json"
            ),
            grader_registry_contract=GRADERS.model_dump(mode="json"),
            tested_system=system.model_dump(mode="json"),
            tested_system_config_digest=canonical_harness_eval_system_config_digest(
                system
            ),
            environment=environment.model_dump(mode="json"),
            environment_digest=canonical_harness_eval_environment_digest(environment),
            admitted_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            run_digest="0" * 64,
        )
        draft["run_digest"] = canonical_harness_eval_run_digest(draft)
        run = HarnessEvalRunV1.model_validate(draft)
        known = [
            REGISTRY,
            suite,
            RUNNER,
            GRADERS,
            FIXTURE,
            OBSERVATION,
            ENVIRONMENT,
            INVARIANT,
            StageGrader.contract,
            HARNESS_EVAL_FAILURE_TAXONOMY_CONTRACT,
            system.workflow_manifest_contract,
            system.provider_adapter_contract,
            system.provider_model_contract,
            *system.component_contracts,
            *[
                x
                for x in (
                    system.prompt_contract,
                    system.policy_contract,
                    system.toolset_contract,
                )
                if x is not None
            ],
        ]
        unique = {(x.name, x.version): x for x in known}
        registry.register(
            HarnessEvalSuiteRegistration(
                registration_contract=REGISTRY,
                suite=suite,
                workflow=entry.workflow,
                stage=entry.stage,
                eval_route=entry.eval_route.value,
                runner_contract=RUNNER,
                grader_registry_contract=GRADERS,
                tested_system=system,
                known_contracts=tuple(unique[k] for k in sorted(unique)),
                allowed_execution_modes=("fixture",),
            )
        )
        adapters.append(
            HarnessEvalRouteAdapter(
                suite=suite,
                eval_route=entry.eval_route.value,
                operation_admitter=authority.admit,
                fixture_resolver=resolve,
                synthetic_resolver=None,
                execute=execute,
            )
        )
        cases_by_suite[suite.name] = tuple(cases)
        runs[suite.name] = run
    runner = HarnessEvalRunner(
        suite_registry=registry,
        adapters=adapters,
        graders=graders,
        operation_resolver=authority,
    )
    runner.stage_cases = cases_by_suite
    runner.stage_runs = runs
    runner.stage_resources = (temporary, store, authority)
    return runner


def close_stage_runner(runner):
    temporary, store, _ = runner.stage_resources
    store.close()
    temporary.cleanup()


def gate_execution(execution, expected_count):
    return (
        execution.report.status == "passed"
        and len(execution.raw_samples) == expected_count
        and all(s.status == "passed" for s in execution.raw_samples)
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", action="append")
    parser.add_argument("--list-suites", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    runner = build_harness_stage_runner()
    try:
        available = {s.name: s for s in runner.registered_suites()}
        if args.list_suites:
            print(json.dumps([s.model_dump(mode="json") for s in available.values()]))
            return 0
        selected = args.suite or sorted(available)
        if (
            not selected
            or len(set(selected)) != len(selected)
            or any(s not in available for s in selected)
        ):
            parser.error("Select unique registered suite names")
        gate = json.loads(GATE_PATH.read_text())
        if (
            gate["schema_version"] != "stage-regression-gates-v1"
            or gate["required_pass_rate"] != 1.0
        ):
            raise ValueError("stage_eval_gate_invalid")
        summary = {}
        for name in selected:
            run = runner.stage_runs[name]
            cases = runner.stage_cases[name]
            execution = runner.run(
                run,
                cases,
                selected_suites=[available[name]],
                release_gate=True,
                deterministic_gate=True,
            )
            passed = gate_execution(execution, gate["sample_counts"][name])
            summary[name] = {
                "samples": len(execution.raw_samples),
                "report": execution.report.status,
                "gate": "passed" if passed else "failed",
                "failures": [
                    {
                        "case": s.case_ref.case_id,
                        "status": s.status,
                        "failures": [f.failure_code for f in s.failures],
                    }
                    for s in execution.raw_samples
                    if s.status != "passed"
                ],
            }
            if args.output_dir:
                folder = args.output_dir / name
                folder.mkdir(parents=True, exist_ok=True)
                for filename, payload in [
                    (
                        "input.json",
                        {
                            "run": run.model_dump(mode="json"),
                            "cases": [c.model_dump(mode="json") for c in cases],
                        },
                    ),
                    ("raw-samples.json", execution.raw_samples_json()),
                    ("aggregate.json", execution.aggregate_json()),
                    ("gate.json", summary[name]),
                ]:
                    (folder / filename).write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(summary, indent=2))
        return 0 if all(v["gate"] == "passed" for v in summary.values()) else 1
    finally:
        close_stage_runner(runner)


if __name__ == "__main__":
    raise SystemExit(main())
