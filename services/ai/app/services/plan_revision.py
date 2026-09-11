from __future__ import annotations

from fastapi import HTTPException

from app.models.domain import VersionedLearningPlanRecord
from app.models.harness import HarnessWorkflow, HarnessStage, HarnessArtifactType
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.plan_revision import (PlanRevisionRequestV1, PlanRevisionProposalV1, PlanRevisionInputManifest, PlanRevisionDecodeError,
    apply_patch, proposal_from_plan, REVISION_INPUT, REVISION_SNAPSHOT, REVISION_PROMPT,
    REVISION_POLICY, REVISION_ADAPTER, REVISION_TRACE)
from app.persistence.plan_revision_repository import PlanRevisionRepository
from app.services.harness_broad_adoption import HarnessProposalRuntimeService
from app.services.provider_capabilities import PlanningModelCapability


class PlanRevisionService:
    def __init__(self, repository: PlanRevisionRepository, harness: HarnessProposalRuntimeService,
                 provider: PlanningModelCapability):
        self.repository, self.harness, self.provider = repository, harness, provider

    def create(self, plan_id: str, request: PlanRevisionRequestV1):
        record, binding = self.repository.admit(plan_id, request)
        if binding is None:
            return self.repository.get(plan_id, request.client_request_id)
        prepared = runtime = None
        provider_started = False
        provider_returned = False
        try:
            historical = (self.repository.historical(plan_id, request.rollback_revision)
                          if request.rollback_revision is not None else None)
            def generate(snapshot):
                nonlocal provider_started, provider_returned
                base = VersionedLearningPlanRecord.model_validate(snapshot["plan"])
                if snapshot["historical"] is not None:
                    old = VersionedLearningPlanRecord.model_validate(snapshot["historical"])
                    proposal = proposal_from_plan(old, "恢复此版本的计划内容与排期顺序，保留当前学习进度。")
                else:
                    provider_started = True
                    try:
                        proposal = self.provider.generate_plan_revision(plan=base, instruction=snapshot["instruction"])
                    except PlanRevisionDecodeError:
                        provider_returned = True
                        raise
                provider_returned = True
                strict = PlanRevisionProposalV1.model_validate(proposal.model_dump(mode="json"), strict=True)
                apply_patch(base, strict)
                return strict
            prepared, runtime = self._prepare(record, binding, "preview", {
                "plan": record.base_plan.model_dump(mode="json"), "instruction": request.instruction,
                "historical": historical.model_dump(mode="json") if historical is not None else None,
            }, generate)
            self.repository.commit(record, proposal=prepared.output, action="preview", prepared=prepared, runtime=runtime)
        except Exception as exc:
            self.repository.fail(record.operation_id, status="uncertain" if provider_started and not provider_returned and prepared is None and not isinstance(exc, PlanRevisionDecodeError) else "failed",
                                 prepared=prepared, runtime=runtime)
        return self.repository.get(plan_id, request.client_request_id)

    def decide(self, plan_id: str, request_id: str, decision: str):
        record = self.repository.get(plan_id, request_id)
        if (decision, record.status) in {("accept", "accepted"), ("reject", "rejected")}:
            return record
        if record.status != "ready":
            raise HTTPException(409, "plan_revision_decision_unavailable")
        if decision == "reject":
            self.repository.reject(record)
            return self.repository.get(plan_id, request_id)
        if not self.repository.begin_accept(record):
            return self.repository.get(plan_id, request_id)
        binding = self.repository.bindings.require_domain(
            domain_operation_kind=HarnessDomainOperationKind.LEARNING_PLAN_REVISION,
            domain_operation_id=record.operation_id)
        prepared = runtime = None
        try:
            def generate(snapshot):
                proposal = PlanRevisionProposalV1.model_validate(snapshot["proposal"], strict=True)
                apply_patch(VersionedLearningPlanRecord.model_validate(snapshot["plan"]), proposal)
                return proposal
            prepared, runtime = self._prepare(record, binding, "accept", {
                "plan": record.base_plan.model_dump(mode="json"),
                "proposal": record.proposal.model_dump(mode="json"),
            }, generate)
            self.repository.commit(record, proposal=prepared.output, action="accept", prepared=prepared, runtime=runtime)
        except HTTPException as exc:
            self.repository.fail(record.operation_id, status="conflict" if exc.status_code == 409 else "failed",
                                 prepared=prepared, runtime=runtime)
        except Exception:
            self.repository.fail(record.operation_id, status="failed", prepared=prepared, runtime=runtime)
        return self.repository.get(plan_id, request_id)

    def _prepare(self, record, binding, action, snapshot, generate):
        return self.harness.prepare_existing_operation(operation_binding=binding,
            workflow=HarnessWorkflow.PLANNING, stage=HarnessStage.PLAN_REVISION,
            manifest=PlanRevisionInputManifest(operation_id=record.operation_id, plan_id=record.plan_id,
                base_revision=record.base_revision, action=action),
            input_contract=REVISION_INPUT, artifact_type=HarnessArtifactType.PLANNING_CONTEXT,
            artifact_contract=REVISION_SNAPSHOT, prompt_contract=REVISION_PROMPT,
            policy_contract=REVISION_POLICY, adapter_contract=REVISION_ADAPTER,
            trace_contract=REVISION_TRACE, protected_input=snapshot, generate=generate,
            output_type=PlanRevisionProposalV1, trace_slot=0 if action == "preview" else 1)
