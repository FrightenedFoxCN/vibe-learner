from __future__ import annotations

from app.services.harness_domain_port import HarnessDomainExecutionPort
from app.models.planning_runtime import (
    LearningPlanInputManifest,
    LearningPlanRuntimeOutputV1,
    PlanningToolExecutionInputManifest,
    PlanningToolExecutionEvidenceV1,
    PLAN_INPUT_CONTRACT,
    PLAN_SNAPSHOT_CONTRACT,
    PLAN_PROMPT_CONTRACT,
    PLAN_POLICY_CONTRACT,
    PLAN_ADAPTER_CONTRACT,
    PLAN_TRACE_CONTRACT,
    PLANNING_TOOL_STAGE_INPUT_CONTRACT,
    PLANNING_TOOL_STAGE_PROTECTED_INPUT_CONTRACT,
    PLANNING_TOOL_STAGE_POLICY_CONTRACT,
    PLANNING_TOOL_STAGE_ADAPTER_CONTRACT,
    PLANNING_TOOL_STAGE_TRACE_CONTRACT,
)
from typing import Callable
from app.models.harness import (
    HarnessArtifactType,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.harness_operation import HarnessOperationBindingV1
from app.services.harness_runtime import HarnessOperationRuntime, HarnessRuntimePreparedOutput


class PlanningHarnessAdapter:
    def __init__(self, runtime: HarnessDomainExecutionPort):
        self.runtime = runtime

    def prepare_plan(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        manifest: LearningPlanInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], LearningPlanRuntimeOutputV1],
    ) -> tuple[HarnessRuntimePreparedOutput, HarnessOperationRuntime]:
        return self.runtime.prepare_existing_operation(
            operation_binding=operation_binding,
            workflow=HarnessWorkflow.PLANNING,
            stage=HarnessStage.PLAN_GENERATION,
            manifest=manifest,
            input_contract=PLAN_INPUT_CONTRACT,
            artifact_type=HarnessArtifactType.PLANNING_CONTEXT,
            artifact_contract=PLAN_SNAPSHOT_CONTRACT,
            prompt_contract=PLAN_PROMPT_CONTRACT,
            policy_contract=PLAN_POLICY_CONTRACT,
            adapter_contract=PLAN_ADAPTER_CONTRACT,
            trace_contract=PLAN_TRACE_CONTRACT,
            protected_input=protected_input,
            generate=generate,
            output_type=LearningPlanRuntimeOutputV1,
        )

    def emit_planning_tool_evidence(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        parent_trace_id: str,
        trace_slot: int,
        input_manifest: PlanningToolExecutionInputManifest,
        evidence: PlanningToolExecutionEvidenceV1,
        protected_input: dict[str, object],
    ) -> HarnessTraceV3:
        return self.runtime.emit_stage_evidence(
            operation_binding=operation_binding,
            workflow=HarnessWorkflow.PLANNING,
            stage=HarnessStage.PLANNING_TOOL_EXECUTION,
            trace_slot=trace_slot,
            input_manifest=input_manifest,
            input_contract=PLANNING_TOOL_STAGE_INPUT_CONTRACT,
            protected_input={"output": evidence.model_dump(mode="json", exclude_none=False), **protected_input},
            artifact_type=HarnessArtifactType.PLANNING_CONTEXT,
            artifact_contract=PLANNING_TOOL_STAGE_PROTECTED_INPUT_CONTRACT,
            policy_contract=PLANNING_TOOL_STAGE_POLICY_CONTRACT,
            adapter_contract=PLANNING_TOOL_STAGE_ADAPTER_CONTRACT,
            trace_contract=PLANNING_TOOL_STAGE_TRACE_CONTRACT,
            output_type=PlanningToolExecutionEvidenceV1,
            parent_trace_id=parent_trace_id,
            claim_owner="wave4-planning-tool",
        )
