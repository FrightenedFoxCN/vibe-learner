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
    with op.batch_alter_table("tavern_rooms") as batch_op:
        batch_op.add_column(
            sa.Column("creation_key", sa.String(length=80), nullable=True),
        )
        batch_op.create_unique_constraint(
            "uq_tavern_rooms_creation_key",
            ["creation_key"],
        )
        batch_op.add_column(
            sa.Column(
                "creation_input_digest",
                sa.String(length=64),
                nullable=False,
                server_default="",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("tavern_rooms") as batch_op:
        batch_op.drop_column("creation_input_digest")
        batch_op.drop_constraint(
            "uq_tavern_rooms_creation_key",
            type_="unique",
        )
        batch_op.drop_column("creation_key")
