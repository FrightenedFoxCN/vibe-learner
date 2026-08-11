"""add normalized tavern schema

Revision ID: 20260812_0002
Revises: 20260413_0001
Create Date: 2026-08-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260812_0002"
down_revision = "20260413_0001"
branch_labels = None
depends_on = None


JSON_TYPE = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "tavern_rooms",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("scene_profile", JSON_TYPE, nullable=True),
        sa.Column("harness_policy", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index("ix_tavern_rooms_status", "tavern_rooms", ["status"])
    op.create_index("ix_tavern_rooms_updated_at", "tavern_rooms", ["updated_at"])

    op.create_table(
        "tavern_participants",
        sa.Column(
            "room_id",
            sa.String(length=64),
            sa.ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("persona_id", sa.String(length=64), primary_key=True),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("persona_snapshot", JSON_TYPE, nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("joined_at", sa.String(length=64), nullable=False, server_default=""),
        sa.UniqueConstraint("room_id", "display_order", name="uq_tavern_participant_order"),
    )

    op.create_table(
        "tavern_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(length=64),
            sa.ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default="direct"),
        sa.Column("input_message_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("expected_room_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("completed_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("room_id", "idempotency_key", name="uq_tavern_run_idempotency"),
    )
    op.create_index("ix_tavern_runs_room_id", "tavern_runs", ["room_id"])
    op.create_index("ix_tavern_runs_status", "tavern_runs", ["status"])

    op.create_table(
        "tavern_messages",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column(
            "room_id",
            sa.String(length=64),
            sa.ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("author_kind", sa.String(length=32), nullable=False),
        sa.Column("persona_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("client_request_id", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("room_id", "sequence", name="uq_tavern_message_sequence"),
    )
    op.create_index("ix_tavern_messages_room_id", "tavern_messages", ["room_id"])
    op.create_index("ix_tavern_messages_run_id", "tavern_messages", ["run_id"])
    op.create_index("ix_tavern_messages_persona_id", "tavern_messages", ["persona_id"])


def downgrade() -> None:
    op.drop_index("ix_tavern_messages_persona_id", table_name="tavern_messages")
    op.drop_index("ix_tavern_messages_run_id", table_name="tavern_messages")
    op.drop_index("ix_tavern_messages_room_id", table_name="tavern_messages")
    op.drop_table("tavern_messages")
    op.drop_index("ix_tavern_runs_status", table_name="tavern_runs")
    op.drop_index("ix_tavern_runs_room_id", table_name="tavern_runs")
    op.drop_table("tavern_runs")
    op.drop_table("tavern_participants")
    op.drop_index("ix_tavern_rooms_updated_at", table_name="tavern_rooms")
    op.drop_index("ix_tavern_rooms_status", table_name="tavern_rooms")
    op.drop_table("tavern_rooms")
