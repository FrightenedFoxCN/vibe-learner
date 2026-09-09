from __future__ import annotations

from typing import ClassVar, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from app.models.harness import HarnessContractRef, HarnessSafeManifest


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


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


class PersonaGenerationInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"request_kind", "mode", "requested_count", "input_char_count"}
    )

    request_kind: Literal["card_batch", "setting_assist", "slot_assist"]
    mode: str
    requested_count: int
    input_char_count: int


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


class PersonaCardBatchContentProposalV1(_StrictModel):
    """Raw model response, before application/provider metadata is attached."""

    summary: str = Field(max_length=8000)
    relationship: str = Field(max_length=2000)
    learner_address: str = Field(max_length=500)
    cards: list[PersonaCardContentProposalV1] = Field(min_length=1, max_length=24)


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
