"""Persist server only Study Chat v3 trace."""

from alembic import op
import sqlalchemy as sa

revision = "20260903_0017"
down_revision = "20260903_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "study_chat_operations",
        sa.Column("harness_trace", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("study_chat_operations", "harness_trace")
