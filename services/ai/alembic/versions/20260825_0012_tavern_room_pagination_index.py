"""add Tavern Room pagination index

Revision ID: 20260825_0012
Revises: 20260824_0011
Create Date: 2026-08-25 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260825_0012"
down_revision = "20260824_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_tavern_rooms_updated_at_id",
        "tavern_rooms",
        [sa.text("updated_at DESC"), sa.text("id DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_tavern_rooms_updated_at_id", table_name="tavern_rooms")
