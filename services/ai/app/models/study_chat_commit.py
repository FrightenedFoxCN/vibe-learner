from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.domain import StudySessionRecord
from app.models.harness import (
    HarnessCommitStatus,
    HarnessDigestScope,
    HarnessResourceType,
    HarnessTraceV3,
    canonical_harness_digest,
)
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN


class StudySessionTurnCommittedProjectionV1(BaseModel):
    """Content-free digest binding for one authoritative committed Study turn."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_name: Literal["StudySessionTurnCommittedProjection"] = (
        "StudySessionTurnCommittedProjection"
    )
    schema_version: Literal["study-chat-turn-committed-projection-v1"] = (
        "study-chat-turn-committed-projection-v1"
    )
    operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    session_id: str = Field(min_length=1, max_length=64)
    expected_session_revision: int = Field(ge=0)
    committed_session_revision: int = Field(ge=1)
    turn_id: str = Field(min_length=1, max_length=64)
    turn_sequence: int = Field(ge=1)
    turn_payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_progression(self) -> "StudySessionTurnCommittedProjectionV1":
        if self.committed_session_revision != self.expected_session_revision + 1:
            raise ValueError("study_chat_commit_revision_increment_invalid")
        if self.committed_session_revision < self.turn_sequence:
            raise ValueError("study_chat_commit_revision_before_turn_sequence")
        return self


class StudyChatOperationBindingV1(BaseModel):
    """Trace-safe binding for the admitted Study Chat operation."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_name: Literal["StudyChatOperationBinding"] = "StudyChatOperationBinding"
    schema_version: Literal["study-chat-operation-binding-v1"] = (
        "study-chat-operation-binding-v1"
    )
    operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    session_id: str = Field(min_length=1, max_length=64)
    admitted_session_revision: int = Field(ge=0)
    projection_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


def build_study_session_turn_committed_projection(
    *,
    operation_id: str,
    session: StudySessionRecord,
    expected_session_revision: int,
    turn_id: str,
    turn_sequence: int,
) -> StudySessionTurnCommittedProjectionV1:
    matching = [turn for turn in session.turns if turn.id == turn_id]
    if len(matching) != 1:
        raise ValueError("study_chat_committed_turn_read_back_missing")
    turn = matching[0]
    if turn.sequence != turn_sequence:
        raise ValueError("study_chat_committed_turn_sequence_mismatch")
    if session.last_turn_sequence != turn_sequence:
        raise ValueError("study_chat_committed_turn_not_latest")
    if session.revision != expected_session_revision + 1:
        raise ValueError("study_chat_committed_session_revision_mismatch")
    return StudySessionTurnCommittedProjectionV1(
        operation_id=operation_id,
        session_id=session.id,
        expected_session_revision=expected_session_revision,
        committed_session_revision=session.revision,
        turn_id=turn_id,
        turn_sequence=turn_sequence,
        turn_payload_digest=canonical_harness_digest(turn),
    )


def build_study_chat_operation_binding(
    projection: StudySessionTurnCommittedProjectionV1,
) -> StudyChatOperationBindingV1:
    return StudyChatOperationBindingV1(
        operation_id=projection.operation_id,
        session_id=projection.session_id,
        admitted_session_revision=projection.expected_session_revision,
        projection_digest=canonical_harness_digest(projection),
    )


def validate_study_chat_operation_commit(
    *,
    trace: HarnessTraceV3,
    binding: StudyChatOperationBindingV1,
    projection: StudySessionTurnCommittedProjectionV1,
) -> None:
    strict_trace = HarnessTraceV3.model_validate(
        trace.model_dump(mode="json", exclude_none=False)
    )
    strict_projection = StudySessionTurnCommittedProjectionV1.model_validate(
        projection.model_dump(mode="json", exclude_none=False)
    )
    strict_binding = StudyChatOperationBindingV1.model_validate(
        binding.model_dump(mode="json", exclude_none=False)
    )
    evidence = strict_trace.commit_evidence
    if evidence.status != HarnessCommitStatus.COMMITTED:
        raise ValueError("study_chat_commit_success_required")
    if evidence.digest_scope != HarnessDigestScope.COMMITTED_PROJECTION:
        raise ValueError("study_chat_commit_digest_scope_mismatch")
    subject_refs = [
        item
        for item in strict_trace.context.subject_refs
        if item.resource_type == HarnessResourceType.STUDY_SESSION
    ]
    if len(subject_refs) != 1:
        raise ValueError("study_chat_commit_subject_set_mismatch")
    subject = subject_refs[0]
    if (
        strict_trace.operation_id != strict_projection.operation_id
        or strict_binding.operation_id != strict_projection.operation_id
    ):
        raise ValueError("study_chat_commit_operation_mismatch")
    if (
        subject.resource_id != strict_projection.session_id
        or subject.revision != strict_projection.expected_session_revision
        or strict_binding.session_id != strict_projection.session_id
        or strict_binding.admitted_session_revision
        != strict_projection.expected_session_revision
    ):
        raise ValueError("study_chat_commit_session_binding_mismatch")
    attempted = evidence.attempted_resource_refs
    committed = evidence.committed_resources
    if len(attempted) != 1 or len(committed) != 1:
        raise ValueError("study_chat_commit_resource_count_mismatch")
    if (
        attempted[0].resource_type != HarnessResourceType.STUDY_SESSION
        or committed[0].resource_type != HarnessResourceType.STUDY_SESSION
        or attempted[0].resource_id != strict_projection.session_id
        or committed[0].resource_id != strict_projection.session_id
        or attempted[0].revision != strict_projection.expected_session_revision
        or committed[0].expected_revision
        != strict_projection.expected_session_revision
        or committed[0].committed_revision
        != strict_projection.committed_session_revision
    ):
        raise ValueError("study_chat_commit_resource_binding_mismatch")
    digest = canonical_harness_digest(strict_projection)
    if (
        strict_binding.projection_digest != digest
        or committed[0].payload_digest != digest
        or evidence.payload_digest != digest
    ):
        raise ValueError("study_chat_commit_projection_digest_mismatch")
