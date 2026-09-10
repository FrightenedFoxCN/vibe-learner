from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest


from app.models.harness import HarnessAttemptPhase, HarnessContractRef, HarnessStage, HarnessStatus, HarnessCommitStatus, HarnessContractRef
from app.models.harness_runtime import HarnessRuntimeExecutionV1, HarnessRuntimeRecoveryDisposition
from app.persistence.harness_runtime_repository import (
    HarnessRuntimeIdentityConflict,
    HarnessRuntimeRepository,
)
from app.persistence.models import HarnessRuntimeExecutionRow
from app.services.harness_runtime import HarnessOperationRuntime, HarnessRuntimeStageAdapter, HarnessRuntimeCommitOutcomeUnknown, HarnessRuntimeResolvedArtifact, HarnessRuntimeError
from app.services.harness_runtime import HarnessRuntimeResolvedArtifact


from tests.support.harness_runtime import HarnessRuntimeFixture, ADAPTER_CONTRACT, TRACE_CONTRACT


class HarnessRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = HarnessRuntimeFixture()
        self.addCleanup(self.fixture.close)

    def test_execute_persists_terminal_trace_and_duplicate_is_read_back(self) -> None:
        calls: dict[str, int] = {}
        runtime = HarnessOperationRuntime(repository=self.fixture.repository)
        first = runtime.execute(
            request=self.fixture.request,
            adapter=self.fixture.adapter(calls),
            claim_owner="worker-a",
        )

        self.assertEqual(first.state.value, "terminal")
        assert first.terminal_trace is not None
        self.assertEqual(first.terminal_trace.status, HarnessStatus.PASSED)
        self.assertEqual(
            [item.phase for item in first.attempt_records],
            [
                HarnessAttemptPhase.GENERATE,
                HarnessAttemptPhase.DECODE,
                HarnessAttemptPhase.VALIDATE,
            ],
        )
        restarted = HarnessOperationRuntime(
            repository=HarnessRuntimeRepository(self.fixture.database)
        )
        duplicate = restarted.execute(
            request=self.fixture.request,
            adapter=self.fixture.adapter(calls),
            claim_owner="worker-b",
        )
        self.assertEqual(duplicate, first)
        self.assertEqual(calls, {"generate": 1, "decode": 1, "validate": 1})

    def test_decode_failure_repairs_once_and_records_ordered_attempts(self) -> None:
        calls = {"repair": 0}

        def repair(_raw, _error, _index):
            calls["repair"] += 1
            return {"value": "valid"}

        base = self.fixture.adapter(calls)
        adapter = HarnessRuntimeStageAdapter(
            adapter_contract=base.adapter_contract,
            trace_contract=base.trace_contract,
            generate=lambda _context, _artifacts: {"value": "invalid"},
            decode=base.decode,
            validate=base.validate,
            repair=repair,
            recovery_strategy="repair_fixture_payload",
        )
        result = HarnessOperationRuntime(repository=self.fixture.repository).execute(
            request=self.fixture.request,
            adapter=adapter,
            claim_owner="worker-a",
        )
        assert result.terminal_trace is not None
        self.assertEqual(result.terminal_trace.status, HarnessStatus.REPAIRED)
        self.assertEqual(
            [item.phase for item in result.attempt_records],
            [
                HarnessAttemptPhase.GENERATE,
                HarnessAttemptPhase.DECODE,
                HarnessAttemptPhase.REPAIR,
                HarnessAttemptPhase.DECODE,
                HarnessAttemptPhase.VALIDATE,
            ],
        )
        self.assertEqual(calls["repair"], 1)

    def test_adapter_failure_terminalizes_not_committed(self) -> None:
        adapter = self.fixture.adapter()
        failed = HarnessRuntimeStageAdapter(
            adapter_contract=adapter.adapter_contract,
            trace_contract=adapter.trace_contract,
            generate=lambda _context, _artifacts: (_ for _ in ()).throw(
                RuntimeError("fixture_generate_failed")
            ),
            decode=adapter.decode,
            validate=adapter.validate,
        )
        result = HarnessOperationRuntime(repository=self.fixture.repository).execute(
            request=self.fixture.request,
            adapter=failed,
            claim_owner="worker-a",
        )
        assert result.terminal_trace is not None
        self.assertEqual(result.terminal_trace.status, HarnessStatus.FAILED)
        self.assertEqual(
            result.terminal_trace.error_code,
            "fixture_generate_failed",
        )
        self.assertEqual(
            result.terminal_trace.commit_evidence.status.value,
            "not_committed",
        )

    def test_claim_exhaustion_is_fenced_after_three_expired_claims(self) -> None:
        prepared = self.fixture.repository.prepare(operation_binding=self.fixture.binding, stage=HarnessStage.TAVERN_ACTOR_REPLY, trace_slot=0, adapter_contract=ADAPTER_CONTRACT, trace_contract=TRACE_CONTRACT, context=self.fixture.context)
        for index in range(3):
            claim = self.fixture.repository.claim(trace_id=prepared.trace_id, claim_owner=f"worker-{index}")
            self.assertIsNotNone(claim)
            self._expire(prepared.trace_id)
        self.assertEqual(self.fixture.repository.inspect_recovery(prepared.trace_id).disposition, HarnessRuntimeRecoveryDisposition.ATTEMPTS_EXHAUSTED)
        self.assertIsNone(self.fixture.repository.claim(trace_id=prepared.trace_id, claim_owner="worker-final", recovery=True))

    def test_claim_renewal_extends_database_lease_and_preserves_fence(self) -> None:
        prepared = self.fixture.repository.prepare(
            operation_binding=self.fixture.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            context=self.fixture.context,
        )
        claim = self.fixture.repository.claim(
            trace_id=prepared.trace_id,
            claim_owner="worker-a",
            lease_seconds=1,
        )
        assert claim is not None
        renewed = self.fixture.repository.renew(claim=claim, lease_seconds=30)
        self.assertGreater(renewed.lease_expires_at, claim.lease_expires_at)
        self.assertEqual(renewed.claim_token, claim.claim_token)
        self._expire(prepared.trace_id)
        with self.assertRaises(HarnessRuntimeError):
            self.fixture.repository.renew(claim=renewed, lease_seconds=30)

    def test_wall_time_budget_fails_closed_after_long_callback(self) -> None:
        current = [datetime(2026, 9, 3, tzinfo=UTC)]

        def clock() -> datetime:
            return current[0]

        def generate(_context, _artifacts):
            current[0] += timedelta(minutes=4)
            return {"value": "valid"}

        base = self.fixture.adapter()
        result = HarnessOperationRuntime(
            repository=self.fixture.repository,
            clock=clock,
        ).execute(
            request=self.fixture.request,
            adapter=HarnessRuntimeStageAdapter(
                adapter_contract=base.adapter_contract,
                trace_contract=base.trace_contract,
                generate=generate,
                decode=base.decode,
                validate=base.validate,
            ),
            claim_owner="worker-a",
        )
        assert result.terminal_trace is not None
        self.assertEqual(result.terminal_trace.status, HarnessStatus.FAILED)
        self.assertEqual(
            result.terminal_trace.error_code,
            "harness_runtime_wall_time_budget_exceeded",
        )

    def test_forged_terminal_trace_is_rejected(self) -> None:
        prepared = self.fixture.repository.prepare(operation_binding=self.fixture.binding, stage=HarnessStage.TAVERN_ACTOR_REPLY, trace_slot=0, adapter_contract=ADAPTER_CONTRACT, trace_contract=TRACE_CONTRACT, context=self.fixture.context)
        claim = self.fixture.repository.claim(trace_id=prepared.trace_id, claim_owner="worker-a")
        assert claim is not None
        forged = HarnessRuntimeExecutionV1.model_construct(**prepared.model_dump())
        with self.assertRaises(Exception):
            self.fixture.repository.terminalize(claim=claim, trace=forged.terminal_trace)  # type: ignore[arg-type]

    def test_rollback_callback_is_delegated_without_fabricating_evidence(self) -> None:
        base = self.fixture.adapter()
        calls = {"rollback": 0}
        rollback = SimpleNamespace(status=HarnessCommitStatus.ROLLED_BACK, payload_digest=None)
        def compensate(_output, _error):
            calls["rollback"] += 1
            return rollback
        adapter = HarnessRuntimeStageAdapter(**{**base.__dict__, "commit": lambda _output: (_ for _ in ()).throw(RuntimeError("commit_failed")), "rollback": compensate})
        with self.assertRaises(HarnessRuntimeCommitOutcomeUnknown):
            HarnessOperationRuntime(repository=self.fixture.repository).execute(request=self.fixture.request, adapter=adapter, claim_owner="worker-a")
        self.assertEqual(calls["rollback"], 1)

    def test_protected_artifact_replay_requires_exact_digest(self) -> None:
        ref = SimpleNamespace(artifact_id="artifact-1", payload_digest="a" * 64)
        request = SimpleNamespace(context=SimpleNamespace(snapshot_refs=[ref]), operation_binding=self.fixture.binding)
        resolver = SimpleNamespace(resolve=lambda **_kwargs: (HarnessRuntimeResolvedArtifact("artifact-1", "a" * 64, {"secret": "protected"}),))
        runtime = HarnessOperationRuntime(repository=self.fixture.repository, artifact_resolver=resolver)
        self.assertEqual(runtime._resolve_artifacts(request)["artifact-1"], {"secret": "protected"})
        bad_request = SimpleNamespace(context=SimpleNamespace(snapshot_refs=[SimpleNamespace(artifact_id="artifact-1", payload_digest="b" * 64)]), operation_binding=self.fixture.binding)
        with self.assertRaises(HarnessRuntimeError):
            runtime._resolve_artifacts(bad_request)

    def test_expired_claim_recovery_distinguishes_unstarted_and_ambiguous(self) -> None:
        prepared = self.fixture.repository.prepare(
            operation_binding=self.fixture.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            context=self.fixture.context,
        )
        first = self.fixture.repository.claim(
            trace_id=prepared.trace_id,
            claim_owner="worker-a",
            lease_seconds=30,
        )
        assert first is not None
        self._expire(prepared.trace_id)
        safe = self.fixture.repository.inspect_recovery(prepared.trace_id)
        self.assertEqual(
            safe.disposition,
            HarnessRuntimeRecoveryDisposition.SAFE_TO_RESUME,
        )

        second = self.fixture.repository.claim(
            trace_id=prepared.trace_id,
            claim_owner="worker-b",
            lease_seconds=30,
        )
        assert second is not None
        self.fixture.repository.mark_execution_started(second)
        self._expire(prepared.trace_id)
        ambiguous = self.fixture.repository.inspect_recovery(prepared.trace_id)
        self.assertEqual(
            ambiguous.disposition,
            HarnessRuntimeRecoveryDisposition.READ_BACK_REQUIRED,
        )
        self.assertTrue(ambiguous.execution_started)

    def test_prepare_identity_is_immutable(self) -> None:
        self.fixture.repository.prepare(
            operation_binding=self.fixture.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            context=self.fixture.context,
        )
        with self.assertRaises(HarnessRuntimeIdentityConflict):
            self.fixture.repository.prepare(
                operation_binding=self.fixture.binding,
                stage=HarnessStage.TAVERN_ACTOR_REPLY,
                trace_slot=0,
                adapter_contract=ADAPTER_CONTRACT,
                trace_contract=HarnessContractRef(
                    name="TavernActorReply",
                    version="tavern-actor-reply-v999",
                ),
                context=self.fixture.context,
            )

    def _expire(self, trace_id: str) -> None:
        with self.fixture.database.session() as session:
            row = session.get(HarnessRuntimeExecutionRow, trace_id)
            assert row is not None
            row.lease_expires_at = "2000-01-01T00:00:00.000000+00:00"


if __name__ == "__main__":
    unittest.main()
