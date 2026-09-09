from __future__ import annotations

from typing import ClassVar, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.models.harness import HarnessContractRef, HarnessSafeManifest
from app.models.scene import SceneTreeProposalV1


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


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


class SceneGenerationInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"mode", "requested_layer_count", "input_char_count"}
    )

    mode: Literal["keywords", "long_text"]
    requested_layer_count: int
    input_char_count: int


class SceneGenerationProposalV1(_StrictModel):
    schema_name: Literal["SceneGenerationProposal"] = "SceneGenerationProposal"
    schema_version: Literal["scene-generation-proposal-v1"] = (
        "scene-generation-proposal-v1"
    )
    used_model: str = Field(max_length=500)
    used_web_search: bool
    proposal: SceneTreeProposalV1
