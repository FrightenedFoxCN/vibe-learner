from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.harness import (
    HARNESS_COMPONENT_REGISTRATIONS,
    HARNESS_OPERATION_COMMIT_POLICIES,
    HARNESS_OPERATION_STAGE_REGISTRATIONS,
    HARNESS_STAGE_WORKFLOWS,
    HarnessArtifactType,
    HarnessComponentName,
    HarnessContractRef,
    HarnessStage,
    HarnessWorkflow,
    require_versioned_harness_contract,
)
from app.models.harness_eval import HARNESS_EVAL_CASE_SCHEMA_VERSION
from app.models.tool_manifest import TOOL_MANIFEST_SCHEMA_VERSION


HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION = "harness-workflow-manifest-v1"
HARNESS_WORKFLOW_MANIFEST_EVAL_CASE_VERSION = HARNESS_EVAL_CASE_SCHEMA_VERSION


class HarnessManifestModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        allow_inf_nan=False,
    )


class HarnessManifestSlotStatus(StrEnum):
    REGISTERED = "registered"
    NOT_APPLICABLE = "not_applicable"
    UNREGISTERED = "unregistered"


class HarnessManifestNotApplicableReason(StrEnum):
    NO_MODEL_PROPOSAL = "no_model_proposal"
    NO_PROMPT = "no_prompt"
    NO_POLICY = "no_policy"
    NO_TOOLS = "no_tools"
    NO_ARTIFACTS = "no_artifacts"
    NO_EFFECTS = "no_effects"
    NO_COMMIT = "no_commit"
    NO_DECODER = "no_decoder"


class HarnessManifestUnregisteredReason(StrEnum):
    WORKFLOW_NOT_AUDITED = "workflow_not_audited"
    CONTRACT_NOT_REGISTERED = "contract_not_registered"
    ADAPTER_NOT_REGISTERED = "adapter_not_registered"
    COMPONENT_CONTRACT_NOT_REGISTERED = "component_contract_not_registered"
    POLICY_NOT_REGISTERED = "policy_not_registered"
    ARTIFACT_ALLOWLIST_NOT_REGISTERED = "artifact_allowlist_not_registered"
    EFFECT_ADAPTER_NOT_REGISTERED = "effect_adapter_not_registered"
    COMMIT_POLICY_NOT_REGISTERED = "commit_policy_not_registered"
    DECODER_NOT_REGISTERED = "decoder_not_registered"
    EVAL_SUITE_NOT_REGISTERED = "eval_suite_not_registered"


class HarnessManifestContractRefV1(HarnessManifestModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")

    @model_validator(mode="after")
    def reject_placeholder_version(self) -> "HarnessManifestContractRefV1":
        require_versioned_harness_contract(
            HarnessContractRef(name=self.name, version=self.version)
        )
        return self

    def to_harness_ref(self) -> HarnessContractRef:
        return HarnessContractRef(name=self.name, version=self.version)


class HarnessManifestRegisteredContractSlotV1(HarnessManifestModel):
    status: Literal[HarnessManifestSlotStatus.REGISTERED] = (
        HarnessManifestSlotStatus.REGISTERED
    )
    contract: HarnessManifestContractRefV1


class HarnessManifestRegisteredStringSlotV1(HarnessManifestModel):
    status: Literal[HarnessManifestSlotStatus.REGISTERED] = (
        HarnessManifestSlotStatus.REGISTERED
    )
    value: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$")


class HarnessManifestRegisteredArtifactSlotV1(HarnessManifestModel):
    status: Literal[HarnessManifestSlotStatus.REGISTERED] = (
        HarnessManifestSlotStatus.REGISTERED
    )
    artifact_types: tuple[HarnessArtifactType, ...] = Field(
        min_length=1,
        max_length=len(HarnessArtifactType),
    )

    @model_validator(mode="after")
    def validate_artifact_types(self) -> "HarnessManifestRegisteredArtifactSlotV1":
        values = tuple(item.value for item in self.artifact_types)
        if values != tuple(sorted(values)) or len(values) != len(set(values)):
            raise ValueError("harness_workflow_manifest_artifacts_not_canonical")
        return self


class HarnessManifestRegisteredContractListSlotV1(HarnessManifestModel):
    status: Literal[HarnessManifestSlotStatus.REGISTERED] = (
        HarnessManifestSlotStatus.REGISTERED
    )
    contracts: tuple[HarnessManifestContractRefV1, ...] = Field(
        min_length=1,
        max_length=64,
    )

    @model_validator(mode="after")
    def validate_contracts(self) -> "HarnessManifestRegisteredContractListSlotV1":
        identities = tuple((item.name, item.version) for item in self.contracts)
        if identities != tuple(sorted(identities)) or len(identities) != len(
            set(identities)
        ):
            raise ValueError("harness_workflow_manifest_contracts_not_canonical")
        return self


class HarnessManifestCommitPolicyKeyV1(HarnessManifestModel):
    workflow: HarnessWorkflow
    stage: HarnessStage
    trace_contract: HarnessManifestContractRefV1
    payload_contract: HarnessManifestContractRefV1


class HarnessManifestRegisteredCommitPolicySlotV1(HarnessManifestModel):
    status: Literal[HarnessManifestSlotStatus.REGISTERED] = (
        HarnessManifestSlotStatus.REGISTERED
    )
    key: HarnessManifestCommitPolicyKeyV1


class HarnessManifestNotApplicableSlotV1(HarnessManifestModel):
    status: Literal[HarnessManifestSlotStatus.NOT_APPLICABLE] = (
        HarnessManifestSlotStatus.NOT_APPLICABLE
    )
    reason: HarnessManifestNotApplicableReason


class HarnessManifestUnregisteredSlotV1(HarnessManifestModel):
    status: Literal[HarnessManifestSlotStatus.UNREGISTERED] = (
        HarnessManifestSlotStatus.UNREGISTERED
    )
    reason: HarnessManifestUnregisteredReason


HarnessManifestContractSlotV1 = Annotated[
    HarnessManifestRegisteredContractSlotV1
    | HarnessManifestNotApplicableSlotV1
    | HarnessManifestUnregisteredSlotV1,
    Field(discriminator="status"),
]
HarnessManifestStringSlotV1 = Annotated[
    HarnessManifestRegisteredStringSlotV1
    | HarnessManifestNotApplicableSlotV1
    | HarnessManifestUnregisteredSlotV1,
    Field(discriminator="status"),
]
HarnessManifestArtifactSlotV1 = Annotated[
    HarnessManifestRegisteredArtifactSlotV1
    | HarnessManifestNotApplicableSlotV1
    | HarnessManifestUnregisteredSlotV1,
    Field(discriminator="status"),
]
HarnessManifestContractListSlotV1 = Annotated[
    HarnessManifestRegisteredContractListSlotV1
    | HarnessManifestNotApplicableSlotV1
    | HarnessManifestUnregisteredSlotV1,
    Field(discriminator="status"),
]
HarnessManifestCommitPolicySlotV1 = Annotated[
    HarnessManifestRegisteredCommitPolicySlotV1
    | HarnessManifestNotApplicableSlotV1
    | HarnessManifestUnregisteredSlotV1,
    Field(discriminator="status"),
]


class HarnessManifestComponentContractV1(HarnessManifestModel):
    component_name: HarnessComponentName
    contract: HarnessManifestContractSlotV1


class HarnessManifestAttemptCeilingV1(HarnessManifestModel):
    max_attempts: int = Field(ge=1, le=8)
    max_repair_attempts: int = Field(ge=0, le=7)

    @model_validator(mode="after")
    def validate_attempts(self) -> "HarnessManifestAttemptCeilingV1":
        if self.max_repair_attempts >= self.max_attempts:
            raise ValueError("harness_workflow_manifest_attempt_ceiling_invalid")
        return self


class HarnessManifestExecutionBudgetV1(HarnessManifestModel):
    max_provider_calls: int = Field(ge=0, le=64)
    max_tool_calls: int = Field(ge=0, le=256)
    max_input_tokens: int = Field(ge=0, le=2_000_000)
    max_output_tokens: int = Field(ge=0, le=1_000_000)
    max_wall_time_ms: int = Field(ge=100, le=3_600_000)
    per_call_timeout_ms: int = Field(ge=100, le=900_000)

    @model_validator(mode="after")
    def validate_timeout(self) -> "HarnessManifestExecutionBudgetV1":
        if self.per_call_timeout_ms > self.max_wall_time_ms:
            raise ValueError("harness_workflow_manifest_timeout_budget_invalid")
        return self


class HarnessWorkflowManifestEntryV1(HarnessManifestModel):
    key: str = Field(
        pattern=r"^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*$",
    )
    workflow: HarnessWorkflow
    stage: HarnessStage
    registration: HarnessManifestContractSlotV1
    owner_module: str = Field(pattern=r"^[A-Za-z0-9_.]+$")
    owner_adapter: HarnessManifestContractSlotV1
    input_contract: HarnessManifestContractSlotV1
    proposal_contract: HarnessManifestContractSlotV1
    output_contract: HarnessManifestContractSlotV1
    component_contracts: tuple[HarnessManifestComponentContractV1, ...] = Field(
        min_length=1,
        max_length=32,
    )
    prompt_contract: HarnessManifestContractSlotV1
    policy_contract: HarnessManifestContractSlotV1
    toolset_contract: HarnessManifestContractSlotV1
    attempt_ceiling: HarnessManifestAttemptCeilingV1
    execution_budget: HarnessManifestExecutionBudgetV1
    allowed_artifact_types: HarnessManifestArtifactSlotV1
    allowed_effect_adapters: HarnessManifestContractListSlotV1
    commit_policy: HarnessManifestCommitPolicySlotV1
    decoder_route: HarnessManifestStringSlotV1
    eval_route: HarnessManifestStringSlotV1
    eval_suites: HarnessManifestContractListSlotV1

    @model_validator(mode="after")
    def validate_entry(self) -> "HarnessWorkflowManifestEntryV1":
        if self.key != f"{self.workflow.value}:{self.stage.value}":
            raise ValueError("harness_workflow_manifest_key_mismatch")
        if HARNESS_STAGE_WORKFLOWS.get(self.stage) != self.workflow:
            raise ValueError("harness_workflow_manifest_stage_workflow_mismatch")
        component_names = tuple(
            item.component_name.value for item in self.component_contracts
        )
        if component_names != tuple(sorted(component_names)) or len(
            component_names
        ) != len(set(component_names)):
            raise ValueError("harness_workflow_manifest_components_not_canonical")
        return self


class HarnessWorkflowManifestV1(HarnessManifestModel):
    schema_name: Literal["HarnessWorkflowManifest"] = "HarnessWorkflowManifest"
    schema_version: Literal["harness-workflow-manifest-v1"] = (
        HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION
    )
    stages: tuple[HarnessWorkflowManifestEntryV1, ...]

    @model_validator(mode="after")
    def validate_manifest(self) -> "HarnessWorkflowManifestV1":
        keys = tuple(entry.key for entry in self.stages)
        expected_keys = tuple(
            sorted(
                f"{workflow.value}:{stage.value}"
                for workflow, stage in HARNESS_OPERATION_STAGE_REGISTRATIONS
            )
        )
        if keys != expected_keys or len(keys) != len(set(keys)):
            raise ValueError("harness_workflow_manifest_stage_set_invalid")
        for entry in self.stages:
            _validate_entry_against_vocabulary(entry)
        return self


def _contract(name: str, version: str) -> HarnessManifestContractRefV1:
    return HarnessManifestContractRefV1(name=name, version=version)


def _registered_contract(
    name: str,
    version: str,
) -> HarnessManifestRegisteredContractSlotV1:
    return HarnessManifestRegisteredContractSlotV1(
        contract=_contract(name, version),
    )


def _registered_string(value: str) -> HarnessManifestRegisteredStringSlotV1:
    return HarnessManifestRegisteredStringSlotV1(value=value)


def _not_applicable(
    reason: HarnessManifestNotApplicableReason,
) -> HarnessManifestNotApplicableSlotV1:
    return HarnessManifestNotApplicableSlotV1(reason=reason)


def _unregistered(
    reason: HarnessManifestUnregisteredReason,
) -> HarnessManifestUnregisteredSlotV1:
    return HarnessManifestUnregisteredSlotV1(reason=reason)


def _artifact_allowlist(
    *artifact_types: HarnessArtifactType,
) -> HarnessManifestRegisteredArtifactSlotV1:
    return HarnessManifestRegisteredArtifactSlotV1(
        artifact_types=tuple(sorted(artifact_types, key=lambda item: item.value))
    )


def _registered_contracts(
    *contracts: tuple[str, str],
) -> HarnessManifestRegisteredContractListSlotV1:
    return HarnessManifestRegisteredContractListSlotV1(
        contracts=tuple(
            sorted(
                (_contract(name, version) for name, version in contracts),
                key=lambda item: (item.name, item.version),
            )
        )
    )


def _component_contracts(
    workflow: HarnessWorkflow,
    stage: HarnessStage,
) -> tuple[HarnessManifestComponentContractV1, ...]:
    stage_registration = HARNESS_OPERATION_STAGE_REGISTRATIONS[(workflow, stage)]
    items: list[HarnessManifestComponentContractV1] = []
    for component_name in stage_registration.component_names:
        component = HARNESS_COMPONENT_REGISTRATIONS[component_name]
        slot: HarnessManifestContractSlotV1
        if component.contract is None:
            slot = _unregistered(
                HarnessManifestUnregisteredReason.COMPONENT_CONTRACT_NOT_REGISTERED
            )
        else:
            slot = _registered_contract(
                component.contract.name,
                component.contract.version,
            )
        items.append(
            HarnessManifestComponentContractV1(
                component_name=component_name,
                contract=slot,
            )
        )
    return tuple(sorted(items, key=lambda item: item.component_name.value))


_DEFAULT_ATTEMPTS = HarnessManifestAttemptCeilingV1(
    max_attempts=3,
    max_repair_attempts=2,
)
_DEFAULT_BUDGET = HarnessManifestExecutionBudgetV1(
    max_provider_calls=3,
    max_tool_calls=16,
    max_input_tokens=64_000,
    max_output_tokens=8_000,
    max_wall_time_ms=180_000,
    per_call_timeout_ms=120_000,
)


def _unregistered_entry(
    workflow: HarnessWorkflow,
    stage: HarnessStage,
    *,
    artifact_types: tuple[HarnessArtifactType, ...],
    prompt: HarnessManifestContractSlotV1 | None = None,
    toolset: HarnessManifestContractSlotV1 | None = None,
    no_effects: bool = False,
    no_commit: bool = False,
) -> HarnessWorkflowManifestEntryV1:
    vocabulary = HARNESS_OPERATION_STAGE_REGISTRATIONS[(workflow, stage)]
    return HarnessWorkflowManifestEntryV1(
        key=f"{workflow.value}:{stage.value}",
        workflow=workflow,
        stage=stage,
        registration=_unregistered(
            HarnessManifestUnregisteredReason.WORKFLOW_NOT_AUDITED
        ),
        owner_module=vocabulary.owner_module,
        owner_adapter=_unregistered(
            HarnessManifestUnregisteredReason.ADAPTER_NOT_REGISTERED
        ),
        input_contract=_unregistered(
            HarnessManifestUnregisteredReason.CONTRACT_NOT_REGISTERED
        ),
        proposal_contract=_unregistered(
            HarnessManifestUnregisteredReason.CONTRACT_NOT_REGISTERED
        ),
        output_contract=_unregistered(
            HarnessManifestUnregisteredReason.CONTRACT_NOT_REGISTERED
        ),
        component_contracts=_component_contracts(workflow, stage),
        prompt_contract=prompt
        or _not_applicable(HarnessManifestNotApplicableReason.NO_PROMPT),
        policy_contract=_unregistered(
            HarnessManifestUnregisteredReason.POLICY_NOT_REGISTERED
        ),
        toolset_contract=toolset
        or _not_applicable(HarnessManifestNotApplicableReason.NO_TOOLS),
        attempt_ceiling=_DEFAULT_ATTEMPTS,
        execution_budget=_DEFAULT_BUDGET,
        allowed_artifact_types=_artifact_allowlist(*artifact_types),
        allowed_effect_adapters=(
            _not_applicable(HarnessManifestNotApplicableReason.NO_EFFECTS)
            if no_effects
            else _unregistered(
                HarnessManifestUnregisteredReason.EFFECT_ADAPTER_NOT_REGISTERED
            )
        ),
        commit_policy=(
            _not_applicable(HarnessManifestNotApplicableReason.NO_COMMIT)
            if no_commit
            else _unregistered(
                HarnessManifestUnregisteredReason.COMMIT_POLICY_NOT_REGISTERED
            )
        ),
        decoder_route=_unregistered(
            HarnessManifestUnregisteredReason.DECODER_NOT_REGISTERED
        ),
        eval_route=_registered_string(vocabulary.eval_route),
        eval_suites=_unregistered(
            HarnessManifestUnregisteredReason.EVAL_SUITE_NOT_REGISTERED
        ),
    )


_TOOL_MANIFEST_SLOT = _registered_contract(
    "ToolManifestRegistry",
    TOOL_MANIFEST_SCHEMA_VERSION,
)


_TAVERN_ENTRY = HarnessWorkflowManifestEntryV1(
    key="tavern:actor_reply",
    workflow=HarnessWorkflow.TAVERN,
    stage=HarnessStage.TAVERN_ACTOR_REPLY,
    registration=_registered_contract(
        "TavernActorReplyWorkflowManifestEntry",
        "tavern-actor-reply-workflow-manifest-v1",
    ),
    owner_module="app.services.tavern",
    owner_adapter=_registered_contract(
        "TavernActorWorkflowAdapter",
        "tavern-actor-workflow-adapter-v1",
    ),
    input_contract=_registered_contract(
        "TavernActorInputManifest",
        "tavern-actor-input-manifest-v1",
    ),
    proposal_contract=_registered_contract(
        "TavernActorReply",
        "tavern-actor-reply-v1",
    ),
    output_contract=_registered_contract(
        "TavernPersonaMessageCommittedProjection",
        "tavern-persona-message-committed-projection-v1",
    ),
    component_contracts=_component_contracts(
        HarnessWorkflow.TAVERN,
        HarnessStage.TAVERN_ACTOR_REPLY,
    ),
    prompt_contract=_registered_contract(
        "TavernActorPrompt",
        "tavern-actor-v1",
    ),
    policy_contract=_registered_contract(
        "TavernHarnessPolicy",
        "tavern-harness-v1",
    ),
    toolset_contract=_not_applicable(HarnessManifestNotApplicableReason.NO_TOOLS),
    attempt_ceiling=HarnessManifestAttemptCeilingV1(
        max_attempts=3,
        max_repair_attempts=2,
    ),
    execution_budget=HarnessManifestExecutionBudgetV1(
        max_provider_calls=3,
        max_tool_calls=0,
        max_input_tokens=24_000,
        max_output_tokens=4_000,
        max_wall_time_ms=180_000,
        per_call_timeout_ms=120_000,
    ),
    allowed_artifact_types=_artifact_allowlist(
        HarnessArtifactType.PERSONA_SNAPSHOT,
        HarnessArtifactType.SCENE_SNAPSHOT,
        HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,
        HarnessArtifactType.TAVERN_TRANSCRIPT,
    ),
    allowed_effect_adapters=_not_applicable(
        HarnessManifestNotApplicableReason.NO_EFFECTS
    ),
    commit_policy=HarnessManifestRegisteredCommitPolicySlotV1(
        key=HarnessManifestCommitPolicyKeyV1(
            workflow=HarnessWorkflow.TAVERN,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            trace_contract=_contract(
                "TavernActorReply",
                "tavern-actor-reply-v2",
            ),
            payload_contract=_contract(
                "TavernPersonaMessageCommittedProjection",
                "tavern-persona-message-committed-projection-v1",
            ),
        )
    ),
    decoder_route=_registered_string(
        "app.services.tavern_harness.TavernActorHarness"
    ),
    eval_route=_registered_string("tavern.actor_reply"),
    eval_suites=_unregistered(
        HarnessManifestUnregisteredReason.EVAL_SUITE_NOT_REGISTERED
    ),
)


_ENTRIES = (
    _unregistered_entry(
        HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.DOCUMENT_PARSE,
        artifact_types=(HarnessArtifactType.DOCUMENT_UPLOAD,),
    ),
    _unregistered_entry(
        HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.PAGE_EXTRACTION,
        artifact_types=(HarnessArtifactType.DOCUMENT_UPLOAD,),
        no_effects=True,
        no_commit=True,
    ),
    _unregistered_entry(
        HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.SECTION_DETECTION,
        artifact_types=(HarnessArtifactType.DOCUMENT_DEBUG,),
        no_effects=True,
        no_commit=True,
    ),
    _unregistered_entry(
        HarnessWorkflow.DOCUMENT_PARSE,
        HarnessStage.CHUNK_BUILDING,
        artifact_types=(
            HarnessArtifactType.DOCUMENT_DEBUG,
            HarnessArtifactType.DOCUMENT_UPLOAD,
        ),
        no_effects=True,
        no_commit=True,
    ),
    _unregistered_entry(
        HarnessWorkflow.OCR,
        HarnessStage.OCR_PAGE,
        artifact_types=(
            HarnessArtifactType.DOCUMENT_UPLOAD,
            HarnessArtifactType.OCR_PAGE,
        ),
    ),
    _unregistered_entry(
        HarnessWorkflow.STUDY_UNIT_CLEANUP,
        HarnessStage.STUDY_UNIT_CLEANUP,
        artifact_types=(
            HarnessArtifactType.DOCUMENT_DEBUG,
            HarnessArtifactType.STUDY_UNIT_INPUT,
        ),
    ),
    _unregistered_entry(
        HarnessWorkflow.PLANNING,
        HarnessStage.PLAN_GENERATION,
        artifact_types=(
            HarnessArtifactType.DOCUMENT_DEBUG,
            HarnessArtifactType.PERSONA_SNAPSHOT,
            HarnessArtifactType.PLANNING_CONTEXT,
            HarnessArtifactType.SCENE_SNAPSHOT,
            HarnessArtifactType.STUDY_UNIT_INPUT,
        ),
        prompt=_unregistered(
            HarnessManifestUnregisteredReason.CONTRACT_NOT_REGISTERED
        ),
        toolset=_TOOL_MANIFEST_SLOT,
    ),
    _unregistered_entry(
        HarnessWorkflow.PLANNING,
        HarnessStage.PLANNING_TOOL_EXECUTION,
        artifact_types=(
            HarnessArtifactType.DOCUMENT_DEBUG,
            HarnessArtifactType.PLANNING_CONTEXT,
            HarnessArtifactType.STUDY_UNIT_INPUT,
        ),
        toolset=_TOOL_MANIFEST_SLOT,
    ),
    _unregistered_entry(
        HarnessWorkflow.PERSONA,
        HarnessStage.PERSONA_GENERATION,
        artifact_types=(HarnessArtifactType.PERSONA_SNAPSHOT,),
    ),
    _unregistered_entry(
        HarnessWorkflow.SCENE,
        HarnessStage.SCENE_GENERATION,
        artifact_types=(
            HarnessArtifactType.PERSONA_SNAPSHOT,
            HarnessArtifactType.SCENE_SNAPSHOT,
        ),
    ),
    _unregistered_entry(
        HarnessWorkflow.STUDY_CHAT,
        HarnessStage.STUDY_CHAT_REPLY,
        artifact_types=(
            HarnessArtifactType.DOCUMENT_UPLOAD,
            HarnessArtifactType.PLANNING_CONTEXT,
            HarnessArtifactType.SCENE_SNAPSHOT,
            HarnessArtifactType.STUDY_SESSION_SNAPSHOT,
        ),
        prompt=_unregistered(
            HarnessManifestUnregisteredReason.CONTRACT_NOT_REGISTERED
        ),
        toolset=_TOOL_MANIFEST_SLOT,
    ),
    _TAVERN_ENTRY,
    _unregistered_entry(
        HarnessWorkflow.FRONTEND_DECODE,
        HarnessStage.FRONTEND_RESPONSE_DECODE,
        artifact_types=(HarnessArtifactType.FRONTEND_RESPONSE_FIXTURE,),
        no_effects=True,
        no_commit=True,
    ),
)


def _validate_entry_against_vocabulary(
    entry: HarnessWorkflowManifestEntryV1,
) -> None:
    vocabulary = HARNESS_OPERATION_STAGE_REGISTRATIONS.get(
        (entry.workflow, entry.stage)
    )
    if vocabulary is None:
        raise ValueError("harness_workflow_manifest_stage_unknown")
    if entry.owner_module != vocabulary.owner_module:
        raise ValueError("harness_workflow_manifest_owner_mismatch")
    expected_components = tuple(
        item.value for item in vocabulary.component_names
    )
    actual_components = tuple(
        item.component_name.value for item in entry.component_contracts
    )
    if actual_components != expected_components:
        raise ValueError("harness_workflow_manifest_component_set_mismatch")
    for item in entry.component_contracts:
        canonical = HARNESS_COMPONENT_REGISTRATIONS[item.component_name].contract
        if canonical is None:
            if not isinstance(item.contract, HarnessManifestUnregisteredSlotV1):
                raise ValueError(
                    "harness_workflow_manifest_unregistered_component_claim"
                )
        elif not isinstance(
            item.contract,
            HarnessManifestRegisteredContractSlotV1,
        ) or (
            item.contract.contract.name,
            item.contract.contract.version,
        ) != (canonical.name, canonical.version):
            raise ValueError("harness_workflow_manifest_component_contract_mismatch")
    if not isinstance(entry.eval_route, HarnessManifestRegisteredStringSlotV1):
        raise ValueError("harness_workflow_manifest_eval_route_unregistered")
    if entry.eval_route.value != vocabulary.eval_route:
        raise ValueError("harness_workflow_manifest_eval_route_mismatch")
    if entry.stage == HarnessStage.PLANNING_TOOL_EXECUTION:
        if not isinstance(
            entry.toolset_contract,
            HarnessManifestRegisteredContractSlotV1,
        ) or entry.toolset_contract.contract != _contract(
            "ToolManifestRegistry",
            TOOL_MANIFEST_SCHEMA_VERSION,
        ):
            raise ValueError("harness_workflow_manifest_tool_manifest_mismatch")
    if isinstance(
        entry.commit_policy,
        HarnessManifestRegisteredCommitPolicySlotV1,
    ):
        key = entry.commit_policy.key
        matches = [
            policy
            for policy_key, policy in HARNESS_OPERATION_COMMIT_POLICIES.items()
            if (
                policy_key.workflow == key.workflow
                and policy_key.stage == key.stage
                and policy_key.trace_contract_name == key.trace_contract.name
                and policy_key.trace_contract_version == key.trace_contract.version
                and policy_key.payload_contract_name == key.payload_contract.name
                and policy_key.payload_contract_version
                == key.payload_contract.version
            )
        ]
        if len(matches) != 1:
            raise ValueError("harness_workflow_manifest_commit_policy_unknown")


HARNESS_WORKFLOW_MANIFEST = HarnessWorkflowManifestV1(
    stages=tuple(sorted(_ENTRIES, key=lambda item: item.key))
)
HARNESS_WORKFLOW_MANIFEST_ENTRIES = MappingProxyType(
    {entry.key: entry for entry in HARNESS_WORKFLOW_MANIFEST.stages}
)


def require_executable_workflow_manifest_entry(
    workflow: HarnessWorkflow,
    stage: HarnessStage,
) -> HarnessWorkflowManifestEntryV1:
    entry = HARNESS_WORKFLOW_MANIFEST_ENTRIES.get(
        f"{workflow.value}:{stage.value}"
    )
    if entry is None:
        raise ValueError("harness_workflow_manifest_stage_unknown")
    if not isinstance(
        entry.registration,
        HarnessManifestRegisteredContractSlotV1,
    ):
        raise ValueError("harness_workflow_manifest_stage_unregistered")
    required_contracts = (
        entry.owner_adapter,
        entry.input_contract,
        entry.proposal_contract,
        entry.output_contract,
    )
    if any(
        not isinstance(item, HarnessManifestRegisteredContractSlotV1)
        for item in required_contracts
    ):
        raise ValueError("harness_workflow_manifest_required_contract_unregistered")
    if any(
        not isinstance(
            item.contract,
            HarnessManifestRegisteredContractSlotV1,
        )
        for item in entry.component_contracts
    ):
        raise ValueError("harness_workflow_manifest_component_unregistered")
    optional_slots = (
        entry.prompt_contract,
        entry.policy_contract,
        entry.toolset_contract,
        entry.allowed_artifact_types,
        entry.allowed_effect_adapters,
        entry.commit_policy,
        entry.decoder_route,
    )
    if any(isinstance(item, HarnessManifestUnregisteredSlotV1) for item in optional_slots):
        raise ValueError("harness_workflow_manifest_execution_slot_unregistered")
    if not isinstance(entry.eval_route, HarnessManifestRegisteredStringSlotV1):
        raise ValueError("harness_workflow_manifest_eval_route_unregistered")
    # Eval suites are governance-visible but intentionally not an execution
    # prerequisite until the runner/baseline wave establishes suite contracts.
    return entry


def validate_harness_context_manifest_inputs(
    *,
    entry: HarnessWorkflowManifestEntryV1,
    input_contract: HarnessContractRef,
    prompt_contract: HarnessContractRef | None,
    policy_contract: HarnessContractRef | None,
    component_contracts: tuple[HarnessContractRef, ...],
    artifact_types: tuple[HarnessArtifactType, ...],
) -> None:
    _require_contract_slot_match(
        entry.input_contract,
        input_contract,
        "input_contract",
    )
    _require_optional_contract_slot_match(
        entry.prompt_contract,
        prompt_contract,
        "prompt_contract",
    )
    _require_optional_contract_slot_match(
        entry.policy_contract,
        policy_contract,
        "policy_contract",
    )
    expected_components = tuple(
        item.contract.contract.to_harness_ref()
        for item in entry.component_contracts
        if isinstance(
            item.contract,
            HarnessManifestRegisteredContractSlotV1,
        )
    )
    if component_contracts != expected_components:
        raise ValueError("harness_workflow_manifest_component_contract_drift")
    if isinstance(
        entry.allowed_artifact_types,
        HarnessManifestRegisteredArtifactSlotV1,
    ):
        allowed = set(entry.allowed_artifact_types.artifact_types)
        if any(item not in allowed for item in artifact_types):
            raise ValueError("harness_workflow_manifest_artifact_not_allowed")
    elif artifact_types:
        raise ValueError("harness_workflow_manifest_artifact_not_allowed")


def _require_contract_slot_match(
    slot: HarnessManifestContractSlotV1,
    actual: HarnessContractRef,
    field_name: str,
) -> None:
    if not isinstance(slot, HarnessManifestRegisteredContractSlotV1):
        raise ValueError(f"harness_workflow_manifest_{field_name}_unregistered")
    if (actual.name, actual.version) != (
        slot.contract.name,
        slot.contract.version,
    ):
        raise ValueError(f"harness_workflow_manifest_{field_name}_drift")


def _require_optional_contract_slot_match(
    slot: HarnessManifestContractSlotV1,
    actual: HarnessContractRef | None,
    field_name: str,
) -> None:
    if isinstance(slot, HarnessManifestRegisteredContractSlotV1):
        if actual is None or (actual.name, actual.version) != (
            slot.contract.name,
            slot.contract.version,
        ):
            raise ValueError(f"harness_workflow_manifest_{field_name}_drift")
    elif isinstance(slot, HarnessManifestNotApplicableSlotV1):
        if actual is not None:
            raise ValueError(
                f"harness_workflow_manifest_{field_name}_not_applicable"
            )
    else:
        raise ValueError(f"harness_workflow_manifest_{field_name}_unregistered")


def harness_workflow_manifest_snapshot() -> dict[str, object]:
    return HARNESS_WORKFLOW_MANIFEST.model_dump(mode="json")
