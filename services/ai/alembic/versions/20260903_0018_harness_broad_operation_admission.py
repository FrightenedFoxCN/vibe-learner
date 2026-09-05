"""add durable admission rows for broad Harness workflows

Revision ID: 20260903_0018
Revises: 20260903_0017
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260903_0018"
down_revision = "20260903_0017"
branch_labels = None
depends_on = None


_ROUTE_CHECK = (
    "(domain_operation_kind = 'document_process' AND workflow = 'document_parse' AND entry_stage = 'document_parse') OR "
    "(domain_operation_kind = 'document_ocr' AND workflow = 'ocr' AND entry_stage = 'ocr_page') OR "
    "(domain_operation_kind = 'study_unit_cleanup' AND workflow = 'study_unit_cleanup' AND entry_stage = 'study_unit_cleanup') OR "
    "(domain_operation_kind = 'learning_plan_generation' AND workflow = 'planning' AND entry_stage = 'plan_generation') OR "
    "(domain_operation_kind = 'persona_generation' AND workflow = 'persona' AND entry_stage = 'persona_generation') OR "
    "(domain_operation_kind = 'scene_generation' AND workflow = 'scene' AND entry_stage = 'scene_generation') OR "
    "(domain_operation_kind = 'study_chat' AND workflow = 'study_chat' AND entry_stage = 'study_chat_reply') OR "
    "(domain_operation_kind = 'tavern_run' AND workflow = 'tavern' AND entry_stage = 'actor_reply')"
)

_LEGACY_ROUTE_CHECK = (
    "(domain_operation_kind = 'document_process' AND workflow = 'document_parse' AND entry_stage = 'document_parse') OR "
    "(domain_operation_kind = 'learning_plan_generation' AND workflow = 'planning' AND entry_stage = 'plan_generation') OR "
    "(domain_operation_kind = 'study_chat' AND workflow = 'study_chat' AND entry_stage = 'study_chat_reply') OR "
    "(domain_operation_kind = 'tavern_run' AND workflow = 'tavern' AND entry_stage = 'actor_reply')"
)


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_harness_operation_bindings_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_operation_bindings_no_delete")
        _drop_sqlite_domain_validation_guards()
    with op.batch_alter_table("harness_operation_bindings") as batch_op:
        batch_op.drop_constraint(
            "ck_harness_operation_binding_route", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_harness_operation_binding_route", _ROUTE_CHECK
        )
    op.create_table(
        "harness_workflow_operations",
        sa.Column("operation_id", sa.String(160), nullable=False),
        sa.Column("harness_operation_id", sa.String(64), nullable=True),
        sa.Column("domain_operation_kind", sa.String(64), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(160), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("completed_at", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint(
            "harness_operation_id",
            name="uq_harness_workflow_operation_harness_operation",
        ),
        sa.ForeignKeyConstraint(
            ["harness_operation_id"],
            ["harness_operation_bindings.harness_operation_id"],
            name="fk_harness_workflow_operation_harness_operation",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "domain_operation_kind IN ('document_ocr', 'study_unit_cleanup', "
            "'persona_generation', 'scene_generation')",
            name="ck_harness_workflow_operation_kind",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_harness_workflow_operation_status",
        ),
    )
    op.create_index(
        "ix_harness_workflow_operations_domain_operation_kind",
        "harness_workflow_operations",
        ["domain_operation_kind"],
    )
    op.create_index(
        "ix_harness_workflow_operations_status",
        "harness_workflow_operations",
        ["status"],
    )
    op.create_index(
        "ix_harness_workflow_operations_created_at",
        "harness_workflow_operations",
        ["created_at"],
    )
    _create_guards()


def downgrade() -> None:
    _drop_guards()
    for name in (
        "ix_harness_workflow_operations_created_at",
        "ix_harness_workflow_operations_status",
        "ix_harness_workflow_operations_domain_operation_kind",
    ):
        op.drop_index(name, table_name="harness_workflow_operations")
    op.drop_table("harness_workflow_operations")
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_harness_operation_bindings_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_operation_bindings_no_delete")
    with op.batch_alter_table("harness_operation_bindings") as batch_op:
        batch_op.drop_constraint(
            "ck_harness_operation_binding_route", type_="check"
        )
        batch_op.create_check_constraint(
            "ck_harness_operation_binding_route", _LEGACY_ROUTE_CHECK
        )
    _create_binding_guards()


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    _create_binding_guards()
    if dialect == "sqlite":
        _create_sqlite_domain_validation_guards()
        op.execute(
            """
            CREATE TRIGGER trg_harness_workflow_operations_harness_operation_immutable
            BEFORE UPDATE OF harness_operation_id ON harness_workflow_operations
            WHEN NEW.harness_operation_id IS NOT OLD.harness_operation_id
            BEGIN SELECT RAISE(ABORT, 'harness_operation_rebinding_forbidden'); END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_harness_workflow_operations_harness_operation_validate_insert
            BEFORE INSERT ON harness_workflow_operations
            WHEN NEW.harness_operation_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM harness_operation_bindings AS binding
                WHERE binding.harness_operation_id = NEW.harness_operation_id
                  AND binding.domain_operation_kind = NEW.domain_operation_kind
                  AND binding.domain_operation_id = NEW.operation_id
            )
            BEGIN SELECT RAISE(ABORT, 'harness_operation_domain_binding_mismatch'); END
            """
        )
    elif dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION validate_harness_workflow_operation_insert()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.harness_operation_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM harness_operation_bindings AS binding
                    WHERE binding.harness_operation_id = NEW.harness_operation_id
                      AND binding.domain_operation_kind = NEW.domain_operation_kind
                      AND binding.domain_operation_id = NEW.operation_id
                ) THEN
                    RAISE EXCEPTION 'harness_operation_domain_binding_mismatch';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER trg_harness_workflow_operations_harness_operation_immutable "
            "BEFORE UPDATE ON harness_workflow_operations FOR EACH ROW "
            "EXECUTE FUNCTION reject_harness_operation_rebinding()"
        )
        op.execute(
            "CREATE TRIGGER trg_harness_workflow_operations_harness_operation_validate_insert "
            "BEFORE INSERT ON harness_workflow_operations FOR EACH ROW "
            "EXECUTE FUNCTION validate_harness_workflow_operation_insert()"
        )


def _create_binding_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_harness_operation_bindings_no_update
            BEFORE UPDATE ON harness_operation_bindings
            BEGIN SELECT RAISE(ABORT, 'harness_operation_binding_update_forbidden'); END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_harness_operation_bindings_no_delete
            BEFORE DELETE ON harness_operation_bindings
            BEGIN SELECT RAISE(ABORT, 'harness_operation_binding_delete_forbidden'); END
            """
        )


def _drop_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for name in (
            "trg_harness_workflow_operations_harness_operation_immutable",
            "trg_harness_workflow_operations_harness_operation_validate_insert",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif dialect == "postgresql":
        for name in (
            "trg_harness_workflow_operations_harness_operation_immutable",
            "trg_harness_workflow_operations_harness_operation_validate_insert",
        ):
            op.execute(
                f"DROP TRIGGER IF EXISTS {name} ON harness_workflow_operations"
            )
        op.execute("DROP FUNCTION IF EXISTS validate_harness_workflow_operation_insert()")


_EXISTING_DOMAIN_ROUTES = (
    ("document_process_operations", "document_process", "operation_id"),
    ("learning_plan_operations", "learning_plan_generation", "operation_id"),
    ("study_chat_operations", "study_chat", "operation_id"),
    ("tavern_runs", "tavern_run", "id"),
)


def _drop_sqlite_domain_validation_guards() -> None:
    for table_name, _, _ in _EXISTING_DOMAIN_ROUTES:
        op.execute(
            f"DROP TRIGGER IF EXISTS trg_{table_name}_harness_operation_validate_insert"
        )


def _create_sqlite_domain_validation_guards() -> None:
    for table_name, domain_kind, identity_column in _EXISTING_DOMAIN_ROUTES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_harness_operation_validate_insert
            BEFORE INSERT ON {table_name}
            WHEN NEW.harness_operation_id IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM harness_operation_bindings AS binding
                WHERE binding.harness_operation_id = NEW.harness_operation_id
                  AND binding.domain_operation_kind = '{domain_kind}'
                  AND binding.domain_operation_id = NEW.{identity_column}
            )
            BEGIN SELECT RAISE(ABORT, 'harness_operation_domain_binding_mismatch'); END
            """
        )
