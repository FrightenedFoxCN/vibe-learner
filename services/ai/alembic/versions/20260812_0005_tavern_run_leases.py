"""add tavern speaker-step leases

Revision ID: 20260812_0005
Revises: 20260812_0004
Create Date: 2026-08-12 06:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260812_0005"
down_revision = "20260812_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tavern_run_steps",
        sa.Column("lease_owner", sa.String(length=64), nullable=False, server_default=""),
    )
    op.add_column(
        "tavern_run_steps",
        sa.Column(
            "lease_expires_at",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "tavern_run_steps",
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("tavern_run_steps", "claim_count")
    op.drop_column("tavern_run_steps", "lease_expires_at")
    op.drop_column("tavern_run_steps", "lease_owner")
