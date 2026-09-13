"""Merge the plan revision and Study Chat diagnostic migration branches.

Revision ID: 20260914_0022
Revises: 20260911_0021, 20260913_0019
"""

revision = "20260914_0022"
down_revision = ("20260911_0021", "20260913_0019")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge point; both parent migrations have already run."""


def downgrade() -> None:
    """Merge point; Alembic downgrades through both parent branches."""
