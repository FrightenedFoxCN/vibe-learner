from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    FAILED = "failed"
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
    title: str
    scene_profile: SceneProfileRecord | None = None
    harness_policy: TavernHarnessPolicy = Field(default_factory=TavernHarnessPolicy)
    status: TavernRoomStatus = TavernRoomStatus.ACTIVE
    revision: int = Field(default=0, ge=0)
    last_sequence: int = Field(default=0, ge=0)
    created_at: str
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
    client_request_id: str = ""
    created_at: str
    harness_trace: HarnessTraceRecord | None = None


class TavernRunRecord(BaseModel):
    id: str
    room_id: str
    idempotency_key: str
    mode: TavernInteractionMode
    input_message_id: str = ""
    requested_participant_ids: list[str] = Field(default_factory=list)
    max_character_messages: int = Field(default=1, ge=1, le=4)
    guidance: str = ""
    status: TavernRunStatus = TavernRunStatus.PENDING
    expected_room_revision: int = Field(ge=0)
    generated_message_ids: list[str] = Field(default_factory=list)
    harness_trace: list[HarnessTraceRecord] = Field(default_factory=list)
    error_code: str = ""
    created_at: str
    completed_at: str = ""


class TavernRoomDetail(BaseModel):
    room: TavernRoomRecord
    participants: list[TavernParticipantRecord]
    messages: list[TavernMessageRecord]
    message_count: int = Field(ge=0)
    next_after_sequence: int | None = None


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
    mood: str = Field(default="calm", min_length=1, max_length=80)
    action: str = Field(default="", max_length=160)
    speech_style: str = Field(default="", max_length=80)
    delivery_cue: str = Field(default="", max_length=160)
    state_commentary: str = Field(default="", max_length=280)
    addressed_participant_ids: list[str] = Field(default_factory=list, max_length=6)


class CreateTavernRoomRequest(BaseModel):
    title: str = Field(default="新酒馆", min_length=1, max_length=80)
    persona_ids: list[str] = Field(min_length=1, max_length=6)
    scene_profile: SceneProfileRecord | None = None
    opening_prompt: str = Field(default="", max_length=2000)
    harness_policy: TavernHarnessPolicy = Field(default_factory=TavernHarnessPolicy)

    @model_validator(mode="after")
    def validate_personas(self) -> "CreateTavernRoomRequest":
        self.persona_ids = _distinct_ids(self.persona_ids, field_name="persona_ids")
        return self


class UpdateTavernRoomRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    persona_ids: list[str] | None = Field(default=None, min_length=1, max_length=6)
    scene_profile: SceneProfileRecord | None = None
    expected_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_personas(self) -> "UpdateTavernRoomRequest":
        if self.persona_ids is not None:
            self.persona_ids = _distinct_ids(self.persona_ids, field_name="persona_ids")
        return self


class TavernTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    mode: TavernInteractionMode = TavernInteractionMode.DIRECT
    target_persona_ids: list[str] = Field(default_factory=list, max_length=6)
    guidance: str = Field(default="", max_length=1000)
    max_character_messages: int = Field(default=1, ge=1, le=4)
    idempotency_key: str = Field(min_length=8, max_length=80)
    expected_room_revision: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_targets(self) -> "TavernTurnRequest":
        self.target_persona_ids = _distinct_ids(
            self.target_persona_ids,
            field_name="target_persona_ids",
            allow_empty=True,
        )
        if self.mode == TavernInteractionMode.DIRECT and self.max_character_messages != 1:
            raise ValueError("tavern_direct_mode_requires_one_character_message")
        return self


class TavernRoomListResponse(BaseModel):
    items: list[TavernRoomSummary]


class TavernTurnResponse(BaseModel):
    run: TavernRunRecord
    generated_messages: list[TavernMessageRecord]
    room: TavernRoomDetail


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
