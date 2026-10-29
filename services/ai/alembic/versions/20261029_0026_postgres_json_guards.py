"""Compare immutable JSON fields through PostgreSQL's JSONB equality operator."""

from alembic import op

revision = "20261029_0026"
down_revision = "20261029_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    # Historical Alembic tables use JSON, while metadata-created tables can use
    # JSONB. Explicit casts support both without rewriting any stored payload,
    # canonical digest or application-owned immutable field set.
    op.execute("""
        CREATE OR REPLACE FUNCTION validate_harness_runtime_update()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.state = 'terminal' OR NEW.trace_id IS DISTINCT FROM OLD.trace_id
            OR NEW.trace_slot IS DISTINCT FROM OLD.trace_slot OR NEW.harness_operation_id IS DISTINCT FROM OLD.harness_operation_id
            OR NEW.parent_trace_id IS DISTINCT FROM OLD.parent_trace_id OR NEW.workflow IS DISTINCT FROM OLD.workflow
            OR NEW.stage IS DISTINCT FROM OLD.stage OR NEW.adapter_contract_name IS DISTINCT FROM OLD.adapter_contract_name
            OR NEW.adapter_contract_version IS DISTINCT FROM OLD.adapter_contract_version
            OR NEW.trace_contract_name IS DISTINCT FROM OLD.trace_contract_name OR NEW.trace_contract_version IS DISTINCT FROM OLD.trace_contract_version
            OR NEW.context_payload::jsonb IS DISTINCT FROM OLD.context_payload::jsonb OR NEW.context_digest IS DISTINCT FROM OLD.context_digest
            OR NEW.schema_name IS DISTINCT FROM OLD.schema_name OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
            OR NEW.created_at IS DISTINCT FROM OLD.created_at
            THEN RAISE EXCEPTION 'harness_runtime_identity_mutation_forbidden'; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION validate_harness_effect_journal_update()
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
               OR NEW.target_refs::jsonb IS DISTINCT FROM OLD.target_refs::jsonb
               OR NEW.schema_name IS DISTINCT FROM OLD.schema_name
               OR NEW.schema_version IS DISTINCT FROM OLD.schema_version
               OR NEW.prepared_at IS DISTINCT FROM OLD.prepared_at
            THEN RAISE EXCEPTION 'harness_effect_journal_mutation_forbidden'; END IF;
            RETURN NEW;
        END; $$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    # This comparison repair is read-compatible with the previous schema and
    # preserves its exact immutable field set. Keep it on downgrade rather than
    # reintroducing an unusable JSON equality operator.
    pass
