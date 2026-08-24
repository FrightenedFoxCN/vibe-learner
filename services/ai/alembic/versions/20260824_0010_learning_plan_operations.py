"""add durable Learning Plan operation journal

Revision ID: 20260824_0010
Revises: 20260824_0009
Create Date: 2026-08-24 22:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260824_0010"
down_revision = "20260824_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_payload = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
    nullable_json_payload = sa.JSON(none_as_null=True).with_variant(
        postgresql.JSONB(none_as_null=True),
        "postgresql",
    )
    op.create_table(
        "learning_plan_operations",
        sa.Column("operation_id", sa.String(length=64), nullable=False),
        sa.Column("client_request_id", sa.String(length=80), nullable=False),
        sa.Column("scope_key", sa.String(length=160), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=True),
        sa.Column("persona_id", sa.String(length=64), nullable=False),
        sa.Column("request_schema_version", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_contract_version", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_payload", json_payload, nullable=False),
        sa.Column("base_document_updated_at", sa.String(length=64), nullable=False),
        sa.Column("base_document_digest", sa.String(length=64), nullable=False),
        sa.Column("base_debug_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("projection_state", sa.String(length=32), nullable=False),
        sa.Column("provider_started_at", sa.String(length=64), nullable=False),
        sa.Column("plan_id", sa.String(length=64), nullable=False),
        sa.Column("commit_contract_version", sa.String(length=64), nullable=False),
        sa.Column("committed_projection_digest", sa.String(length=64), nullable=False),
        sa.Column("committed_projection_payload", nullable_json_payload, nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("completed_at", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "(status = 'running' AND active_slot = 1 AND projection_state = 'pending' "
            "AND completed_at = '' AND error_code = '' "
            "AND plan_id = '' AND committed_projection_digest = '' "
            "AND committed_projection_payload IS NULL AND commit_contract_version = '') OR "
            "(status = 'committed' AND active_slot IS NULL AND projection_state = 'committed' "
            "AND completed_at <> '' AND error_code = '' AND plan_id <> '' "
            "AND committed_projection_digest <> '' AND committed_projection_payload IS NOT NULL "
            "AND commit_contract_version <> '') OR "
            "(status IN ('not_committed', 'interrupted', 'uncertain') "
            "AND active_slot IS NULL AND projection_state = 'not_committed' "
            "AND completed_at <> '' AND error_code <> '' AND plan_id = '' "
            "AND committed_projection_digest = '' AND committed_projection_payload IS NULL "
            "AND commit_contract_version = '')",
            name="ck_learning_plan_operation_state",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint(
            "client_request_id",
            name="uq_learning_plan_operation_client_request",
        ),
        sa.UniqueConstraint(
            "scope_key",
            "active_slot",
            name="uq_learning_plan_operation_active_scope",
        ),
    )
    op.create_index(
        "ix_learning_plan_operations_document_id",
        "learning_plan_operations",
        ["document_id"],
    )
    op.create_index(
        "ix_learning_plan_operations_persona_id",
        "learning_plan_operations",
        ["persona_id"],
    )
    op.create_index(
        "ix_learning_plan_operations_status",
        "learning_plan_operations",
        ["status"],
    )
    op.create_index(
        "ix_learning_plan_operations_updated_at",
        "learning_plan_operations",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_plan_operations_updated_at",
        table_name="learning_plan_operations",
    )
    op.drop_index(
        "ix_learning_plan_operations_status",
        table_name="learning_plan_operations",
    )
    op.drop_index(
        "ix_learning_plan_operations_persona_id",
        table_name="learning_plan_operations",
    )
    op.drop_index(
        "ix_learning_plan_operations_document_id",
        table_name="learning_plan_operations",
    )
    op.drop_table("learning_plan_operations")
