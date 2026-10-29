from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.models.domain import DocumentDebugRecord, DocumentRecord
from app.models.harness import HarnessArtifactType, HarnessStage, HarnessWorkflow
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.study_unit_revision import (
    UNIT_REVISION_ADAPTER,
    UNIT_REVISION_INPUT,
    UNIT_REVISION_OUTPUT,
    UNIT_REVISION_POLICY,
    UNIT_REVISION_PROMPT,
    UNIT_REVISION_SNAPSHOT,
    StudyUnitRevisionInputManifest,
    StudyUnitRevisionOutputV1,
    StudyUnitRevisionPreviewV1,
    StudyUnitRevisionResponseV1,
    apply_unit_suggestions,
)
from app.persistence.document_repository import DocumentRevisionConflict
from app.persistence.study_unit_revision_repository import StudyUnitRevisionRepository
from app.services.harness_broad_adoption import HarnessProposalRuntimeService
from app.services.local_store import LocalJsonStore
from fastapi import HTTPException

logger = logging.getLogger(__name__)


class StudyUnitRevisionService:
    def __init__(
        self,
        repository: StudyUnitRevisionRepository,
        harness: HarnessProposalRuntimeService,
        store: LocalJsonStore,
    ) -> None:
        self.repository = repository
        self.harness = harness
        self.store = store

    def decide(
        self, plan_id: str, operation_id: str, decision: str
    ) -> StudyUnitRevisionResponseV1:
        if decision not in {"accept", "reject"}:
            raise HTTPException(422, "study_unit_revision_invalid_decision")
        record = self.repository.get(plan_id)
        if record.preview.operation_id != operation_id:
            raise HTTPException(409, "study_unit_revision_identity_mismatch")
        if (decision, record.status) in {
            ("accept", "accepted"),
            ("reject", "rejected"),
        }:
            return record
        if record.status != "ready":
            raise HTTPException(409, "study_unit_revision_decision_unavailable")
        if decision == "reject":
            self.repository.reject(plan_id, operation_id)
            return self.repository.get(plan_id)
        if not self.repository.begin_accept(plan_id, operation_id):
            return self.repository.get(plan_id)
        prepared = runtime = None
        try:
            binding = self.repository.bindings.require_domain(
                domain_operation_kind=HarnessDomainOperationKind.STUDY_UNIT_REVISION,
                domain_operation_id=operation_id,
            )

            def generate(snapshot: dict[str, object]) -> StudyUnitRevisionOutputV1:
                preview = StudyUnitRevisionPreviewV1.model_validate(snapshot["preview"])
                debug = DocumentDebugRecord.model_validate(snapshot["debug_report"])
                return apply_unit_suggestions(
                    preview, debug, datetime.now(timezone.utc).isoformat()
                )

            prepared, runtime = self.harness.prepare_existing_operation(
                operation_binding=binding,
                workflow=HarnessWorkflow.PLANNING,
                stage=HarnessStage.STUDY_UNIT_REVISION,
                manifest=StudyUnitRevisionInputManifest(
                    operation_id=operation_id,
                    document_id=record.preview.base_document.id,
                    base_revision=record.preview.base_document.revision,
                ),
                input_contract=UNIT_REVISION_INPUT,
                artifact_type=HarnessArtifactType.PLANNING_CONTEXT,
                artifact_contract=UNIT_REVISION_SNAPSHOT,
                prompt_contract=UNIT_REVISION_PROMPT,
                policy_contract=UNIT_REVISION_POLICY,
                adapter_contract=UNIT_REVISION_ADAPTER,
                trace_contract=UNIT_REVISION_OUTPUT,
                protected_input=self.repository.protected_snapshot(plan_id),
                generate=generate,
                output_type=StudyUnitRevisionOutputV1,
            )
            self.repository.commit(plan_id, prepared=prepared, runtime=runtime)
        except (HTTPException, DocumentRevisionConflict) as exc:
            conflict = (
                isinstance(exc, DocumentRevisionConflict) or exc.status_code == 409
            )
            self.repository.fail(
                plan_id,
                status="conflict" if conflict else "failed",
                prepared=prepared,
                runtime=runtime,
            )
        except Exception as exc:
            logger.error(
                "Study Unit revision acceptance failed for %s (%s)",
                operation_id,
                type(exc).__name__,
            )
            self.repository.fail(
                plan_id, status="failed", prepared=prepared, runtime=runtime
            )
        result = self.repository.get(plan_id)
        if result.status == "accepted":
            self.store.mirror_document_projection(
                self.store.load_list("documents", DocumentRecord),
                self.store.load_item(
                    "document_debug",
                    result.preview.base_document.id,
                    DocumentDebugRecord,
                ),
            )
        return result
