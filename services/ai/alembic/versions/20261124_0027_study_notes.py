"""Add Study Notes separate from the session/chat aggregate."""

from alembic import context, op
import sqlalchemy as sa

revision = "20261124_0027"
down_revision = "20261029_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not context.is_offline_mode() and sa.inspect(op.get_bind()).has_table(
        "study_notes"
    ):
        # Application bootstrap may already have installed the metadata table.
        return
    op.create_table(
        "study_notes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("study_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("search_title", sa.Text(), nullable=False),
        sa.Column("search_content", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
        sa.CheckConstraint("revision >= 1", name="ck_study_notes_revision"),
    )
    op.create_index("ix_study_notes_session_id_id", "study_notes", ["session_id", "id"])
    op.create_index(
        "ix_study_notes_session_recent",
        "study_notes",
        ["session_id", "updated_at", "id"],
    )


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("study_notes_downgrade_requires_online_empty_table_check")
    if op.get_bind().execute(sa.text("SELECT 1 FROM study_notes LIMIT 1")).first():
        raise RuntimeError("study_notes_downgrade_requires_empty_table")
    op.drop_table("study_notes")
