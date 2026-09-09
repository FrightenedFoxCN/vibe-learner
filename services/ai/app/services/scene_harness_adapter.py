from __future__ import annotations

from app.services.harness_domain_port import HarnessDomainExecutionPort
from app.models.scene_generation import (
    SceneGenerationInputManifest,
    SceneGenerationProposalV1,
    SCENE_INPUT_CONTRACT,
    SCENE_SNAPSHOT_CONTRACT,
    SCENE_PROMPT_CONTRACT,
    SCENE_POLICY_CONTRACT,
    SCENE_ADAPTER_CONTRACT,
    SCENE_TRACE_CONTRACT,
)
from typing import Callable
from app.models.harness import (
    HarnessArtifactType,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
)
from app.models.harness_operation import HarnessDomainOperationKind


class SceneHarnessAdapter:
    def __init__(self, runtime: HarnessDomainExecutionPort):
        self.runtime = runtime

    def run_scene(
        self,
        *,
        manifest: SceneGenerationInputManifest,
        protected_input: dict[str, object],
        generate: Callable[[dict[str, object]], SceneGenerationProposalV1],
    ) -> tuple[SceneGenerationProposalV1, HarnessTraceV3]:
        output, trace = self.runtime.run_proposal(
            kind=HarnessDomainOperationKind.SCENE_GENERATION,
            workflow=HarnessWorkflow.SCENE,
            stage=HarnessStage.SCENE_GENERATION,
            manifest=manifest,
            input_contract=SCENE_INPUT_CONTRACT,
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
