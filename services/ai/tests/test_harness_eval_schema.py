from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from app.models.harness_eval import (
    HarnessEvalCaseV1,
    HarnessEvalContractGoldenV1,
    HarnessEvalFailureTaxonomyRegistryV1,
    HarnessEvalReportV1,
    HarnessEvalRunV1,
    HarnessEvalSampleV1,
    canonical_harness_eval_case_digest,
    canonical_harness_eval_environment_digest,
    canonical_harness_eval_report_digest,
    canonical_harness_eval_run_digest,
    canonical_harness_eval_sample_digest,
    canonical_harness_eval_system_config_digest,
    expected_harness_eval_report_id,
    expected_harness_eval_sample_id,
    harness_eval_failure_taxonomy_registry_snapshot,
)


FIXTURE_ROOT = (
    Path(__file__).parents[3] / "packages" / "shared" / "fixtures" / "harness"
)


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _refresh_case(payload: dict[str, object]) -> None:
    case = payload["case"]
    assert isinstance(case, dict)
    case["case_digest"] = canonical_harness_eval_case_digest(case)


def _refresh_run(payload: dict[str, object]) -> None:
    run = payload["run"]
    assert isinstance(run, dict)
    tested_system = run["tested_system"]
    environment = run["environment"]
    assert isinstance(tested_system, dict)
    assert isinstance(environment, dict)
    run["tested_system_config_digest"] = canonical_harness_eval_system_config_digest(
        tested_system
    )
    run["environment_digest"] = canonical_harness_eval_environment_digest(environment)
    run["run_digest"] = canonical_harness_eval_run_digest(run)


def _refresh_sample(payload: dict[str, object]) -> None:
    case = payload["case"]
    sample = payload["sample"]
    assert isinstance(case, dict)
    assert isinstance(sample, dict)
    case_ref = sample["case_ref"]
    assert isinstance(case_ref, dict)
    case_ref["case_digest"] = case["case_digest"]
    sample["sample_id"] = expected_harness_eval_sample_id(
        run_id=str(sample["run_id"]),
        harness_operation_id=str(sample["harness_operation_id"]),
        case_ref=case_ref,
        repetition_index=int(sample["repetition_index"]),
        seed=int(sample["seed"]),
    )
    sample["sample_digest"] = canonical_harness_eval_sample_digest(sample)


def _refresh_report(payload: dict[str, object]) -> None:
    run = payload["run"]
    sample = payload["sample"]
    report = payload["report"]
    assert isinstance(run, dict)
    assert isinstance(sample, dict)
    assert isinstance(report, dict)
    report["report_id"] = expected_harness_eval_report_id(str(report["run_id"]))
    report["run_digest"] = run["run_digest"]
    report["tested_system_config_digest"] = run["tested_system_config_digest"]
    refs = report["sample_refs"]
    assert isinstance(refs, list) and isinstance(refs[0], dict)
    refs[0]["sample_id"] = sample["sample_id"]
    refs[0]["case_ref"] = deepcopy(sample["case_ref"])
    refs[0]["sample_digest"] = sample["sample_digest"]
    report["report_digest"] = canonical_harness_eval_report_digest(report)


class HarnessEvalSchemaTests(unittest.TestCase):
    def test_golden_contract_round_trips_with_stable_identity_and_digests(self) -> None:
        payload = _fixture("eval-contract-golden-v1.json")
        golden = HarnessEvalContractGoldenV1.model_validate(payload)

        self.assertEqual(golden.case.case_digest, canonical_harness_eval_case_digest(golden.case))
        self.assertEqual(
            golden.run.tested_system_config_digest,
            canonical_harness_eval_system_config_digest(golden.run.tested_system),
        )
        self.assertEqual(golden.run.run_digest, canonical_harness_eval_run_digest(golden.run))
        self.assertEqual(
            golden.sample.sample_id,
            expected_harness_eval_sample_id(
                run_id=golden.run.run_id,
                harness_operation_id=golden.sample.harness_operation_id,
                case_ref=golden.sample.case_ref,
                repetition_index=golden.sample.repetition_index,
                seed=golden.sample.seed,
            ),
        )
        self.assertEqual(
            golden.sample.sample_digest,
            canonical_harness_eval_sample_digest(golden.sample),
        )
        self.assertEqual(
            golden.report.report_digest,
            canonical_harness_eval_report_digest(golden.report),
        )
        self.assertEqual(
            HarnessEvalContractGoldenV1.model_validate(
                golden.model_dump(mode="json", exclude_none=False)
            ),
            golden,
        )

    def test_failure_taxonomy_matches_shared_golden(self) -> None:
        payload = _fixture("eval-failure-taxonomy-v1.json")
        decoded = HarnessEvalFailureTaxonomyRegistryV1.model_validate(payload)

        self.assertEqual(
            decoded.model_dump(mode="json", exclude_none=False),
            harness_eval_failure_taxonomy_registry_snapshot(),
        )
        self.assertTrue(
            all(
                entry.counts_as_candidate_failure == (entry.owner == "candidate")
                for entry in decoded.entries
            )
        )

    def test_case_route_sensitivity_review_and_digest_fail_closed(self) -> None:
        payload = _fixture("eval-contract-golden-v1.json")["case"]
        assert isinstance(payload, dict)

        route = deepcopy(payload)
        route["eval_route"] = "planning.tool_execution"
        route["case_digest"] = canonical_harness_eval_case_digest(route)
        with self.assertRaisesRegex(ValidationError, "harness_eval_case_route_mismatch"):
            HarnessEvalCaseV1.model_validate(route)

        protected = deepcopy(payload)
        protected["source"] = {
            "source_mode": "protected_artifact",
            "artifact_type": "tavern_transcript",
            "artifact_id": "artifact-private-1",
            "artifact_contract": {
                "name": "TavernTranscriptFixture",
                "version": "tavern-transcript-fixture-v1",
            },
            "payload_digest": "a" * 64,
        }
        protected["case_digest"] = canonical_harness_eval_case_digest(protected)
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_case_sensitivity_source_mismatch",
        ):
            HarnessEvalCaseV1.model_validate(protected)

        held_out = deepcopy(payload)
        held_out["split"] = "held_out"
        held_out["case_digest"] = canonical_harness_eval_case_digest(held_out)
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_case_independent_review_required",
        ):
            HarnessEvalCaseV1.model_validate(held_out)

        tampered = deepcopy(payload)
        tampered["tags"] = ["deterministic", "identity", "tampered"]
        with self.assertRaisesRegex(ValidationError, "harness_eval_case_digest_mismatch"):
            HarnessEvalCaseV1.model_validate(tampered)

    def test_strict_versions_extra_fields_and_coercion_are_rejected(self) -> None:
        payload = _fixture("eval-contract-golden-v1.json")

        unknown = deepcopy(payload["case"])
        assert isinstance(unknown, dict)
        unknown["schema_version"] = "harness-eval-case-v2"
        with self.assertRaises(ValidationError):
            HarnessEvalCaseV1.model_validate(unknown)

        extra = deepcopy(payload["sample"])
        assert isinstance(extra, dict)
        extra["raw_output"] = "must never enter CI evidence"
        with self.assertRaises(ValidationError):
            HarnessEvalSampleV1.model_validate(extra)

        missing_operation = deepcopy(payload["sample"])
        assert isinstance(missing_operation, dict)
        del missing_operation["harness_operation_id"]
        with self.assertRaises(ValidationError):
            HarnessEvalSampleV1.model_validate(missing_operation)

        caller_owned_operation = deepcopy(payload["sample"])
        assert isinstance(caller_owned_operation, dict)
        caller_owned_operation["harness_operation_id"] = "caller-operation-1"
        caller_owned_operation["sample_digest"] = canonical_harness_eval_sample_digest(
            caller_owned_operation
        )
        with self.assertRaises(ValidationError):
            HarnessEvalSampleV1.model_validate(caller_owned_operation)

        rebound_operation = deepcopy(payload["sample"])
        assert isinstance(rebound_operation, dict)
        rebound_operation["harness_operation_id"] = (
            f"harness-operation-{'c' * 32}"
        )
        rebound_operation["sample_digest"] = canonical_harness_eval_sample_digest(
            rebound_operation
        )
        with self.assertRaisesRegex(ValidationError, "sample_id_mismatch"):
            HarnessEvalSampleV1.model_validate(rebound_operation)

        coerced = deepcopy(payload["run"])
        assert isinstance(coerced, dict)
        tested_system = coerced["tested_system"]
        assert isinstance(tested_system, dict)
        budgets = tested_system["budgets"]
        assert isinstance(budgets, dict)
        budgets["max_attempts"] = "2"
        with self.assertRaises(ValidationError):
            HarnessEvalRunV1.model_validate(coerced)

        non_finite = deepcopy(payload["sample"])
        assert isinstance(non_finite, dict)
        metrics = non_finite["metrics"]
        assert isinstance(metrics, list) and isinstance(metrics[0], dict)
        metrics[0]["value"] = float("nan")
        with self.assertRaises(ValidationError):
            HarnessEvalSampleV1.model_validate(non_finite)

    def test_tested_system_config_and_environment_are_digest_bound(self) -> None:
        payload = _fixture("eval-contract-golden-v1.json")
        run = deepcopy(payload["run"])
        assert isinstance(run, dict)
        tested_system = run["tested_system"]
        assert isinstance(tested_system, dict)
        sampling = tested_system["sampling"]
        assert isinstance(sampling, dict)
        sampling["temperature"] = 0.5
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_system_config_digest_mismatch",
        ):
            HarnessEvalRunV1.model_validate(run)

        dirty = deepcopy(payload)
        dirty_run = dirty["run"]
        assert isinstance(dirty_run, dict)
        dirty_system = dirty_run["tested_system"]
        assert isinstance(dirty_system, dict)
        dirty_system["worktree_state"] = "dirty"
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_source_tree_digest_mismatch",
        ):
            HarnessEvalRunV1.model_validate(dirty_run)

        environment = deepcopy(payload["run"])
        assert isinstance(environment, dict)
        env = environment["environment"]
        assert isinstance(env, dict)
        env["platform"] = "different"
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_environment_digest_mismatch",
        ):
            HarnessEvalRunV1.model_validate(environment)

    def test_candidate_failure_can_be_expected_but_infrastructure_failure_is_broken(self) -> None:
        candidate = _fixture("eval-contract-golden-v1.json")
        sample = candidate["sample"]
        assert isinstance(sample, dict)
        sample["candidate_outcome"] = "failed"
        sample["raw_schema_valid"] = False
        sample["final_schema_valid"] = False
        sample["failures"] = [
            {
                "schema_name": "HarnessEvalFailure",
                "schema_version": "harness-eval-failure-v1",
                "failure_code": "candidate_decode_failed",
                "owner": "candidate",
                "reason_code": "expected_invalid_shape",
                "evidence_digest": "b" * 64,
            }
        ]
        sample["sample_digest"] = canonical_harness_eval_sample_digest(sample)
        decoded = HarnessEvalSampleV1.model_validate(sample)
        self.assertEqual(decoded.status, "passed")

        grader_error = _fixture("eval-contract-golden-v1.json")["sample"]
        assert isinstance(grader_error, dict)
        results = grader_error["grader_results"]
        assert isinstance(results, list) and isinstance(results[0], dict)
        results[0]["execution_status"] = "error"
        results[0]["verdict"] = None
        results[0]["score"] = None
        results[0]["failure_codes"] = ["grader_execution_failed"]
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_infrastructure_failure_not_broken",
        ):
            HarnessEvalSampleV1.model_validate(grader_error)

    def test_sample_and_report_identity_counts_and_raw_evidence_are_consistent(self) -> None:
        payload = _fixture("eval-contract-golden-v1.json")

        wrong_id = deepcopy(payload["sample"])
        assert isinstance(wrong_id, dict)
        wrong_id["sample_id"] = "harness-eval-sample-ffffffffffffffffffffffffffffffff"
        wrong_id["sample_digest"] = canonical_harness_eval_sample_digest(wrong_id)
        with self.assertRaisesRegex(ValidationError, "harness_eval_sample_id_mismatch"):
            HarnessEvalSampleV1.model_validate(wrong_id)

        wrong_count = deepcopy(payload["report"])
        assert isinstance(wrong_count, dict)
        wrong_count["passed_count"] = 0
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_report_terminal_counts_mismatch",
        ):
            HarnessEvalReportV1.model_validate(wrong_count)

        wrong_artifact = deepcopy(payload["report"])
        assert isinstance(wrong_artifact, dict)
        artifact = wrong_artifact["raw_samples_artifact"]
        assert isinstance(artifact, dict)
        artifact["sample_count"] = 2
        with self.assertRaisesRegex(
            ValidationError,
            "harness_eval_report_raw_samples_mismatch",
        ):
            HarnessEvalReportV1.model_validate(wrong_artifact)

        drift = deepcopy(payload["report"])
        assert isinstance(drift, dict)
        drift["completed_at"] = "2026-08-25T00:00:02Z"
        with self.assertRaisesRegex(ValidationError, "harness_eval_report_digest_mismatch"):
            HarnessEvalReportV1.model_validate(drift)


if __name__ == "__main__":
    unittest.main()
