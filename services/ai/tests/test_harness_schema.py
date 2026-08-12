from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from pydantic import BaseModel, ValidationError

from app.models.harness import (
    HarnessCommitEvidence,
    HarnessCommitStatus,
    HarnessProposalEnvelope,
    HarnessTraceRecord,
    HarnessTraceV2,
    HarnessV2Model,
    canonical_harness_commit_digest,
    canonical_harness_digest,
    validate_harness_trace,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "harness"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


class _ExampleProposal(HarnessV2Model):
    text: str


class _LooseProposal(BaseModel):
    text: str


class HarnessSchemaTests(unittest.TestCase):
    def test_legacy_v1_fixture_remains_readable_without_fabricated_evidence(self) -> None:
        trace = validate_harness_trace(_fixture("legacy_v1.json"))

        self.assertIsInstance(trace, HarnessTraceRecord)
        self.assertFalse(hasattr(trace, "trace_id"))
        self.assertFalse(hasattr(trace, "commit_evidence"))
        self.assertEqual(trace.version, "tavern-harness-v1/tavern-actor-prompt-v1")

    def test_repaired_committed_v2_fixture_round_trips(self) -> None:
        trace = validate_harness_trace(_fixture("repaired_committed_v2.json"))

        self.assertIsInstance(trace, HarnessTraceV2)
        assert isinstance(trace, HarnessTraceV2)
        self.assertEqual(trace.context.operation_id, trace.operation_id)
        self.assertEqual(trace.context.workflow, trace.workflow)
        self.assertEqual(trace.commit_evidence.status, HarnessCommitStatus.COMMITTED)
        self.assertEqual(trace.commit_evidence.committed_resources[0].first_sequence, 10)
        self.assertEqual(
            trace.commit_evidence.payload_digest,
            canonical_harness_commit_digest(
                payload_contract=trace.commit_evidence.payload_contract,
                committed_resources=trace.commit_evidence.committed_resources,
                digest_scope=trace.commit_evidence.digest_scope,
            ),
        )
        self.assertEqual(
            HarnessTraceV2.model_validate(trace.model_dump(mode="json")),
            trace,
        )

    def test_failed_not_committed_fixture_uses_explicit_nulls(self) -> None:
        trace = HarnessTraceV2.model_validate(_fixture("failed_not_committed_v2.json"))

        evidence = trace.model_dump(mode="json")["commit_evidence"]
        self.assertEqual(evidence["status"], "not_committed")
        self.assertEqual(evidence["committed_resources"], [])
        self.assertIsNone(evidence["payload_digest"])
        self.assertIsNone(evidence["committed_at"])

    def test_unknown_trace_schema_version_is_rejected_instead_of_downgraded(self) -> None:
        payload = _fixture("repaired_committed_v2.json")
        payload["trace_schema_version"] = "harness-trace-v3"

        with self.assertRaises(ValidationError):
            validate_harness_trace(payload)

        disguised_legacy = _fixture("legacy_v1.json")
        disguised_legacy["version"] = "harness-trace-v3"
        with self.assertRaisesRegex(
            ValidationError,
            "harness_trace_schema_version_discriminator_required",
        ):
            validate_harness_trace(disguised_legacy)

    def test_commit_evidence_rejects_partial_or_fabricated_committed_state(self) -> None:
        payload = _fixture("repaired_committed_v2.json")["commit_evidence"]
        assert isinstance(payload, dict)
        incomplete = deepcopy(payload)
        incomplete["payload_digest"] = None
        with self.assertRaisesRegex(ValidationError, "harness_committed_evidence_incomplete"):
            HarnessCommitEvidence.model_validate(incomplete)

        uncommitted = deepcopy(payload)
        uncommitted["status"] = "not_committed"
        with self.assertRaisesRegex(
            ValidationError,
            "harness_not_committed_contains_committed_state",
        ):
            HarnessCommitEvidence.model_validate(uncommitted)

        revision_mismatch = deepcopy(payload)
        revision_mismatch["committed_resources"][1]["expected_revision"] = 3
        with self.assertRaisesRegex(
            ValidationError,
            "harness_commit_expected_revision_mismatch",
        ):
            HarnessCommitEvidence.model_validate(revision_mismatch)

        multi_resource_projection = deepcopy(payload)
        multi_resource_projection["digest_scope"] = "committed_projection"
        with self.assertRaisesRegex(
            ValidationError,
            "harness_projection_digest_requires_single_resource",
        ):
            HarnessCommitEvidence.model_validate(multi_resource_projection)

        projection_digest_mismatch = deepcopy(payload)
        projection_digest_mismatch["digest_scope"] = "committed_projection"
        projection_digest_mismatch["attempted_resource_refs"] = [
            projection_digest_mismatch["attempted_resource_refs"][0]
        ]
        projection_digest_mismatch["committed_resources"] = [
            projection_digest_mismatch["committed_resources"][0]
        ]
        with self.assertRaisesRegex(
            ValidationError,
            "harness_projection_digest_mismatch",
        ):
            HarnessCommitEvidence.model_validate(projection_digest_mismatch)

        batch_manifest_mismatch = deepcopy(payload)
        batch_manifest_mismatch["committed_resources"][0]["payload_digest"] = "9" * 64
        with self.assertRaisesRegex(
            ValidationError,
            "harness_batch_manifest_digest_mismatch",
        ):
            HarnessCommitEvidence.model_validate(batch_manifest_mismatch)

    def test_trace_rejects_mismatched_context_and_noncontiguous_attempts(self) -> None:
        context_mismatch = _fixture("repaired_committed_v2.json")
        context = context_mismatch["context"]
        assert isinstance(context, dict)
        context["operation_id"] = "operation-other"
        with self.assertRaisesRegex(ValidationError, "harness_context_operation_mismatch"):
            HarnessTraceV2.model_validate(context_mismatch)

        indexes = _fixture("repaired_committed_v2.json")
        attempts = indexes["attempt_records"]
        assert isinstance(attempts, list)
        assert isinstance(attempts[1], dict)
        attempts[1]["attempt_index"] = 3
        with self.assertRaisesRegex(ValidationError, "harness_attempt_indexes_not_contiguous"):
            HarnessTraceV2.model_validate(indexes)

    def test_committed_trace_requires_a_matching_successful_commit_attempt(self) -> None:
        missing = _fixture("repaired_committed_v2.json")
        attempts = missing["attempt_records"]
        assert isinstance(attempts, list)
        missing["attempt_records"] = attempts[:-1]
        with self.assertRaisesRegex(ValidationError, "harness_commit_attempt_not_terminal"):
            HarnessTraceV2.model_validate(missing)

        mismatch = _fixture("repaired_committed_v2.json")
        mismatch_attempts = mismatch["attempt_records"]
        assert isinstance(mismatch_attempts, list)
        assert isinstance(mismatch_attempts[-1], dict)
        mismatch_attempts[-1]["output_digest"] = "f" * 64
        with self.assertRaisesRegex(ValidationError, "harness_commit_attempt_digest_mismatch"):
            HarnessTraceV2.model_validate(mismatch)

    def test_trace_terminal_state_rejects_contradictory_evidence(self) -> None:
        failed_but_committed = _fixture("repaired_committed_v2.json")
        failed_but_committed["status"] = "failed"
        failed_but_committed["error_code"] = "late_failure"
        with self.assertRaisesRegex(ValidationError, "harness_failed_trace_cannot_be_committed"):
            HarnessTraceV2.model_validate(failed_but_committed)

        passed_with_recovery = _fixture("repaired_committed_v2.json")
        passed_with_recovery["status"] = "passed"
        with self.assertRaisesRegex(
            ValidationError,
            "harness_passed_trace_contains_failure_or_warning",
        ):
            HarnessTraceV2.model_validate(passed_with_recovery)

        uncommitted_after_success = _fixture("repaired_committed_v2.json")
        uncommitted_after_success["commit_evidence"] = {
            "status": "not_committed",
            "effect_batch_id": None,
            "payload_contract": None,
            "digest_algorithm": None,
            "digest_scope": None,
            "attempted_resource_refs": [],
            "committed_resources": [],
            "payload_digest": None,
            "committed_at": None,
            "rollback_reason_code": "",
            "rolled_back_at": None,
        }
        with self.assertRaisesRegex(ValidationError, "harness_uncommitted_trace_has_passed_commit"):
            HarnessTraceV2.model_validate(uncommitted_after_success)

    def test_repaired_trace_rejects_a_later_output_failure(self) -> None:
        payload = _fixture("repaired_committed_v2.json")
        attempts = payload["attempt_records"]
        assert isinstance(attempts, list)
        attempts.insert(
            -1,
            {
                "attempt_id": "attempt-validate-3",
                "attempt_index": 5,
                "phase": "validate",
                "status": "failed",
                "output_digest": "3" * 64,
                "error_code": "late_validation_failure",
                "duration_ms": 1,
            },
        )
        assert isinstance(attempts[-1], dict)
        attempts[-1]["attempt_index"] = 6
        payload["duration_ms"] = 50

        with self.assertRaisesRegex(
            ValidationError,
            "harness_terminal_output_attempt_not_passed",
        ):
            HarnessTraceV2.model_validate(payload)

        payload = _fixture("repaired_committed_v2.json")
        attempts = payload["attempt_records"]
        assert isinstance(attempts, list)
        payload["attempt_records"] = attempts[:3] + attempts[-1:]
        assert isinstance(attempts[-1], dict)
        attempts[-1]["attempt_index"] = 4
        payload["duration_ms"] = 48

        with self.assertRaisesRegex(
            ValidationError,
            "harness_terminal_output_attempt_not_passed",
        ):
            HarnessTraceV2.model_validate(payload)

    def test_success_trace_requires_terminal_validation(self) -> None:
        payload = _fixture("repaired_committed_v2.json")
        payload["status"] = "passed"
        payload["checks"] = []
        payload["recovery_strategy"] = "none"
        attempts = payload["attempt_records"]
        assert isinstance(attempts, list)
        generate = deepcopy(attempts[0])
        assert isinstance(generate, dict)
        generate["output_digest"] = payload["output_digest"]
        commit = deepcopy(attempts[-1])
        assert isinstance(commit, dict)
        commit["attempt_index"] = 2
        payload["attempt_records"] = [generate, commit]

        with self.assertRaisesRegex(
            ValidationError,
            "harness_terminal_output_attempt_not_passed",
        ):
            HarnessTraceV2.model_validate(payload)

    def test_rolled_back_trace_requires_failed_commit_and_terminal_rollback(self) -> None:
        payload = _fixture("failed_not_committed_v2.json")
        payload["attempt_records"] = [
            {
                "attempt_id": "attempt-commit-1",
                "attempt_index": 1,
                "phase": "commit",
                "status": "failed",
                "output_digest": None,
                "error_code": "database_commit_failed",
                "duration_ms": 3,
            },
            {
                "attempt_id": "attempt-rollback-1",
                "attempt_index": 2,
                "phase": "rollback",
                "status": "passed",
                "output_digest": None,
                "error_code": "",
                "duration_ms": 1,
            },
        ]
        payload["error_code"] = "database_commit_failed"
        payload["duration_ms"] = 4
        payload["commit_evidence"] = {
            "status": "rolled_back",
            "effect_batch_id": "effect-batch-1",
            "payload_contract": {
                "name": "DocumentCommitBatch",
                "version": "document-commit-v1",
            },
            "digest_algorithm": "sha256",
            "digest_scope": "committed_batch",
            "attempted_resource_refs": [
                {
                    "resource_type": "document",
                    "resource_id": "document-1",
                    "revision": None,
                }
            ],
            "committed_resources": [],
            "payload_digest": None,
            "committed_at": None,
            "rollback_reason_code": "database_commit_failed",
            "rolled_back_at": "2026-08-12T08:05:00Z",
        }

        trace = HarnessTraceV2.model_validate(payload)
        self.assertEqual(trace.commit_evidence.status, HarnessCommitStatus.ROLLED_BACK)

        missing_rollback = deepcopy(payload)
        missing_rollback["attempt_records"] = missing_rollback["attempt_records"][:-1]
        with self.assertRaisesRegex(ValidationError, "harness_rollback_attempt_not_terminal"):
            HarnessTraceV2.model_validate(missing_rollback)

        successful_commit_before_rollback = deepcopy(payload)
        successful_commit_before_rollback["attempt_records"].insert(
            1,
            {
                "attempt_id": "attempt-commit-2",
                "attempt_index": 2,
                "phase": "commit",
                "status": "passed",
                "output_digest": "e" * 64,
                "error_code": "",
                "duration_ms": 1,
            },
        )
        successful_commit_before_rollback["attempt_records"][-1]["attempt_index"] = 3
        successful_commit_before_rollback["duration_ms"] = 5
        with self.assertRaisesRegex(
            ValidationError,
            "harness_rollback_failed_commit_missing",
        ):
            HarnessTraceV2.model_validate(successful_commit_before_rollback)

    def test_proposal_envelope_requires_a_strict_domain_proposal(self) -> None:
        envelope_type = HarnessProposalEnvelope[_ExampleProposal]
        proposal = _ExampleProposal(text="validated content")
        envelope = envelope_type(
            operation_id="operation-example-1",
            contract={"name": "ExampleProposal", "version": "example-proposal-v1"},
            context_digest="c" * 64,
            payload_digest=canonical_harness_digest(proposal),
            proposal=proposal,
        )
        self.assertEqual(envelope.proposal, proposal)

        payload = {
            "operation_id": "operation-example-1",
            "contract": {"name": "ExampleProposal", "version": "example-proposal-v1"},
            "context_digest": "c" * 64,
            "payload_digest": canonical_harness_digest(proposal),
            "proposal": {"text": "validated content", "server_owned_id": "unsafe"},
        }

        with self.assertRaises(ValidationError):
            envelope_type.model_validate(payload)

        bad_digest = {
            **payload,
            "proposal": {"text": "validated content"},
            "payload_digest": "d" * 64,
        }
        with self.assertRaisesRegex(
            ValidationError,
            "harness_proposal_payload_digest_mismatch",
        ):
            envelope_type.model_validate(bad_digest)

        with self.assertRaises(ValidationError):
            HarnessProposalEnvelope.model_validate(
                {
                    **bad_digest,
                    "payload_digest": canonical_harness_digest(
                        {"text": "validated content"}
                    ),
                }
            )

        loose = _LooseProposal(text="validated content")
        with self.assertRaisesRegex(
            ValidationError,
            "harness_proposal_extra_forbid_required",
        ):
            HarnessProposalEnvelope[_LooseProposal](
                operation_id="operation-loose-1",
                contract={"name": "LooseProposal", "version": "loose-proposal-v1"},
                context_digest="c" * 64,
                payload_digest=canonical_harness_digest(loose),
                proposal=loose,
            )

    def test_canonical_digest_is_order_independent_and_rejects_nan(self) -> None:
        self.assertEqual(
            canonical_harness_digest({"b": [2, None], "a": "你好"}),
            canonical_harness_digest({"a": "你好", "b": [2, None]}),
        )
        with self.assertRaises(ValueError):
            canonical_harness_digest({"score": float("nan")})


if __name__ == "__main__":
    unittest.main()
