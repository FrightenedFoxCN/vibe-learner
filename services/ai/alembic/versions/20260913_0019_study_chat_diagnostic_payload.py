"""Store server-only provider payloads for failed Study Chat operations."""

from alembic import op
import sqlalchemy as sa


revision = "20260913_0019"
down_revision = "20260903_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("study_chat_operations", sa.Column("diagnostic_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("study_chat_operations", "diagnostic_payload")
