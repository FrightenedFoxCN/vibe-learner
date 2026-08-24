"""add private Study question attempt journal

Revision ID: 20260824_0008
Revises: 20260812_0007
Create Date: 2026-08-24 18:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260824_0008"
down_revision = "20260812_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_question_attempts",
        sa.Column("attempt_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("turn_id", sa.String(length=64), nullable=False),
        sa.Column("client_attempt_id", sa.String(length=80), nullable=False),
        sa.Column("request_schema_version", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_contract_version", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "request_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("response_schema_version", sa.String(length=64), nullable=False),
        sa.Column(
            "response_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("response_digest", sa.String(length=64), nullable=False),
        sa.Column("before_session_revision", sa.Integer(), nullable=False),
        sa.Column("committed_session_revision", sa.Integer(), nullable=False),
        sa.Column("committed_at", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "committed_session_revision = before_session_revision + 1",
            name="ck_study_question_attempt_revision",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["study_sessions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint(
            "session_id",
            "client_attempt_id",
            name="uq_study_question_attempt_request",
        ),
        sa.UniqueConstraint(
            "session_id",
            "turn_id",
            name="uq_study_question_attempt_turn",
        ),
    )
    op.create_index(
        "ix_study_question_attempts_session_id",
        "study_question_attempts",
        ["session_id"],
    )
    op.create_index(
        "ix_study_question_attempts_turn_id",
        "study_question_attempts",
        ["turn_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_study_question_attempts_turn_id",
        table_name="study_question_attempts",
    )
    op.drop_index(
        "ix_study_question_attempts_session_id",
        table_name="study_question_attempts",
    )
    op.drop_table("study_question_attempts")
