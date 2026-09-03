"""add durable Harness v3 runtime execution records

Revision ID: 20260903_0016
Revises: 20260903_0015
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260903_0016"
down_revision = "20260903_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harness_runtime_executions",
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("trace_slot", sa.Integer, nullable=False),
        sa.Column("harness_operation_id", sa.String(64), nullable=False),
        sa.Column("parent_trace_id", sa.String(64), nullable=True),
        sa.Column("workflow", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("adapter_contract_name", sa.String(160), nullable=False),
        sa.Column("adapter_contract_version", sa.String(160), nullable=False),
        sa.Column("trace_contract_name", sa.String(160), nullable=False),
        sa.Column("trace_contract_version", sa.String(160), nullable=False),
        sa.Column("context_payload", sa.JSON, nullable=False),
        sa.Column("context_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("claim_owner", sa.String(160), nullable=False),
        sa.Column("claim_token", sa.String(64), nullable=False),
        sa.Column("claim_count", sa.Integer, nullable=False),
        sa.Column("lease_expires_at", sa.String(64), nullable=False),
        sa.Column("execution_started_at", sa.String(64), nullable=False),
        sa.Column("attempt_records", sa.JSON, nullable=False),
        sa.Column("checks", sa.JSON, nullable=False),
        sa.Column("terminal_trace", sa.JSON, nullable=True),
        sa.Column("terminal_trace_digest", sa.String(64), nullable=False),
        sa.Column("schema_name", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(
            ["harness_operation_id"], ["harness_operation_bindings.harness_operation_id"],
            name="fk_harness_runtime_operation", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["parent_trace_id"], ["harness_runtime_executions.trace_id"],
            name="fk_harness_runtime_parent_trace", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("trace_id"),
        sa.UniqueConstraint("harness_operation_id", "stage", "trace_slot",
                            name="uq_harness_runtime_operation_stage_slot"),
        sa.CheckConstraint(
            "schema_name = 'HarnessRuntimeExecution' AND schema_version = 'harness-runtime-execution-v1'",
            name="ck_harness_runtime_schema",
        ),
        sa.CheckConstraint("trace_slot >= 0 AND trace_slot <= 127", name="ck_harness_runtime_trace_slot"),
        sa.CheckConstraint("claim_count >= 0 AND claim_count <= 3", name="ck_harness_runtime_claim_count"),
        sa.CheckConstraint("state IN ('prepared', 'claimed', 'terminal')", name="ck_harness_runtime_state"),
        sa.CheckConstraint(
            "(state = 'prepared' AND claim_owner = '' AND claim_token = '' AND lease_expires_at = '' AND terminal_trace IS NULL) OR "
            "(state = 'claimed' AND claim_owner <> '' AND claim_token <> '' AND lease_expires_at <> '' AND claim_count >= 1 AND terminal_trace IS NULL) OR "
            "(state = 'terminal' AND claim_owner = '' AND claim_token = '' AND lease_expires_at = '' AND terminal_trace IS NOT NULL)",
            name="ck_harness_runtime_state_shape",
        ),
    )
    for column in ("harness_operation_id", "parent_trace_id", "stage", "state", "lease_expires_at", "created_at", "updated_at"):
        op.create_index(f"ix_harness_runtime_executions_{column}", "harness_runtime_executions", [column])
    _create_guards()


def downgrade() -> None:
    _drop_guards()
    for column in ("harness_operation_id", "parent_trace_id", "stage", "state", "lease_expires_at", "created_at", "updated_at"):
        op.drop_index(f"ix_harness_runtime_executions_{column}", table_name="harness_runtime_executions")
    op.drop_table("harness_runtime_executions")


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("""
            CREATE TRIGGER trg_harness_runtime_identity_immutable
            BEFORE UPDATE ON harness_runtime_executions
            WHEN NOT (
                NEW.trace_id IS OLD.trace_id AND NEW.trace_slot IS OLD.trace_slot
                AND NEW.harness_operation_id IS OLD.harness_operation_id AND NEW.parent_trace_id IS OLD.parent_trace_id
                AND NEW.workflow IS OLD.workflow AND NEW.stage IS OLD.stage
                AND NEW.adapter_contract_name IS OLD.adapter_contract_name AND NEW.adapter_contract_version IS OLD.adapter_contract_version
                AND NEW.trace_contract_name IS OLD.trace_contract_name AND NEW.trace_contract_version IS OLD.trace_contract_version
                AND NEW.context_payload IS OLD.context_payload AND NEW.context_digest IS OLD.context_digest
                AND NEW.schema_name IS OLD.schema_name AND NEW.schema_version IS OLD.schema_version AND NEW.created_at IS OLD.created_at
                AND OLD.state <> 'terminal'
            ) BEGIN SELECT RAISE(ABORT, 'harness_runtime_identity_mutation_forbidden'); END
        """)
        op.execute("""
            CREATE TRIGGER trg_harness_runtime_no_delete BEFORE DELETE ON harness_runtime_executions
            BEGIN SELECT RAISE(ABORT, 'harness_runtime_delete_forbidden'); END
        """)
    elif dialect == "postgresql":
        op.execute("""
            CREATE FUNCTION validate_harness_runtime_update() RETURNS trigger AS $$
            BEGIN
                IF OLD.state = 'terminal' OR NEW.trace_id IS DISTINCT FROM OLD.trace_id
                OR NEW.trace_slot IS DISTINCT FROM OLD.trace_slot OR NEW.harness_operation_id IS DISTINCT FROM OLD.harness_operation_id
                OR NEW.parent_trace_id IS DISTINCT FROM OLD.parent_trace_id OR NEW.workflow IS DISTINCT FROM OLD.workflow
                OR NEW.stage IS DISTINCT FROM OLD.stage OR NEW.adapter_contract_name IS DISTINCT FROM OLD.adapter_contract_name
                OR NEW.adapter_contract_version IS DISTINCT FROM OLD.adapter_contract_version
                OR NEW.trace_contract_name IS DISTINCT FROM OLD.trace_contract_name OR NEW.trace_contract_version IS DISTINCT FROM OLD.trace_contract_version
                OR NEW.context_payload IS DISTINCT FROM OLD.context_payload OR NEW.context_digest IS DISTINCT FROM OLD.context_digest
                OR NEW.schema_name IS DISTINCT FROM OLD.schema_name OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN RAISE EXCEPTION 'harness_runtime_identity_mutation_forbidden'; END IF;
                RETURN NEW;
            END; $$ LANGUAGE plpgsql
        """)
        op.execute("""CREATE FUNCTION reject_harness_runtime_delete() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'harness_runtime_delete_forbidden'; END; $$ LANGUAGE plpgsql""")
        op.execute("CREATE TRIGGER trg_harness_runtime_identity_immutable BEFORE UPDATE ON harness_runtime_executions FOR EACH ROW EXECUTE FUNCTION validate_harness_runtime_update()")
        op.execute("CREATE TRIGGER trg_harness_runtime_no_delete BEFORE DELETE ON harness_runtime_executions FOR EACH ROW EXECUTE FUNCTION reject_harness_runtime_delete()")


def _drop_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_harness_runtime_identity_immutable")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_runtime_no_delete")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_harness_runtime_identity_immutable ON harness_runtime_executions")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_runtime_no_delete ON harness_runtime_executions")
        op.execute("DROP FUNCTION IF EXISTS validate_harness_runtime_update()")
        op.execute("DROP FUNCTION IF EXISTS reject_harness_runtime_delete()")
