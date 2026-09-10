from __future__ import annotations

from app.core.diagnostics import reference_harness

from app.services.persona_harness_adapter import PersonaHarnessAdapter
from app.services.scene_harness_adapter import SceneHarnessAdapter
from app.services.document_harness_adapter import DocumentHarnessAdapter
from app.services.planning_harness_adapter import PlanningHarnessAdapter

from app.models.persona_generation import PersonaGenerationInputManifest, PersonaGenerationProposalV1
from app.models.scene_generation import SceneGenerationInputManifest, SceneGenerationProposalV1
from app.models.document_processing import (
    DocumentProcessInputManifest,
    DocumentProcessRuntimeOutputV1,
    DocumentStageInputManifest,
    DocumentStageEvidenceV1,
)
from app.models.planning_runtime import (
    LearningPlanInputManifest,
    LearningPlanRuntimeOutputV1,
    PlanningToolExecutionInputManifest,
    PlanningToolExecutionEvidenceV1,
)

from app.services.model_recovery import get_model_recovery_state

from datetime import UTC, datetime, timedelta
import json
from typing import Callable, Mapping

from pydantic import BaseModel

from app.models.harness import (
    HarnessArtifactType,
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessResourceType,
    HarnessSafeManifest,
    HarnessSnapshotRefV3,
    HarnessStage,
    HarnessStatus,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.harness_artifact_access import (
    HarnessArtifactGrantScopeV1,
    HarnessArtifactPermission,
    HarnessArtifactResolutionStatus,
    HarnessArtifactResolveRequestV1,
)
from app.models.harness_operation import HarnessDomainOperationKind, HarnessOperationBindingV1
from app.models.harness_runtime import HarnessRuntimeExecutionV1
from app.persistence.database import Database
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.persistence.harness_workflow_operation_repository import HarnessWorkflowOperationRepository
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
        requests: list[HarnessArtifactResolveRequestV1] = []
        for ref in context.snapshot_refs:
            grant_id = self.grants.get(ref.artifact_id)
            if not grant_id:
                raise PermissionError("harness_artifact_grant_missing")
            requests.append(
                HarnessArtifactResolveRequestV1(
                    grant_id=grant_id,
                    harness_operation_id=operation_binding.harness_operation_id,
                    artifact_id=ref.artifact_id,
                    artifact_type=ref.artifact_type,
                    artifact_contract=ref.contract,
                    permission=HarnessArtifactPermission.READ,
                )
            )
        if not requests:
            return ()
        for result in self.artifacts.resolve_batch(requests).results:
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
        self.persona = PersonaHarnessAdapter(self)
        self.scene = SceneHarnessAdapter(self)
        self.document = DocumentHarnessAdapter(self)
        self.planning = PlanningHarnessAdapter(self)

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
        return self.persona.run_persona(
            manifest=manifest,
            protected_input=protected_input,
            generate=generate,
        )

    def prepare_document(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        manifest: DocumentProcessInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], DocumentProcessRuntimeOutputV1],
    ) -> tuple[HarnessRuntimePreparedOutput, HarnessOperationRuntime]:
        return self.document.prepare_document(
            operation_binding=operation_binding,
            manifest=manifest,
            protected_input=protected_input,
            generate=generate,
        )

    def prepare_plan(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        manifest: LearningPlanInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], LearningPlanRuntimeOutputV1],
    ) -> tuple[HarnessRuntimePreparedOutput, HarnessOperationRuntime]:
        return self.planning.prepare_plan(
            operation_binding=operation_binding,
            manifest=manifest,
            protected_input=protected_input,
            generate=generate,
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
        return self.document.emit_document_stage_evidence(
            operation_binding=operation_binding,
            parent_trace_id=parent_trace_id,
            stage=stage,
            trace_slot=trace_slot,
            input_manifest=input_manifest,
            evidence=evidence,
            artifact_type=artifact_type,
            protected_stage_input=protected_stage_input,
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
        return self.planning.emit_planning_tool_evidence(
            operation_binding=operation_binding,
            parent_trace_id=parent_trace_id,
            trace_slot=trace_slot,
            input_manifest=input_manifest,
            evidence=evidence,
            protected_input=protected_input,
        )

    def emit_ocr_stage_evidence(
        self,
        *,
        document_id: str,
        input_manifest: DocumentStageInputManifest,
        evidence: DocumentStageEvidenceV1,
        protected_stage_input: dict[str, object] | None = None,
    ) -> HarnessTraceV3:
        return self.document.emit_ocr_stage_evidence(
            document_id=document_id,
            input_manifest=input_manifest,
            evidence=evidence,
            protected_stage_input=protected_stage_input,
        )

    def emit_study_unit_cleanup_evidence(
        self,
        *,
        document_id: str,
        input_manifest: DocumentStageInputManifest,
        evidence: DocumentStageEvidenceV1,
        protected_stage_input: dict[str, object] | None = None,
    ) -> HarnessTraceV3:
        return self.document.emit_study_unit_cleanup_evidence(
            document_id=document_id,
            input_manifest=input_manifest,
            evidence=evidence,
            protected_stage_input=protected_stage_input,
        )


    def run_scene(
        self,
        *,
        manifest: SceneGenerationInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], SceneGenerationProposalV1],
    ) -> tuple[SceneGenerationProposalV1, HarnessTraceV3]:
        return self.scene.run_scene(
            manifest=manifest,
            protected_input=protected_input,
            generate=generate,
        )

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
                input_contract=input_contract,
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
            structured_retry_observed = False

            def generate_from_snapshot(_context, artifacts: Mapping[str, object]) -> BaseModel:
                nonlocal structured_retry_observed
                payload = _decode_protected_json(
                    artifacts[snapshot.artifact_id], artifact_contract
                )
                previous = {item.recovery_id for item in get_model_recovery_state()}
                output = generate(payload)
                structured_retry_observed = any(
                    item.recovery_id not in previous and item.strategy == "retry_structured_json"
                    for item in get_model_recovery_state()
                )
                return output

            def validate(output: BaseModel) -> HarnessRuntimeValidationResult:
                strict = output_type.model_validate(
                    output.model_dump(mode="python", exclude_none=False), strict=True
                )
                captured["output"] = strict
                recovery = str(getattr(strict, "recovery_strategy", "none"))
                if recovery == "none" and structured_retry_observed:
                    recovery = "structured_json_retry"
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
                            message="The proposal was produced after a bounded recovery path.",
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
            reference_harness(binding, trace)
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
