from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_PAYLOAD = JSON().with_variant(JSONB, "postgresql")


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
    section_id: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
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
