"""add Study Session CAS and turn sequence watermarks

Revision ID: 20260812_0006
Revises: 20260812_0005
Create Date: 2026-08-12 21:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0006"
down_revision = "20260812_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "study_sessions",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "study_sessions",
        sa.Column(
            "last_turn_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("study_sessions", "last_turn_sequence")
    op.drop_column("study_sessions", "revision")
