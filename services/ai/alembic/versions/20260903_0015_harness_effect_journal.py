"""add durable Harness effect journal and terminal evidence

Revision ID: 20260903_0015
Revises: 20260831_0014
Create Date: 2026-09-03 10:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260903_0015"
down_revision = "20260831_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harness_effect_batches",
        sa.Column("effect_batch_id", sa.String(length=64), nullable=False),
        sa.Column("harness_operation_id", sa.String(length=64), nullable=False),
        sa.Column("max_slots", sa.Integer(), nullable=False),
        sa.Column("sealed_at", sa.String(length=64), nullable=False),
        sa.Column("schema_name", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "schema_name = 'HarnessEffectBatchV1' AND "
            "schema_version = 'harness-effect-batch-v1'",
            name="ck_harness_effect_batch_schema",
        ),
        sa.CheckConstraint(
            "max_slots >= 1 AND max_slots <= 128",
            name="ck_harness_effect_batch_max_slots",
        ),
        sa.ForeignKeyConstraint(
            ["harness_operation_id"],
            ["harness_operation_bindings.harness_operation_id"],
            name="fk_harness_effect_batch_operation",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("effect_batch_id"),
        sa.UniqueConstraint(
            "harness_operation_id",
            name="uq_harness_effect_batch_operation",
        ),
        sa.UniqueConstraint(
            "effect_batch_id",
            "harness_operation_id",
            name="uq_harness_effect_batch_identity",
        ),
    )
    op.create_index(
        "ix_harness_effect_batches_harness_operation_id",
        "harness_effect_batches",
        ["harness_operation_id"],
    )
    op.create_index(
        "ix_harness_effect_batches_created_at",
        "harness_effect_batches",
        ["created_at"],
    )

    op.create_table(
        "harness_effect_journal",
        sa.Column("effect_id", sa.String(length=64), nullable=False),
        sa.Column("effect_batch_id", sa.String(length=64), nullable=False),
        sa.Column("harness_operation_id", sa.String(length=64), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("adapter_name", sa.String(length=160), nullable=False),
        sa.Column("adapter_version", sa.String(length=160), nullable=False),
        sa.Column("boundary_kind", sa.String(length=32), nullable=False),
        sa.Column("prepare_policy", sa.String(length=64), nullable=False),
        sa.Column("commit_policy", sa.String(length=64), nullable=False),
        sa.Column("compensation_policy", sa.String(length=64), nullable=False),
        sa.Column("read_back_policy", sa.String(length=64), nullable=False),
        sa.Column("proposal_contract_name", sa.String(length=160), nullable=False),
        sa.Column("proposal_contract_version", sa.String(length=160), nullable=False),
        sa.Column("proposal_digest", sa.String(length=64), nullable=False),
        sa.Column("target_refs", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("claim_owner", sa.String(length=160), nullable=False),
        sa.Column("claim_count", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.String(length=64), nullable=False),
        sa.Column("commit_started_at", sa.String(length=64), nullable=False),
        sa.Column("read_back_started_at", sa.String(length=64), nullable=False),
        sa.Column("compensation_started_at", sa.String(length=64), nullable=False),
        sa.Column("provider_effect_identity", sa.JSON(), nullable=True),
        sa.Column("terminal_outcome", sa.String(length=32), nullable=True),
        sa.Column("terminal_evidence", sa.JSON(), nullable=True),
        sa.Column("schema_name", sa.String(length=64), nullable=False),
        sa.Column("schema_version", sa.String(length=64), nullable=False),
        sa.Column("prepared_at", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.String(length=64), nullable=False),
        sa.Column("terminal_at", sa.String(length=64), nullable=False),
        sa.CheckConstraint(
            "schema_name = 'HarnessEffectJournalEntryV1' AND "
            "schema_version = 'harness-effect-journal-entry-v1'",
            name="ck_harness_effect_journal_schema",
        ),
        sa.CheckConstraint(
            "slot >= 0 AND slot <= 127",
            name="ck_harness_effect_journal_slot",
        ),
        sa.CheckConstraint(
            "claim_count >= 0 AND claim_count <= 3",
            name="ck_harness_effect_journal_claim_count",
        ),
        sa.CheckConstraint(
            "state IN ('prepared', 'claimed', 'terminal')",
            name="ck_harness_effect_journal_state",
        ),
        sa.CheckConstraint(
            "terminal_outcome IS NULL OR "
            "terminal_outcome IN ('not_committed', 'committed', 'uncertain')",
            name="ck_harness_effect_journal_terminal_outcome",
        ),
        sa.CheckConstraint(
            "(state = 'prepared' AND claim_owner = '' AND lease_expires_at = '' "
            "AND terminal_outcome IS NULL AND terminal_evidence IS NULL) OR "
            "(state = 'claimed' AND claim_owner <> '' AND lease_expires_at <> '' "
            "AND claim_count >= 1 AND terminal_outcome IS NULL AND terminal_evidence IS NULL) OR "
            "(state = 'terminal' AND claim_owner = '' AND lease_expires_at = '' "
            "AND terminal_outcome IS NOT NULL AND terminal_evidence IS NOT NULL)",
            name="ck_harness_effect_journal_state_shape",
        ),
        sa.ForeignKeyConstraint(
            ["effect_batch_id", "harness_operation_id"],
            [
                "harness_effect_batches.effect_batch_id",
                "harness_effect_batches.harness_operation_id",
            ],
            name="fk_harness_effect_journal_batch_identity",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("effect_id"),
        sa.UniqueConstraint(
            "effect_batch_id",
            "slot",
            name="uq_harness_effect_journal_batch_slot",
        ),
        sa.UniqueConstraint(
            "harness_operation_id",
            "slot",
            name="uq_harness_effect_journal_operation_slot",
        ),
    )
    for column in (
        "effect_batch_id",
        "harness_operation_id",
        "state",
        "lease_expires_at",
        "terminal_outcome",
        "prepared_at",
        "updated_at",
        "terminal_at",
    ):
        op.create_index(
            f"ix_harness_effect_journal_{column}",
            "harness_effect_journal",
            [column],
        )
    _create_guards()


def downgrade() -> None:
    _drop_guards()
    for column in reversed(
        (
            "effect_batch_id",
            "harness_operation_id",
            "state",
            "lease_expires_at",
            "terminal_outcome",
            "prepared_at",
            "updated_at",
            "terminal_at",
        )
    ):
        op.drop_index(
            f"ix_harness_effect_journal_{column}",
            table_name="harness_effect_journal",
        )
    op.drop_table("harness_effect_journal")
    op.drop_index(
        "ix_harness_effect_batches_created_at",
        table_name="harness_effect_batches",
    )
    op.drop_index(
        "ix_harness_effect_batches_harness_operation_id",
        table_name="harness_effect_batches",
    )
    op.drop_table("harness_effect_batches")


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_harness_effect_batches_identity_immutable
            BEFORE UPDATE ON harness_effect_batches
            WHEN NOT (
                NEW.effect_batch_id IS OLD.effect_batch_id
                AND NEW.harness_operation_id IS OLD.harness_operation_id
                AND NEW.max_slots IS OLD.max_slots
                AND NEW.schema_name IS OLD.schema_name
                AND NEW.schema_version IS OLD.schema_version
                AND NEW.created_at IS OLD.created_at
                AND (
                    NEW.sealed_at IS OLD.sealed_at
                    OR (OLD.sealed_at = '' AND NEW.sealed_at <> '')
                )
            )
            BEGIN
                SELECT RAISE(ABORT, 'harness_effect_batch_mutation_forbidden');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_harness_effect_batches_no_delete
            BEFORE DELETE ON harness_effect_batches
            BEGIN
                SELECT RAISE(ABORT, 'harness_effect_batch_delete_forbidden');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_harness_effect_journal_identity_immutable
            BEFORE UPDATE ON harness_effect_journal
            WHEN NOT (
                NEW.effect_id IS OLD.effect_id
                AND NEW.effect_batch_id IS OLD.effect_batch_id
                AND NEW.harness_operation_id IS OLD.harness_operation_id
                AND NEW.slot IS OLD.slot
                AND NEW.adapter_name IS OLD.adapter_name
                AND NEW.adapter_version IS OLD.adapter_version
                AND NEW.boundary_kind IS OLD.boundary_kind
                AND NEW.prepare_policy IS OLD.prepare_policy
                AND NEW.commit_policy IS OLD.commit_policy
                AND NEW.compensation_policy IS OLD.compensation_policy
                AND NEW.read_back_policy IS OLD.read_back_policy
                AND NEW.proposal_contract_name IS OLD.proposal_contract_name
                AND NEW.proposal_contract_version IS OLD.proposal_contract_version
                AND NEW.proposal_digest IS OLD.proposal_digest
                AND NEW.target_refs IS OLD.target_refs
                AND NEW.schema_name IS OLD.schema_name
                AND NEW.schema_version IS OLD.schema_version
                AND NEW.prepared_at IS OLD.prepared_at
                AND OLD.state <> 'terminal'
            )
            BEGIN
                SELECT RAISE(ABORT, 'harness_effect_journal_mutation_forbidden');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_harness_effect_journal_no_delete
            BEFORE DELETE ON harness_effect_journal
            BEGIN
                SELECT RAISE(ABORT, 'harness_effect_journal_delete_forbidden');
            END
            """
        )
    elif dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION validate_harness_effect_batch_update()
            RETURNS trigger AS $$
            BEGIN
                IF NEW.effect_batch_id IS DISTINCT FROM OLD.effect_batch_id
                   OR NEW.harness_operation_id IS DISTINCT FROM OLD.harness_operation_id
                   OR NEW.max_slots IS DISTINCT FROM OLD.max_slots
                   OR NEW.schema_name IS DISTINCT FROM OLD.schema_name
                   OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
                   OR NEW.created_at IS DISTINCT FROM OLD.created_at
                   OR NOT (
                       NEW.sealed_at IS NOT DISTINCT FROM OLD.sealed_at
                       OR (OLD.sealed_at = '' AND NEW.sealed_at <> '')
                   ) THEN
                    RAISE EXCEPTION 'harness_effect_batch_mutation_forbidden';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE FUNCTION validate_harness_effect_journal_update()
            RETURNS trigger AS $$
            BEGIN
                IF OLD.state = 'terminal'
                   OR NEW.effect_id IS DISTINCT FROM OLD.effect_id
                   OR NEW.effect_batch_id IS DISTINCT FROM OLD.effect_batch_id
                   OR NEW.harness_operation_id IS DISTINCT FROM OLD.harness_operation_id
                   OR NEW.slot IS DISTINCT FROM OLD.slot
                   OR NEW.adapter_name IS DISTINCT FROM OLD.adapter_name
                   OR NEW.adapter_version IS DISTINCT FROM OLD.adapter_version
                   OR NEW.boundary_kind IS DISTINCT FROM OLD.boundary_kind
                   OR NEW.prepare_policy IS DISTINCT FROM OLD.prepare_policy
                   OR NEW.commit_policy IS DISTINCT FROM OLD.commit_policy
                   OR NEW.compensation_policy IS DISTINCT FROM OLD.compensation_policy
                   OR NEW.read_back_policy IS DISTINCT FROM OLD.read_back_policy
                   OR NEW.proposal_contract_name IS DISTINCT FROM OLD.proposal_contract_name
                   OR NEW.proposal_contract_version IS DISTINCT FROM OLD.proposal_contract_version
                   OR NEW.proposal_digest IS DISTINCT FROM OLD.proposal_digest
                   OR NEW.target_refs IS DISTINCT FROM OLD.target_refs
                   OR NEW.schema_name IS DISTINCT FROM OLD.schema_name
                   OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
                   OR NEW.prepared_at IS DISTINCT FROM OLD.prepared_at THEN
                    RAISE EXCEPTION 'harness_effect_journal_mutation_forbidden';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE FUNCTION reject_harness_effect_delete()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'harness_effect_delete_forbidden';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            "CREATE TRIGGER trg_harness_effect_batches_identity_immutable BEFORE UPDATE "
            "ON harness_effect_batches FOR EACH ROW EXECUTE FUNCTION "
            "validate_harness_effect_batch_update()"
        )
        op.execute(
            "CREATE TRIGGER trg_harness_effect_batches_no_delete BEFORE DELETE "
            "ON harness_effect_batches FOR EACH ROW EXECUTE FUNCTION "
            "reject_harness_effect_delete()"
        )
        op.execute(
            "CREATE TRIGGER trg_harness_effect_journal_identity_immutable BEFORE UPDATE "
            "ON harness_effect_journal FOR EACH ROW EXECUTE FUNCTION "
            "validate_harness_effect_journal_update()"
        )
        op.execute(
            "CREATE TRIGGER trg_harness_effect_journal_no_delete BEFORE DELETE "
            "ON harness_effect_journal FOR EACH ROW EXECUTE FUNCTION "
            "reject_harness_effect_delete()"
        )


def _drop_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for name in (
            "trg_harness_effect_batches_identity_immutable",
            "trg_harness_effect_batches_no_delete",
            "trg_harness_effect_journal_identity_immutable",
            "trg_harness_effect_journal_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {name}")
    elif dialect == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_harness_effect_batches_identity_immutable "
            "ON harness_effect_batches"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_harness_effect_batches_no_delete "
            "ON harness_effect_batches"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_harness_effect_journal_identity_immutable "
            "ON harness_effect_journal"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_harness_effect_journal_no_delete "
            "ON harness_effect_journal"
        )
        op.execute("DROP FUNCTION IF EXISTS validate_harness_effect_batch_update()")
        op.execute("DROP FUNCTION IF EXISTS validate_harness_effect_journal_update()")
        op.execute("DROP FUNCTION IF EXISTS reject_harness_effect_delete()")
