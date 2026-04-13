"""pgsql rebuild

Revision ID: 20260413_0001
Revises:
Create Date: 2026-04-13 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260413_0001"
down_revision = None
branch_labels = None
depends_on = None


JSON_TYPE = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("original_filename", sa.Text(), nullable=False, server_default=""),
        sa.Column("stored_path", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="uploaded"),
        sa.Column("ocr_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "learning_plans",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("document_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("persona_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("creation_mode", sa.String(length=32), nullable=False, server_default="document"),
        sa.Column("course_title", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_learning_plans_document_id", "learning_plans", ["document_id"])
    op.create_index("ix_learning_plans_persona_id", "learning_plans", ["persona_id"])
    op.create_table(
        "study_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("document_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("persona_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("plan_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("study_unit_id", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_study_sessions_document_id", "study_sessions", ["document_id"])
    op.create_index("ix_study_sessions_persona_id", "study_sessions", ["persona_id"])
    op.create_index("ix_study_sessions_plan_id", "study_sessions", ["plan_id"])
    op.create_table(
        "personas",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, server_default=""),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="user"),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "persona_cards",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("kind", sa.String(length=64), nullable=False, server_default="custom"),
        sa.Column("source", sa.String(length=64), nullable=False, server_default="manual"),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "scene_setup_states",
        sa.Column("config_id", sa.String(length=64), primary_key=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "scene_library_entries",
        sa.Column("scene_id", sa.String(length=64), primary_key=True),
        sa.Column("scene_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "reusable_scene_nodes",
        sa.Column("node_id", sa.String(length=64), primary_key=True),
        sa.Column("node_type", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_scene_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "session_scenes",
        sa.Column("scene_instance_id", sa.String(length=64), primary_key=True),
        sa.Column("session_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("document_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("persona_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_session_scenes_session_id", "session_scenes", ["session_id"])
    op.create_index("ix_session_scenes_document_id", "session_scenes", ["document_id"])
    op.create_index("ix_session_scenes_persona_id", "session_scenes", ["persona_id"])
    op.create_table(
        "document_debug_records",
        sa.Column("document_id", sa.String(length=64), primary_key=True),
        sa.Column("processed_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extraction_method", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "planning_traces",
        sa.Column("document_id", sa.String(length=64), primary_key=True),
        sa.Column("plan_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "stream_reports",
        sa.Column("record_id", sa.String(length=128), primary_key=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("stream_kind", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("category", "document_id", name="uq_stream_reports_category_document"),
    )
    op.create_index("ix_stream_reports_category", "stream_reports", ["category"])
    op.create_index("ix_stream_reports_document_id", "stream_reports", ["document_id"])
    op.create_table(
        "runtime_settings",
        sa.Column("config_id", sa.String(length=64), primary_key=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("plan_provider", sa.String(length=32), nullable=False, server_default="mock"),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "model_tool_configs",
        sa.Column("config_id", sa.String(length=64), primary_key=True),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_table(
        "token_usage_records",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("feature", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("model", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_token_usage_records_feature", "token_usage_records", ["feature"])
    op.create_index("ix_token_usage_records_model", "token_usage_records", ["model"])
    op.create_index("ix_token_usage_records_created_at", "token_usage_records", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_token_usage_records_created_at", table_name="token_usage_records")
    op.drop_index("ix_token_usage_records_model", table_name="token_usage_records")
    op.drop_index("ix_token_usage_records_feature", table_name="token_usage_records")
    op.drop_table("token_usage_records")
    op.drop_table("model_tool_configs")
    op.drop_table("runtime_settings")
    op.drop_index("ix_stream_reports_document_id", table_name="stream_reports")
    op.drop_index("ix_stream_reports_category", table_name="stream_reports")
    op.drop_table("stream_reports")
    op.drop_table("planning_traces")
    op.drop_table("document_debug_records")
    op.drop_index("ix_session_scenes_persona_id", table_name="session_scenes")
    op.drop_index("ix_session_scenes_document_id", table_name="session_scenes")
    op.drop_index("ix_session_scenes_session_id", table_name="session_scenes")
    op.drop_table("session_scenes")
    op.drop_table("reusable_scene_nodes")
    op.drop_table("scene_library_entries")
    op.drop_table("scene_setup_states")
    op.drop_table("persona_cards")
    op.drop_table("personas")
    op.drop_index("ix_study_sessions_plan_id", table_name="study_sessions")
    op.drop_index("ix_study_sessions_persona_id", table_name="study_sessions")
    op.drop_index("ix_study_sessions_document_id", table_name="study_sessions")
    op.drop_table("study_sessions")
    op.drop_index("ix_learning_plans_persona_id", table_name="learning_plans")
    op.drop_index("ix_learning_plans_document_id", table_name="learning_plans")
    op.drop_table("learning_plans")
    op.drop_table("documents")
