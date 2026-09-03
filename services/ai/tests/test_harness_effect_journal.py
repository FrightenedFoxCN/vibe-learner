from __future__ import annotations

from datetime import datetime, timezone
import tempfile
import unittest

from pydantic import BaseModel, ConfigDict
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models.harness import HarnessContractRef, HarnessResourceType
from app.models.harness_effect import (
    HARNESS_EFFECT_ADAPTER_POLICIES,
    HarnessEffectJournalState,
    HarnessEffectTargetRefV1,
    HarnessEffectTerminalEvidenceV1,
    HarnessProviderEffectIdentityV1,
    harness_effect_batch_id,
    harness_effect_id,
)
from app.models.harness_operation import HarnessOperationBindingV1
from app.models.study_chat_effect import StudyMemoryUpsertEffectProposalV1
from app.persistence.database import Database
from app.persistence.harness_effect_repository import (
    HarnessEffectClaimFenced,
    HarnessEffectJournalError,
    HarnessEffectJournalRepository,
)
from app.persistence.models import HarnessEffectJournalRow, HarnessOperationBindingRow


OPERATION_ID = f"harness-operation-{'1' * 32}"
PROPOSAL_CONTRACT = HarnessContractRef(
    name="StudyMemoryUpsertEffectProposalV1",
    version="study-memory-upsert-effect-v1",
)
PROJECTION_CONTRACT = HarnessContractRef(
    name="StudyMemoryUpsertCommittedProjectionV1",
    version="study-memory-upsert-committed-projection-v1",
)
COMPENSATION_CONTRACT = HarnessContractRef(
    name="StudyAttachmentCleanupEvidenceV1",
    version="study-attachment-cleanup-evidence-v1",
)


class _Projection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    value: str


class HarnessEffectJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.database = Database(f"sqlite:///{self._tmp.name}/effects.sqlite3")
        self.database.create_schema()
        self.repository = HarnessEffectJournalRepository(self.database)
        self.binding = HarnessOperationBindingV1(
            harness_operation_id=OPERATION_ID,
            domain_operation_kind="study_chat",
            domain_operation_id="study-chat-op-effect-test",
            workflow="study_chat",
            entry_stage="study_chat_reply",
            parent_harness_operation_id=None,
            admitted_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        )
        with self.database.session() as session:
            session.add(
                HarnessOperationBindingRow(
                    harness_operation_id=OPERATION_ID,
                    schema_name="HarnessOperationBindingV1",
                    schema_version="harness-operation-binding-v1",
                    domain_operation_kind="study_chat",
                    domain_operation_id="study-chat-op-effect-test",
                    workflow="study_chat",
                    entry_stage="study_chat_reply",
                    parent_harness_operation_id=None,
                    admitted_at="2026-09-03T00:00:00+00:00",
                )
            )

    def tearDown(self) -> None:
        self.database.dispose()
        self._tmp.cleanup()

    def _prepare(self, *, slot: int = 0, adapter_name: str = "study_memory_upsert"):
        return self.repository.prepare_effect(
            operation_binding=self.binding,
            slot=slot,
            adapter=HARNESS_EFFECT_ADAPTER_POLICIES[adapter_name],
            proposal_contract=PROPOSAL_CONTRACT,
            target_refs=(
                HarnessEffectTargetRefV1(
                    resource_type=HarnessResourceType.STUDY_SESSION,
                    resource_id="session-effect-test",
                ),
            ),
            proposal=StudyMemoryUpsertEffectProposalV1(key="goal", content="review"),
        )

    def test_prepare_retry_keeps_operation_slot_identity_and_rejects_divergence(self) -> None:
        first = self._prepare()
        replay = self._prepare()
        self.assertEqual(first, replay)
        self.assertEqual(first.effect_batch_id, harness_effect_batch_id(OPERATION_ID))
        self.assertEqual(first.effect_id, harness_effect_id(OPERATION_ID, 0))
        self.assertEqual(first.state, HarnessEffectJournalState.PREPARED)

        with self.assertRaisesRegex(HarnessEffectJournalError, "retry_identity_mismatch"):
            self.repository.prepare_effect(
                operation_binding=self.binding,
                slot=0,
                adapter=HARNESS_EFFECT_ADAPTER_POLICIES["study_memory_upsert"],
                proposal_contract=PROPOSAL_CONTRACT,
                target_refs=first.target_refs,
                proposal=StudyMemoryUpsertEffectProposalV1(
                    key="goal",
                    content="changed",
                ),
            )
        with self.assertRaises(IntegrityError):
            with self.database.session() as session:
                session.execute(
                    update(HarnessEffectJournalRow)
                    .where(HarnessEffectJournalRow.effect_id == first.effect_id)
                    .values(adapter_version="forged-adapter-v2")
                )

    def test_claim_uses_database_lease_and_fences_old_owner(self) -> None:
        entry = self._prepare()
        claim = self.repository.claim_effect(
            effect_id=entry.effect_id,
            claim_owner="worker-one",
        )
        assert claim is not None
        self.assertIsNone(
            self.repository.claim_effect(
                effect_id=entry.effect_id,
                claim_owner="worker-two",
            )
        )
        forged = claim.__class__(
            effect_id=claim.effect_id,
            claim_owner="worker-two",
            claim_count=claim.claim_count,
            lease_expires_at=claim.lease_expires_at,
        )
        with self.assertRaises(HarnessEffectClaimFenced):
            self.repository.mark_commit_started(claim=forged)

    def test_database_commit_requires_exact_read_back_and_is_atomic_with_caller(self) -> None:
        entry = self._prepare()
        try:
            with self.database.session() as session:
                self.repository.commit_with_read_back_in_session(
                    session,
                    effect_id=entry.effect_id,
                    projection_contract=PROJECTION_CONTRACT,
                    projection=_Projection(value="committed"),
                )
                raise RuntimeError("rollback business transaction")
        except RuntimeError:
            pass
        self.assertEqual(
            self.repository.list_effects(harness_operation_id=OPERATION_ID)[0].state,
            HarnessEffectJournalState.PREPARED,
        )

        evidence = self.repository.commit_with_read_back(
            effect_id=entry.effect_id,
            projection_contract=PROJECTION_CONTRACT,
            projection=_Projection(value="committed"),
        )
        self.assertEqual(evidence.outcome.value, "committed")
        self.assertEqual(evidence.read_back_outcome.value, "verified")
        self.assertIsNotNone(evidence.read_back_started_at)
        self.assertEqual(len(evidence.evidence_digest), 64)

    def test_partial_file_write_needs_compensation_and_failure_stays_uncertain(self) -> None:
        entry = self._prepare(adapter_name="study_attachment_stage")
        claim = self.repository.claim_effect(effect_id=entry.effect_id)
        assert claim is not None
        self.repository.mark_commit_started(claim=claim)
        self.repository.mark_compensation_started(claim=claim)
        cleanup = _Projection(value="operation directory removed")
        evidence = self.repository.terminalize_not_committed(
            effect_id=entry.effect_id,
            compensation_contract=COMPENSATION_CONTRACT,
            compensation_evidence=cleanup,
        )
        self.assertEqual(evidence.outcome.value, "not_committed")
        self.assertEqual(evidence.compensation_outcome.value, "succeeded")

        second = self._prepare(slot=1, adapter_name="study_attachment_stage")
        second_claim = self.repository.claim_effect(effect_id=second.effect_id)
        assert second_claim is not None
        self.repository.mark_commit_started(claim=second_claim)
        self.repository.mark_compensation_started(claim=second_claim)
        failed = self.repository.terminalize_uncertain(
            effect_id=second.effect_id,
            failure_code="attachment_cleanup_failed",
            compensation_contract=COMPENSATION_CONTRACT,
            compensation_evidence=_Projection(value="partial path remains"),
        )
        self.assertEqual(failed.outcome.value, "uncertain")
        self.assertEqual(failed.compensation_outcome.value, "failed")

    def test_provider_timeout_after_start_is_uncertain_and_cannot_claim_commit(self) -> None:
        entry = self._prepare(adapter_name="study_provider_execution")
        claim = self.repository.claim_effect(effect_id=entry.effect_id)
        assert claim is not None
        provider = HarnessProviderEffectIdentityV1(
            provider_name="fixture-provider",
            request_id="provider-request-1",
            request_digest="a" * 64,
            idempotency_supported=False,
            read_back_supported=False,
        )
        self.repository.mark_commit_started(
            claim=claim,
            provider_effect_identity=provider,
        )
        with self.assertRaisesRegex(ValueError, "external_commit_unverifiable"):
            self.repository.commit_with_read_back(
                effect_id=entry.effect_id,
                projection_contract=PROJECTION_CONTRACT,
                projection=_Projection(value="forged provider commit"),
                provider_effect_identity=provider,
            )
        evidence = self.repository.terminalize_uncertain(
            effect_id=entry.effect_id,
            failure_code="provider_timeout_after_start",
        )
        self.assertEqual(evidence.outcome.value, "uncertain")
        self.assertEqual(evidence.read_back_outcome.value, "unsupported")

    def test_forged_terminal_identity_is_rejected(self) -> None:
        entry = self._prepare()
        evidence = self.repository.commit_with_read_back(
            effect_id=entry.effect_id,
            projection_contract=PROJECTION_CONTRACT,
            projection=_Projection(value="committed"),
        )
        forged = evidence.model_dump(mode="json", exclude_none=False)
        forged["effect_id"] = f"harness-effect-{'f' * 32}"
        with self.assertRaisesRegex(ValueError, "harness_effect_identity_mismatch"):
            HarnessEffectTerminalEvidenceV1.model_validate(forged)

    def test_expired_claim_recovery_terminalizes_without_blind_replay(self) -> None:
        unstarted = self._prepare(slot=0)
        external = self._prepare(slot=1, adapter_name="study_provider_execution")
        interrupted_cleanup = self._prepare(
            slot=2,
            adapter_name="study_attachment_stage",
        )
        first_claim = self.repository.claim_effect(effect_id=unstarted.effect_id)
        second_claim = self.repository.claim_effect(effect_id=external.effect_id)
        third_claim = self.repository.claim_effect(effect_id=interrupted_cleanup.effect_id)
        assert first_claim is not None and second_claim is not None and third_claim is not None
        self.repository.mark_commit_started(
            claim=second_claim,
            provider_effect_identity=HarnessProviderEffectIdentityV1(
                provider_name="fixture-provider",
                request_id="provider-recovery-request",
                request_digest="b" * 64,
                idempotency_supported=False,
                read_back_supported=False,
            ),
        )
        self.repository.mark_commit_started(claim=third_claim)
        self.repository.mark_compensation_started(claim=third_claim)
        with self.database.session() as session:
            session.execute(
                update(HarnessEffectJournalRow)
                .where(
                    HarnessEffectJournalRow.effect_id.in_(
                        (unstarted.effect_id, external.effect_id)
                        + (interrupted_cleanup.effect_id,)
                    )
                )
                .values(lease_expires_at="2000-01-01T00:00:00.000000+00:00")
            )

        recovered = self.repository.recover_expired_claims()
        self.assertEqual(
            [item.outcome.value for item in recovered],
            ["not_committed", "uncertain", "uncertain"],
        )
        self.assertEqual(
            recovered[1].failure_code,
            "harness_effect_worker_lease_expired",
        )
        self.assertEqual(recovered[2].compensation_outcome.value, "incomplete")


if __name__ == "__main__":
    unittest.main()
