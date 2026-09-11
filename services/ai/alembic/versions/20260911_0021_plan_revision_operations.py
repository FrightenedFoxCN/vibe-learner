"""Durable Plan revision admissions and immutable decision receipts.

Revision ID: 20260911_0021
Revises: 20260911_0020
"""
import sqlalchemy as sa
from alembic import op, context

revision = "20260911_0021"
down_revision = "20260911_0020"
branch_labels = None
depends_on = None

ROUTE = "(domain_operation_kind = 'learning_plan_revision' AND workflow = 'planning' AND entry_stage = 'plan_revision')"

FULL_ROUTE = "(domain_operation_kind = 'document_process' AND workflow = 'document_parse' AND entry_stage = 'document_parse') OR (domain_operation_kind = 'document_ocr' AND workflow = 'ocr' AND entry_stage = 'ocr_page') OR (domain_operation_kind = 'study_unit_cleanup' AND workflow = 'study_unit_cleanup' AND entry_stage = 'study_unit_cleanup') OR (domain_operation_kind = 'learning_plan_generation' AND workflow = 'planning' AND entry_stage = 'plan_generation') OR (domain_operation_kind = 'learning_plan_revision' AND workflow = 'planning' AND entry_stage = 'plan_revision') OR (domain_operation_kind = 'persona_generation' AND workflow = 'persona' AND entry_stage = 'persona_generation') OR (domain_operation_kind = 'scene_generation' AND workflow = 'scene' AND entry_stage = 'scene_generation') OR (domain_operation_kind = 'study_chat' AND workflow = 'study_chat' AND entry_stage = 'study_chat_reply') OR (domain_operation_kind = 'tavern_run' AND workflow = 'tavern' AND entry_stage = 'actor_reply') OR (domain_operation_kind = 'frontend_decode' AND workflow = 'frontend_decode' AND entry_stage = 'response_decode')"


def upgrade() -> None:
    connection = op.get_bind()
    offline = context.is_offline_mode()
    constraint = None if offline else next(item for item in sa.inspect(connection).get_check_constraints("harness_operation_bindings")
                      if item["name"] == "ck_harness_operation_binding_route")
    if offline or "learning_plan_revision" not in constraint["sqltext"]:
        triggers = []
        if connection.dialect.name == "sqlite":
            triggers = connection.execute(sa.text("SELECT name, sql FROM sqlite_master WHERE type='trigger' AND sql LIKE '%harness_operation_bindings%'")).all()
            for name, _ in triggers:
                connection.exec_driver_sql('DROP TRIGGER "' + name.replace('"', '""') + '"')
        with op.batch_alter_table("harness_operation_bindings") as batch:
            batch.drop_constraint("ck_harness_operation_binding_route", type_="check")
            batch.create_check_constraint("ck_harness_operation_binding_route", FULL_ROUTE)
        for _, sql in triggers:
            connection.exec_driver_sql(sql)
    if offline or not sa.inspect(connection).has_table("plan_revision_operations"):
        op.create_table("plan_revision_operations",
            sa.Column("operation_id", sa.String(80), primary_key=True),
            sa.Column("harness_operation_id", sa.String(64), sa.ForeignKey("harness_operation_bindings.harness_operation_id"), unique=True),
            sa.Column("plan_id", sa.String(64), nullable=False, index=True),
            sa.Column("client_request_id", sa.String(80), nullable=False),
            sa.Column("base_revision", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("request", sa.JSON(), nullable=False),
            sa.Column("base_plan", sa.JSON(), nullable=False),
            sa.Column("proposal", sa.JSON(), nullable=True),
            sa.Column("preview_receipt", sa.JSON(), nullable=True),
            sa.Column("decision_receipt", sa.JSON(), nullable=True),
            sa.Column("error_code", sa.String(160), nullable=False, server_default=""),
            sa.Column("created_at", sa.String(64), nullable=False),
            sa.UniqueConstraint("plan_id", "client_request_id", name="uq_plan_revision_request"))


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM harness_operation_bindings WHERE domain_operation_kind='learning_plan_revision'")).scalar_one():
        raise RuntimeError("plan_revision_admission_tombstones_prevent_downgrade")
    op.drop_table("plan_revision_operations")
    # Preserve the widened route check: it is read-compatible and carries no data.
