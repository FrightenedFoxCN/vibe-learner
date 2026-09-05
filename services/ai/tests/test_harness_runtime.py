from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import ClassVar
import unittest

from pydantic import BaseModel, ConfigDict

from app.models.harness import (
    HarnessAttemptPhase,
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessContractRef,
    HarnessSafeManifest,
    HarnessStage,
    HarnessStatus,
    HarnessWorkflow,
    HarnessCommitEvidenceV3,
    HarnessCommitStatus,
    HarnessContractRef,
    HarnessDigestAlgorithm,
    HarnessDigestScope,
    HarnessResourceRefV3,
    HarnessResourceType,
)
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.models.harness_runtime import HarnessRuntimeExecutionV1, HarnessRuntimeRecoveryDisposition
from app.persistence.database import Database
from app.persistence.harness_runtime_repository import (
    HarnessRuntimeIdentityConflict,
    HarnessRuntimeRepository,
)
from app.persistence.models import (
    HarnessOperationBindingRow,
    HarnessRuntimeExecutionRow,
)
from app.services.harness_context import build_harness_context
from app.services.harness_runtime import (
    HarnessOperationRuntime,
    HarnessRuntimeRequest,
    HarnessRuntimeStageAdapter,
    HarnessRuntimeValidationResult,
    HarnessRuntimeCommitOutcomeUnknown,
    HarnessRuntimeResolvedArtifact,
    HarnessRuntimeError,
)
from app.services.harness_runtime import HarnessRuntimeArtifactResolver, HarnessRuntimeResolvedArtifact


ADAPTER_CONTRACT = HarnessContractRef(
    name="TavernActorWorkflowAdapter",
    version="tavern-actor-workflow-adapter-v1",
)
TRACE_CONTRACT = HarnessContractRef(
    name="TavernActorReply",
    version="tavern-actor-reply-v1",
)
INPUT_CONTRACT = HarnessContractRef(
    name="TavernActorInputManifest",
    version="tavern-actor-input-manifest-v1",
)
PROMPT_CONTRACT = HarnessContractRef(
    name="TavernActorPrompt",
    version="tavern-actor-v1",
)
POLICY_CONTRACT = HarnessContractRef(
    name="TavernHarnessPolicy",
    version="tavern-harness-v1",
)


class _InputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"mode", "room_revision", "target_ids"}
    )

    mode: str
    room_revision: int
    target_ids: list[str]


class _Output(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    value: str


class HarnessRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(
            f"sqlite:///{Path(self.temp.name) / 'runtime.sqlite3'}"
        )
        self.database.create_schema()
        self.repository = HarnessRuntimeRepository(self.database)
        self.binding = HarnessOperationBindingV1(
            harness_operation_id="harness-operation-0123456789abcdef0123456789abcdef",
            domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
            domain_operation_id="tavern-runtime-test-run",
            workflow=HarnessWorkflow.TAVERN,
            entry_stage=HarnessStage.TAVERN_ACTOR_REPLY,
            admitted_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
        with self.database.session() as session:
            session.add(
                HarnessOperationBindingRow(
                    **self.binding.model_dump(mode="json", exclude_none=False)
                )
            )
        self.context = build_harness_context(
            workflow=HarnessWorkflow.TAVERN,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            operation_binding=self.binding,
            input_contract=INPUT_CONTRACT,
            input_manifest=_InputManifest(
                mode="direct",
                room_revision=0,
                target_ids=["persona-a"],
            ),
            subject_refs=[],
            prompt_contract=PROMPT_CONTRACT,
            policy_contract=POLICY_CONTRACT,
        )
        self.request = HarnessRuntimeRequest(
            operation_binding=self.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            context=self.context,
        )

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def _adapter(self, calls: dict[str, int] | None = None):
        counts = calls if calls is not None else {}

        def generate(_context, _artifacts):
            counts["generate"] = counts.get("generate", 0) + 1
            return {"value": "valid"}

        def decode(raw):
            counts["decode"] = counts.get("decode", 0) + 1
            if not isinstance(raw, dict) or raw.get("value") != "valid":
                raise ValueError("fixture_decode_failed")
            return _Output.model_validate(raw)

        def validate(output):
            counts["validate"] = counts.get("validate", 0) + 1
            return HarnessRuntimeValidationResult(
                output=output,
                checks=(
                    HarnessCheckV2(
                        name="fixture_value",
                        status=HarnessCheckStatus.PASSED,
                        code="",
                        message="fixture output is valid",
                    ),
                ),
            )

        return HarnessRuntimeStageAdapter(
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            generate=generate,
            decode=decode,
            validate=validate,
        )

    def test_execute_persists_terminal_trace_and_duplicate_is_read_back(self) -> None:
        calls: dict[str, int] = {}
        runtime = HarnessOperationRuntime(repository=self.repository)
        first = runtime.execute(
            request=self.request,
            adapter=self._adapter(calls),
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
            repository=HarnessRuntimeRepository(self.database)
        )
        duplicate = restarted.execute(
            request=self.request,
            adapter=self._adapter(calls),
            claim_owner="worker-b",
        )
        self.assertEqual(duplicate, first)
        self.assertEqual(calls, {"generate": 1, "decode": 1, "validate": 1})

    def test_decode_failure_repairs_once_and_records_ordered_attempts(self) -> None:
        calls = {"repair": 0}

        def repair(_raw, _error, _index):
            calls["repair"] += 1
            return {"value": "valid"}

        base = self._adapter(calls)
        adapter = HarnessRuntimeStageAdapter(
            adapter_contract=base.adapter_contract,
            trace_contract=base.trace_contract,
            generate=lambda _context, _artifacts: {"value": "invalid"},
            decode=base.decode,
            validate=base.validate,
            repair=repair,
            recovery_strategy="repair_fixture_payload",
        )
        result = HarnessOperationRuntime(repository=self.repository).execute(
            request=self.request,
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
        adapter = self._adapter()
        failed = HarnessRuntimeStageAdapter(
            adapter_contract=adapter.adapter_contract,
            trace_contract=adapter.trace_contract,
            generate=lambda _context, _artifacts: (_ for _ in ()).throw(
                RuntimeError("fixture_generate_failed")
            ),
            decode=adapter.decode,
            validate=adapter.validate,
        )
        result = HarnessOperationRuntime(repository=self.repository).execute(
            request=self.request,
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
        prepared = self.repository.prepare(operation_binding=self.binding, stage=HarnessStage.TAVERN_ACTOR_REPLY, trace_slot=0, adapter_contract=ADAPTER_CONTRACT, trace_contract=TRACE_CONTRACT, context=self.context)
        for index in range(3):
            claim = self.repository.claim(trace_id=prepared.trace_id, claim_owner=f"worker-{index}")
            self.assertIsNotNone(claim)
            self._expire(prepared.trace_id)
        self.assertEqual(self.repository.inspect_recovery(prepared.trace_id).disposition, HarnessRuntimeRecoveryDisposition.ATTEMPTS_EXHAUSTED)
        self.assertIsNone(self.repository.claim(trace_id=prepared.trace_id, claim_owner="worker-final", recovery=True))

    def test_claim_renewal_extends_database_lease_and_preserves_fence(self) -> None:
        prepared = self.repository.prepare(
            operation_binding=self.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            context=self.context,
        )
        claim = self.repository.claim(
            trace_id=prepared.trace_id,
            claim_owner="worker-a",
            lease_seconds=1,
        )
        assert claim is not None
        renewed = self.repository.renew(claim=claim, lease_seconds=30)
        self.assertGreater(renewed.lease_expires_at, claim.lease_expires_at)
        self.assertEqual(renewed.claim_token, claim.claim_token)
        self._expire(prepared.trace_id)
        with self.assertRaises(HarnessRuntimeError):
            self.repository.renew(claim=renewed, lease_seconds=30)

    def test_wall_time_budget_fails_closed_after_long_callback(self) -> None:
        current = [datetime(2026, 9, 3, tzinfo=UTC)]

        def clock() -> datetime:
            return current[0]

        def generate(_context, _artifacts):
            current[0] += timedelta(minutes=4)
            return {"value": "valid"}

        base = self._adapter()
        result = HarnessOperationRuntime(
            repository=self.repository,
            clock=clock,
        ).execute(
            request=self.request,
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
        prepared = self.repository.prepare(operation_binding=self.binding, stage=HarnessStage.TAVERN_ACTOR_REPLY, trace_slot=0, adapter_contract=ADAPTER_CONTRACT, trace_contract=TRACE_CONTRACT, context=self.context)
        claim = self.repository.claim(trace_id=prepared.trace_id, claim_owner="worker-a")
        assert claim is not None
        forged = HarnessRuntimeExecutionV1.model_construct(**prepared.model_dump())
        with self.assertRaises(Exception):
            self.repository.terminalize(claim=claim, trace=forged.terminal_trace)  # type: ignore[arg-type]

    def test_rollback_callback_is_delegated_without_fabricating_evidence(self) -> None:
        base = self._adapter()
        calls = {"rollback": 0}
        rollback = SimpleNamespace(status=HarnessCommitStatus.ROLLED_BACK, payload_digest=None)
        def compensate(_output, _error):
            calls["rollback"] += 1
            return rollback
        adapter = HarnessRuntimeStageAdapter(**{**base.__dict__, "commit": lambda _output: (_ for _ in ()).throw(RuntimeError("commit_failed")), "rollback": compensate})
        with self.assertRaises(HarnessRuntimeCommitOutcomeUnknown):
            HarnessOperationRuntime(repository=self.repository).execute(request=self.request, adapter=adapter, claim_owner="worker-a")
        self.assertEqual(calls["rollback"], 1)

    def test_protected_artifact_replay_requires_exact_digest(self) -> None:
        ref = SimpleNamespace(artifact_id="artifact-1", payload_digest="a" * 64)
        request = SimpleNamespace(context=SimpleNamespace(snapshot_refs=[ref]), operation_binding=self.binding)
        resolver = SimpleNamespace(resolve=lambda **_kwargs: (HarnessRuntimeResolvedArtifact("artifact-1", "a" * 64, {"secret": "protected"}),))
        runtime = HarnessOperationRuntime(repository=self.repository, artifact_resolver=resolver)
        self.assertEqual(runtime._resolve_artifacts(request)["artifact-1"], {"secret": "protected"})
        bad_request = SimpleNamespace(context=SimpleNamespace(snapshot_refs=[SimpleNamespace(artifact_id="artifact-1", payload_digest="b" * 64)]), operation_binding=self.binding)
        with self.assertRaises(HarnessRuntimeError):
            runtime._resolve_artifacts(bad_request)

    def test_expired_claim_recovery_distinguishes_unstarted_and_ambiguous(self) -> None:
        prepared = self.repository.prepare(
            operation_binding=self.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            context=self.context,
        )
        first = self.repository.claim(
            trace_id=prepared.trace_id,
            claim_owner="worker-a",
            lease_seconds=30,
        )
        assert first is not None
        self._expire(prepared.trace_id)
        safe = self.repository.inspect_recovery(prepared.trace_id)
        self.assertEqual(
            safe.disposition,
            HarnessRuntimeRecoveryDisposition.SAFE_TO_RESUME,
        )

        second = self.repository.claim(
            trace_id=prepared.trace_id,
            claim_owner="worker-b",
            lease_seconds=30,
        )
        assert second is not None
        self.repository.mark_execution_started(second)
        self._expire(prepared.trace_id)
        ambiguous = self.repository.inspect_recovery(prepared.trace_id)
        self.assertEqual(
            ambiguous.disposition,
            HarnessRuntimeRecoveryDisposition.READ_BACK_REQUIRED,
        )
        self.assertTrue(ambiguous.execution_started)

    def test_prepare_identity_is_immutable(self) -> None:
        self.repository.prepare(
            operation_binding=self.binding,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_slot=0,
            adapter_contract=ADAPTER_CONTRACT,
            trace_contract=TRACE_CONTRACT,
            context=self.context,
        )
        with self.assertRaises(HarnessRuntimeIdentityConflict):
            self.repository.prepare(
                operation_binding=self.binding,
                stage=HarnessStage.TAVERN_ACTOR_REPLY,
                trace_slot=0,
                adapter_contract=ADAPTER_CONTRACT,
                trace_contract=HarnessContractRef(
                    name="TavernActorReply",
                    version="tavern-actor-reply-v999",
                ),
                context=self.context,
            )

    def _expire(self, trace_id: str) -> None:
        with self.database.session() as session:
            row = session.get(HarnessRuntimeExecutionRow, trace_id)
            assert row is not None
            row.lease_expires_at = "2000-01-01T00:00:00.000000+00:00"


if __name__ == "__main__":
    unittest.main()
