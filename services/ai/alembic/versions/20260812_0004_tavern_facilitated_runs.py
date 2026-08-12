"""add facilitated tavern run steps

Revision ID: 20260812_0004
Revises: 20260812_0003
Create Date: 2026-08-12 02:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260812_0004"
down_revision = "20260812_0003"
branch_labels = None
depends_on = None


JSON_TYPE = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "tavern_runs",
        sa.Column("parent_run_id", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_tavern_runs_parent_run_id",
        "tavern_runs",
        ["parent_run_id"],
    )
    op.create_foreign_key(
        "fk_tavern_runs_parent_run_id",
        "tavern_runs",
        "tavern_runs",
        ["parent_run_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_table(
        "tavern_run_steps",
        sa.Column(
            "run_id",
            sa.String(length=64),
            sa.ForeignKey("tavern_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("step_index", sa.Integer(), primary_key=True),
        sa.Column("persona_id", sa.String(length=64), nullable=False),
        sa.Column(
            "participant_prompt_hash",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("message_id", sa.String(length=64), nullable=True, unique=True),
        sa.Column("reply_to_message_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("error_code", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("started_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("completed_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("payload", JSON_TYPE, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("run_id", "persona_id", name="uq_tavern_run_step_persona"),
    )
    op.create_index(
        "ix_tavern_run_steps_persona_id",
        "tavern_run_steps",
        ["persona_id"],
    )
    op.create_index(
        "ix_tavern_run_steps_status",
        "tavern_run_steps",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_tavern_run_steps_status", table_name="tavern_run_steps")
    op.drop_index("ix_tavern_run_steps_persona_id", table_name="tavern_run_steps")
    op.drop_table("tavern_run_steps")
    op.drop_constraint(
        "fk_tavern_runs_parent_run_id",
        "tavern_runs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "uq_tavern_runs_parent_run_id",
        "tavern_runs",
        type_="unique",
    )
    op.drop_column("tavern_runs", "parent_run_id")
