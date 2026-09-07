from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Callable, ClassVar, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.harness import (
    HarnessArtifactType,
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessContractRef,
    canonical_harness_digest,
    HarnessResourceRefV3,
    HarnessResourceType,
    HarnessSafeManifest,
    HarnessSnapshotRefV3,
    HarnessStage,
    HarnessStatus,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    LearningPlanRecord,
    PlanGenerationTraceRecord,
    StudyUnitRecord,
)
from app.models.harness_artifact_access import (
    HarnessArtifactGrantScopeV1,
    HarnessArtifactPermission,
    HarnessArtifactResolutionStatus,
    HarnessArtifactResolveRequestV1,
)
from app.models.harness_operation import HarnessDomainOperationKind, HarnessOperationBindingV1
from app.models.harness_runtime import HarnessRuntimeExecutionV1
from app.models.scene import SceneTreeProposalV1
from app.persistence.database import Database
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.persistence.harness_workflow_operation_repository import (
    HarnessWorkflowOperationRepository,
)
from app.services.harness_context import build_harness_context
from app.services.harness_runtime import (
    HarnessOperationRuntime,
    HarnessRuntimeArtifactResolver,
    HarnessRuntimeRequest,
    HarnessRuntimeResolvedArtifact,
    HarnessRuntimeStageAdapter,
    HarnessRuntimeValidationResult,
    HarnessRuntimePreparedOutput,
)
from app.services.stream_interrupts import StreamInterruptedError


PERSONA_INPUT_CONTRACT = HarnessContractRef(
    name="PersonaGenerationInputManifest",
    version="persona-generation-input-manifest-v1",
)
PERSONA_SNAPSHOT_CONTRACT = HarnessContractRef(
    name="PersonaGenerationProtectedInput",
    version="persona-generation-protected-input-v1",
)
PERSONA_PROMPT_CONTRACT = HarnessContractRef(
    name="PersonaGenerationPrompt", version="persona-generation-prompt-v1"
)
PERSONA_POLICY_CONTRACT = HarnessContractRef(
    name="PersonaGenerationHarnessPolicy", version="persona-generation-harness-v1"
)
PERSONA_ADAPTER_CONTRACT = HarnessContractRef(
    name="PersonaGenerationWorkflowAdapter",
    version="persona-generation-workflow-adapter-v1",
)
PERSONA_TRACE_CONTRACT = HarnessContractRef(
    name="PersonaGenerationProposal", version="persona-generation-proposal-v1"
)

SCENE_INPUT_CONTRACT = HarnessContractRef(
    name="SceneGenerationInputManifest", version="scene-generation-input-manifest-v1"
)
SCENE_SNAPSHOT_CONTRACT = HarnessContractRef(
    name="SceneGenerationProtectedInput",
    version="scene-generation-protected-input-v1",
)
SCENE_PROMPT_CONTRACT = HarnessContractRef(
    name="SceneGenerationPrompt", version="scene-generation-prompt-v1"
)
SCENE_POLICY_CONTRACT = HarnessContractRef(
    name="SceneGenerationHarnessPolicy", version="scene-generation-harness-v1"
)
SCENE_ADAPTER_CONTRACT = HarnessContractRef(
    name="SceneGenerationWorkflowAdapter",
    version="scene-generation-workflow-adapter-v1",
)
SCENE_TRACE_CONTRACT = HarnessContractRef(
    name="SceneTreeProposal", version="scene-tree-proposal-v1"
)

DOCUMENT_INPUT_CONTRACT = HarnessContractRef(
    name="DocumentProcessInputManifest", version="document-process-input-manifest-v1"
)
DOCUMENT_SNAPSHOT_CONTRACT = HarnessContractRef(
    name="DocumentProcessProtectedInput", version="document-process-protected-input-v1"
)
DOCUMENT_POLICY_CONTRACT = HarnessContractRef(
    name="DocumentProcessHarnessPolicy", version="document-process-harness-v1"
)
DOCUMENT_ADAPTER_CONTRACT = HarnessContractRef(
    name="DocumentProcessWorkflowAdapter", version="document-process-workflow-adapter-v1"
)
DOCUMENT_TRACE_CONTRACT = HarnessContractRef(
    name="DocumentProcessRuntimeOutput", version="document-process-runtime-output-v1"
)

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

DOCUMENT_STAGE_INPUT_CONTRACT = HarnessContractRef(
    name="DocumentStageInputManifest", version="document-stage-input-manifest-v1"
)
DOCUMENT_STAGE_PROTECTED_INPUT_CONTRACT = HarnessContractRef(
    name="DocumentStageProtectedInput",
    version="document-stage-protected-input-v1",
)
DOCUMENT_STAGE_POLICY_CONTRACT = HarnessContractRef(
    name="DocumentStageHarnessPolicy", version="document-stage-harness-v1"
)
DOCUMENT_STAGE_ADAPTER_CONTRACT = HarnessContractRef(
    name="DocumentStageWorkflowAdapter", version="document-stage-workflow-adapter-v1"
)
DOCUMENT_STAGE_TRACE_CONTRACT = HarnessContractRef(
    name="DocumentStageEvidence", version="document-stage-evidence-v1"
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


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PersonaGenerationInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"request_kind", "mode", "requested_count", "input_char_count"}
    )

    request_kind: Literal["card_batch", "setting_assist", "slot_assist"]
    mode: str
    requested_count: int
    input_char_count: int


class SceneGenerationInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"mode", "requested_layer_count", "input_char_count"}
    )

    mode: Literal["keywords", "long_text"]
    requested_layer_count: int
    input_char_count: int


class DocumentProcessInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"document_id", "force_ocr"}
    )

    document_id: str
    force_ocr: bool


class LearningPlanInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"client_request_id", "document_id", "persona_id", "creation_mode"}
    )

    client_request_id: str
    document_id: str
    persona_id: str
    creation_mode: Literal["document", "goal_only"]




class PersonaCardContentProposalV1(_StrictModel):
    title: str = Field(min_length=1, max_length=500)
    kind: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list, max_length=24)
    source_note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def validate_tags(self) -> "PersonaCardContentProposalV1":
        if any(not item.strip() for item in self.tags) or len(set(self.tags)) != len(self.tags):
            raise ValueError("persona_proposal_tags_invalid")
        return self


class PersonaSlotContentProposalV1(_StrictModel):
    kind: str = Field(min_length=1, max_length=160)
    label: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1, max_length=8000)
    weight: float = Field(default=1.0, ge=0, le=100)
    locked: bool = False
    sort_order: int = Field(default=0, ge=0, le=10000)


class PersonaGenerationProposalV1(_StrictModel):
    schema_name: Literal["PersonaGenerationProposal"] = "PersonaGenerationProposal"
    schema_version: Literal["persona-generation-proposal-v1"] = (
        "persona-generation-proposal-v1"
    )
    request_kind: Literal["card_batch", "setting_assist", "slot_assist"]
    used_model: str = Field(default="", max_length=500)
    used_web_search: bool = False
    summary: str = Field(default="", max_length=8000)
    relationship: str = Field(default="", max_length=2000)
    learner_address: str = Field(default="", max_length=500)
    cards: list[PersonaCardContentProposalV1] = Field(default_factory=list, max_length=24)
    slots: list[PersonaSlotContentProposalV1] = Field(default_factory=list, max_length=64)
    slot: PersonaSlotContentProposalV1 | None = None
    system_prompt_suggestion: str = Field(default="", max_length=16000)
    recovery_strategy: Literal["none", "local_fallback"] = "none"

    @model_validator(mode="after")
    def validate_shape(self) -> "PersonaGenerationProposalV1":
        if self.request_kind == "card_batch":
            if not self.cards or self.slots or self.slot is not None:
                raise ValueError("persona_card_proposal_shape_invalid")
        elif self.request_kind == "setting_assist":
            if not self.slots or not self.system_prompt_suggestion or self.cards or self.slot is not None:
                raise ValueError("persona_setting_proposal_shape_invalid")
        elif self.slot is None or self.cards or self.slots:
            raise ValueError("persona_slot_proposal_shape_invalid")
        return self


class SceneGenerationProposalV1(_StrictModel):
    schema_name: Literal["SceneGenerationProposal"] = "SceneGenerationProposal"
    schema_version: Literal["scene-generation-proposal-v1"] = (
        "scene-generation-proposal-v1"
    )
    used_model: str = Field(max_length=500)
    used_web_search: bool
    proposal: SceneTreeProposalV1


class DocumentProcessRuntimeOutputV1(_StrictModel):
    schema_name: Literal["DocumentProcessRuntimeOutput"] = (
        "DocumentProcessRuntimeOutput"
    )
    schema_version: Literal["document-process-runtime-output-v1"] = (
        "document-process-runtime-output-v1"
    )
    debug_report: DocumentDebugRecord
    study_units: list[StudyUnitRecord]

    @model_validator(mode="after")
    def validate_document_output(self) -> "DocumentProcessRuntimeOutputV1":
        page_count = self.debug_report.page_count
        if page_count < 1 or self.debug_report.total_characters < 0:
            raise ValueError("document_counts_invalid")
        if page_count != len(self.debug_report.pages):
            raise ValueError("document_page_coverage_invalid")
        page_numbers = [item.page_number for item in self.debug_report.pages]
        if page_numbers != list(range(1, page_count + 1)):
            raise ValueError("document_page_order_invalid")
        for page in self.debug_report.pages:
            if page.char_count < 0 or page.word_count < 0:
                raise ValueError("document_page_counts_invalid")
            if page.char_count == 0 and page.word_count != 0:
                raise ValueError("document_page_word_count_invalid")

        sections = self.debug_report.sections
        section_ids = {section.id for section in sections}
        if len(section_ids) != len(sections):
            raise ValueError("document_section_identity_invalid")
        for section in sections:
            if (
                section.document_id != self.debug_report.document_id
                or section.level < 1
                or section.page_start < 1
                or section.page_end < section.page_start
                or section.page_end > page_count
            ):
                raise ValueError("document_section_boundary_invalid")

        chunks = self.debug_report.chunks
        chunk_ids = {chunk.id for chunk in chunks}
        if len(chunk_ids) != len(chunks):
            raise ValueError("document_chunk_identity_invalid")
        for chunk in chunks:
            if (
                chunk.document_id != self.debug_report.document_id
                or (sections and chunk.section_id not in section_ids)
                or chunk.page_start < 1
                or chunk.page_end < chunk.page_start
                or chunk.page_end > page_count
                or chunk.char_count < 0
            ):
                raise ValueError("document_chunk_boundary_invalid")

        def is_synthetic_study_anchor(section_id: str) -> bool:
            prefix = f"{self.debug_report.document_id}:study-anchor:"
            return section_id.startswith(prefix) and len(section_id) > len(prefix)

        if any(
            unit.document_id != self.debug_report.document_id
            or unit.page_start < 1
            or unit.page_end < unit.page_start
            or unit.page_end > page_count
            or any(
                section_id not in section_ids
                and not is_synthetic_study_anchor(section_id)
                for section_id in unit.source_section_ids
            )
            for unit in self.study_units
        ):
            raise ValueError("study_unit_boundary_invalid")
        return self


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


class DocumentStageInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"document_id", "stage", "item_count"}
    )

    document_id: str
    stage: Literal[
        "page_extraction",
        "section_detection",
        "chunk_building",
        "ocr_page",
        "study_unit_cleanup",
    ]
    item_count: int


class DocumentStageEvidenceV1(_StrictModel):
    schema_name: Literal["DocumentStageEvidence"] = "DocumentStageEvidence"
    schema_version: Literal["document-stage-evidence-v1"] = (
        "document-stage-evidence-v1"
    )
    stage: Literal[
        "page_extraction",
        "section_detection",
        "chunk_building",
        "ocr_page",
        "study_unit_cleanup",
    ]
    outcome: Literal["passed", "applied", "not_needed", "unavailable", "failed"]
    item_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt_count: int = Field(default=1, ge=1, le=3)
    duration_ms: int = Field(default=0, ge=0, le=86_400_000)
    evidence_source: Literal["observed_runtime"] = "observed_runtime"


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




class AuthorizedJsonArtifactResolver(HarnessRuntimeArtifactResolver):
    """Resolve each operation-scoped snapshot only after repository authorization."""

    def __init__(self, artifacts: HarnessArtifactRepository, grants: Mapping[str, str]):
        self.artifacts = artifacts
        self.grants = dict(grants)

    def resolve(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        context,
    ) -> tuple[HarnessRuntimeResolvedArtifact, ...]:
        resolved: list[HarnessRuntimeResolvedArtifact] = []
        for ref in context.snapshot_refs:
            grant_id = self.grants.get(ref.artifact_id)
            if not grant_id:
                raise PermissionError("harness_artifact_grant_missing")
            result = self.artifacts.resolve(
                HarnessArtifactResolveRequestV1(
                    grant_id=grant_id,
                    harness_operation_id=operation_binding.harness_operation_id,
                    artifact_id=ref.artifact_id,
                    artifact_type=ref.artifact_type,
                    artifact_contract=ref.contract,
                    permission=HarnessArtifactPermission.READ,
                )
            )
            if result.status != HarnessArtifactResolutionStatus.RESOLVED or result.content is None:
                raise PermissionError(
                    f"harness_artifact_resolution_{result.status.value}"
                )
            resolved.append(
                HarnessRuntimeResolvedArtifact(
                    artifact_id=result.artifact_id,
                    payload_digest=result.payload_digest,
                    payload=result.content,
                )
            )
        return tuple(resolved)


class HarnessProposalRuntimeService:
    """Production v3 boundary for proposal-only Persona and Scene workflows."""

    def __init__(
        self,
        database: Database,
        artifacts: HarnessArtifactRepository,
        workflow_operations: HarnessWorkflowOperationRepository,
    ) -> None:
        self.database = database
        self.artifacts = artifacts
        self.workflow_operations = workflow_operations

    @classmethod
    def from_database(cls, database: Database) -> "HarnessProposalRuntimeService":
        return cls(
            database,
            HarnessArtifactRepository(database),
            HarnessWorkflowOperationRepository(database),
        )

    def run_persona(
        self,
        *,
        manifest: PersonaGenerationInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], PersonaGenerationProposalV1],
    ) -> tuple[PersonaGenerationProposalV1, HarnessTraceV3]:
        output, trace = self._run(
            kind=HarnessDomainOperationKind.PERSONA_GENERATION,
            workflow=HarnessWorkflow.PERSONA,
            stage=HarnessStage.PERSONA_GENERATION,
            manifest=manifest,
            artifact_type=HarnessArtifactType.PERSONA_SNAPSHOT,
            artifact_contract=PERSONA_SNAPSHOT_CONTRACT,
            prompt_contract=PERSONA_PROMPT_CONTRACT,
            policy_contract=PERSONA_POLICY_CONTRACT,
            adapter_contract=PERSONA_ADAPTER_CONTRACT,
            trace_contract=PERSONA_TRACE_CONTRACT,
            protected_input=protected_input,
            generate=generate,
            output_type=PersonaGenerationProposalV1,
        )
        return PersonaGenerationProposalV1.model_validate(output), trace

    def prepare_document(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        manifest: DocumentProcessInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], DocumentProcessRuntimeOutputV1],
    ) -> tuple[HarnessRuntimePreparedOutput, HarnessOperationRuntime]:
        return self._prepare_existing_operation(
            operation_binding=operation_binding,
            workflow=HarnessWorkflow.DOCUMENT_PARSE,
            stage=HarnessStage.DOCUMENT_PARSE,
            manifest=manifest,
            input_contract=DOCUMENT_INPUT_CONTRACT,
            artifact_type=HarnessArtifactType.DOCUMENT_UPLOAD,
            artifact_contract=DOCUMENT_SNAPSHOT_CONTRACT,
            prompt_contract=None,
            policy_contract=DOCUMENT_POLICY_CONTRACT,
            adapter_contract=DOCUMENT_ADAPTER_CONTRACT,
            trace_contract=DOCUMENT_TRACE_CONTRACT,
            protected_input=protected_input,
            generate=generate,
            output_type=DocumentProcessRuntimeOutputV1,
        )

    def prepare_plan(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        manifest: LearningPlanInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], LearningPlanRuntimeOutputV1],
    ) -> tuple[HarnessRuntimePreparedOutput, HarnessOperationRuntime]:
        return self._prepare_existing_operation(
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
        """Persist one observed child-stage trace under an admitted operation.

        The caller records the output of the stage that just ran.  The runtime
        then strictly decodes and validates that observation under the admitted
        operation; it never re-executes the parser, model, or tool from the
        protected snapshot.  Protected snapshots retain source payloads while
        trace-safe evidence carries only bounded counts and digests.
        """
        snapshot, grant_id = self._register_snapshot(
            binding=operation_binding,
            artifact_type=artifact_type,
            artifact_contract=artifact_contract,
            protected_input=protected_input,
        )
        context = build_harness_context(
            workflow=workflow,
            stage=stage,
            operation_binding=operation_binding,
            input_contract=input_contract,
            input_manifest=input_manifest,
            subject_refs=(
                HarnessResourceRefV3(
                    resource_type=HarnessResourceType.FRONTEND_REQUEST,
                    resource_id=operation_binding.domain_operation_id,
                ),
            ),
            snapshot_refs=(snapshot,),
            policy_contract=policy_contract,
        )

        def generate_from_snapshot(_context, artifacts: Mapping[str, object]) -> BaseModel:
            payload = _decode_protected_json(artifacts[snapshot.artifact_id], artifact_contract)
            return output_type.model_validate(payload["output"], strict=True)

        def validate(output: BaseModel) -> HarnessRuntimeValidationResult:
            strict = output_type.model_validate(
                output.model_dump(mode="python", exclude_none=False), strict=True
            )
            outcome = str(getattr(strict, "outcome", "passed"))
            if outcome in {"failed", "unavailable"}:
                check_status = HarnessCheckStatus.FAILED
                check_code = f"stage_evidence_{outcome}"
                check_message = f"The observed stage reported outcome={outcome}."
            else:
                check_status = HarnessCheckStatus.PASSED
                check_code = "stage_evidence_valid"
                check_message = "Stage output evidence passed strict validation."
            return HarnessRuntimeValidationResult(
                output=strict,
                checks=(
                    HarnessCheckV2(
                        name="stage_output_and_invariants",
                        status=check_status,
                        code=check_code,
                        message=check_message,
                    ),
                ),
            )

        runtime = HarnessOperationRuntime(
            repository=HarnessRuntimeRepository(self.database),
            artifact_resolver=AuthorizedJsonArtifactResolver(
                self.artifacts, {snapshot.artifact_id: grant_id}
            ),
        )
        result = runtime.execute(
            request=HarnessRuntimeRequest(
                operation_binding=operation_binding,
                stage=stage,
                trace_slot=trace_slot,
                context=context,
                parent_trace_id=parent_trace_id,
            ),
            adapter=HarnessRuntimeStageAdapter(
                adapter_contract=adapter_contract,
                trace_contract=trace_contract,
                generate=generate_from_snapshot,
                decode=lambda raw: output_type.model_validate(raw, strict=True),
                validate=validate,
                recovery_strategy="bounded_repair",
            ),
            claim_owner=claim_owner,
        )
        if not isinstance(result, HarnessRuntimeExecutionV1):
            raise RuntimeError("harness_stage_runtime_execution_invalid")
        trace = result.terminal_trace
        if trace is None:
            raise RuntimeError("harness_stage_runtime_trace_missing")
        return trace

    def emit_document_stage_evidence(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        parent_trace_id: str,
        stage: HarnessStage,
        trace_slot: int,
        input_manifest: DocumentStageInputManifest,
        evidence: DocumentStageEvidenceV1,
        artifact_type: HarnessArtifactType,
        protected_stage_input: dict[str, object] | None = None,
    ) -> HarnessTraceV3:
        return self.emit_stage_evidence(
            operation_binding=operation_binding,
            workflow=HarnessWorkflow.DOCUMENT_PARSE,
            stage=stage,
            trace_slot=trace_slot,
            input_manifest=input_manifest,
            input_contract=DOCUMENT_STAGE_INPUT_CONTRACT,
            protected_input={
                "output": evidence.model_dump(mode="json", exclude_none=False),
                "source": protected_stage_input or {},
            },
            artifact_type=artifact_type,
            artifact_contract=DOCUMENT_STAGE_PROTECTED_INPUT_CONTRACT,
            policy_contract=DOCUMENT_STAGE_POLICY_CONTRACT,
            adapter_contract=DOCUMENT_STAGE_ADAPTER_CONTRACT,
            trace_contract=DOCUMENT_STAGE_TRACE_CONTRACT,
            output_type=DocumentStageEvidenceV1,
            parent_trace_id=parent_trace_id,
            claim_owner=f"wave4-document-{stage.value}",
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
        return self.emit_stage_evidence(
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

    def emit_ocr_stage_evidence(
        self,
        *,
        document_id: str,
        input_manifest: DocumentStageInputManifest,
        evidence: DocumentStageEvidenceV1,
        protected_stage_input: dict[str, object] | None = None,
    ) -> HarnessTraceV3:
        binding = self.workflow_operations.admit(
            kind=HarnessDomainOperationKind.DOCUMENT_OCR,
            request_manifest=input_manifest.model_dump(mode="json", exclude_none=False),
        )
        try:
            trace = self.emit_stage_evidence(
                operation_binding=binding,
                workflow=HarnessWorkflow.OCR,
                stage=HarnessStage.OCR_PAGE,
                trace_slot=0,
                input_manifest=input_manifest,
                input_contract=DOCUMENT_STAGE_INPUT_CONTRACT,
                protected_input={
                    "output": evidence.model_dump(mode="json", exclude_none=False),
                    "source": protected_stage_input or {},
                },
                artifact_type=HarnessArtifactType.OCR_PAGE,
                artifact_contract=DOCUMENT_STAGE_PROTECTED_INPUT_CONTRACT,
                policy_contract=DOCUMENT_STAGE_POLICY_CONTRACT,
                adapter_contract=DOCUMENT_STAGE_ADAPTER_CONTRACT,
                trace_contract=DOCUMENT_STAGE_TRACE_CONTRACT,
                output_type=DocumentStageEvidenceV1,
                claim_owner="wave4-ocr-page",
            )
        except Exception as error:
            self.workflow_operations.terminalize(
                binding=binding, success=False, error_code=str(error)
            )
            raise
        success = trace.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}
        self.workflow_operations.terminalize(
            binding=binding,
            success=success,
            error_code=trace.error_code,
        )
        return trace

    def emit_study_unit_cleanup_evidence(
        self,
        *,
        document_id: str,
        input_manifest: DocumentStageInputManifest,
        evidence: DocumentStageEvidenceV1,
        protected_stage_input: dict[str, object] | None = None,
    ) -> HarnessTraceV3:
        binding = self.workflow_operations.admit(
            kind=HarnessDomainOperationKind.STUDY_UNIT_CLEANUP,
            request_manifest=input_manifest.model_dump(mode="json", exclude_none=False),
        )
        try:
            trace = self.emit_stage_evidence(
                operation_binding=binding,
                workflow=HarnessWorkflow.STUDY_UNIT_CLEANUP,
                stage=HarnessStage.STUDY_UNIT_CLEANUP,
                trace_slot=0,
                input_manifest=input_manifest,
                input_contract=DOCUMENT_STAGE_INPUT_CONTRACT,
                protected_input={
                    "output": evidence.model_dump(mode="json", exclude_none=False),
                    "source": protected_stage_input or {},
                },
                artifact_type=HarnessArtifactType.STUDY_UNIT_INPUT,
                artifact_contract=DOCUMENT_STAGE_PROTECTED_INPUT_CONTRACT,
                policy_contract=DOCUMENT_STAGE_POLICY_CONTRACT,
                adapter_contract=DOCUMENT_STAGE_ADAPTER_CONTRACT,
                trace_contract=DOCUMENT_STAGE_TRACE_CONTRACT,
                output_type=DocumentStageEvidenceV1,
                claim_owner="wave4-study-unit-cleanup",
            )
        except Exception as error:
            self.workflow_operations.terminalize(
                binding=binding, success=False, error_code=str(error)
            )
            raise
        success = trace.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}
        self.workflow_operations.terminalize(
            binding=binding,
            success=success,
            error_code=trace.error_code,
        )
        return trace


    def run_scene(
        self,
        *,
        manifest: SceneGenerationInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], SceneGenerationProposalV1],
    ) -> tuple[SceneGenerationProposalV1, HarnessTraceV3]:
        output, trace = self._run(
            kind=HarnessDomainOperationKind.SCENE_GENERATION,
            workflow=HarnessWorkflow.SCENE,
            stage=HarnessStage.SCENE_GENERATION,
            manifest=manifest,
            artifact_type=HarnessArtifactType.SCENE_SNAPSHOT,
            artifact_contract=SCENE_SNAPSHOT_CONTRACT,
            prompt_contract=SCENE_PROMPT_CONTRACT,
            policy_contract=SCENE_POLICY_CONTRACT,
            adapter_contract=SCENE_ADAPTER_CONTRACT,
            trace_contract=SCENE_TRACE_CONTRACT,
            protected_input=protected_input,
            generate=generate,
            output_type=SceneGenerationProposalV1,
        )
        return SceneGenerationProposalV1.model_validate(output), trace

    def _run(
        self,
        *,
        kind: HarnessDomainOperationKind,
        workflow: HarnessWorkflow,
        stage: HarnessStage,
        manifest: HarnessSafeManifest,
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
        binding = self.workflow_operations.admit(
            kind=kind,
            request_manifest=manifest.model_dump(mode="json", exclude_none=False),
        )
        try:
            snapshot, grant_id = self._register_snapshot(
                binding=binding,
                artifact_type=artifact_type,
                artifact_contract=artifact_contract,
                protected_input=protected_input,
            )
            context = build_harness_context(
                workflow=workflow,
                stage=stage,
                operation_binding=binding,
                input_contract=(
                    PERSONA_INPUT_CONTRACT
                    if workflow == HarnessWorkflow.PERSONA
                    else SCENE_INPUT_CONTRACT
                ),
                input_manifest=manifest,
                subject_refs=(
                    HarnessResourceRefV3(
                        resource_type=HarnessResourceType.FRONTEND_REQUEST,
                        resource_id=binding.domain_operation_id,
                    ),
                ),
                snapshot_refs=(snapshot,),
                prompt_contract=prompt_contract,
                policy_contract=policy_contract,
            )
            captured: dict[str, BaseModel] = {}

            def generate_from_snapshot(_context, artifacts: Mapping[str, object]) -> BaseModel:
                payload = _decode_protected_json(
                    artifacts[snapshot.artifact_id], artifact_contract
                )
                return generate(payload)

            def validate(output: BaseModel) -> HarnessRuntimeValidationResult:
                strict = output_type.model_validate(
                    output.model_dump(mode="python", exclude_none=False), strict=True
                )
                captured["output"] = strict
                recovery = str(getattr(strict, "recovery_strategy", "none"))
                checks = [
                    HarnessCheckV2(
                        name="proposal_schema_and_invariants",
                        status=HarnessCheckStatus.PASSED,
                        code="proposal_valid",
                        message="Strict proposal schema and domain invariants passed.",
                    )
                ]
                if recovery != "none":
                    checks.append(
                        HarnessCheckV2(
                            name="bounded_recovery",
                            status=HarnessCheckStatus.WARNING,
                            code=f"{recovery}_applied",
                            message="The proposal was produced by a bounded local recovery path.",
                        )
                    )
                return HarnessRuntimeValidationResult(
                    output=strict,
                    checks=tuple(checks),
                    status=(
                        HarnessStatus.REPAIRED
                        if recovery != "none"
                        else HarnessStatus.PASSED
                    ),
                    recovery_strategy=recovery,
                )

            runtime = HarnessOperationRuntime(
                repository=HarnessRuntimeRepository(self.database),
                artifact_resolver=AuthorizedJsonArtifactResolver(
                    self.artifacts, {snapshot.artifact_id: grant_id}
                ),
            )
            execution = runtime.execute(
                request=HarnessRuntimeRequest(
                    operation_binding=binding,
                    stage=stage,
                    trace_slot=0,
                    context=context,
                ),
                adapter=HarnessRuntimeStageAdapter(
                    adapter_contract=adapter_contract,
                    trace_contract=trace_contract,
                    generate=generate_from_snapshot,
                    decode=lambda raw: output_type.model_validate(raw, strict=True),
                    validate=validate,
                    recovery_strategy="bounded_repair",
                ),
                claim_owner=f"wave4-{kind.value}",
            )
            if not isinstance(execution, HarnessRuntimeExecutionV1):
                raise RuntimeError("harness_broad_runtime_execution_invalid")
            trace = execution.terminal_trace
            if trace is None:
                raise RuntimeError("harness_broad_runtime_trace_missing")
            success = trace.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}
            self.workflow_operations.terminalize(
                binding=binding,
                success=success,
                error_code=trace.error_code,
            )
            if not success:
                raise RuntimeError(trace.error_code or "harness_broad_workflow_failed")
            output = captured.get("output")
            if output is None:
                raise RuntimeError("harness_broad_runtime_output_missing")
            return output, trace
        except Exception as error:
            self.workflow_operations.terminalize(
                binding=binding,
                success=False,
                error_code=str(error),
            )
            raise

    def _prepare_existing_operation(
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
        snapshot, grant_id = self._register_snapshot(
            binding=operation_binding,
            artifact_type=artifact_type,
            artifact_contract=artifact_contract,
            protected_input=protected_input,
        )
        context = build_harness_context(
            workflow=workflow,
            stage=stage,
            operation_binding=operation_binding,
            input_contract=input_contract,
            input_manifest=manifest,
            subject_refs=(
                HarnessResourceRefV3(
                    resource_type=HarnessResourceType.FRONTEND_REQUEST,
                    resource_id=operation_binding.domain_operation_id,
                ),
            ),
            snapshot_refs=(snapshot,),
            prompt_contract=prompt_contract,
            policy_contract=policy_contract,
        )

        def generate_from_snapshot(_context, artifacts: Mapping[str, object]) -> BaseModel:
            return generate(
                _decode_protected_json(
                    artifacts[snapshot.artifact_id], artifact_contract
                )
            )

        def validate(output: BaseModel) -> HarnessRuntimeValidationResult:
            strict = output_type.model_validate(
                output.model_dump(mode="python", exclude_none=False), strict=True
            )
            checks = [
                HarnessCheckV2(
                    name="strict_output_schema",
                    status=HarnessCheckStatus.PASSED,
                    code="output_schema_valid",
                    message="Strict output schema passed.",
                )
            ]
            if isinstance(strict, DocumentProcessRuntimeOutputV1):
                checks.extend(
                    (
                        HarnessCheckV2(
                            name="page_coverage_and_order",
                            status=HarnessCheckStatus.PASSED,
                            code="page_coverage_valid",
                            message="Every page is present once in source order.",
                        ),
                        HarnessCheckV2(
                            name="section_chunk_study_unit_boundaries",
                            status=HarnessCheckStatus.PASSED,
                            code="document_boundaries_valid",
                            message="Section, Chunk, and Study Unit boundaries are valid.",
                        ),
                    )
                )
            else:
                checks.append(
                    HarnessCheckV2(
                        name="plan_grounding_and_references",
                        status=HarnessCheckStatus.PASSED,
                        code="plan_grounding_valid",
                        message="Schedule references resolve to the supplied Study Units.",
                    )
                )
            return HarnessRuntimeValidationResult(output=strict, checks=tuple(checks))

        runtime = HarnessOperationRuntime(
            repository=HarnessRuntimeRepository(self.database),
            artifact_resolver=AuthorizedJsonArtifactResolver(
                self.artifacts, {snapshot.artifact_id: grant_id}
            ),
        )
        result = runtime.execute(
            request=HarnessRuntimeRequest(
                operation_binding=operation_binding,
                stage=stage,
                trace_slot=0,
                context=context,
            ),
            adapter=HarnessRuntimeStageAdapter(
                adapter_contract=adapter_contract,
                trace_contract=trace_contract,
                generate=generate_from_snapshot,
                decode=lambda raw: output_type.model_validate(raw, strict=True),
                validate=validate,
                recovery_strategy="bounded_repair",
            ),
            claim_owner=f"wave4-{workflow.value}",
            _prepare_only=True,
        )
        if isinstance(result, HarnessRuntimeExecutionV1):
            trace = result.terminal_trace
            if trace is not None and trace.error_code == "stream_interrupted":
                raise StreamInterruptedError("stream_interrupted")
            raise RuntimeError(
                trace.error_code
                if trace is not None and trace.error_code
                else "harness_broad_runtime_prepare_failed"
            )
        if not isinstance(result, HarnessRuntimePreparedOutput):
            raise RuntimeError("harness_broad_runtime_prepare_invalid")
        return result, runtime

    def _register_snapshot(
        self,
        *,
        binding: HarnessOperationBindingV1,
        artifact_type: HarnessArtifactType,
        artifact_contract: HarnessContractRef,
        protected_input: dict[str, object],
    ) -> tuple[HarnessSnapshotRefV3, str]:
        content = json.dumps(
            {
                "schema_name": artifact_contract.name,
                "schema_version": artifact_contract.version,
                "input": protected_input,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        registration = self.artifacts.register_artifact(
            artifact_type=artifact_type,
            artifact_contract=artifact_contract,
            content=content,
        )
        grant = self.artifacts.issue_grant(
            harness_operation_id=binding.harness_operation_id,
            scopes=(
                HarnessArtifactGrantScopeV1(
                    artifact_id=registration.artifact_id,
                    artifact_type=artifact_type,
                    artifact_contract=artifact_contract,
                    permission=HarnessArtifactPermission.READ,
                ),
            ),
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        return (
            HarnessSnapshotRefV3(
                artifact_type=artifact_type,
                artifact_id=registration.artifact_id,
                contract=artifact_contract,
                payload_digest=registration.payload_digest,
            ),
            grant.grant_id,
        )



def _decode_protected_json(payload: object, contract: HarnessContractRef) -> dict[str, object]:
    if not isinstance(payload, bytes):
        raise ValueError("harness_protected_snapshot_bytes_required")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("harness_protected_snapshot_invalid") from error
    if not isinstance(decoded, dict):
        raise ValueError("harness_protected_snapshot_object_required")
    if (
        decoded.get("schema_name") != contract.name
        or decoded.get("schema_version") != contract.version
        or not isinstance(decoded.get("input"), dict)
    ):
        raise ValueError("harness_protected_snapshot_contract_mismatch")
    return dict(decoded["input"])




# Manifest decoder-route anchors. Runtime construction uses the shared service
# above; these names keep ownership explicit and import-checkable.
PersonaGenerationWorkflowAdapter = HarnessProposalRuntimeService
SceneGenerationWorkflowAdapter = HarnessProposalRuntimeService
DocumentProcessWorkflowAdapter = HarnessProposalRuntimeService
LearningPlanWorkflowAdapter = HarnessProposalRuntimeService
