from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.domain import PersonaProfile, SceneProfileRecord
from app.models.harness import HarnessTraceRecord


class TavernRoomStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TavernAuthorKind(StrEnum):
    USER = "user"
    PERSONA = "persona"
    DIRECTOR = "director"
    SYSTEM = "system"


class TavernInteractionMode(StrEnum):
    DIRECT = "direct"
    FACILITATED = "facilitated"


class TavernRunStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELED = "canceled"


class TavernRunTriggerKind(StrEnum):
    USER_MESSAGE = "user_message"
    CONTINUE = "continue"
    RETRY = "retry"


class TavernSpeakerStepStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    CANCELED = "canceled"


class TavernHarnessPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "tavern-harness-v1"
    max_character_messages: int = Field(default=4, ge=1, le=4)
    max_reply_characters: int = Field(default=1200, ge=120, le=4000)
    context_message_limit: int = Field(default=18, ge=4, le=40)
    prevent_speaker_impersonation: bool = True


class TavernRoomRecord(BaseModel):
    id: str
    creation_key: str = ""
    creation_input_digest: str = ""
    title: str
    scene_profile: SceneProfileRecord | None = None
    harness_policy: TavernHarnessPolicy = Field(default_factory=TavernHarnessPolicy)
    status: TavernRoomStatus = TavernRoomStatus.ACTIVE
    revision: int = Field(default=0, ge=0)
    last_sequence: int = Field(default=0, ge=0)
    created_at: str
    updated_at: str


class TavernRoomState(BaseModel):
    id: str
    status: TavernRoomStatus
    revision: int = Field(ge=0)
    last_sequence: int = Field(ge=0)
    updated_at: str


class TavernParticipantRecord(BaseModel):
    room_id: str
    persona_id: str
    display_order: int = Field(ge=0)
    display_name: str
    persona_snapshot: PersonaProfile
    prompt_hash: str
    joined_at: str


class TavernMessageRecord(BaseModel):
    id: str
    room_id: str
    sequence: int = Field(ge=1)
    run_id: str = ""
    author_kind: TavernAuthorKind
    persona_id: str = ""
    persona_name: str = ""
    content: str
    emotion: str = "calm"
    action: str = ""
    speech_style: str = ""
    addressed_participant_ids: list[str] = Field(default_factory=list)
    reply_to_message_id: str = ""
    client_request_id: str = ""
    created_at: str
    harness_trace: HarnessTraceRecord | None = None


class TavernSpeakerStepRecord(BaseModel):
    run_id: str
    step_index: int = Field(ge=0, le=3)
    persona_id: str
    participant_prompt_hash: str = ""
    status: TavernSpeakerStepStatus = TavernSpeakerStepStatus.PENDING
    message_id: str = ""
    reply_to_message_id: str = ""
    error_code: str = ""
    harness_trace: HarnessTraceRecord | None = None
    started_at: str = ""
    completed_at: str = ""


class TavernRunRecord(BaseModel):
    id: str
    room_id: str
    idempotency_key: str
    request_digest: str = ""
    context_digest: str = ""
    mode: TavernInteractionMode
    trigger_kind: TavernRunTriggerKind = TavernRunTriggerKind.USER_MESSAGE
    parent_run_id: str = ""
    root_run_id: str = ""
    input_message_id: str | None = None
    anchor_message_id: str = ""
    scheduled_participant_ids: list[str] = Field(default_factory=list, max_length=4)
    speaker_steps: list[TavernSpeakerStepRecord] = Field(default_factory=list, max_length=4)
    guidance: str = ""
    status: TavernRunStatus = TavernRunStatus.PENDING
    expected_room_revision: int = Field(ge=0)
    generated_message_ids: list[str] = Field(default_factory=list)
    harness_trace: list[HarnessTraceRecord] = Field(default_factory=list)
    error_code: str = ""
    terminal_sequence: int = Field(default=0, ge=0)
    created_at: str
    completed_at: str = ""


class TavernRoomDetail(BaseModel):
    room: TavernRoomRecord
    participants: list[TavernParticipantRecord]
    messages: list[TavernMessageRecord]
    message_count: int = Field(ge=0)
    next_after_sequence: int | None = None
    next_before_sequence: int | None = None


class TavernRoomSummary(BaseModel):
    id: str
    title: str
    participant_persona_ids: list[str]
    participant_names: list[str]
    message_count: int = Field(ge=0)
    revision: int = Field(ge=0)
    status: TavernRoomStatus
    created_at: str
    updated_at: str


class TavernActorReply(BaseModel):
    """Strict model-owned payload. Speaker identity and sequence are server-owned."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)
    mood: str = Field(min_length=1, max_length=80)
    action: str = Field(max_length=160)
    speech_style: str = Field(max_length=80)
    delivery_cue: str = Field(max_length=160)
    state_commentary: str = Field(max_length=280)
    addressed_participant_ids: list[str] = Field(max_length=6)

    @classmethod
    def transport_json_schema(cls) -> dict[str, object]:
        """OpenAI Structured Outputs subset; Pydantic keeps semantic string bounds."""

        normalized = _without_unsupported_transport_keywords(cls.model_json_schema())
        if not isinstance(normalized, dict):
            raise RuntimeError("tavern_actor_transport_schema_invalid")
        return normalized


class CreateTavernRoomRequest(BaseModel):
    title: str = Field(default="新酒馆", min_length=1, max_length=80)
    persona_ids: list[str] = Field(min_length=1, max_length=6)
    scene_profile: SceneProfileRecord | None = None
    opening_prompt: str = Field(default="", max_length=2000)
    harness_policy: TavernHarnessPolicy = Field(default_factory=TavernHarnessPolicy)
    idempotency_key: str = Field(min_length=8, max_length=80)

    @field_validator("title", "idempotency_key", mode="before")
    @classmethod
    def strip_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("opening_prompt", mode="before")
    @classmethod
    def strip_optional_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_personas(self) -> "CreateTavernRoomRequest":
        self.persona_ids = _distinct_ids(self.persona_ids, field_name="persona_ids")
        return self


class UpdateTavernRoomRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    persona_ids: list[str] | None = Field(default=None, min_length=1, max_length=6)
    scene_profile: SceneProfileRecord | None = None
    status: TavernRoomStatus | None = None
    expected_revision: int = Field(ge=0)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_personas(self) -> "UpdateTavernRoomRequest":
        if self.persona_ids is not None:
            self.persona_ids = _distinct_ids(self.persona_ids, field_name="persona_ids")
        return self


class TavernUserMessageInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["user_message"] = "user_message"
    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content", mode="before")
    @classmethod
    def strip_content(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TavernContinueInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["continue"] = "continue"
    anchor_message_id: str = Field(min_length=1, max_length=64)

    @field_validator("anchor_message_id", mode="before")
    @classmethod
    def strip_anchor(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


TavernTurnInput = Annotated[
    TavernUserMessageInput | TavernContinueInput,
    Field(discriminator="kind"),
]


class TavernTurnRequest(BaseModel):
    input: TavernTurnInput
    mode: TavernInteractionMode = TavernInteractionMode.DIRECT
    target_persona_ids: list[str] = Field(default_factory=list, max_length=6)
    guidance: str = Field(default="", max_length=1000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    expected_room_revision: int = Field(ge=0)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def strip_required_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("guidance", mode="before")
    @classmethod
    def strip_guidance(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_targets(self) -> "TavernTurnRequest":
        self.target_persona_ids = _distinct_ids(
            self.target_persona_ids,
            field_name="target_persona_ids",
            allow_empty=True,
        )
        if self.mode == TavernInteractionMode.DIRECT and len(self.target_persona_ids) != 1:
            raise ValueError("tavern_direct_mode_requires_one_target")
        if self.mode == TavernInteractionMode.FACILITATED and not (
            2 <= len(self.target_persona_ids) <= 4
        ):
            raise ValueError("tavern_facilitated_mode_requires_two_to_four_targets")
        return self


class RetryTavernRunRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=80)
    expected_room_revision: int = Field(ge=0)

    @field_validator("idempotency_key", mode="before")
    @classmethod
    def strip_idempotency_key(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class TavernRoomListResponse(BaseModel):
    items: list[TavernRoomSummary]


class TavernRunListResponse(BaseModel):
    items: list[TavernRunRecord]


class TavernTurnResponse(BaseModel):
    run: TavernRunRecord
    input_message: TavernMessageRecord | None = None
    generated_messages: list[TavernMessageRecord]
    room_state: TavernRoomState


def _distinct_ids(
    values: list[str],
    *,
    field_name: str,
    allow_empty: bool = False,
) -> list[str]:
    normalized = [item.strip() for item in values if item.strip()]
    if not normalized and not allow_empty:
        raise ValueError(f"tavern_{field_name}_required")
    if len(normalized) != len(set(normalized)):
        raise ValueError(f"tavern_{field_name}_must_be_distinct")
    return normalized


def _without_unsupported_transport_keywords(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_unsupported_transport_keywords(item)
            for key, item in value.items()
            if key not in {"title", "minLength", "maxLength"}
        }
    if isinstance(value, list):
        return [_without_unsupported_transport_keywords(item) for item in value]
    return value
