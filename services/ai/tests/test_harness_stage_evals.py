from __future__ import annotations

import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.services import harness_stage_eval_adapters as executors
from app.services.harness_eval_runner import HarnessEvalFixturePayload
from app.services.harness_stage_evals import (
    GATE_PATH,
    build_harness_stage_runner,
    close_stage_runner,
    gate_execution,
)


class HarnessStageEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = build_harness_stage_runner()
        cls.gates = json.loads(GATE_PATH.read_text())

    @classmethod
    def tearDownClass(cls):
        close_stage_runner(cls.runner)

    def execute(self, name):
        run = self.runner.stage_runs[name]
        return self.runner.run(
            run,
            self.runner.stage_cases[name],
            selected_suites=[run.suite],
            release_gate=True,
            deterministic_gate=True,
        )

    def test_all_ten_registered_suites_execute_with_real_admissions(self):
        self.assertEqual(len(self.runner.registered_suites()), 10)
        self.assertEqual(set(self.runner.stage_cases), set(self.gates["sample_counts"]))
        authority = self.runner.stage_resources[2]
        identities = set()
        for name, cases in self.runner.stage_cases.items():
            with self.subTest(suite=name):
                result = self.execute(name)
                self.assertTrue(
                    gate_execution(result, self.gates["sample_counts"][name]),
                    result.report.model_dump(),
                )
                self.assertFalse(gate_execution(result, len(cases) + 1))
                for sample in result.raw_samples:
                    self.assertNotIn(sample.harness_operation_id, identities)
                    identities.add(sample.harness_operation_id)
                    binding = authority.resolve_harness_id(
                        harness_operation_id=sample.harness_operation_id
                    )
                    self.assertEqual(binding.workflow.value, cases[0].workflow)
                    self.assertEqual(sample.status, "passed")
                for case in cases:
                    self.assertEqual(case.split, "regression")
                    self.assertEqual(case.provenance.source_kind, "developer_authored")
                    self.assertIsNone(case.provenance.attestation_digest)
        self.assertEqual(len(identities), sum(self.gates["sample_counts"].values()))

    def test_every_suite_fails_when_stage_output_regresses(self):
        real = executors.execute_stage

        def corrupted(stage, payload):
            observation = real(stage, payload)
            # Corrupt an actually observed field, not the expected fixture.
            key = next(k for k in payload["expected"] if k in observation)
            value = observation[key]
            observation[key] = (
                not value
                if type(value) is bool
                else value + 1
                if type(value) is int
                else value + "-wrong"
            )
            return observation

        with patch(
            "app.services.harness_stage_evals.execute_stage", side_effect=corrupted
        ):
            for name in self.runner.stage_cases:
                with self.subTest(suite=name):
                    result = self.execute(name)
                    self.assertEqual(result.report.status, "failed")
                    self.assertEqual(result.report.broken_count, 0)
                    self.assertFalse(
                        gate_execution(result, self.gates["sample_counts"][name])
                    )

    def test_bypassed_production_validators_are_detected(self):
        for name, target in [
            (
                "persona_generation_regression",
                "PersonaGenerationProposalV1.model_validate",
            ),
            ("plan_generation_regression", "_validate_learning_plan_proposal_refs"),
            (
                "document_process_regression",
                "DocumentProcessRuntimeOutputV1.model_validate",
            ),
        ]:
            with (
                self.subTest(suite=name),
                patch.object(executors, target.split(".")[0])
                if "." in target
                else patch.object(executors, target),
            ):
                result = self.execute(name)
                self.assertEqual(result.report.status, "failed")
                self.assertGreater(result.report.failed_count, 0)

    def test_infrastructure_crash_cannot_count_as_successful_rejection(self):
        with patch(
            "app.services.harness_stage_evals.execute_stage",
            side_effect=OSError("synthetic execution failure"),
        ):
            result = self.execute("frontend_decode_regression")
        self.assertEqual(result.report.status, "broken")
        self.assertEqual(result.report.failed_count, 0)
        self.assertEqual(
            result.report.broken_count,
            len(self.runner.stage_cases["frontend_decode_regression"]),
        )

    def test_generic_cli_returns_failure_for_a_failed_report(self):
        from app.services.harness_eval_runner import main

        run = self.runner.stage_runs["persona_generation_regression"]
        with TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            path.write_text(
                json.dumps(
                    {
                        "run": run.model_dump(mode="json"),
                        "cases": [
                            c.model_dump(mode="json")
                            for c in self.runner.stage_cases[run.suite.name]
                        ],
                    }
                )
            )
            with (
                patch(
                    "app.services.harness_eval_runner._load_factory",
                    return_value=self.runner,
                ),
                patch(
                    "app.services.harness_stage_evals.execute_stage",
                    return_value={"accepted": True},
                ),
                redirect_stdout(StringIO()),
            ):
                code = main(
                    [
                        "--registry",
                        "fixture:runner",
                        "--suite",
                        run.suite.name + "@" + run.suite.version,
                        "--input",
                        str(path),
                        "--output-dir",
                        folder,
                    ]
                )
            self.assertEqual(code, 1)
            self.assertEqual(
                json.loads((Path(folder) / "aggregate.json").read_text())["status"],
                "failed",
            )

    def test_fixture_digest_tampering_is_case_failure_not_candidate_success(self):
        run = self.runner.stage_runs["persona_generation_regression"]
        key = (
            (run.suite.name, run.suite.version),
            self.runner.stage_cases[run.suite.name][0].eval_route,
        )
        adapter = self.runner._adapters[key]
        try:
            self.runner._adapters[key] = replace(
                adapter,
                fixture_resolver=lambda case: HarnessEvalFixturePayload(
                    payload={}, payload_digest="0" * 64
                ),
            )
            result = self.execute(run.suite.name)
            self.assertEqual(result.report.status, "broken")
            self.assertEqual(result.report.failed_count, 0)
        finally:
            self.runner._adapters[key] = adapter


if __name__ == "__main__":
    unittest.main()
