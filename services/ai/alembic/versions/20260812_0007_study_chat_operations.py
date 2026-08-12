"""add durable Study Chat operation admission journal

Revision ID: 20260812_0007
Revises: 20260812_0006
Create Date: 2026-08-12 21:50:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260812_0007"
down_revision = "20260812_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_chat_operations",
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("client_request_id", sa.String(length=80), nullable=False),
        sa.Column("request_schema_version", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_contract_version", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "request_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("admitted_session_revision", sa.Integer(), nullable=False),
        sa.Column("execution_token", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_started_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("provider_started_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("execution_deadline_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("heartbeat_at", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("committed_session_revision", sa.Integer(), nullable=True),
        sa.Column("committed_turn_id", sa.String(length=64), nullable=True),
        sa.Column("committed_turn_sequence", sa.Integer(), nullable=True),
        sa.Column("response_schema_version", sa.String(length=64), nullable=False, server_default=""),
        sa.Column(
            "response_payload",
            sa.JSON(none_as_null=True).with_variant(
                postgresql.JSONB(none_as_null=True),
                "postgresql",
            ),
            nullable=True,
        ),
        sa.Column("response_digest", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("error_code", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.String(length=64), nullable=False, server_default=""),
        sa.CheckConstraint("claim_count IN (0, 1)", name="ck_study_chat_operation_claim_count"),
        sa.CheckConstraint(
            "(status IN ('admitted', 'running') AND active_slot = 1) OR "
            "(status IN ('committed', 'not_committed', 'uncertain') AND active_slot IS NULL)",
            name="ck_study_chat_operation_active_status",
        ),
        sa.CheckConstraint(
            "(status IN ('admitted', 'not_committed') AND claim_count = 0 "
            "AND execution_token = '' AND execution_started_at = '' "
            "AND provider_started_at = '' AND execution_deadline_at = '' AND heartbeat_at = '') OR "
            "(status IN ('running', 'committed', 'uncertain') AND claim_count = 1 "
            "AND execution_token <> '' AND execution_started_at <> '' AND execution_deadline_at <> '')",
            name="ck_study_chat_operation_execution_evidence",
        ),
        sa.CheckConstraint(
            "(status = 'committed' AND committed_session_revision IS NOT NULL "
            "AND committed_turn_id IS NOT NULL AND committed_turn_sequence IS NOT NULL "
            "AND response_schema_version <> '' AND response_payload IS NOT NULL "
            "AND response_digest <> '' AND error_code = '' AND completed_at <> '') OR "
            "(status <> 'committed' AND committed_session_revision IS NULL "
            "AND committed_turn_id IS NULL AND committed_turn_sequence IS NULL "
            "AND response_schema_version = '' AND response_payload IS NULL AND response_digest = '')",
            name="ck_study_chat_operation_result_evidence",
        ),
        sa.CheckConstraint(
            "(status IN ('committed', 'not_committed', 'uncertain') AND completed_at <> '') OR "
            "(status IN ('admitted', 'running') AND completed_at = '')",
            name="ck_study_chat_operation_terminal_time",
        ),
        sa.CheckConstraint(
            "(status IN ('not_committed', 'uncertain') AND error_code <> '') OR "
            "(status IN ('admitted', 'running', 'committed') AND error_code = '')",
            name="ck_study_chat_operation_error_evidence",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["study_sessions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint("committed_turn_id", name="uq_study_chat_operation_turn"),
        sa.UniqueConstraint(
            "session_id",
            "active_slot",
            name="uq_study_chat_operation_active_slot",
        ),
        sa.UniqueConstraint(
            "session_id",
            "client_request_id",
            name="uq_study_chat_operation_request",
        ),
    )
    op.create_index(
        "ix_study_chat_operations_session_id",
        "study_chat_operations",
        ["session_id"],
    )
    op.create_index(
        "ix_study_chat_operations_status",
        "study_chat_operations",
        ["status"],
    )
    op.create_index(
        "ix_study_chat_operations_updated_at",
        "study_chat_operations",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_study_chat_operations_updated_at", table_name="study_chat_operations")
    op.drop_index("ix_study_chat_operations_status", table_name="study_chat_operations")
    op.drop_index("ix_study_chat_operations_session_id", table_name="study_chat_operations")
    op.drop_table("study_chat_operations")
