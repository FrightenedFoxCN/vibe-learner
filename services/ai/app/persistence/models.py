from __future__ import annotations

from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    desc,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


JSON_PAYLOAD = JSON().with_variant(JSONB, "postgresql")
NULLABLE_JSON_PAYLOAD = JSON(none_as_null=True).with_variant(
    JSONB(none_as_null=True),
    "postgresql",
)


class Base(DeclarativeBase):
    pass


class HarnessOperationBindingRow(Base):
    __tablename__ = "harness_operation_bindings"
    __table_args__ = (
        UniqueConstraint(
            "domain_operation_kind",
            "domain_operation_id",
            name="uq_harness_operation_binding_domain_identity",
        ),
        CheckConstraint(
            "schema_name = 'HarnessOperationBindingV1' AND "
            "schema_version = 'harness-operation-binding-v1'",
            name="ck_harness_operation_binding_schema",
        ),
        CheckConstraint(
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
        CheckConstraint(
            "parent_harness_operation_id IS NULL OR "
            "parent_harness_operation_id <> harness_operation_id",
            name="ck_harness_operation_binding_parent_not_self",
        ),
        CheckConstraint(
            "parent_harness_operation_id IS NULL OR "
            "domain_operation_kind = 'tavern_run'",
            name="ck_harness_operation_binding_parent_kind",
        ),
    )

    harness_operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    domain_operation_kind: Mapped[str] = mapped_column(String(64))
    domain_operation_id: Mapped[str] = mapped_column(String(160))
    workflow: Mapped[str] = mapped_column(String(64))
    entry_stage: Mapped[str] = mapped_column(String(64))
    parent_harness_operation_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "harness_operation_bindings.harness_operation_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
        index=True,
    )
    admitted_at: Mapped[str] = mapped_column(String(64), index=True)


class HarnessArtifactPrincipalRow(Base):
    """The one server-owned principal for a local installation."""

    __tablename__ = "harness_artifact_principals"
    __table_args__ = (
        UniqueConstraint("principal_id", name="uq_harness_artifact_principal_id"),
        CheckConstraint(
            "schema_name = 'HarnessArtifactPrincipal' AND "
            "schema_version = 'harness-artifact-principal-v1'",
            name="ck_harness_artifact_principal_schema",
        ),
    )

    installation_slot: Mapped[str] = mapped_column(String(64), primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(64), index=True)
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(64))


class HarnessArtifactContractRow(Base):
    __tablename__ = "harness_artifact_contracts"
    __table_args__ = (
        CheckConstraint(
            "schema_name = 'HarnessArtifactContractRegistrationV1' AND "
            "schema_version = 'harness-artifact-contract-registration-v1'",
            name="ck_harness_artifact_contract_schema",
        ),
    )

    contract_name: Mapped[str] = mapped_column(String(160), primary_key=True)
    contract_version: Mapped[str] = mapped_column(String(160), primary_key=True)
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    registered_at: Mapped[str] = mapped_column(String(64))


class HarnessArtifactRow(Base):
    __tablename__ = "harness_artifacts"
    __table_args__ = (
        CheckConstraint(
            "schema_name = 'HarnessArtifactRegistrationV1' AND "
            "schema_version = 'harness-artifact-registration-v1'",
            name="ck_harness_artifact_schema",
        ),
        ForeignKeyConstraint(
            ["contract_name", "contract_version"],
            [
                "harness_artifact_contracts.contract_name",
                "harness_artifact_contracts.contract_version",
            ],
            name="fk_harness_artifact_contract",
            ondelete="RESTRICT",
        ),
    )

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_type: Mapped[str] = mapped_column(String(64), index=True)
    contract_name: Mapped[str] = mapped_column(String(160))
    contract_version: Mapped[str] = mapped_column(String(160))
    digest_algorithm: Mapped[str] = mapped_column(String(32))
    payload_digest: Mapped[str] = mapped_column(String(64))
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    deleted_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    registered_principal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("harness_artifact_principals.principal_id", ondelete="RESTRICT")
    )
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    registered_at: Mapped[str] = mapped_column(String(64), index=True)


class HarnessArtifactGrantRow(Base):
    __tablename__ = "harness_artifact_grants"
    __table_args__ = (
        CheckConstraint(
            "schema_name = 'HarnessArtifactGrant' AND "
            "schema_version = 'harness-artifact-grant-v1'",
            name="ck_harness_artifact_grant_schema",
        ),
    )

    grant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    harness_operation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("harness_operation_bindings.harness_operation_id", ondelete="RESTRICT"), index=True
    )
    principal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("harness_artifact_principals.principal_id", ondelete="RESTRICT"), index=True
    )
    issued_at: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[str] = mapped_column(String(64), index=True)
    revoked_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))


class HarnessArtifactGrantScopeRow(Base):
    __tablename__ = "harness_artifact_grant_scopes"
    __table_args__ = (
        UniqueConstraint("grant_id", "artifact_id", "permission", name="uq_harness_artifact_grant_scope"),
    )

    scope_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("harness_artifact_grants.grant_id", ondelete="RESTRICT"), index=True
    )
    # Keep a durable scope/audit reference after retention deletes content.
    artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64))
    contract_name: Mapped[str] = mapped_column(String(160))
    contract_version: Mapped[str] = mapped_column(String(160))
    permission: Mapped[str] = mapped_column(String(32))


class HarnessArtifactAccessAuditRow(Base):
    __tablename__ = "harness_artifact_access_audits"

    __table_args__ = (
        CheckConstraint(
            "schema_name = 'HarnessArtifactResolutionAuditV1' AND "
            "schema_version = 'harness-artifact-resolution-audit-v1'",
            name="ck_harness_artifact_resolution_audit_schema",
        ),
    )

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    grant_id: Mapped[str] = mapped_column(String(64), index=True)
    harness_operation_id: Mapped[str] = mapped_column(String(64), index=True)
    grant_harness_operation_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    presented_principal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    grant_subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    artifact_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(64))
    contract_name: Mapped[str] = mapped_column(String(160))
    contract_version: Mapped[str] = mapped_column(String(160))
    permission: Mapped[str] = mapped_column(String(32))
    authorization_outcome: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )
    resolution_status: Mapped[str] = mapped_column(String(32), index=True)
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    evaluated_at: Mapped[str] = mapped_column(String(64), index=True)


class HarnessEffectBatchRow(Base):
    __tablename__ = "harness_effect_batches"
    __table_args__ = (
        UniqueConstraint(
            "harness_operation_id",
            name="uq_harness_effect_batch_operation",
        ),
        UniqueConstraint(
            "effect_batch_id",
            "harness_operation_id",
            name="uq_harness_effect_batch_identity",
        ),
        CheckConstraint(
            "schema_name = 'HarnessEffectBatchV1' AND "
            "schema_version = 'harness-effect-batch-v1'",
            name="ck_harness_effect_batch_schema",
        ),
        CheckConstraint(
            "max_slots >= 1 AND max_slots <= 128",
            name="ck_harness_effect_batch_max_slots",
        ),
    )

    effect_batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    harness_operation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "harness_operation_bindings.harness_operation_id",
            ondelete="RESTRICT",
        ),
        index=True,
    )
    max_slots: Mapped[int] = mapped_column(Integer, default=128)
    sealed_at: Mapped[str] = mapped_column(String(64), default="")
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(64), index=True)


class HarnessEffectJournalRow(Base):
    __tablename__ = "harness_effect_journal"
    __table_args__ = (
        UniqueConstraint(
            "effect_batch_id",
            "slot",
            name="uq_harness_effect_journal_batch_slot",
        ),
        UniqueConstraint(
            "harness_operation_id",
            "slot",
            name="uq_harness_effect_journal_operation_slot",
        ),
        ForeignKeyConstraint(
            ["effect_batch_id", "harness_operation_id"],
            [
                "harness_effect_batches.effect_batch_id",
                "harness_effect_batches.harness_operation_id",
            ],
            name="fk_harness_effect_journal_batch_identity",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "schema_name = 'HarnessEffectJournalEntryV1' AND "
            "schema_version = 'harness-effect-journal-entry-v1'",
            name="ck_harness_effect_journal_schema",
        ),
        CheckConstraint(
            "slot >= 0 AND slot <= 127",
            name="ck_harness_effect_journal_slot",
        ),
        CheckConstraint(
            "claim_count >= 0 AND claim_count <= 3",
            name="ck_harness_effect_journal_claim_count",
        ),
        CheckConstraint(
            "state IN ('prepared', 'claimed', 'terminal')",
            name="ck_harness_effect_journal_state",
        ),
        CheckConstraint(
            "terminal_outcome IS NULL OR "
            "terminal_outcome IN ('not_committed', 'committed', 'uncertain')",
            name="ck_harness_effect_journal_terminal_outcome",
        ),
        CheckConstraint(
            "(state = 'prepared' AND claim_owner = '' AND lease_expires_at = '' "
            "AND terminal_outcome IS NULL AND terminal_evidence IS NULL) OR "
            "(state = 'claimed' AND claim_owner <> '' AND lease_expires_at <> '' "
            "AND claim_count >= 1 AND terminal_outcome IS NULL AND terminal_evidence IS NULL) OR "
            "(state = 'terminal' AND claim_owner = '' AND lease_expires_at = '' "
            "AND terminal_outcome IS NOT NULL AND terminal_evidence IS NOT NULL)",
            name="ck_harness_effect_journal_state_shape",
        ),
    )

    effect_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    effect_batch_id: Mapped[str] = mapped_column(String(64), index=True)
    harness_operation_id: Mapped[str] = mapped_column(String(64), index=True)
    slot: Mapped[int] = mapped_column(Integer)
    adapter_name: Mapped[str] = mapped_column(String(160))
    adapter_version: Mapped[str] = mapped_column(String(160))
    boundary_kind: Mapped[str] = mapped_column(String(32))
    prepare_policy: Mapped[str] = mapped_column(String(64))
    commit_policy: Mapped[str] = mapped_column(String(64))
    compensation_policy: Mapped[str] = mapped_column(String(64))
    read_back_policy: Mapped[str] = mapped_column(String(64))
    proposal_contract_name: Mapped[str] = mapped_column(String(160))
    proposal_contract_version: Mapped[str] = mapped_column(String(160))
    proposal_digest: Mapped[str] = mapped_column(String(64))
    target_refs: Mapped[list[dict[str, Any]]] = mapped_column(JSON_PAYLOAD)
    state: Mapped[str] = mapped_column(String(32), index=True)
    claim_owner: Mapped[str] = mapped_column(String(160), default="")
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[str] = mapped_column(String(64), default="", index=True)
    commit_started_at: Mapped[str] = mapped_column(String(64), default="")
    read_back_started_at: Mapped[str] = mapped_column(String(64), default="")
    compensation_started_at: Mapped[str] = mapped_column(String(64), default="")
    provider_effect_identity: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD,
        nullable=True,
    )
    terminal_outcome: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        index=True,
    )
    terminal_evidence: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD,
        nullable=True,
    )
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    prepared_at: Mapped[str] = mapped_column(String(64), index=True)
    updated_at: Mapped[str] = mapped_column(String(64), index=True)
    terminal_at: Mapped[str] = mapped_column(String(64), default="", index=True)


class HarnessRuntimeExecutionRow(Base):
    __tablename__ = "harness_runtime_executions"
    __table_args__ = (
        UniqueConstraint(
            "harness_operation_id",
            "stage",
            "trace_slot",
            name="uq_harness_runtime_operation_stage_slot",
        ),
        CheckConstraint(
            "schema_name = 'HarnessRuntimeExecution' AND "
            "schema_version = 'harness-runtime-execution-v1'",
            name="ck_harness_runtime_schema",
        ),
        CheckConstraint(
            "trace_slot >= 0 AND trace_slot <= 127",
            name="ck_harness_runtime_trace_slot",
        ),
        CheckConstraint(
            "claim_count >= 0 AND claim_count <= 3",
            name="ck_harness_runtime_claim_count",
        ),
        CheckConstraint(
            "state IN ('prepared', 'claimed', 'terminal')",
            name="ck_harness_runtime_state",
        ),
        CheckConstraint(
            "(state = 'prepared' AND claim_owner = '' AND claim_token = '' "
            "AND lease_expires_at = '' AND terminal_trace IS NULL) OR "
            "(state = 'claimed' AND claim_owner <> '' AND claim_token <> '' "
            "AND lease_expires_at <> '' AND claim_count >= 1 "
            "AND terminal_trace IS NULL) OR "
            "(state = 'terminal' AND claim_owner = '' AND claim_token = '' "
            "AND lease_expires_at = '' AND terminal_trace IS NOT NULL)",
            name="ck_harness_runtime_state_shape",
        ),
    )

    trace_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    trace_slot: Mapped[int] = mapped_column(Integer)
    harness_operation_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(
            "harness_operation_bindings.harness_operation_id",
            ondelete="RESTRICT",
        ),
        index=True,
    )
    parent_trace_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("harness_runtime_executions.trace_id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    workflow: Mapped[str] = mapped_column(String(64))
    stage: Mapped[str] = mapped_column(String(64), index=True)
    adapter_contract_name: Mapped[str] = mapped_column(String(160))
    adapter_contract_version: Mapped[str] = mapped_column(String(160))
    trace_contract_name: Mapped[str] = mapped_column(String(160))
    trace_contract_version: Mapped[str] = mapped_column(String(160))
    context_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    context_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), index=True)
    claim_owner: Mapped[str] = mapped_column(String(160), default="")
    claim_token: Mapped[str] = mapped_column(String(64), default="")
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[str] = mapped_column(String(64), default="", index=True)
    execution_started_at: Mapped[str] = mapped_column(String(64), default="")
    attempt_records: Mapped[list[dict[str, Any]]] = mapped_column(JSON_PAYLOAD)
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSON_PAYLOAD)
    terminal_trace: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD,
        nullable=True,
    )
    terminal_trace_digest: Mapped[str] = mapped_column(String(64), default="")
    schema_name: Mapped[str] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(64), index=True)
    updated_at: Mapped[str] = mapped_column(String(64), index=True)


class DocumentRow(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="")
    original_filename: Mapped[str] = mapped_column(Text, default="")
    stored_path: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    ocr_status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class DocumentProcessOperationRow(Base):
    __tablename__ = "document_process_operations"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "active_slot",
            name="uq_document_process_operation_active_slot",
        ),
        UniqueConstraint(
            "harness_operation_id",
            name="uq_document_process_operation_harness_operation",
        ),
        CheckConstraint(
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
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    harness_operation_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "harness_operation_bindings.harness_operation_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    document_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        index=True,
    )
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    status: Mapped[str] = mapped_column(String(32), index=True)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    projection_state: Mapped[str] = mapped_column(String(32))
    base_document_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    document_digest: Mapped[str] = mapped_column(String(64), default="")
    debug_digest: Mapped[str] = mapped_column(String(64), default="")
    commit_contract_version: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(64), index=True)
    completed_at: Mapped[str] = mapped_column(String(64), default="")


class LearningPlanOperationRow(Base):
    __tablename__ = "learning_plan_operations"
    __table_args__ = (
        UniqueConstraint(
            "client_request_id",
            name="uq_learning_plan_operation_client_request",
        ),
        UniqueConstraint(
            "scope_key",
            "active_slot",
            name="uq_learning_plan_operation_active_scope",
        ),
        UniqueConstraint(
            "harness_operation_id",
            name="uq_learning_plan_operation_harness_operation",
        ),
        CheckConstraint(
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
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    harness_operation_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "harness_operation_bindings.harness_operation_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    client_request_id: Mapped[str] = mapped_column(String(80))
    scope_key: Mapped[str] = mapped_column(String(160))
    document_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    persona_id: Mapped[str] = mapped_column(String(64), index=True)
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    base_document_updated_at: Mapped[str] = mapped_column(String(64), default="")
    base_document_digest: Mapped[str] = mapped_column(String(64), default="")
    base_debug_digest: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), index=True)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    projection_state: Mapped[str] = mapped_column(String(32))
    provider_started_at: Mapped[str] = mapped_column(String(64), default="")
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    commit_contract_version: Mapped[str] = mapped_column(String(64), default="")
    committed_projection_digest: Mapped[str] = mapped_column(String(64), default="")
    committed_projection_payload: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD,
        nullable=True,
    )
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(64), index=True)
    completed_at: Mapped[str] = mapped_column(String(64), default="")


class LearningPlanRow(Base):
    __tablename__ = "learning_plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    creation_mode: Mapped[str] = mapped_column(String(32), default="document")
    course_title: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class StudySessionRow(Base):
    __tablename__ = "study_sessions"
    __mapper_args__ = {"confirm_deleted_rows": False}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    plan_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    study_unit_id: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    last_turn_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class StudyQuestionAttemptRow(Base):
    __tablename__ = "study_question_attempts"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "client_attempt_id",
            name="uq_study_question_attempt_request",
        ),
        UniqueConstraint(
            "session_id",
            "turn_id",
            name="uq_study_question_attempt_turn",
        ),
        CheckConstraint(
            "committed_session_revision = before_session_revision + 1",
            name="ck_study_question_attempt_revision",
        ),
    )

    attempt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("study_sessions.id", ondelete="RESTRICT"),
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(String(64), index=True)
    client_attempt_id: Mapped[str] = mapped_column(String(80))
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    response_schema_version: Mapped[str] = mapped_column(String(64))
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    response_digest: Mapped[str] = mapped_column(String(64))
    before_session_revision: Mapped[int] = mapped_column(Integer)
    committed_session_revision: Mapped[int] = mapped_column(Integer)
    committed_at: Mapped[str] = mapped_column(String(64))


class StudyChatOperationRow(Base):
    __tablename__ = "study_chat_operations"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "client_request_id",
            name="uq_study_chat_operation_request",
        ),
        UniqueConstraint(
            "session_id",
            "active_slot",
            name="uq_study_chat_operation_active_slot",
        ),
        UniqueConstraint("committed_turn_id", name="uq_study_chat_operation_turn"),
        UniqueConstraint(
            "harness_operation_id",
            name="uq_study_chat_operation_harness_operation",
        ),
        CheckConstraint("claim_count IN (0, 1)", name="ck_study_chat_operation_claim_count"),
        CheckConstraint(
            "(status IN ('admitted', 'running') AND active_slot = 1) OR "
            "(status IN ('committed', 'not_committed', 'uncertain') AND active_slot IS NULL)",
            name="ck_study_chat_operation_active_status",
        ),
        CheckConstraint(
            "(status IN ('admitted', 'not_committed') AND claim_count = 0 "
            "AND execution_token = '' AND execution_started_at = '' "
            "AND provider_started_at = '' AND execution_deadline_at = '' AND heartbeat_at = '') OR "
            "(status IN ('running', 'committed', 'uncertain') AND claim_count = 1 "
            "AND execution_token <> '' AND execution_started_at <> '' AND execution_deadline_at <> '')",
            name="ck_study_chat_operation_execution_evidence",
        ),
        CheckConstraint(
            "(status = 'committed' AND committed_session_revision IS NOT NULL "
            "AND committed_turn_id IS NOT NULL AND committed_turn_sequence IS NOT NULL "
            "AND response_schema_version <> '' AND response_payload IS NOT NULL "
            "AND response_digest <> '' AND error_code = '' AND completed_at <> '') OR "
            "(status <> 'committed' AND committed_session_revision IS NULL "
            "AND committed_turn_id IS NULL AND committed_turn_sequence IS NULL "
            "AND response_schema_version = '' AND response_payload IS NULL AND response_digest = '')",
            name="ck_study_chat_operation_result_evidence",
        ),
        CheckConstraint(
            "(status IN ('committed', 'not_committed', 'uncertain') AND completed_at <> '') OR "
            "(status IN ('admitted', 'running') AND completed_at = '')",
            name="ck_study_chat_operation_terminal_time",
        ),
        CheckConstraint(
            "(status IN ('not_committed', 'uncertain') AND error_code <> '') OR "
            "(status IN ('admitted', 'running', 'committed') AND error_code = '')",
            name="ck_study_chat_operation_error_evidence",
        ),
    )

    operation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    harness_operation_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "harness_operation_bindings.harness_operation_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("study_sessions.id", ondelete="RESTRICT"),
        index=True,
    )
    client_request_id: Mapped[str] = mapped_column(String(80))
    request_schema_version: Mapped[str] = mapped_column(String(64))
    fingerprint_contract_version: Mapped[str] = mapped_column(String(64))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    status: Mapped[str] = mapped_column(String(32), index=True)
    active_slot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    admitted_session_revision: Mapped[int] = mapped_column(Integer)
    execution_token: Mapped[str] = mapped_column(String(64), default="")
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    execution_started_at: Mapped[str] = mapped_column(String(64), default="")
    provider_started_at: Mapped[str] = mapped_column(String(64), default="")
    execution_deadline_at: Mapped[str] = mapped_column(String(64), default="")
    heartbeat_at: Mapped[str] = mapped_column(String(64), default="")
    committed_session_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    committed_turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    committed_turn_sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_schema_version: Mapped[str] = mapped_column(String(64), default="")
    response_payload: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD,
        nullable=True,
    )
    harness_trace: Mapped[dict[str, Any] | None] = mapped_column(
        NULLABLE_JSON_PAYLOAD, nullable=True
    )
    response_digest: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64))
    updated_at: Mapped[str] = mapped_column(String(64), index=True)
    completed_at: Mapped[str] = mapped_column(String(64), default="")


class TavernRoomRow(Base):
    __tablename__ = "tavern_rooms"
    __table_args__ = (
        Index(
            "ix_tavern_rooms_updated_at_id",
            desc("updated_at"),
            desc("id"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    creation_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    creation_input_digest: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="active")
    scene_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON_PAYLOAD, nullable=True)
    harness_policy: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), index=True, default="")


class TavernParticipantRow(Base):
    __tablename__ = "tavern_participants"
    __table_args__ = (UniqueConstraint("room_id", "display_order", name="uq_tavern_participant_order"),)

    room_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
        primary_key=True,
    )
    persona_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_order: Mapped[int] = mapped_column(Integer)
    display_name: Mapped[str] = mapped_column(Text, default="")
    persona_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD)
    prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    joined_at: Mapped[str] = mapped_column(String(64), default="")


class TavernRunRow(Base):
    __tablename__ = "tavern_runs"
    __table_args__ = (
        UniqueConstraint(
            "room_id",
            "idempotency_key",
            name="uq_tavern_run_idempotency",
        ),
        UniqueConstraint(
            "harness_operation_id",
            name="uq_tavern_run_harness_operation",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    harness_operation_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey(
            "harness_operation_bindings.harness_operation_id",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    room_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(80))
    parent_run_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("tavern_runs.id", ondelete="CASCADE"),
        unique=True,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    mode: Mapped[str] = mapped_column(String(32), default="direct")
    input_message_id: Mapped[str] = mapped_column(String(64), default="")
    expected_room_revision: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    completed_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class TavernRunStepRow(Base):
    __tablename__ = "tavern_run_steps"
    __table_args__ = (
        UniqueConstraint("run_id", "persona_id", name="uq_tavern_run_step_persona"),
    )

    run_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_runs.id", ondelete="CASCADE"),
        primary_key=True,
    )
    step_index: Mapped[int] = mapped_column(Integer, primary_key=True)
    persona_id: Mapped[str] = mapped_column(String(64), index=True)
    participant_prompt_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), index=True, default="pending")
    message_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    reply_to_message_id: Mapped[str] = mapped_column(String(64), default="")
    error_code: Mapped[str] = mapped_column(String(128), default="")
    started_at: Mapped[str] = mapped_column(String(64), default="")
    completed_at: Mapped[str] = mapped_column(String(64), default="")
    lease_owner: Mapped[str] = mapped_column(String(64), default="")
    lease_expires_at: Mapped[str] = mapped_column(String(64), default="")
    claim_count: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class TavernMessageRow(Base):
    __tablename__ = "tavern_messages"
    __table_args__ = (UniqueConstraint("room_id", "sequence", name="uq_tavern_message_sequence"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("tavern_rooms.id", ondelete="CASCADE"),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    author_kind: Mapped[str] = mapped_column(String(32))
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    client_request_id: Mapped[str] = mapped_column(String(80), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class PersonaRow(Base):
    __tablename__ = "personas"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="user")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class PersonaCardRow(Base):
    __tablename__ = "persona_cards"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(64), default="custom")
    source: Mapped[str] = mapped_column(String(64), default="manual")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class SceneSetupRow(Base):
    __tablename__ = "scene_setup_states"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class SceneLibraryRow(Base):
    __tablename__ = "scene_library_entries"

    scene_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    scene_name: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class ReusableSceneNodeRow(Base):
    __tablename__ = "reusable_scene_nodes"

    node_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    node_type: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(Text, default="")
    source_scene_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class SessionSceneRow(Base):
    __tablename__ = "session_scenes"

    scene_instance_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    document_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    persona_id: Mapped[str] = mapped_column(String(64), index=True, default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class DocumentDebugRow(Base):
    __tablename__ = "document_debug_records"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    processed_at: Mapped[str] = mapped_column(String(64), default="")
    page_count: Mapped[int] = mapped_column(default=0)
    extraction_method: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class PlanningTraceRow(Base):
    __tablename__ = "planning_traces"

    document_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class StreamReportRow(Base):
    __tablename__ = "stream_reports"
    __table_args__ = (UniqueConstraint("category", "document_id", name="uq_stream_reports_category_document"),)

    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    stream_kind: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="idle")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class RuntimeSettingsRow(Base):
    __tablename__ = "runtime_settings"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    plan_provider: Mapped[str] = mapped_column(String(32), default="mock")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class ModelToolConfigRow(Base):
    __tablename__ = "model_tool_configs"

    config_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    updated_at: Mapped[str] = mapped_column(String(64), default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)


class TokenUsageRow(Base):
    __tablename__ = "token_usage_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    feature: Mapped[str] = mapped_column(String(64), index=True, default="")
    model: Mapped[str] = mapped_column(String(128), index=True, default="")
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[str] = mapped_column(String(64), index=True, default="")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_PAYLOAD, default=dict)
