"""add append-only Harness operation bindings

Revision ID: 20260825_0013
Revises: 20260825_0012
Create Date: 2026-08-25 14:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260825_0013"
down_revision = "20260825_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harness_operation_bindings",
        sa.Column("harness_operation_id", sa.String(length=64), nullable=False),
        sa.Column("schema_name", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("domain_operation_kind", sa.String(length=64), nullable=False),
        sa.Column("domain_operation_id", sa.String(length=160), nullable=False),
        sa.Column("workflow", sa.String(length=64), nullable=False),
        sa.Column("entry_stage", sa.String(length=64), nullable=False),
        sa.Column(
            "parent_harness_operation_id",
            sa.String(length=64),
            nullable=True,
        ),
        sa.Column("admitted_at", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "schema_name = 'HarnessOperationBindingV1' AND "
            "schema_version = 'harness-operation-binding-v1'",
            name="ck_harness_operation_binding_schema",
        ),
        sa.CheckConstraint(
            "(domain_operation_kind = 'document_process' "
            "AND workflow = 'document_parse' AND entry_stage = 'document_parse') OR "
            "(domain_operation_kind = 'learning_plan_generation' "
            "AND workflow = 'planning' AND entry_stage = 'plan_generation') OR "
            "(domain_operation_kind = 'study_chat' "
            "AND workflow = 'study_chat' AND entry_stage = 'study_chat_reply') OR "
            "(domain_operation_kind = 'tavern_run' "
            "AND workflow = 'tavern' AND entry_stage = 'actor_reply')",
            name="ck_harness_operation_binding_route",
        ),
        sa.CheckConstraint(
            "parent_harness_operation_id IS NULL OR "
            "parent_harness_operation_id <> harness_operation_id",
            name="ck_harness_operation_binding_parent_not_self",
        ),
        sa.CheckConstraint(
            "parent_harness_operation_id IS NULL OR "
            "domain_operation_kind = 'tavern_run'",
            name="ck_harness_operation_binding_parent_kind",
        ),
        sa.ForeignKeyConstraint(
            ["parent_harness_operation_id"],
            ["harness_operation_bindings.harness_operation_id"],
            name="fk_harness_operation_binding_parent",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("harness_operation_id"),
        sa.UniqueConstraint(
            "domain_operation_kind",
            "domain_operation_id",
            name="uq_harness_operation_binding_domain_identity",
        ),
    )
    op.create_index(
        "ix_harness_operation_bindings_admitted_at",
        "harness_operation_bindings",
        ["admitted_at"],
    )
    op.create_index(
        "ix_harness_operation_bindings_parent_harness_operation_id",
        "harness_operation_bindings",
        ["parent_harness_operation_id"],
    )
    for table_name, unique_name, foreign_key_name in _DOMAIN_REFERENCES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "harness_operation_id",
                    sa.String(length=64),
                    nullable=True,
                )
            )
            batch_op.create_unique_constraint(
                unique_name,
                ["harness_operation_id"],
            )
            batch_op.create_foreign_key(
                foreign_key_name,
                "harness_operation_bindings",
                ["harness_operation_id"],
                ["harness_operation_id"],
                ondelete="RESTRICT",
            )
    _create_append_only_guards()


def downgrade() -> None:
    _drop_append_only_guards()
    for table_name, unique_name, foreign_key_name in reversed(_DOMAIN_REFERENCES):
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.drop_constraint(foreign_key_name, type_="foreignkey")
            batch_op.drop_constraint(unique_name, type_="unique")
            batch_op.drop_column("harness_operation_id")
    op.drop_index(
        "ix_harness_operation_bindings_parent_harness_operation_id",
        table_name="harness_operation_bindings",
    )
    op.drop_index(
        "ix_harness_operation_bindings_admitted_at",
        table_name="harness_operation_bindings",
    )
    op.drop_table("harness_operation_bindings")


_DOMAIN_REFERENCES = (
    (
        "document_process_operations",
        "uq_document_process_operation_harness_operation",
        "fk_document_process_operation_harness_operation",
    ),
    (
        "learning_plan_operations",
        "uq_learning_plan_operation_harness_operation",
        "fk_learning_plan_operation_harness_operation",
    ),
    (
        "study_chat_operations",
        "uq_study_chat_operation_harness_operation",
        "fk_study_chat_operation_harness_operation",
    ),
    (
        "tavern_runs",
        "uq_tavern_run_harness_operation",
        "fk_tavern_run_harness_operation",
    ),
)

_DOMAIN_BINDING_ROUTES = {
    "document_process_operations": ("document_process", "operation_id"),
    "learning_plan_operations": ("learning_plan_generation", "operation_id"),
    "study_chat_operations": ("study_chat", "operation_id"),
    "tavern_runs": ("tavern_run", "id"),
}


def _create_append_only_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_harness_operation_bindings_no_update
            BEFORE UPDATE ON harness_operation_bindings
            BEGIN
                SELECT RAISE(ABORT, 'harness_operation_binding_update_forbidden');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_harness_operation_bindings_no_delete
            BEFORE DELETE ON harness_operation_bindings
            BEGIN
                SELECT RAISE(ABORT, 'harness_operation_binding_delete_forbidden');
            END
            """
        )
        for table_name, _, _ in _DOMAIN_REFERENCES:
            op.execute(
                f"""
                CREATE TRIGGER trg_{table_name}_harness_operation_immutable
                BEFORE UPDATE OF harness_operation_id ON {table_name}
                WHEN NEW.harness_operation_id IS NOT OLD.harness_operation_id
                BEGIN
                    SELECT RAISE(ABORT, 'harness_operation_rebinding_forbidden');
                END
                """
            )
            domain_kind, identity_column = _DOMAIN_BINDING_ROUTES[table_name]
            op.execute(
                f"""
                CREATE TRIGGER trg_{table_name}_harness_operation_validate_insert
                BEFORE INSERT ON {table_name}
                WHEN NEW.harness_operation_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1
                        FROM harness_operation_bindings AS binding
                        WHERE binding.harness_operation_id = NEW.harness_operation_id
                            AND binding.domain_operation_kind = '{domain_kind}'
                            AND binding.domain_operation_id = NEW.{identity_column}
                    )
                BEGIN
                    SELECT RAISE(
                        ABORT,
                        'harness_operation_domain_binding_mismatch'
                    );
                END
                """
            )
        return
    if dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_harness_operation_binding_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'harness_operation_binding_%_forbidden', lower(TG_OP);
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_harness_operation_bindings_append_only
            BEFORE UPDATE OR DELETE ON harness_operation_bindings
            FOR EACH ROW EXECUTE FUNCTION reject_harness_operation_binding_mutation()
            """
        )
        op.execute(
            """
            CREATE FUNCTION reject_harness_operation_rebinding()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.harness_operation_id IS DISTINCT FROM OLD.harness_operation_id THEN
                    RAISE EXCEPTION 'harness_operation_rebinding_forbidden';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE FUNCTION validate_harness_operation_domain_insert()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.harness_operation_id IS NOT NULL AND NOT EXISTS (
                    SELECT 1
                    FROM harness_operation_bindings AS binding
                    WHERE binding.harness_operation_id = NEW.harness_operation_id
                        AND binding.domain_operation_kind = TG_ARGV[0]
                        AND binding.domain_operation_id = to_jsonb(NEW) ->> TG_ARGV[1]
                ) THEN
                    RAISE EXCEPTION 'harness_operation_domain_binding_mismatch';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table_name, _, _ in _DOMAIN_REFERENCES:
            op.execute(
                f"""
                CREATE TRIGGER trg_{table_name}_harness_operation_immutable
                BEFORE UPDATE OF harness_operation_id ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION reject_harness_operation_rebinding()
                """
            )
            domain_kind, identity_column = _DOMAIN_BINDING_ROUTES[table_name]
            op.execute(
                f"""
                CREATE TRIGGER trg_{table_name}_harness_operation_validate_insert
                BEFORE INSERT ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION
                    validate_harness_operation_domain_insert(
                        '{domain_kind}', '{identity_column}'
                    )
                """
            )


def _drop_append_only_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table_name, _, _ in _DOMAIN_REFERENCES:
            op.execute(
                f"DROP TRIGGER IF EXISTS "
                f"trg_{table_name}_harness_operation_validate_insert"
            )
            op.execute(
                f"DROP TRIGGER IF EXISTS trg_{table_name}_harness_operation_immutable"
            )
        op.execute("DROP TRIGGER IF EXISTS trg_harness_operation_bindings_no_delete")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_operation_bindings_no_update")
        return
    if dialect == "postgresql":
        for table_name, _, _ in _DOMAIN_REFERENCES:
            op.execute(
                f"DROP TRIGGER IF EXISTS "
                f"trg_{table_name}_harness_operation_validate_insert "
                f"ON {table_name}"
            )
            op.execute(
                f"DROP TRIGGER IF EXISTS "
                f"trg_{table_name}_harness_operation_immutable ON {table_name}"
            )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_harness_operation_bindings_append_only "
            "ON harness_operation_bindings"
        )
        op.execute("DROP FUNCTION IF EXISTS reject_harness_operation_rebinding()")
        op.execute(
            "DROP FUNCTION IF EXISTS validate_harness_operation_domain_insert()"
        )
        op.execute(
            "DROP FUNCTION IF EXISTS reject_harness_operation_binding_mutation()"
        )
