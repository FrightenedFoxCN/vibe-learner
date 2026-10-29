"""Bounded durable parse checkpoints and one child per explicit resume."""

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "20261029_0025"
down_revision = "20261029_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    offline = context.is_offline_mode()
    payload = sa.JSON().with_variant(JSONB(), "postgresql")
    nullable = sa.JSON(none_as_null=True).with_variant(
        JSONB(none_as_null=True), "postgresql"
    )
    if offline or not sa.inspect(connection).has_table("document_checkpoints"):
        op.create_table(
            "document_checkpoints",
            sa.Column(
                "operation_id",
                sa.String(64),
                sa.ForeignKey("document_process_operations.operation_id"),
                primary_key=True,
            ),
            sa.Column("document_id", sa.String(64), nullable=False, index=True),
            sa.Column("upload_digest", sa.String(64), nullable=False),
            sa.Column("configuration_digest", sa.String(64), nullable=False),
            sa.Column("force_ocr", sa.Boolean(), nullable=False),
            sa.Column("page_count", sa.Integer(), nullable=False),
            sa.Column("byte_count", sa.Integer(), nullable=False),
            sa.Column("storage_limited", sa.Boolean(), nullable=False),
            sa.Column("report", nullable, nullable=True),
            sa.Column("output", nullable, nullable=True),
            sa.Column("stage_digest", sa.String(64), nullable=False),
            sa.Column("committed_document", nullable, nullable=True),
        )
    if offline or not sa.inspect(connection).has_table("document_checkpoint_pages"):
        op.create_table(
            "document_checkpoint_pages",
            sa.Column(
                "operation_id",
                sa.String(64),
                sa.ForeignKey("document_checkpoints.operation_id"),
                primary_key=True,
            ),
            sa.Column("page_number", sa.Integer(), primary_key=True),
            sa.Column("payload", payload, nullable=False),
            sa.Column("payload_digest", sa.String(64), nullable=False),
        )
    if offline or not sa.inspect(connection).has_table("document_checkpoint_resumes"):
        op.create_table(
            "document_checkpoint_resumes",
            sa.Column(
                "source_operation_id",
                sa.String(64),
                sa.ForeignKey("document_checkpoints.operation_id"),
                primary_key=True,
            ),
            sa.Column(
                "child_operation_id",
                sa.String(64),
                sa.ForeignKey("document_process_operations.operation_id"),
                nullable=False,
                unique=True,
            ),
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table in (
        "document_checkpoint_resumes",
        "document_checkpoint_pages",
        "document_checkpoints",
    ):
        if connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one():
            raise RuntimeError(
                "document_checkpoint_retention_requires_explicit_export_before_downgrade"
            )
    for table in (
        "document_checkpoint_resumes",
        "document_checkpoint_pages",
        "document_checkpoints",
    ):
        op.drop_table(table)
