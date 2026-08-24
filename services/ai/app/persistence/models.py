from __future__ import annotations

from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_PAYLOAD = JSON().with_variant(JSONB, "postgresql")
NULLABLE_JSON_PAYLOAD = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True),
    "postgresql",
)


class Base(DeclarativeBase):
    pass


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="")
    original_filename: Mapped[str] = mapped_column(Text, default="")
    stored_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    ocr_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class DocumentProcessOperationRow(Base):
    __tablename__ = "document_process_operations"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "active_slot",
            name="uq_document_process_operation_active_slot",
        ),
        CheckConstraint(
            "(status = 'running' AND active_slot = 1 AND projection_state = 'pending' "
            "AND completed_at = '' AND error_code = '') OR "
            "(status = 'committed' AND active_slot IS NULL AND projection_state = 'committed' "
            "AND completed_at <> '' AND error_code = '' "
            "AND document_digest <> '' AND debug_digest <> '' AND commit_contract_version <> '') OR "
            "(status IN ('failed', 'interrupted') AND active_slot IS NULL "
            "AND projection_state = 'not_committed' AND completed_at <> '' AND error_code <> '' "
            "AND document_digest = '' AND debug_digest = '' AND commit_contract_version = '')",
            name="ck_document_process_operation_state",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        index=True,
    )
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    status: Mapped[str] = mapped_column(String(32), index=True)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    projection_state: Mapped[str] = mapped_column(String(32))
    base_document_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    document_digest: Mapped[str] = mapped_column(String(64), default="")
    debug_digest: Mapped[str] = mapped_column(String(64), default="")
    commit_contract_version: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(64), index=True)
    completed_at: Mapped[str] = mapped_column(String(64), default="")


class LearningPlanOperationRow(Base):
    __tablename__ = "learning_plan_operations"
    __table_args__ = (
        UniqueConstraint(
            "client_request_id",
            name="uq_learning_plan_operation_client_request",
        ),
        UniqueConstraint(
            "scope_key",
            "active_slot",
            name="uq_learning_plan_operation_active_scope",
        ),
        CheckConstraint(
            "(status = 'running' AND active_slot = 1 AND projection_state = 'pending' "
            "AND completed_at = '' AND error_code = '' "
            "AND plan_id = '' AND committed_projection_digest = '' "
            "AND committed_projection_payload IS NULL AND commit_contract_version = '') OR "
            "(status = 'committed' AND active_slot IS NULL AND projection_state = 'committed' "
            "AND completed_at <> '' AND error_code = '' AND plan_id <> '' "
            "AND committed_projection_digest <> '' AND committed_projection_payload IS NOT NULL "
            "AND commit_contract_version <> '') OR "
            "(status IN ('not_committed', 'interrupted', 'uncertain') "
            "AND active_slot IS NULL AND projection_state = 'not_committed' "
            "AND completed_at <> '' AND error_code <> '' AND plan_id = '' "
            "AND committed_projection_digest = '' AND committed_projection_payload IS NULL "
            "AND commit_contract_version = '')",
            name="ck_learning_plan_operation_state",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_request_id: Mapped[str] = mapped_column(String(80))
    scope_key: Mapped[str] = mapped_column(String(160))
    document_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    persona_id: Mapped[str] = mapped_column(String(64), index=True)
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    base_document_updated_at: Mapped[str] = mapped_column(String(64), default="")
    base_document_digest: Mapped[str] = mapped_column(String(64), default="")
    base_debug_digest: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    projection_state: Mapped[str] = mapped_column(String(32))
    provider_started_at: Mapped[str] = mapped_column(String(64), default="")
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    commit_contract_version: Mapped[str] = mapped_column(String(64), default="")
    committed_projection_digest: Mapped[str] = mapped_column(String(64), default="")
    committed_projection_payload: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD,
        nullable=True,
    )
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(64), index=True)
    completed_at: Mapped[str] = mapped_column(String(64), default="")


class LearningPlanRow(Base):
    __tablename__ = "learning_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    creation_mode: Mapped[str] = mapped_column(String(32), default="document")
    course_title: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class StudySessionRow(Base):
    __tablename__ = "study_sessions"
    __mapper_args__ = {"confirm_deleted_rows": False}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    plan_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    study_unit_id: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    last_turn_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class StudyQuestionAttemptRow(Base):
    __tablename__ = "study_question_attempts"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "client_attempt_id",
            name="uq_study_question_attempt_request",
        ),
        UniqueConstraint(
            "session_id",
            "turn_id",
            name="uq_study_question_attempt_turn",
        ),
        CheckConstraint(
            "committed_session_revision = before_session_revision + 1",
            name="ck_study_question_attempt_revision",
        ),
    )

    attempt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("study_sessions.id", ondelete="RESTRICT"),
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String(64), index=True)
    client_attempt_id: Mapped[str] = mapped_column(String(80))
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    response_schema_version: Mapped[str] = mapped_column(String(64))
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    response_digest: Mapped[str] = mapped_column(String(64))
    before_session_revision: Mapped[int] = mapped_column(Integer)
    committed_session_revision: Mapped[int] = mapped_column(Integer)
    committed_at: Mapped[str] = mapped_column(String(64))


class StudyChatOperationRow(Base):
    __tablename__ = "study_chat_operations"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "client_request_id",
            name="uq_study_chat_operation_request",
        ),
        UniqueConstraint(
            "session_id",
            "active_slot",
            name="uq_study_chat_operation_active_slot",
        ),
        UniqueConstraint("committed_turn_id", name="uq_study_chat_operation_turn"),
        CheckConstraint("claim_count IN (0, 1)", name="ck_study_chat_operation_claim_count"),
        CheckConstraint(
            "(status IN ('admitted', 'running') AND active_slot = 1) OR "
            "(status IN ('committed', 'not_committed', 'uncertain') AND active_slot IS NULL)",
            name="ck_study_chat_operation_active_status",
        ),
        CheckConstraint(
            "(status IN ('admitted', 'not_committed') AND claim_count = 0 "
            "AND execution_token = '' AND execution_started_at = '' "
            "AND provider_started_at = '' AND execution_deadline_at = '' AND heartbeat_at = '') OR "
            "(status IN ('running', 'committed', 'uncertain') AND claim_count = 1 "
            "AND execution_token <> '' AND execution_started_at <> '' AND execution_deadline_at <> '')",
            name="ck_study_chat_operation_execution_evidence",
        ),
        CheckConstraint(
            "(status = 'committed' AND committed_session_revision IS NOT NULL "
            "AND committed_turn_id IS NOT NULL AND committed_turn_sequence IS NOT NULL "
            "AND response_schema_version <> '' AND response_payload IS NOT NULL "
            "AND response_digest <> '' AND error_code = '' AND completed_at <> '') OR "
            "(status <> 'committed' AND committed_session_revision IS NULL "
            "AND committed_turn_id IS NULL AND committed_turn_sequence IS NULL "
            "AND response_schema_version = '' AND response_payload IS NULL AND response_digest = '')",
            name="ck_study_chat_operation_result_evidence",
        ),
        CheckConstraint(
            "(status IN ('committed', 'not_committed', 'uncertain') AND completed_at <> '') OR "
            "(status IN ('admitted', 'running') AND completed_at = '')",
            name="ck_study_chat_operation_terminal_time",
        ),
        CheckConstraint(
            "(status IN ('not_committed', 'uncertain') AND error_code <> '') OR "
            "(status IN ('admitted', 'running', 'committed') AND error_code = '')",
            name="ck_study_chat_operation_error_evidence",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("study_sessions.id", ondelete="RESTRICT"),
        index=True,
    )
    client_request_id: Mapped[str] = mapped_column(String(80))
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    status: Mapped[str] = mapped_column(String(32), index=True)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admitted_session_revision: Mapped[int] = mapped_column(Integer)
    execution_token: Mapped[str] = mapped_column(String(64), default="")
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    execution_started_at: Mapped[str] = mapped_column(String(64), default="")
    provider_started_at: Mapped[str] = mapped_column(String(64), default="")
    execution_deadline_at: Mapped[str] = mapped_column(String(64), default="")
    heartbeat_at: Mapped[str] = mapped_column(String(64), default="")
    committed_session_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    committed_turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    committed_turn_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_schema_version: Mapped[str] = mapped_column(String(64), default="")
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD,
        nullable=True,
    )
    response_digest: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(64), index=True)
    completed_at: Mapped[str] = mapped_column(String(64), default="")


class TavernRoomRow(Base):
    __tablename__ = "tavern_rooms"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    creation_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    creation_input_digest: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    scene_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD, nullable=True)
    harness_policy: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), index=True, default="")


class TavernParticipantRow(Base):
    __tablename__ = "tavern_participants"
    __table_args__ = (UniqueConstraint("room_id", "display_order", name="uq_tavern_participant_order"),)

    room_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    persona_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_order: Mapped[int] = mapped_column(Integer)
    display_name: Mapped[str] = mapped_column(Text, default="")
    persona_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    joined_at: Mapped[str] = mapped_column(String(64), default="")


class TavernRunRow(Base):
    __tablename__ = "tavern_runs"
    __table_args__ = (UniqueConstraint("room_id", "idempotency_key", name="uq_tavern_run_idempotency"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(80))
    parent_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("tavern_runs.id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    mode: Mapped[str] = mapped_column(String(32), default="direct")
    input_message_id: Mapped[str] = mapped_column(String(64), default="")
    expected_room_revision: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    completed_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class TavernRunStepRow(Base):
    __tablename__ = "tavern_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "persona_id", name="uq_tavern_run_step_persona"),
    )

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    step_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(64), index=True)
    participant_prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    message_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    reply_to_message_id: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str] = mapped_column(String(128), default="")
    started_at: Mapped[str] = mapped_column(String(64), default="")
    completed_at: Mapped[str] = mapped_column(String(64), default="")
    lease_owner: Mapped[str] = mapped_column(String(64), default="")
    lease_expires_at: Mapped[str] = mapped_column(String(64), default="")
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class TavernMessageRow(Base):
    __tablename__ = "tavern_messages"
    __table_args__ = (UniqueConstraint("room_id", "sequence", name="uq_tavern_message_sequence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    author_kind: Mapped[str] = mapped_column(String(32))
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    client_request_id: Mapped[str] = mapped_column(String(80), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class PersonaRow(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="user")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class PersonaCardRow(Base):
    __tablename__ = "persona_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(64), default="custom")
    source: Mapped[str] = mapped_column(String(64), default="manual")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class SceneSetupRow(Base):
    __tablename__ = "scene_setup_states"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class SceneLibraryRow(Base):
    __tablename__ = "scene_library_entries"

    scene_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    scene_name: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class ReusableSceneNodeRow(Base):
    __tablename__ = "reusable_scene_nodes"

    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    source_scene_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class SessionSceneRow(Base):
    __tablename__ = "session_scenes"

    scene_instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    document_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class DocumentDebugRow(Base):
    __tablename__ = "document_debug_records"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[str] = mapped_column(String(64), default="")
    page_count: Mapped[int] = mapped_column(default=0)
    extraction_method: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class PlanningTraceRow(Base):
    __tablename__ = "planning_traces"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class StreamReportRow(Base):
    __tablename__ = "stream_reports"
    __table_args__ = (UniqueConstraint("category", "document_id", name="uq_stream_reports_category_document"),)

    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    stream_kind: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="idle")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class RuntimeSettingsRow(Base):
    __tablename__ = "runtime_settings"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    plan_provider: Mapped[str] = mapped_column(String(32), default="mock")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class ModelToolConfigRow(Base):
    __tablename__ = "model_tool_configs"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class TokenUsageRow(Base):
    __tablename__ = "token_usage_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feature: Mapped[str] = mapped_column(String(64), index=True, default="")
    model: Mapped[str] = mapped_column(String(128), index=True, default="")
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(String(64), index=True, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)
