"""Add Document revision for single-record CAS writes."""

from alembic import op
import sqlalchemy as sa


revision = "20261029_0023"
down_revision = "20260914_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("documents", "revision")
