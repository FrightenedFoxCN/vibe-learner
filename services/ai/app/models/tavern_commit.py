from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.harness_component_versions import (
    TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_NAME,
    TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_VERSION,
    TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_NAME,
    TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_VERSION,
    TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_NAME,
    TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_VERSION,
)


_RESOURCE_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$"
_OPERATION_ID_PATTERN = r"^harness-operation-[0-9a-f]{32}$"


class _TavernCommitModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TavernPersonaMessageCommitMetadataV1(_TavernCommitModel):
    """Server-owned identity persisted atomically with one persona Message."""

    schema_name: Literal[TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_NAME] = (
        TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_NAME
    )
    schema_version: Literal[TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_VERSION] = (
        TAVERN_MESSAGE_COMMIT_METADATA_CONTRACT_VERSION
    )
    operation_id: str = Field(pattern=_OPERATION_ID_PATTERN)
    effect_batch_id: str = Field(pattern=_RESOURCE_ID_PATTERN)


class TavernPersonaMessageCommittedProjectionV1(_TavernCommitModel):
    """The complete application-owned Tavern persona-message projection.

    This DTO is canonical digest input and protected read-back material. It is
    intentionally not embedded in trace-visible evidence because it contains
    conversation content.
    """

    schema_name: Literal[TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_NAME] = (
        TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_NAME
    )
    schema_version: Literal[TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_VERSION] = (
        TAVERN_MESSAGE_COMMITTED_PROJECTION_CONTRACT_VERSION
    )
    operation_id: str = Field(pattern=_OPERATION_ID_PATTERN)
    effect_batch_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    room_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    message_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    sequence: int = Field(ge=1)
    run_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    step_index: int = Field(ge=0, le=3)
    reply_to_message_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    author_kind: Literal["persona"] = "persona"
    persona_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    persona_name: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=4000)
    emotion: str = Field(min_length=1, max_length=80)
    action: str = Field(max_length=160)
    speech_style: str = Field(max_length=80)
    addressed_participant_ids: list[str] = Field(default_factory=list, max_length=6)
    # This is a caller-owned idempotency key, not an application-owned resource
    # ID. Keep it aligned with the existing Tavern request contract so commit
    # evidence remains available for keys containing spaces or URL punctuation.
    client_request_id: str = Field(min_length=8, max_length=80)
    created_at: AwareDatetime

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("tavern_commit_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_participant_ids(self) -> "TavernPersonaMessageCommittedProjectionV1":
        if len(self.addressed_participant_ids) != len(
            set(self.addressed_participant_ids)
        ):
            raise ValueError("tavern_commit_addressed_participant_duplicate")
        return self


class TavernPersonaMessageCommitBindingV1(_TavernCommitModel):
    """Trace-safe identity binding for a protected committed projection."""

    schema_name: Literal[TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_NAME] = (
        TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_NAME
    )
    schema_version: Literal[TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_VERSION] = (
        TAVERN_MESSAGE_COMMIT_BINDING_CONTRACT_VERSION
    )
    operation_id: str = Field(pattern=_OPERATION_ID_PATTERN)
    effect_batch_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    room_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    message_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    sequence: int = Field(ge=1)
    run_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    step_index: int = Field(ge=0, le=3)
    reply_to_message_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    author_kind: Literal["persona"] = "persona"
    persona_id: str = Field(pattern=_RESOURCE_ID_PATTERN)
    persona_name: str = Field(min_length=1, max_length=160)
    client_request_id: str = Field(min_length=8, max_length=80)
    created_at: AwareDatetime
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at")
    @classmethod
    def require_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("tavern_commit_timestamp_must_be_utc")
        return value


def revalidate_tavern_message_commit_binding(
    binding: object,
) -> TavernPersonaMessageCommitBindingV1:
    payload = (
        binding.model_dump(mode="json", exclude_none=False)
        if isinstance(binding, TavernPersonaMessageCommitBindingV1)
        else binding
    )
    return TavernPersonaMessageCommitBindingV1.model_validate(payload)


def revalidate_tavern_message_commit_metadata(
    metadata: object,
) -> TavernPersonaMessageCommitMetadataV1:
    payload = (
        metadata.model_dump(mode="json", exclude_none=False)
        if isinstance(metadata, TavernPersonaMessageCommitMetadataV1)
        else metadata
    )
    return TavernPersonaMessageCommitMetadataV1.model_validate(payload)


def revalidate_tavern_message_committed_projection(
    projection: object,
) -> TavernPersonaMessageCommittedProjectionV1:
    payload = (
        projection.model_dump(mode="json", exclude_none=False)
        if isinstance(projection, TavernPersonaMessageCommittedProjectionV1)
        else projection
    )
    return TavernPersonaMessageCommittedProjectionV1.model_validate(payload)
