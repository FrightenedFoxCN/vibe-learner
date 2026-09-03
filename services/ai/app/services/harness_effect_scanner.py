from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app.models.harness_effect import (
    HARNESS_EFFECT_JOURNAL_ENTRY_SCHEMA_VERSION,
    HarnessEffectTerminalEvidenceV1,
)
from app.persistence.database import Database
from app.persistence.models import HarnessEffectJournalRow


class HarnessJournalFindingKind(StrEnum):
    CORRUPTION = "corruption"
    UNKNOWN_VERSION = "unknown_version"
    DIGEST_DRIFT = "digest_drift"


class HarnessJournalFindingV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    effect_id: str
    kind: HarnessJournalFindingKind
    reason_code: str


class HarnessJournalScanResultV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    findings: tuple[HarnessJournalFindingV1, ...]
    healthy: bool


def scan_harness_effect_journal(database: Database) -> HarnessJournalScanResultV1:
    """Validate server side journal rows without exposing proposal content."""
    findings: list[HarnessJournalFindingV1] = []
    with database.session() as session:
        rows = session.scalars(select(HarnessEffectJournalRow).order_by(HarnessEffectJournalRow.effect_id)).all()
        for row in rows:
            if row.schema_name != "HarnessEffectJournalEntryV1" or row.schema_version != HARNESS_EFFECT_JOURNAL_ENTRY_SCHEMA_VERSION:
                findings.append(HarnessJournalFindingV1(effect_id=row.effect_id, kind=HarnessJournalFindingKind.UNKNOWN_VERSION, reason_code="journal_schema_unsupported"))
                continue
            if row.state not in {"prepared", "claimed", "terminal"}:
                findings.append(HarnessJournalFindingV1(effect_id=row.effect_id, kind=HarnessJournalFindingKind.CORRUPTION, reason_code="journal_state_invalid"))
                continue
            if row.state == "terminal":
                if not isinstance(row.terminal_evidence, dict):
                    findings.append(HarnessJournalFindingV1(effect_id=row.effect_id, kind=HarnessJournalFindingKind.CORRUPTION, reason_code="terminal_evidence_missing"))
                    continue
                try:
                    evidence = HarnessEffectTerminalEvidenceV1.model_validate(row.terminal_evidence)
                except Exception:
                    findings.append(HarnessJournalFindingV1(effect_id=row.effect_id, kind=HarnessJournalFindingKind.CORRUPTION, reason_code="terminal_evidence_invalid"))
                    continue
                if evidence.effect_id != row.effect_id or evidence.proposal_digest != row.proposal_digest or evidence.outcome.value != row.terminal_outcome:
                    findings.append(HarnessJournalFindingV1(effect_id=row.effect_id, kind=HarnessJournalFindingKind.DIGEST_DRIFT, reason_code="terminal_evidence_identity_drift"))
            if row.state == "prepared" and (row.claim_count != 0 or row.claim_owner or row.lease_expires_at):
                findings.append(HarnessJournalFindingV1(effect_id=row.effect_id, kind=HarnessJournalFindingKind.CORRUPTION, reason_code="prepared_claim_shape_invalid"))
    return HarnessJournalScanResultV1(findings=tuple(findings), healthy=not findings)
