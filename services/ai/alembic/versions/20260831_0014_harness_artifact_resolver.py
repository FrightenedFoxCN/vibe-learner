"""add durable protected Harness artifact resolver

Revision ID: 20260831_0014
Revises: 20260825_0013
Create Date: 2026-08-31 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260831_0014"
down_revision = "20260825_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "harness_artifact_principals",
        sa.Column("installation_slot", sa.String(64), primary_key=True),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("schema_name", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.UniqueConstraint("principal_id", name="uq_harness_artifact_principal_id"),
        sa.CheckConstraint(
            "schema_name = 'HarnessArtifactPrincipal' AND "
            "schema_version = 'harness-artifact-principal-v1'",
            name="ck_harness_artifact_principal_schema",
        ),
    )
    op.create_index("ix_harness_artifact_principals_principal_id", "harness_artifact_principals", ["principal_id"])
    op.create_table(
        "harness_artifact_contracts",
        sa.Column("contract_name", sa.String(160), primary_key=True),
        sa.Column("contract_version", sa.String(160), primary_key=True),
        sa.Column("schema_name", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("registered_at", sa.String(64), nullable=False),
        sa.CheckConstraint("schema_name = 'HarnessArtifactContractRegistrationV1' AND schema_version = 'harness-artifact-contract-registration-v1'", name="ck_harness_artifact_contract_schema"),
    )
    op.create_table(
        "harness_artifacts",
        sa.Column("artifact_id", sa.String(64), primary_key=True),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("contract_name", sa.String(160), nullable=False),
        sa.Column("contract_version", sa.String(160), nullable=False),
        sa.Column("digest_algorithm", sa.String(32), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("expires_at", sa.String(64), nullable=True),
        sa.Column("deleted_at", sa.String(64), nullable=True),
        sa.Column("registered_principal_id", sa.String(64), nullable=False),
        sa.Column("schema_name", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("registered_at", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["registered_principal_id"], ["harness_artifact_principals.principal_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["contract_name", "contract_version"],
            [
                "harness_artifact_contracts.contract_name",
                "harness_artifact_contracts.contract_version",
            ],
            name="fk_harness_artifact_contract",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("schema_name = 'HarnessArtifactRegistrationV1' AND schema_version = 'harness-artifact-registration-v1'", name="ck_harness_artifact_schema"),
    )
    op.create_index("ix_harness_artifacts_artifact_type", "harness_artifacts", ["artifact_type"])
    op.create_index("ix_harness_artifacts_expires_at", "harness_artifacts", ["expires_at"])
    op.create_index("ix_harness_artifacts_deleted_at", "harness_artifacts", ["deleted_at"])
    op.create_index("ix_harness_artifacts_registered_at", "harness_artifacts", ["registered_at"])
    op.create_table(
        "harness_artifact_grants",
        sa.Column("grant_id", sa.String(64), primary_key=True),
        sa.Column("harness_operation_id", sa.String(64), nullable=False),
        sa.Column("principal_id", sa.String(64), nullable=False),
        sa.Column("issued_at", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.String(64), nullable=False),
        sa.Column("revoked_at", sa.String(64), nullable=True),
        sa.Column("schema_name", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["harness_operation_id"], ["harness_operation_bindings.harness_operation_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["principal_id"], ["harness_artifact_principals.principal_id"], ondelete="RESTRICT"),
        sa.CheckConstraint("schema_name = 'HarnessArtifactGrant' AND schema_version = 'harness-artifact-grant-v1'", name="ck_harness_artifact_grant_schema"),
    )
    op.create_index("ix_harness_artifact_grants_harness_operation_id", "harness_artifact_grants", ["harness_operation_id"])
    op.create_index("ix_harness_artifact_grants_principal_id", "harness_artifact_grants", ["principal_id"])
    op.create_index("ix_harness_artifact_grants_expires_at", "harness_artifact_grants", ["expires_at"])
    op.create_table(
        "harness_artifact_grant_scopes",
        sa.Column("scope_id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("grant_id", sa.String(64), nullable=False),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("contract_name", sa.String(160), nullable=False),
        sa.Column("contract_version", sa.String(160), nullable=False),
        sa.Column("permission", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["grant_id"], ["harness_artifact_grants.grant_id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("grant_id", "artifact_id", "permission", name="uq_harness_artifact_grant_scope"),
    )
    op.create_index("ix_harness_artifact_grant_scopes_grant_id", "harness_artifact_grant_scopes", ["grant_id"])
    op.create_index("ix_harness_artifact_grant_scopes_artifact_id", "harness_artifact_grant_scopes", ["artifact_id"])
    op.create_table(
        "harness_artifact_access_audits",
        sa.Column("audit_id", sa.String(64), primary_key=True),
        sa.Column("grant_id", sa.String(64), nullable=False),
        sa.Column("harness_operation_id", sa.String(64), nullable=False),
        sa.Column("grant_harness_operation_id", sa.String(64), nullable=True),
        sa.Column("presented_principal_id", sa.String(64), nullable=True),
        sa.Column("grant_subject_id", sa.String(64), nullable=True),
        sa.Column("artifact_id", sa.String(64), nullable=False),
        sa.Column("artifact_type", sa.String(64), nullable=False),
        sa.Column("contract_name", sa.String(160), nullable=False),
        sa.Column("contract_version", sa.String(160), nullable=False),
        sa.Column("permission", sa.String(32), nullable=False),
        sa.Column("authorization_outcome", sa.String(32), nullable=True),
        sa.Column("resolution_status", sa.String(32), nullable=False),
        sa.Column("schema_name", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(64), nullable=False),
        sa.Column("evaluated_at", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "schema_name = 'HarnessArtifactResolutionAuditV1' AND "
            "schema_version = 'harness-artifact-resolution-audit-v1'",
            name="ck_harness_artifact_resolution_audit_schema",
        ),
    )
    for column in (
        "grant_id",
        "harness_operation_id",
        "artifact_id",
        "authorization_outcome",
        "resolution_status",
        "evaluated_at",
    ):
        op.create_index(f"ix_harness_artifact_access_audits_{column}", "harness_artifact_access_audits", [column])
    _create_immutability_guards()


def downgrade() -> None:
    _drop_immutability_guards()
    op.drop_table("harness_artifact_access_audits")
    op.drop_table("harness_artifact_grant_scopes")
    op.drop_table("harness_artifact_grants")
    op.drop_table("harness_artifacts")
    op.drop_table("harness_artifact_contracts")
    op.drop_table("harness_artifact_principals")


def _create_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(_SQLITE_ARTIFACT_UPDATE_GUARD)
        op.execute(_SQLITE_ARTIFACT_DELETE_GUARD)
        for table_name in (
            "harness_artifact_principals",
            "harness_artifact_contracts",
            "harness_artifact_grant_scopes",
            "harness_artifact_access_audits",
        ):
            op.execute(_sqlite_append_only_guard(table_name, "update"))
            op.execute(_sqlite_append_only_guard(table_name, "delete"))
        op.execute(_SQLITE_GRANT_UPDATE_GUARD)
        op.execute(_sqlite_append_only_guard("harness_artifact_grants", "delete"))
    elif dialect == "postgresql":
        op.execute(_POSTGRES_STATIC_MUTATION_FUNCTION)
        op.execute(_POSTGRES_ARTIFACT_UPDATE_FUNCTION)
        op.execute(_POSTGRES_GRANT_UPDATE_FUNCTION)
        op.execute(
            "CREATE TRIGGER trg_harness_artifacts_immutable_update BEFORE UPDATE "
            "ON harness_artifacts FOR EACH ROW EXECUTE FUNCTION "
            "validate_harness_artifact_soft_delete()"
        )
        op.execute(
            "CREATE TRIGGER trg_harness_artifacts_no_delete BEFORE DELETE "
            "ON harness_artifacts FOR EACH ROW EXECUTE FUNCTION "
            "reject_harness_artifact_static_mutation()"
        )
        for table_name in (
            "harness_artifact_principals",
            "harness_artifact_contracts",
            "harness_artifact_grant_scopes",
            "harness_artifact_access_audits",
        ):
            op.execute(
                f"CREATE TRIGGER trg_{table_name}_append_only BEFORE UPDATE OR DELETE "
                f"ON {table_name} FOR EACH ROW EXECUTE FUNCTION "
                "reject_harness_artifact_static_mutation()"
            )
        op.execute(
            "CREATE TRIGGER trg_harness_artifact_grants_revocation_only BEFORE UPDATE "
            "ON harness_artifact_grants FOR EACH ROW EXECUTE FUNCTION "
            "validate_harness_artifact_grant_revocation()"
        )
        op.execute(
            "CREATE TRIGGER trg_harness_artifact_grants_no_delete BEFORE DELETE "
            "ON harness_artifact_grants FOR EACH ROW EXECUTE FUNCTION "
            "reject_harness_artifact_static_mutation()"
        )


def _drop_immutability_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifacts_immutable_update")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifacts_no_delete")
        for table_name in (
            "harness_artifact_principals",
            "harness_artifact_contracts",
            "harness_artifact_grant_scopes",
            "harness_artifact_access_audits",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_update")
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_no_delete")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifact_grants_revocation_only")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifact_grants_no_delete")
    elif dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifacts_immutable_update ON harness_artifacts")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifacts_no_delete ON harness_artifacts")
        for table_name in (
            "harness_artifact_principals",
            "harness_artifact_contracts",
            "harness_artifact_grant_scopes",
            "harness_artifact_access_audits",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_append_only ON {table_name}")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifact_grants_revocation_only ON harness_artifact_grants")
        op.execute("DROP TRIGGER IF EXISTS trg_harness_artifact_grants_no_delete ON harness_artifact_grants")
        op.execute("DROP FUNCTION IF EXISTS validate_harness_artifact_soft_delete()")
        op.execute("DROP FUNCTION IF EXISTS validate_harness_artifact_grant_revocation()")
        op.execute("DROP FUNCTION IF EXISTS reject_harness_artifact_static_mutation()")


def _sqlite_append_only_guard(table_name: str, operation: str) -> str:
    return f"""
        CREATE TRIGGER trg_{table_name}_no_{operation}
        BEFORE {operation.upper()} ON {table_name}
        BEGIN
            SELECT RAISE(ABORT, 'harness_artifact_{table_name}_{operation}_forbidden');
        END
    """


_SQLITE_ARTIFACT_UPDATE_GUARD = """
    CREATE TRIGGER trg_harness_artifacts_immutable_update
    BEFORE UPDATE ON harness_artifacts
    WHEN NOT (
        OLD.deleted_at IS NULL
        AND NEW.deleted_at IS NOT NULL
        AND length(NEW.payload) = 0
        AND NEW.artifact_id IS OLD.artifact_id
        AND NEW.artifact_type IS OLD.artifact_type
        AND NEW.contract_name IS OLD.contract_name
        AND NEW.contract_version IS OLD.contract_version
        AND NEW.digest_algorithm IS OLD.digest_algorithm
        AND NEW.payload_digest IS OLD.payload_digest
        AND NEW.expires_at IS OLD.expires_at
        AND NEW.registered_principal_id IS OLD.registered_principal_id
        AND NEW.schema_name IS OLD.schema_name
        AND NEW.schema_version IS OLD.schema_version
        AND NEW.registered_at IS OLD.registered_at
    )
    BEGIN
        SELECT RAISE(ABORT, 'harness_artifact_mutation_forbidden');
    END
"""

_SQLITE_ARTIFACT_DELETE_GUARD = _sqlite_append_only_guard(
    "harness_artifacts",
    "delete",
)

_SQLITE_GRANT_UPDATE_GUARD = """
    CREATE TRIGGER trg_harness_artifact_grants_revocation_only
    BEFORE UPDATE ON harness_artifact_grants
    WHEN NOT (
        OLD.revoked_at IS NULL
        AND NEW.revoked_at IS NOT NULL
        AND NEW.grant_id IS OLD.grant_id
        AND NEW.harness_operation_id IS OLD.harness_operation_id
        AND NEW.principal_id IS OLD.principal_id
        AND NEW.issued_at IS OLD.issued_at
        AND NEW.expires_at IS OLD.expires_at
        AND NEW.schema_name IS OLD.schema_name
        AND NEW.schema_version IS OLD.schema_version
    )
    BEGIN
        SELECT RAISE(ABORT, 'harness_artifact_grant_mutation_forbidden');
    END
"""

_POSTGRES_STATIC_MUTATION_FUNCTION = """
    CREATE FUNCTION reject_harness_artifact_static_mutation()
    RETURNS trigger AS $$
    BEGIN
        RAISE EXCEPTION 'harness_artifact_%_%_forbidden', TG_TABLE_NAME, lower(TG_OP);
    END;
    $$ LANGUAGE plpgsql
"""

_POSTGRES_ARTIFACT_UPDATE_FUNCTION = """
    CREATE FUNCTION validate_harness_artifact_soft_delete()
    RETURNS trigger AS $$
    BEGIN
        IF OLD.deleted_at IS NULL
            AND NEW.deleted_at IS NOT NULL
            AND octet_length(NEW.payload) = 0
            AND NEW.artifact_id IS NOT DISTINCT FROM OLD.artifact_id
            AND NEW.artifact_type IS NOT DISTINCT FROM OLD.artifact_type
            AND NEW.contract_name IS NOT DISTINCT FROM OLD.contract_name
            AND NEW.contract_version IS NOT DISTINCT FROM OLD.contract_version
            AND NEW.digest_algorithm IS NOT DISTINCT FROM OLD.digest_algorithm
            AND NEW.payload_digest IS NOT DISTINCT FROM OLD.payload_digest
            AND NEW.expires_at IS NOT DISTINCT FROM OLD.expires_at
            AND NEW.registered_principal_id IS NOT DISTINCT FROM OLD.registered_principal_id
            AND NEW.schema_name IS NOT DISTINCT FROM OLD.schema_name
            AND NEW.schema_version IS NOT DISTINCT FROM OLD.schema_version
            AND NEW.registered_at IS NOT DISTINCT FROM OLD.registered_at
        THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'harness_artifact_mutation_forbidden';
    END;
    $$ LANGUAGE plpgsql
"""

_POSTGRES_GRANT_UPDATE_FUNCTION = """
    CREATE FUNCTION validate_harness_artifact_grant_revocation()
    RETURNS trigger AS $$
    BEGIN
        IF OLD.revoked_at IS NULL
            AND NEW.revoked_at IS NOT NULL
            AND NEW.grant_id IS NOT DISTINCT FROM OLD.grant_id
            AND NEW.harness_operation_id IS NOT DISTINCT FROM OLD.harness_operation_id
            AND NEW.principal_id IS NOT DISTINCT FROM OLD.principal_id
            AND NEW.issued_at IS NOT DISTINCT FROM OLD.issued_at
            AND NEW.expires_at IS NOT DISTINCT FROM OLD.expires_at
            AND NEW.schema_name IS NOT DISTINCT FROM OLD.schema_name
            AND NEW.schema_version IS NOT DISTINCT FROM OLD.schema_version
        THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'harness_artifact_grant_mutation_forbidden';
    END;
    $$ LANGUAGE plpgsql
"""
