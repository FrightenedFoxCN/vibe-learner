from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


STUDY_CHAT_REQUEST_SCHEMA_VERSION = "study-chat-request-v2"
STUDY_CHAT_REQUEST_SCHEMA_VERSIONS = frozenset(
    {"study-chat-request-v1", STUDY_CHAT_REQUEST_SCHEMA_VERSION}
)
STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION = "study-chat-request-fingerprint-v1"
STUDY_CHAT_RESPONSE_SCHEMA_VERSION_V1 = "study-chat-exchange-v1"
STUDY_CHAT_RESPONSE_SCHEMA_VERSION = "study-chat-exchange-v2"
STUDY_CHAT_RESPONSE_SCHEMA_VERSIONS = {
    STUDY_CHAT_RESPONSE_SCHEMA_VERSION_V1,
    STUDY_CHAT_RESPONSE_SCHEMA_VERSION,
}

StudyChatMessageKind = Literal[
    "learner",
    "session_prelude",
    "scheduled_follow_up",
    "interactive_callback",
]


def study_chat_provider_effect_id(
    *,
    operation_id: str,
    source_effect_id: str,
) -> str:
    digest = hashlib.sha256(
        f"{operation_id}:provider:{source_effect_id}".encode("utf-8")
    ).hexdigest()[:20]
    return f"study-provider-effect-{digest}"


class StudyChatOperationStatus(StrEnum):
    ADMITTED = "admitted"
    RUNNING = "running"
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"
    UNCERTAIN = "uncertain"


class StudyChatAttachmentManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    mime_type: str = Field(min_length=1, max_length=255)
    normalized_name: str = Field(min_length=1, max_length=255)


class StudyChatOperationRequestPayload(BaseModel):
    """Server-only canonical input bound to one client request identity."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(max_length=20_000)
    message_kind: StudyChatMessageKind
    follow_up_id: str = Field(max_length=128)
    hidden_message_prefix: str = Field(max_length=20_000)
    expected_session_revision: int = Field(ge=0)
    attachments: list[StudyChatAttachmentManifestEntry] = Field(default_factory=list)

    @field_validator("message_kind", "follow_up_id", mode="before")
    @classmethod
    def strip_normalized_fields(cls, value: object) -> object:
        return str(value or "").strip()


class StudyChatOperationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(min_length=1, max_length=64)
    session_id: str = Field(min_length=1, max_length=64)
    client_request_id: str = Field(min_length=8, max_length=80)
    request_schema_version: str = STUDY_CHAT_REQUEST_SCHEMA_VERSION
    fingerprint_contract_version: str = STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION
    request_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_payload: StudyChatOperationRequestPayload
    status: StudyChatOperationStatus
    admitted_session_revision: int = Field(ge=0)
    execution_token: str = ""
    claim_count: int = Field(default=0, ge=0, le=1)
    execution_started_at: str = ""
    provider_started_at: str = ""
    execution_deadline_at: str = ""
    heartbeat_at: str = ""
    committed_session_revision: int | None = Field(default=None, ge=0)
    committed_turn_id: str | None = None
    committed_turn_sequence: int | None = Field(default=None, ge=1)
    response_schema_version: str = ""
    response_payload: dict[str, Any] | None = None
    response_digest: str = ""
    error_code: str = ""
    created_at: str
    updated_at: str
    completed_at: str = ""

    @model_validator(mode="after")
    def validate_state_projection(self) -> "StudyChatOperationRecord":
        if self.request_schema_version not in STUDY_CHAT_REQUEST_SCHEMA_VERSIONS:
            raise ValueError("study_chat_operation_request_schema_unsupported")
        if self.fingerprint_contract_version != STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION:
            raise ValueError("study_chat_operation_fingerprint_contract_unsupported")
        if self.request_fingerprint != study_chat_request_fingerprint(self.request_payload):
            raise ValueError("study_chat_operation_request_fingerprint_mismatch")
        if self.admitted_session_revision != self.request_payload.expected_session_revision:
            raise ValueError("study_chat_operation_admitted_revision_mismatch")
        terminal = self.status in {
            StudyChatOperationStatus.COMMITTED,
            StudyChatOperationStatus.NOT_COMMITTED,
            StudyChatOperationStatus.UNCERTAIN,
        }
        if terminal != bool(self.completed_at):
            raise ValueError("study_chat_operation_terminal_time_mismatch")
        if self.status in {
            StudyChatOperationStatus.ADMITTED,
            StudyChatOperationStatus.NOT_COMMITTED,
        }:
            if any(
                (
                    self.claim_count,
                    bool(self.execution_token),
                    bool(self.execution_started_at),
                    bool(self.provider_started_at),
                    bool(self.execution_deadline_at),
                    bool(self.heartbeat_at),
                )
            ):
                raise ValueError("study_chat_operation_unstarted_execution_evidence_invalid")
        elif self.status in {
            StudyChatOperationStatus.RUNNING,
            StudyChatOperationStatus.COMMITTED,
            StudyChatOperationStatus.UNCERTAIN,
        }:
            if self.claim_count != 1 or not self.execution_token or not self.execution_started_at:
                raise ValueError("study_chat_operation_execution_evidence_missing")
        if self.status == StudyChatOperationStatus.COMMITTED:
            if (
                self.committed_session_revision is None
                or self.committed_session_revision <= self.admitted_session_revision
                or not self.committed_turn_id
                or self.committed_turn_sequence is None
                or self.response_schema_version not in STUDY_CHAT_RESPONSE_SCHEMA_VERSIONS
                or self.response_payload is None
                or self.response_digest != study_chat_response_digest(self.response_payload)
                or self.error_code
            ):
                raise ValueError("study_chat_operation_committed_evidence_invalid")
        elif any(
            (
                self.committed_session_revision is not None,
                self.committed_turn_id is not None,
                self.committed_turn_sequence is not None,
                self.response_payload is not None,
                bool(self.response_schema_version),
                bool(self.response_digest),
            )
        ):
            raise ValueError("study_chat_operation_non_committed_claims_result")
        if self.status in {
            StudyChatOperationStatus.NOT_COMMITTED,
            StudyChatOperationStatus.UNCERTAIN,
        } and not self.error_code:
            raise ValueError("study_chat_operation_terminal_error_missing")
        return self


class StudyChatOperationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    session_id: str
    client_request_id: str
    status: StudyChatOperationStatus
    safe_to_retry: bool
    created_at: str
    updated_at: str
    completed_at: str | None
    admitted_session_revision: int
    committed_session_revision: int | None
    committed_turn_id: str | None
    committed_turn_sequence: int | None
    error_code: str
    result: dict[str, Any] | None

    @model_validator(mode="after")
    def validate_public_projection(self) -> "StudyChatOperationReceipt":
        if self.safe_to_retry != (
            self.status == StudyChatOperationStatus.NOT_COMMITTED
        ):
            raise ValueError("study_chat_operation_retry_projection_invalid")
        if (self.status == StudyChatOperationStatus.COMMITTED) != (self.result is not None):
            raise ValueError("study_chat_operation_result_projection_invalid")
        return self


def study_chat_request_fingerprint(payload: StudyChatOperationRequestPayload) -> str:
    canonical = {
        "contract": STUDY_CHAT_FINGERPRINT_CONTRACT_VERSION,
        "request": payload.model_dump(mode="json"),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def study_chat_response_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
