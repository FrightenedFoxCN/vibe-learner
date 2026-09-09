from __future__ import annotations

from typing import Protocol
from typing import Callable
from pydantic import BaseModel
from app.models.harness import (
    HarnessArtifactType,
    HarnessContractRef,
    HarnessSafeManifest,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.harness_operation import HarnessDomainOperationKind, HarnessOperationBindingV1
from app.persistence.harness_workflow_operation_repository import HarnessWorkflowOperationRepository
from app.services.harness_runtime import HarnessOperationRuntime, HarnessRuntimePreparedOutput


class HarnessDomainExecutionPort(Protocol):
    workflow_operations: HarnessWorkflowOperationRepository

    def run_proposal(
        self,
        *,
        kind: HarnessDomainOperationKind,
        workflow: HarnessWorkflow,
        stage: HarnessStage,
        manifest: HarnessSafeManifest,
        input_contract: HarnessContractRef,
        artifact_type: HarnessArtifactType,
        artifact_contract: HarnessContractRef,
        prompt_contract: HarnessContractRef,
        policy_contract: HarnessContractRef,
        adapter_contract: HarnessContractRef,
        trace_contract: HarnessContractRef,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], BaseModel],
        output_type: type[BaseModel],
    ) -> tuple[BaseModel, HarnessTraceV3]:
        ...

    def prepare_existing_operation(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        workflow: HarnessWorkflow,
        stage: HarnessStage,
        manifest: HarnessSafeManifest,
        input_contract: HarnessContractRef,
        artifact_type: HarnessArtifactType,
        artifact_contract: HarnessContractRef,
        prompt_contract: HarnessContractRef | None,
        policy_contract: HarnessContractRef,
        adapter_contract: HarnessContractRef,
        trace_contract: HarnessContractRef,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], BaseModel],
        output_type: type[BaseModel],
    ) -> tuple[HarnessRuntimePreparedOutput, HarnessOperationRuntime]:
        ...

    def emit_stage_evidence(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        workflow: HarnessWorkflow,
        stage: HarnessStage,
        trace_slot: int,
        input_manifest: HarnessSafeManifest,
        input_contract: HarnessContractRef,
        protected_input: dict[str, object],
        artifact_type: HarnessArtifactType,
        artifact_contract: HarnessContractRef,
        policy_contract: HarnessContractRef,
        adapter_contract: HarnessContractRef,
        trace_contract: HarnessContractRef,
        output_type: type[BaseModel],
        parent_trace_id: str | None = None,
        claim_owner: str = "wave4-stage",
    ) -> HarnessTraceV3:
        ...
