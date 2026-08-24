"""add durable Document process operation journal

Revision ID: 20260824_0009
Revises: 20260824_0008
Create Date: 2026-08-24 21:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260824_0009"
down_revision = "20260824_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_process_operations",
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
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
        sa.Column("projection_state", sa.String(length=32), nullable=False),
        sa.Column(
            "base_document_payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("document_digest", sa.String(length=64), nullable=False),
        sa.Column("debug_digest", sa.String(length=64), nullable=False),
        sa.Column("commit_contract_version", sa.String(length=64), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "(status = 'running' AND active_slot = 1 AND projection_state = 'pending' "
            "AND completed_at = '' AND error_code = '') OR "
            "(status = 'committed' AND active_slot IS NULL AND projection_state = 'committed' "
            "AND completed_at <> '' AND error_code = '' "
            "AND document_digest <> '' AND debug_digest <> '' AND commit_contract_version <> '') OR "
            "(status IN ('failed', 'interrupted') AND active_slot IS NULL "
            "AND projection_state = 'not_committed' AND completed_at <> '' AND error_code <> '' "
            "AND document_digest = '' AND debug_digest = '' AND commit_contract_version = '')",
            name="ck_document_process_operation_state",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint(
            "document_id",
            "active_slot",
            name="uq_document_process_operation_active_slot",
        ),
    )
    op.create_index(
        "ix_document_process_operations_document_id",
        "document_process_operations",
        ["document_id"],
    )
    op.create_index(
        "ix_document_process_operations_status",
        "document_process_operations",
        ["status"],
    )
    op.create_index(
        "ix_document_process_operations_updated_at",
        "document_process_operations",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_process_operations_updated_at",
        table_name="document_process_operations",
    )
    op.drop_index(
        "ix_document_process_operations_status",
        table_name="document_process_operations",
    )
    op.drop_index(
        "ix_document_process_operations_document_id",
        table_name="document_process_operations",
    )
    op.drop_table("document_process_operations")
