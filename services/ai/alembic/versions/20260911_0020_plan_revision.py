"""Database authoritative Plan CAS and revision history.

Revision ID: 20260911_0020
Revises: 20260909_0019
"""
import sqlalchemy as sa
from alembic import op, context

revision = "20260911_0020"
down_revision = "20260909_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = set() if context.is_offline_mode() else {item["name"] for item in sa.inspect(op.get_bind()).get_columns("learning_plans")}
    for column in ("revision", "deleted"):
        if column not in columns:
            op.add_column("learning_plans", sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
    if context.is_offline_mode() or not sa.inspect(op.get_bind()).has_table("learning_plan_revisions"):
        op.create_table("learning_plan_revisions",
            sa.Column("plan_id", sa.String(64), primary_key=True),
            sa.Column("revision", sa.Integer(), primary_key=True),
            sa.Column("payload", sa.JSON(), nullable=False))
    # Existing JSON is untouched: original creation digests remain valid.


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT count(*) FROM learning_plans WHERE revision > 0 OR deleted > 0")).scalar_one():
        raise RuntimeError("plan_revision_history_prevents_downgrade")
    op.drop_table("learning_plan_revisions")
    with op.batch_alter_table("learning_plans") as batch:
        batch.drop_column("deleted")
        batch.drop_column("revision")
