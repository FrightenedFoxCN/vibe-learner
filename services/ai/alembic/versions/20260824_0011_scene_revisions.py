"""add Scene aggregate revisions

Revision ID: 20260824_0011
Revises: 20260824_0010
Create Date: 2026-08-24 23:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260824_0011"
down_revision = "20260824_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scene_setup_states",
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "scene_library_entries",
        sa.Column(
            "revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("scene_library_entries", "revision")
    op.drop_column("scene_setup_states", "revision")
