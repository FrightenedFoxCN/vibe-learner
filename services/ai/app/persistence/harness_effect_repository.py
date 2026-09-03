from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.harness import HarnessContractRef, canonical_harness_digest
from app.models.harness_effect import (
    HARNESS_EFFECT_JOURNAL_ENTRY_SCHEMA_VERSION,
    HARNESS_EFFECT_ADAPTER_POLICIES,
    HarnessEffectAdapterRefV1,
    HarnessEffectCompensationOutcome,
    HarnessEffectJournalEntryV1,
    HarnessEffectJournalState,
    HarnessEffectReadBackOutcome,
    HarnessEffectTargetRefV1,
    HarnessEffectTerminalEvidenceV1,
    HarnessEffectTerminalOutcome,
    HarnessProviderEffectIdentityV1,
    harness_effect_batch_id,
    harness_effect_id,
)
from app.models.harness_operation import HarnessOperationBindingV1
from app.persistence.database import Database
from app.persistence.harness_operation_repository import HarnessOperationBindingRepository
from app.persistence.models import (
    HarnessEffectBatchRow,
    HarnessEffectJournalRow,
    HarnessOperationBindingRow,
)


MAX_EFFECT_SLOTS = 128
MAX_EFFECT_CLAIMS = 3


@dataclass(frozen=True)
class HarnessEffectClaim:
    effect_id: str
    claim_owner: str
    claim_count: int
    lease_expires_at: datetime


class HarnessEffectJournalRepository:
    """Durable effect preparation, fencing, recovery, and terminal evidence."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.harness_operations = HarnessOperationBindingRepository(database)

    def prepare_effect(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        slot: int,
        adapter: HarnessEffectAdapterRefV1,
        proposal_contract: HarnessContractRef,
        target_refs: Iterable[HarnessEffectTargetRefV1],
        proposal: BaseModel,
    ) -> HarnessEffectJournalEntryV1:
        if slot < 0 or slot >= MAX_EFFECT_SLOTS:
            raise HarnessEffectJournalError("harness_effect_slot_out_of_bounds")
        if proposal.model_config.get("extra") != "forbid":
            raise HarnessEffectJournalError("harness_effect_proposal_extra_forbid_required")
        registered = HARNESS_EFFECT_ADAPTER_POLICIES.get(adapter.name)
        if registered is None or registered != adapter:
            raise HarnessEffectJournalError("harness_effect_adapter_unregistered")
        canonical_targets = tuple(
            sorted(
                target_refs,
                key=lambda item: (item.resource_type.value, item.resource_id),
            )
        )
        if not canonical_targets:
            raise HarnessEffectJournalError("harness_effect_target_required")
        proposal_digest = canonical_harness_digest(
            proposal.model_dump(mode="json", exclude_none=False)
        )
        batch_id = harness_effect_batch_id(operation_binding.harness_operation_id)
        effect_id = harness_effect_id(operation_binding.harness_operation_id, slot)
        with self.database.session() as session:
            authoritative = session.get(
                HarnessOperationBindingRow,
                operation_binding.harness_operation_id,
            )
            if authoritative is None or (
                authoritative.domain_operation_kind
                != operation_binding.domain_operation_kind.value
                or authoritative.domain_operation_id
                != operation_binding.domain_operation_id
                or authoritative.workflow != operation_binding.workflow.value
                or authoritative.entry_stage != operation_binding.entry_stage.value
                or authoritative.parent_harness_operation_id
                != operation_binding.parent_harness_operation_id
            ):
                raise HarnessEffectJournalError("harness_effect_operation_binding_invalid")
            now = _database_utc_now(session)
            now_wire = _wire(now)
            batch = session.get(HarnessEffectBatchRow, batch_id)
            if batch is None:
                batch = HarnessEffectBatchRow(
                    effect_batch_id=batch_id,
                    harness_operation_id=operation_binding.harness_operation_id,
                    max_slots=MAX_EFFECT_SLOTS,
                    sealed_at="",
                    schema_name="HarnessEffectBatchV1",
                    schema_version="harness-effect-batch-v1",
                    created_at=now_wire,
                )
                session.add(batch)
                session.flush()
            elif (
                batch.harness_operation_id != operation_binding.harness_operation_id
                or batch.max_slots != MAX_EFFECT_SLOTS
            ):
                raise HarnessEffectJournalCorrupt("harness_effect_batch_identity_mismatch")

            existing = session.get(HarnessEffectJournalRow, effect_id)
            if existing is not None:
                self._require_retry_identity(
                    existing,
                    batch_id=batch_id,
                    operation_id=operation_binding.harness_operation_id,
                    slot=slot,
                    adapter=adapter,
                    proposal_contract=proposal_contract,
                    proposal_digest=proposal_digest,
                    target_refs=canonical_targets,
                )
                return _from_row(existing)
            if batch.sealed_at:
                raise HarnessEffectJournalError("harness_effect_batch_sealed")
            row = HarnessEffectJournalRow(
                effect_id=effect_id,
                effect_batch_id=batch_id,
                harness_operation_id=operation_binding.harness_operation_id,
                slot=slot,
                adapter_name=adapter.name,
                adapter_version=adapter.version,
                boundary_kind=adapter.boundary_kind.value,
                prepare_policy=adapter.prepare_policy.value,
                commit_policy=adapter.commit_policy.value,
                compensation_policy=adapter.compensation_policy.value,
                read_back_policy=adapter.read_back_policy.value,
                proposal_contract_name=proposal_contract.name,
                proposal_contract_version=proposal_contract.version,
                proposal_digest=proposal_digest,
                target_refs=[item.model_dump(mode="json") for item in canonical_targets],
                state=HarnessEffectJournalState.PREPARED.value,
                claim_owner="",
                claim_count=0,
                lease_expires_at="",
                commit_started_at="",
                read_back_started_at="",
                compensation_started_at="",
                provider_effect_identity=None,
                terminal_outcome=None,
                terminal_evidence=None,
                schema_name="HarnessEffectJournalEntryV1",
                schema_version=HARNESS_EFFECT_JOURNAL_ENTRY_SCHEMA_VERSION,
                prepared_at=now_wire,
                updated_at=now_wire,
                terminal_at="",
            )
            session.add(row)
            session.flush()
            return _from_row(row)

    def seal_batch(self, *, harness_operation_id: str) -> tuple[HarnessEffectJournalEntryV1, ...]:
        batch_id = harness_effect_batch_id(harness_operation_id)
        with self.database.session() as session:
            batch = session.get(HarnessEffectBatchRow, batch_id)
            if batch is None or batch.harness_operation_id != harness_operation_id:
                raise HarnessEffectJournalError("harness_effect_batch_not_found")
            rows = list(
                session.scalars(
                    select(HarnessEffectJournalRow)
                    .where(HarnessEffectJournalRow.effect_batch_id == batch_id)
                    .order_by(HarnessEffectJournalRow.slot)
                )
            )
            if not rows or [row.slot for row in rows] != list(range(len(rows))):
                raise HarnessEffectJournalError("harness_effect_batch_slots_not_contiguous")
            if not batch.sealed_at:
                batch.sealed_at = _wire(_database_utc_now(session))
            return tuple(_from_row(row) for row in rows)

    def list_effects(self, *, harness_operation_id: str) -> tuple[HarnessEffectJournalEntryV1, ...]:
        with self.database.session() as session:
            rows = session.scalars(
                select(HarnessEffectJournalRow)
                .where(HarnessEffectJournalRow.harness_operation_id == harness_operation_id)
                .order_by(HarnessEffectJournalRow.slot)
            )
            return tuple(_from_row(row) for row in rows)

    def claim_effect(
        self,
        *,
        effect_id: str,
        lease_seconds: int = 30,
        claim_owner: str | None = None,
    ) -> HarnessEffectClaim | None:
        if lease_seconds < 1 or lease_seconds > 300:
            raise HarnessEffectJournalError("harness_effect_lease_seconds_invalid")
        owner = claim_owner or f"effect-worker-{uuid4().hex}"
        with self.database.session() as session:
            now = _database_utc_now(session)
            now_wire = _wire(now)
            row = session.get(HarnessEffectJournalRow, effect_id)
            if row is None:
                raise HarnessEffectJournalError("harness_effect_not_found")
            if row.state == HarnessEffectJournalState.TERMINAL.value:
                return None
            if row.claim_count >= MAX_EFFECT_CLAIMS:
                return None
            eligible = row.state == HarnessEffectJournalState.PREPARED.value or (
                row.state == HarnessEffectJournalState.CLAIMED.value
                and bool(row.lease_expires_at)
                and row.lease_expires_at <= now_wire
            )
            if not eligible:
                return None
            expires_at = now + timedelta(seconds=lease_seconds)
            next_count = row.claim_count + 1
            claimed = session.execute(
                update(HarnessEffectJournalRow)
                .where(
                    HarnessEffectJournalRow.effect_id == effect_id,
                    HarnessEffectJournalRow.state == row.state,
                    HarnessEffectJournalRow.claim_count == row.claim_count,
                    HarnessEffectJournalRow.lease_expires_at == row.lease_expires_at,
                )
                .values(
                    state=HarnessEffectJournalState.CLAIMED.value,
                    claim_owner=owner,
                    claim_count=next_count,
                    lease_expires_at=_wire(expires_at),
                    updated_at=now_wire,
                )
            )
            if claimed.rowcount != 1:
                return None
            return HarnessEffectClaim(
                effect_id=effect_id,
                claim_owner=owner,
                claim_count=next_count,
                lease_expires_at=expires_at,
            )

    def mark_commit_started(
        self,
        *,
        claim: HarnessEffectClaim,
        provider_effect_identity: HarnessProviderEffectIdentityV1 | None = None,
    ) -> HarnessEffectJournalEntryV1:
        with self.database.session() as session:
            row, now = self._require_active_claim(session, claim)
            adapter = _adapter_from_row(row)
            if provider_effect_identity is not None and adapter.boundary_kind.value != "external_call":
                raise HarnessEffectJournalError("harness_effect_provider_identity_boundary_mismatch")
            if adapter.boundary_kind.value == "external_call" and provider_effect_identity is None:
                raise HarnessEffectJournalError("harness_effect_provider_identity_required")
            if row.commit_started_at:
                if row.provider_effect_identity != _provider_payload(provider_effect_identity):
                    raise HarnessEffectJournalError("harness_effect_provider_identity_mismatch")
                return _from_row(row)
            row.commit_started_at = _wire(now)
            row.provider_effect_identity = _provider_payload(provider_effect_identity)
            row.updated_at = _wire(now)
            session.flush()
            return _from_row(row)

    def mark_read_back_started(
        self,
        *,
        claim: HarnessEffectClaim,
    ) -> HarnessEffectJournalEntryV1:
        with self.database.session() as session:
            row, now = self._require_active_claim(session, claim)
            if not row.commit_started_at:
                raise HarnessEffectJournalError("harness_effect_read_back_before_commit")
            if not row.read_back_started_at:
                row.read_back_started_at = _wire(now)
                row.updated_at = _wire(now)
                session.flush()
            return _from_row(row)

    def mark_compensation_started(
        self,
        *,
        claim: HarnessEffectClaim,
    ) -> HarnessEffectJournalEntryV1:
        with self.database.session() as session:
            row, now = self._require_active_claim(session, claim)
            adapter = _adapter_from_row(row)
            if not row.commit_started_at:
                raise HarnessEffectJournalError("harness_effect_compensation_before_commit")
            if adapter.compensation_policy.value == "not_applicable":
                raise HarnessEffectJournalError("harness_effect_compensation_unsupported")
            if not row.compensation_started_at:
                row.compensation_started_at = _wire(now)
                row.updated_at = _wire(now)
                session.flush()
            return _from_row(row)

    def commit_with_read_back(
        self,
        *,
        effect_id: str,
        projection_contract: HarnessContractRef,
        projection: BaseModel,
        provider_effect_identity: HarnessProviderEffectIdentityV1 | None = None,
    ) -> HarnessEffectTerminalEvidenceV1:
        with self.database.session() as session:
            return self.commit_with_read_back_in_session(
                session,
                effect_id=effect_id,
                projection_contract=projection_contract,
                projection=projection,
                provider_effect_identity=provider_effect_identity,
            )

    def commit_with_read_back_in_session(
        self,
        session: Session,
        *,
        effect_id: str,
        projection_contract: HarnessContractRef,
        projection: BaseModel,
        provider_effect_identity: HarnessProviderEffectIdentityV1 | None = None,
    ) -> HarnessEffectTerminalEvidenceV1:
        row = session.get(HarnessEffectJournalRow, effect_id)
        if row is None:
            raise HarnessEffectJournalError("harness_effect_not_found")
        if row.state == HarnessEffectJournalState.TERMINAL.value:
            evidence = _terminal_from_row(row)
            if evidence.outcome != HarnessEffectTerminalOutcome.COMMITTED:
                raise HarnessEffectJournalError("harness_effect_terminal_conflict")
            return evidence
        adapter = _adapter_from_row(row)
        provider = provider_effect_identity or _provider_from_row(row)
        now = _database_utc_now(session)
        started_at = _parse(row.commit_started_at) if row.commit_started_at else now
        read_back_started_at = (
            _parse(row.read_back_started_at) if row.read_back_started_at else now
        )
        evidence = _build_terminal_evidence(
            row,
            outcome=HarnessEffectTerminalOutcome.COMMITTED,
            terminal_at=now,
            commit_started_at=started_at,
            provider_effect_identity=provider,
            read_back_outcome=HarnessEffectReadBackOutcome.VERIFIED,
            read_back_started_at=read_back_started_at,
            committed_projection_contract=projection_contract,
            committed_projection_digest=canonical_harness_digest(
                projection.model_dump(mode="json", exclude_none=False)
            ),
            read_back_at=now,
        )
        if adapter.boundary_kind.value == "external_call" and provider is None:
            raise HarnessEffectJournalError("harness_effect_provider_identity_required")
        _persist_terminal(row, evidence)
        session.flush()
        return evidence

    def commit_batch_read_back_in_session(
        self,
        session: Session,
        *,
        harness_operation_id: str,
        projections: Iterable[BaseModel],
    ) -> tuple[HarnessEffectTerminalEvidenceV1, ...]:
        projection_items = tuple(projections)
        rows = list(
            session.scalars(
                select(HarnessEffectJournalRow)
                .where(HarnessEffectJournalRow.harness_operation_id == harness_operation_id)
                .order_by(HarnessEffectJournalRow.slot)
            )
        )
        if not rows:
            return ()
        if len(rows) != len(projection_items) or [row.slot for row in rows] != list(
            range(len(rows))
        ):
            raise HarnessEffectJournalCorrupt("harness_effect_study_batch_mismatch")
        evidence: list[HarnessEffectTerminalEvidenceV1] = []
        for row, projection in zip(rows, projection_items, strict=True):
            schema_name = getattr(projection, "schema_name", "")
            schema_version = getattr(projection, "schema_version", "")
            evidence.append(
                self.commit_with_read_back_in_session(
                    session,
                    effect_id=row.effect_id,
                    projection_contract=HarnessContractRef(
                        name=schema_name,
                        version=schema_version,
                    ),
                    projection=projection,
                )
            )
        return tuple(evidence)

    def terminalize_not_committed(
        self,
        *,
        effect_id: str,
        compensation_contract: HarnessContractRef | None = None,
        compensation_evidence: BaseModel | None = None,
    ) -> HarnessEffectTerminalEvidenceV1:
        with self.database.session() as session:
            row = session.get(HarnessEffectJournalRow, effect_id)
            if row is None:
                raise HarnessEffectJournalError("harness_effect_not_found")
            if row.state == HarnessEffectJournalState.TERMINAL.value:
                evidence = _terminal_from_row(row)
                if evidence.outcome != HarnessEffectTerminalOutcome.NOT_COMMITTED:
                    raise HarnessEffectJournalError("harness_effect_terminal_conflict")
                return evidence
            now = _database_utc_now(session)
            started_at = _parse(row.commit_started_at) if row.commit_started_at else None
            compensation_supplied = (
                compensation_contract is not None and compensation_evidence is not None
            )
            if (compensation_contract is None) != (compensation_evidence is None):
                raise HarnessEffectJournalError("harness_effect_compensation_evidence_incomplete")
            evidence = _build_terminal_evidence(
                row,
                outcome=HarnessEffectTerminalOutcome.NOT_COMMITTED,
                terminal_at=now,
                commit_started_at=started_at,
                read_back_outcome=HarnessEffectReadBackOutcome.NOT_ATTEMPTED,
                compensation_outcome=(
                    HarnessEffectCompensationOutcome.SUCCEEDED
                    if compensation_supplied
                    else HarnessEffectCompensationOutcome.NOT_APPLICABLE
                ),
                compensation_contract=compensation_contract,
                compensation_started_at=(
                    _parse(row.compensation_started_at)
                    if row.compensation_started_at
                    else now if compensation_supplied else None
                ),
                compensation_evidence_digest=(
                    canonical_harness_digest(
                        compensation_evidence.model_dump(mode="json", exclude_none=False)
                    )
                    if compensation_evidence is not None
                    else None
                ),
                compensated_at=now if compensation_supplied else None,
            )
            _persist_terminal(row, evidence)
            session.flush()
            return evidence

    def terminalize_uncertain(
        self,
        *,
        effect_id: str,
        failure_code: str,
        compensation_contract: HarnessContractRef | None = None,
        compensation_evidence: BaseModel | None = None,
    ) -> HarnessEffectTerminalEvidenceV1:
        with self.database.session() as session:
            row = session.get(HarnessEffectJournalRow, effect_id)
            if row is None:
                raise HarnessEffectJournalError("harness_effect_not_found")
            if not row.commit_started_at:
                raise HarnessEffectJournalError("harness_effect_uncertain_before_start")
            if row.state == HarnessEffectJournalState.TERMINAL.value:
                evidence = _terminal_from_row(row)
                if evidence.outcome != HarnessEffectTerminalOutcome.UNCERTAIN:
                    raise HarnessEffectJournalError("harness_effect_terminal_conflict")
                return evidence
            if not failure_code:
                raise HarnessEffectJournalError("harness_effect_failure_code_required")
            if (compensation_contract is None) != (compensation_evidence is None):
                raise HarnessEffectJournalError("harness_effect_compensation_evidence_incomplete")
            now = _database_utc_now(session)
            adapter = _adapter_from_row(row)
            evidence = _build_terminal_evidence(
                row,
                outcome=HarnessEffectTerminalOutcome.UNCERTAIN,
                terminal_at=now,
                commit_started_at=_parse(row.commit_started_at),
                provider_effect_identity=_provider_from_row(row),
                read_back_outcome=(
                    HarnessEffectReadBackOutcome.UNSUPPORTED
                    if adapter.read_back_policy.value == "unsupported"
                    else HarnessEffectReadBackOutcome.FAILED
                ),
                read_back_at=(
                    None if adapter.read_back_policy.value == "unsupported" else now
                ),
                read_back_started_at=(
                    None
                    if adapter.read_back_policy.value == "unsupported"
                    else (
                        _parse(row.read_back_started_at)
                        if row.read_back_started_at
                        else now
                    )
                ),
                compensation_outcome=(
                    HarnessEffectCompensationOutcome.FAILED
                    if compensation_evidence is not None
                    else HarnessEffectCompensationOutcome.NOT_APPLICABLE
                ),
                compensation_contract=compensation_contract,
                compensation_started_at=(
                    _parse(row.compensation_started_at)
                    if row.compensation_started_at
                    else now if compensation_evidence is not None else None
                ),
                compensation_evidence_digest=(
                    canonical_harness_digest(
                        compensation_evidence.model_dump(mode="json", exclude_none=False)
                    )
                    if compensation_evidence is not None
                    else None
                ),
                compensated_at=now if compensation_evidence is not None else None,
                failure_code=failure_code,
            )
            _persist_terminal(row, evidence)
            session.flush()
            return evidence

    def recover_expired_claims(self) -> tuple[HarnessEffectTerminalEvidenceV1, ...]:
        recovered: list[HarnessEffectTerminalEvidenceV1] = []
        with self.database.session() as session:
            now = _database_utc_now(session)
            now_wire = _wire(now)
            rows = list(
                session.scalars(
                    select(HarnessEffectJournalRow)
                    .where(
                        HarnessEffectJournalRow.state
                        == HarnessEffectJournalState.CLAIMED.value,
                        HarnessEffectJournalRow.lease_expires_at <= now_wire,
                    )
                    .order_by(
                        HarnessEffectJournalRow.harness_operation_id,
                        HarnessEffectJournalRow.slot,
                    )
                )
            )
            for row in rows:
                adapter = _adapter_from_row(row)
                if not row.commit_started_at:
                    evidence = _build_terminal_evidence(
                        row,
                        outcome=HarnessEffectTerminalOutcome.NOT_COMMITTED,
                        terminal_at=now,
                        commit_started_at=None,
                        read_back_outcome=HarnessEffectReadBackOutcome.NOT_ATTEMPTED,
                    )
                else:
                    unsupported = adapter.read_back_policy.value == "unsupported"
                    compensation_incomplete = bool(row.compensation_started_at)
                    evidence = _build_terminal_evidence(
                        row,
                        outcome=HarnessEffectTerminalOutcome.UNCERTAIN,
                        terminal_at=now,
                        commit_started_at=_parse(row.commit_started_at),
                        provider_effect_identity=_provider_from_row(row),
                        read_back_outcome=(
                            HarnessEffectReadBackOutcome.UNSUPPORTED
                            if unsupported
                            else HarnessEffectReadBackOutcome.FAILED
                        ),
                        read_back_started_at=(
                            None
                            if unsupported
                            else (
                                _parse(row.read_back_started_at)
                                if row.read_back_started_at
                                else now
                            )
                        ),
                        read_back_at=None if unsupported else now,
                        compensation_outcome=(
                            HarnessEffectCompensationOutcome.INCOMPLETE
                            if compensation_incomplete
                            else HarnessEffectCompensationOutcome.NOT_APPLICABLE
                        ),
                        compensation_started_at=(
                            _parse(row.compensation_started_at)
                            if compensation_incomplete
                            else None
                        ),
                        failure_code="harness_effect_worker_lease_expired",
                    )
                _persist_terminal(row, evidence)
                recovered.append(evidence)
            session.flush()
        return tuple(recovered)

    @staticmethod
    def _require_retry_identity(
        row: HarnessEffectJournalRow,
        *,
        batch_id: str,
        operation_id: str,
        slot: int,
        adapter: HarnessEffectAdapterRefV1,
        proposal_contract: HarnessContractRef,
        proposal_digest: str,
        target_refs: tuple[HarnessEffectTargetRefV1, ...],
    ) -> None:
        expected_targets = [item.model_dump(mode="json") for item in target_refs]
        actual = (
            row.effect_batch_id,
            row.harness_operation_id,
            row.slot,
            _adapter_from_row(row),
            row.proposal_contract_name,
            row.proposal_contract_version,
            row.proposal_digest,
            row.target_refs,
        )
        expected = (
            batch_id,
            operation_id,
            slot,
            adapter,
            proposal_contract.name,
            proposal_contract.version,
            proposal_digest,
            expected_targets,
        )
        if actual != expected:
            raise HarnessEffectJournalError("harness_effect_retry_identity_mismatch")

    @staticmethod
    def _require_active_claim(
        session: Session,
        claim: HarnessEffectClaim,
    ) -> tuple[HarnessEffectJournalRow, datetime]:
        now = _database_utc_now(session)
        row = session.get(HarnessEffectJournalRow, claim.effect_id)
        if (
            row is None
            or row.state != HarnessEffectJournalState.CLAIMED.value
            or row.claim_owner != claim.claim_owner
            or row.claim_count != claim.claim_count
            or not row.lease_expires_at
            or row.lease_expires_at <= _wire(now)
        ):
            raise HarnessEffectClaimFenced(claim.effect_id)
        return row, now


class HarnessEffectJournalError(RuntimeError):
    pass


class HarnessEffectJournalCorrupt(HarnessEffectJournalError):
    pass


class HarnessEffectClaimFenced(HarnessEffectJournalError):
    pass


def _adapter_from_row(row: HarnessEffectJournalRow) -> HarnessEffectAdapterRefV1:
    return HarnessEffectAdapterRefV1(
        name=row.adapter_name,
        version=row.adapter_version,
        boundary_kind=row.boundary_kind,
        prepare_policy=row.prepare_policy,
        commit_policy=row.commit_policy,
        compensation_policy=row.compensation_policy,
        read_back_policy=row.read_back_policy,
    )


def _provider_payload(
    provider: HarnessProviderEffectIdentityV1 | None,
) -> dict[str, object] | None:
    return provider.model_dump(mode="json") if provider is not None else None


def _provider_from_row(
    row: HarnessEffectJournalRow,
) -> HarnessProviderEffectIdentityV1 | None:
    return (
        HarnessProviderEffectIdentityV1.model_validate(row.provider_effect_identity)
        if row.provider_effect_identity is not None
        else None
    )


def _targets_from_row(row: HarnessEffectJournalRow) -> tuple[HarnessEffectTargetRefV1, ...]:
    return tuple(HarnessEffectTargetRefV1.model_validate(item) for item in row.target_refs)


def _from_row(row: HarnessEffectJournalRow) -> HarnessEffectJournalEntryV1:
    return HarnessEffectJournalEntryV1(
        harness_operation_id=row.harness_operation_id,
        effect_batch_id=row.effect_batch_id,
        effect_id=row.effect_id,
        slot=row.slot,
        adapter=_adapter_from_row(row),
        proposal_contract=HarnessContractRef(
            name=row.proposal_contract_name,
            version=row.proposal_contract_version,
        ),
        proposal_digest=row.proposal_digest,
        target_refs=_targets_from_row(row),
        state=row.state,
        claim_owner=row.claim_owner,
        claim_count=row.claim_count,
        lease_expires_at=_parse(row.lease_expires_at) if row.lease_expires_at else None,
        commit_started_at=(
            _parse(row.commit_started_at) if row.commit_started_at else None
        ),
        read_back_started_at=(
            _parse(row.read_back_started_at) if row.read_back_started_at else None
        ),
        compensation_started_at=(
            _parse(row.compensation_started_at)
            if row.compensation_started_at
            else None
        ),
        provider_effect_identity=_provider_from_row(row),
        prepared_at=_parse(row.prepared_at),
        updated_at=_parse(row.updated_at),
        terminal_evidence=(
            HarnessEffectTerminalEvidenceV1.model_validate(row.terminal_evidence)
            if row.terminal_evidence is not None
            else None
        ),
    )


def _terminal_from_row(row: HarnessEffectJournalRow) -> HarnessEffectTerminalEvidenceV1:
    if row.terminal_evidence is None:
        raise HarnessEffectJournalCorrupt("harness_effect_terminal_evidence_missing")
    return HarnessEffectTerminalEvidenceV1.model_validate(row.terminal_evidence)


def _build_terminal_evidence(
    row: HarnessEffectJournalRow,
    *,
    outcome: HarnessEffectTerminalOutcome,
    terminal_at: datetime,
    commit_started_at: datetime | None,
    provider_effect_identity: HarnessProviderEffectIdentityV1 | None = None,
    read_back_outcome: HarnessEffectReadBackOutcome,
    committed_projection_contract: HarnessContractRef | None = None,
    committed_projection_digest: str | None = None,
    read_back_started_at: datetime | None = None,
    read_back_at: datetime | None = None,
    compensation_outcome: HarnessEffectCompensationOutcome = (
        HarnessEffectCompensationOutcome.NOT_APPLICABLE
    ),
    compensation_contract: HarnessContractRef | None = None,
    compensation_evidence_digest: str | None = None,
    compensation_started_at: datetime | None = None,
    compensated_at: datetime | None = None,
    failure_code: str = "",
) -> HarnessEffectTerminalEvidenceV1:
    return HarnessEffectTerminalEvidenceV1(
        harness_operation_id=row.harness_operation_id,
        effect_batch_id=row.effect_batch_id,
        effect_id=row.effect_id,
        slot=row.slot,
        adapter=_adapter_from_row(row),
        proposal_contract=HarnessContractRef(
            name=row.proposal_contract_name,
            version=row.proposal_contract_version,
        ),
        proposal_digest=row.proposal_digest,
        target_refs=_targets_from_row(row),
        outcome=outcome,
        provider_effect_identity=provider_effect_identity,
        read_back_outcome=read_back_outcome,
        committed_projection_contract=committed_projection_contract,
        committed_projection_digest=committed_projection_digest,
        compensation_outcome=compensation_outcome,
        compensation_contract=compensation_contract,
        compensation_evidence_digest=compensation_evidence_digest,
        prepared_at=_parse(row.prepared_at),
        commit_started_at=commit_started_at,
        read_back_started_at=read_back_started_at,
        compensation_started_at=compensation_started_at,
        read_back_at=read_back_at,
        compensated_at=compensated_at,
        terminal_at=terminal_at,
        failure_code=failure_code,
    )


def _persist_terminal(
    row: HarnessEffectJournalRow,
    evidence: HarnessEffectTerminalEvidenceV1,
) -> None:
    row.state = HarnessEffectJournalState.TERMINAL.value
    row.claim_owner = ""
    row.lease_expires_at = ""
    row.commit_started_at = (
        _wire(evidence.commit_started_at) if evidence.commit_started_at else ""
    )
    row.read_back_started_at = (
        _wire(evidence.read_back_started_at)
        if evidence.read_back_started_at
        else ""
    )
    row.compensation_started_at = (
        _wire(evidence.compensation_started_at)
        if evidence.compensation_started_at
        else ""
    )
    row.provider_effect_identity = _provider_payload(evidence.provider_effect_identity)
    row.terminal_outcome = evidence.outcome.value
    row.terminal_evidence = evidence.model_dump(mode="json", exclude_none=False)
    row.updated_at = _wire(evidence.terminal_at)
    row.terminal_at = _wire(evidence.terminal_at)


def _database_utc_now(session: Session) -> datetime:
    if session.bind is not None and session.bind.dialect.name == "sqlite":
        value = session.scalar(select(func.strftime("%Y-%m-%dT%H:%M:%f", "now")))
    elif session.bind is not None and session.bind.dialect.name == "postgresql":
        value = session.scalar(select(func.clock_timestamp()))
    else:
        value = session.scalar(select(func.current_timestamp()))
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace(" ", "T"))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise HarnessEffectJournalError("harness_effect_database_clock_unavailable")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _wire(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _parse(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
