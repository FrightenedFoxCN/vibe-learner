from __future__ import annotations

from typing import ClassVar, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from app.models.harness import HarnessContractRef, HarnessSafeManifest
from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    LearningPlanRecord,
    PlanGenerationTraceRecord,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


PLAN_INPUT_CONTRACT = HarnessContractRef(
    name="LearningPlanInputManifest", version="learning-plan-input-manifest-v1"
)


PLAN_SNAPSHOT_CONTRACT = HarnessContractRef(
    name="LearningPlanProtectedInput", version="learning-plan-protected-input-v1"
)


PLAN_PROMPT_CONTRACT = HarnessContractRef(
    name="LearningPlanPrompt", version="planning-prompt-v1"
)


PLAN_POLICY_CONTRACT = HarnessContractRef(
    name="LearningPlanHarnessPolicy", version="learning-plan-harness-v1"
)


PLAN_ADAPTER_CONTRACT = HarnessContractRef(
    name="LearningPlanWorkflowAdapter", version="learning-plan-workflow-adapter-v1"
)


PLAN_TRACE_CONTRACT = HarnessContractRef(
    name="LearningPlanRuntimeOutput", version="learning-plan-runtime-output-v1"
)


PLANNING_TOOL_STAGE_INPUT_CONTRACT = HarnessContractRef(
    name="PlanningToolExecutionInputManifest",
    version="planning-tool-execution-input-manifest-v1",
)


PLANNING_TOOL_STAGE_PROTECTED_INPUT_CONTRACT = HarnessContractRef(
    name="PlanningToolExecutionProtectedInput",
    version="planning-tool-execution-protected-input-v1",
)


PLANNING_TOOL_STAGE_POLICY_CONTRACT = HarnessContractRef(
    name="PlanningToolExecutionHarnessPolicy",
    version="planning-tool-execution-harness-v1",
)


PLANNING_TOOL_STAGE_ADAPTER_CONTRACT = HarnessContractRef(
    name="PlanningToolExecutionWorkflowAdapter",
    version="planning-tool-execution-workflow-adapter-v1",
)


PLANNING_TOOL_STAGE_TRACE_CONTRACT = HarnessContractRef(
    name="PlanningToolExecutionEvidence",
    version="planning-tool-execution-evidence-v1",
)


class LearningPlanInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"client_request_id", "document_id", "persona_id", "creation_mode"}
    )

    client_request_id: str
    document_id: str
    persona_id: str
    creation_mode: Literal["document", "goal_only"]


class LearningPlanRuntimeOutputV1(_StrictModel):
    schema_name: Literal["LearningPlanRuntimeOutput"] = "LearningPlanRuntimeOutput"
    schema_version: Literal["learning-plan-runtime-output-v1"] = (
        "learning-plan-runtime-output-v1"
    )
    plan: LearningPlanRecord
    document: DocumentRecord | None = None
    debug_report: DocumentDebugRecord | None = None
    trace: PlanGenerationTraceRecord | None = None

    @model_validator(mode="after")
    def validate_plan_output(self) -> "LearningPlanRuntimeOutputV1":
        unit_ids = {item.id for item in self.plan.study_units}
        scheduled = [item.unit_id for item in self.plan.schedule]
        if any(item not in unit_ids for item in scheduled):
            raise ValueError("learning_plan_study_unit_reference_invalid")
        if self.document is not None and self.document.id != self.plan.document_id:
            raise ValueError("learning_plan_document_identity_invalid")
        if self.debug_report is not None and (
            self.document is None
            or self.debug_report.document_id != self.document.id
        ):
            raise ValueError("learning_plan_debug_identity_invalid")
        return self


class PlanningToolExecutionInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"document_id", "tool_name", "tool_call_id"}
    )

    document_id: str
    tool_name: str
    tool_call_id: str


class PlanningToolExecutionEvidenceV1(_StrictModel):
    schema_name: Literal["PlanningToolExecutionEvidence"] = (
        "PlanningToolExecutionEvidence"
    )
    schema_version: Literal["planning-tool-execution-evidence-v1"] = (
        "planning-tool-execution-evidence-v1"
    )
    tool_name: str = Field(min_length=1, max_length=160)
    tool_call_id: str = Field(min_length=1, max_length=160)
    result_contract_version: str = Field(min_length=1, max_length=160)
    arguments_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: Literal["validated", "failed"]
    attempt_count: int = Field(default=1, ge=1, le=3)
    duration_ms: int = Field(default=0, ge=0, le=86_400_000)
    evidence_source: Literal["observed_runtime"] = "observed_runtime"
