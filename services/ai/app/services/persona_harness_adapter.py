from __future__ import annotations

from app.services.harness_domain_port import HarnessDomainExecutionPort
from app.models.persona_generation import (
    PersonaGenerationInputManifest,
    PersonaGenerationProposalV1,
    PERSONA_INPUT_CONTRACT,
    PERSONA_SNAPSHOT_CONTRACT,
    PERSONA_PROMPT_CONTRACT,
    PERSONA_POLICY_CONTRACT,
    PERSONA_ADAPTER_CONTRACT,
    PERSONA_TRACE_CONTRACT,
)
from typing import Callable
from app.models.harness import (
    HarnessArtifactType,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.harness_operation import HarnessDomainOperationKind


class PersonaHarnessAdapter:
    def __init__(self, runtime: HarnessDomainExecutionPort):
        self.runtime = runtime

    def run_persona(
        self,
        *,
        manifest: PersonaGenerationInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], PersonaGenerationProposalV1],
    ) -> tuple[PersonaGenerationProposalV1, HarnessTraceV3]:
        output, trace = self.runtime.run_proposal(
            kind=HarnessDomainOperationKind.PERSONA_GENERATION,
            workflow=HarnessWorkflow.PERSONA,
            stage=HarnessStage.PERSONA_GENERATION,
            manifest=manifest,
            input_contract=PERSONA_INPUT_CONTRACT,
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
