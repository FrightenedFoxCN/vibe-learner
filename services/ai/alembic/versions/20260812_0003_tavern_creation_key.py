"""add tavern room creation idempotency key

Revision ID: 20260812_0003
Revises: 20260812_0002
Create Date: 2026-08-12 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0003"
down_revision = "20260812_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tavern_rooms",
        sa.Column("creation_key", sa.String(length=80), nullable=True),
    )
    op.create_unique_constraint(
        "uq_tavern_rooms_creation_key",
        "tavern_rooms",
        ["creation_key"],
    )
    op.add_column(
        "tavern_rooms",
        sa.Column(
            "creation_input_digest",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )


def downgrade() -> None:
    op.drop_column("tavern_rooms", "creation_input_digest")
    op.drop_constraint(
        "uq_tavern_rooms_creation_key",
        "tavern_rooms",
        type_="unique",
    )
    op.drop_column("tavern_rooms", "creation_key")
