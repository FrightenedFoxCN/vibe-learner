from __future__ import annotations

from app.services.harness_domain_port import HarnessDomainExecutionPort
from app.models.document_processing import (
    DocumentProcessInputManifest,
    DocumentProcessRuntimeOutputV1,
    DocumentStageInputManifest,
    DocumentStageEvidenceV1,
    DOCUMENT_INPUT_CONTRACT,
    DOCUMENT_SNAPSHOT_CONTRACT,
    DOCUMENT_POLICY_CONTRACT,
    DOCUMENT_ADAPTER_CONTRACT,
    DOCUMENT_TRACE_CONTRACT,
    DOCUMENT_STAGE_INPUT_CONTRACT,
    DOCUMENT_STAGE_PROTECTED_INPUT_CONTRACT,
    DOCUMENT_STAGE_POLICY_CONTRACT,
    DOCUMENT_STAGE_ADAPTER_CONTRACT,
    DOCUMENT_STAGE_TRACE_CONTRACT,
)
from typing import Callable
from app.models.harness import (
    HarnessArtifactType,
    HarnessStage,
    HarnessStatus,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.harness_operation import HarnessDomainOperationKind, HarnessOperationBindingV1
from app.services.harness_runtime import HarnessOperationRuntime, HarnessRuntimePreparedOutput


class DocumentHarnessAdapter:
    def __init__(self, runtime: HarnessDomainExecutionPort):
        self.runtime = runtime

    def prepare_document(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        manifest: DocumentProcessInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], DocumentProcessRuntimeOutputV1],
    ) -> tuple[HarnessRuntimePreparedOutput, HarnessOperationRuntime]:
        return self.runtime.prepare_existing_operation(
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
        return self.runtime.emit_stage_evidence(
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

    def emit_ocr_stage_evidence(
        self,
        *,
        document_id: str,
        input_manifest: DocumentStageInputManifest,
        evidence: DocumentStageEvidenceV1,
        protected_stage_input: dict[str, object] | None = None,
    ) -> HarnessTraceV3:
        binding = self.runtime.workflow_operations.admit(
            kind=HarnessDomainOperationKind.DOCUMENT_OCR,
            request_manifest=input_manifest.model_dump(mode="json", exclude_none=False),
        )
        try:
            trace = self.runtime.emit_stage_evidence(
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
            self.runtime.workflow_operations.terminalize(
                binding=binding, success=False, error_code=str(error)
            )
            raise
        success = trace.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}
        self.runtime.workflow_operations.terminalize(
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
        binding = self.runtime.workflow_operations.admit(
            kind=HarnessDomainOperationKind.STUDY_UNIT_CLEANUP,
            request_manifest=input_manifest.model_dump(mode="json", exclude_none=False),
        )
        try:
            trace = self.runtime.emit_stage_evidence(
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
            self.runtime.workflow_operations.terminalize(
                binding=binding, success=False, error_code=str(error)
            )
            raise
        success = trace.status in {HarnessStatus.PASSED, HarnessStatus.REPAIRED}
        self.runtime.workflow_operations.terminalize(
            binding=binding,
            success=success,
            error_code=trace.error_code,
        )
        return trace
