from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
import hashlib
import re
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.harness import (
    HarnessArtifactType,
    HarnessContractRef,
    require_versioned_harness_contract,
)
from app.models.harness_operation import HARNESS_OPERATION_ID_PATTERN


HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION = "harness-artifact-principal-v1"
HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION = "harness-artifact-grant-v1"
HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION = "harness-artifact-access-audit-v1"
HARNESS_ARTIFACT_ACCESS_CONTRACT_REGISTRY_VERSION = (
    "harness-artifact-access-contract-registry-v1"
)
HARNESS_ARTIFACT_CONTRACT_REGISTRATION_SCHEMA_VERSION = (
    "harness-artifact-contract-registration-v1"
)
HARNESS_ARTIFACT_REGISTRATION_SCHEMA_VERSION = "harness-artifact-registration-v1"
HARNESS_ARTIFACT_RESOLUTION_SCHEMA_VERSION = "harness-artifact-resolution-v1"
HARNESS_ARTIFACT_BATCH_RESOLUTION_SCHEMA_VERSION = (
    "harness-artifact-batch-resolution-v1"
)
HARNESS_ARTIFACT_RESOLUTION_AUDIT_SCHEMA_VERSION = (
    "harness-artifact-resolution-audit-v1"
)

_PRINCIPAL_ID_PATTERN = r"^local-installation-[0-9a-f]{32}$"
_GRANT_ID_PATTERN = r"^harness-artifact-grant-[0-9a-f]{32}$"
_ARTIFACT_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$"
_OPAQUE_ARTIFACT_ID_PATTERN = r"^harness-artifact-[0-9a-f]{32}$"
_UTC_TIMESTAMP_PATTERN = (
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)


def _require_canonical_utc_wire(value: object) -> object:
    if isinstance(value, str):
        if not re.fullmatch(_UTC_TIMESTAMP_PATTERN, value):
            raise ValueError("harness_artifact_timestamp_wire_must_be_utc_z")
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    return value


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        frozen=True,
    )


class HarnessArtifactPrincipalKind(StrEnum):
    LOCAL_INSTALLATION = "local_installation"


class HarnessArtifactAuthorizationMode(StrEnum):
    SERVER_RESOLVED_PRINCIPAL = "server_resolved_principal"


class HarnessArtifactPermission(StrEnum):
    READ = "read"
    VERIFY_DIGEST = "verify_digest"


class HarnessArtifactAccessOutcome(StrEnum):
    ALLOWED = "allowed"
    PRINCIPAL_REQUIRED = "principal_required"
    FORBIDDEN = "forbidden"
    GRANT_NOT_ACTIVE = "grant_not_active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class HarnessArtifactResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    FORBIDDEN = "forbidden"
    DIGEST_MISMATCH = "digest_mismatch"
    SCHEMA_UNSUPPORTED = "schema_unsupported"


class HarnessArtifactContractRegistrationV1(_StrictModel):
    schema_name: Literal["HarnessArtifactContractRegistrationV1"] = (
        "HarnessArtifactContractRegistrationV1"
    )
    schema_version: Literal[HARNESS_ARTIFACT_CONTRACT_REGISTRATION_SCHEMA_VERSION] = (
        HARNESS_ARTIFACT_CONTRACT_REGISTRATION_SCHEMA_VERSION
    )
    artifact_contract: HarnessContractRef
    registered_at: AwareDatetime

    @field_validator("registered_at", mode="before")
    @classmethod
    def require_canonical_utc_wire(cls, value: object) -> object:
        return _require_canonical_utc_wire(value)

    @model_validator(mode="after")
    def require_contract(self) -> "HarnessArtifactContractRegistrationV1":
        require_versioned_harness_contract(self.artifact_contract)
        if self.registered_at.utcoffset() != timedelta(0):
            raise ValueError("harness_artifact_contract_timestamp_must_be_utc")
        return self


class HarnessArtifactRegistrationV1(_StrictModel):
    schema_name: Literal["HarnessArtifactRegistrationV1"] = "HarnessArtifactRegistrationV1"
    schema_version: Literal[HARNESS_ARTIFACT_REGISTRATION_SCHEMA_VERSION] = (
        HARNESS_ARTIFACT_REGISTRATION_SCHEMA_VERSION
    )
    artifact_type: HarnessArtifactType
    artifact_id: str = Field(pattern=_OPAQUE_ARTIFACT_ID_PATTERN)
    artifact_contract: HarnessContractRef
    payload_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: AwareDatetime
    expires_at: AwareDatetime | None = None

    @field_validator("registered_at", "expires_at", mode="before")
    @classmethod
    def require_canonical_utc_wire(cls, value: object) -> object:
        return _require_canonical_utc_wire(value)

    @model_validator(mode="after")
    def validate_registration(self) -> "HarnessArtifactRegistrationV1":
        require_versioned_harness_contract(self.artifact_contract)
        if self.registered_at.utcoffset() != timedelta(0) or (
            self.expires_at is not None and self.expires_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("harness_artifact_registration_timestamp_must_be_utc")
        if self.expires_at is not None and self.expires_at <= self.registered_at:
            raise ValueError("harness_artifact_retention_invalid")
        if self.artifact_type == HarnessArtifactType.DOCUMENT_DEBUG:
            raise ValueError("harness_artifact_removable_cache_unsupported")
        return self


class HarnessArtifactResolveRequestV1(_StrictModel):
    grant_id: str = Field(pattern=_GRANT_ID_PATTERN)
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    artifact_id: str = Field(pattern=_OPAQUE_ARTIFACT_ID_PATTERN)
    artifact_type: HarnessArtifactType
    artifact_contract: HarnessContractRef
    permission: HarnessArtifactPermission = HarnessArtifactPermission.READ

    @model_validator(mode="after")
    def require_contract(self) -> "HarnessArtifactResolveRequestV1":
        require_versioned_harness_contract(self.artifact_contract)
        return self


class HarnessArtifactResolutionV1(_StrictModel):
    schema_name: Literal["HarnessArtifactResolutionV1"] = "HarnessArtifactResolutionV1"
    schema_version: Literal[HARNESS_ARTIFACT_RESOLUTION_SCHEMA_VERSION] = (
        HARNESS_ARTIFACT_RESOLUTION_SCHEMA_VERSION
    )
    status: HarnessArtifactResolutionStatus
    artifact_id: str = Field(pattern=_OPAQUE_ARTIFACT_ID_PATTERN)
    artifact_type: HarnessArtifactType
    artifact_contract: HarnessContractRef
    permission: HarnessArtifactPermission
    payload_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    resolved_at: AwareDatetime
    content: bytes | None = None

    @field_validator("resolved_at", mode="before")
    @classmethod
    def require_canonical_utc_wire(cls, value: object) -> object:
        return _require_canonical_utc_wire(value)

    @model_validator(mode="after")
    def validate_result(self) -> "HarnessArtifactResolutionV1":
        require_versioned_harness_contract(self.artifact_contract)
        if self.resolved_at.utcoffset() != timedelta(0):
            raise ValueError("harness_artifact_resolution_timestamp_must_be_utc")
        if self.status == HarnessArtifactResolutionStatus.RESOLVED:
            if self.payload_digest is None:
                raise ValueError("harness_artifact_resolution_digest_required")
            if self.permission == HarnessArtifactPermission.READ and self.content is None:
                raise ValueError("harness_artifact_resolution_content_required")
            if (
                self.permission == HarnessArtifactPermission.VERIFY_DIGEST
                and self.content is not None
            ):
                raise ValueError("harness_artifact_resolution_content_forbidden")
            if (
                self.content is not None
                and hashlib.sha256(self.content).hexdigest() != self.payload_digest
            ):
                raise ValueError("harness_artifact_resolution_content_digest_mismatch")
        elif self.content is not None or self.payload_digest is not None:
            raise ValueError("harness_artifact_resolution_protected_fields_forbidden")
        return self


class HarnessArtifactBatchResolutionV1(_StrictModel):
    schema_name: Literal["HarnessArtifactBatchResolutionV1"] = (
        "HarnessArtifactBatchResolutionV1"
    )
    schema_version: Literal[HARNESS_ARTIFACT_BATCH_RESOLUTION_SCHEMA_VERSION] = (
        HARNESS_ARTIFACT_BATCH_RESOLUTION_SCHEMA_VERSION
    )
    results: tuple[HarnessArtifactResolutionV1, ...] = Field(min_length=1, max_length=64)


class HarnessArtifactResolutionAuditV1(_StrictModel):
    """Content-free durable evidence for one resolver decision.

    ``authorization_outcome`` is deliberately distinct from ``resolution_status``:
    an authorized read can still discover a missing, expired, corrupt, or unsupported
    artifact.  ``None`` is reserved for corrupt authorization metadata that could not
    be decoded safely enough to produce an access-contract outcome.
    """

    schema_name: Literal["HarnessArtifactResolutionAuditV1"] = (
        "HarnessArtifactResolutionAuditV1"
    )
    schema_version: Literal[HARNESS_ARTIFACT_RESOLUTION_AUDIT_SCHEMA_VERSION] = (
        HARNESS_ARTIFACT_RESOLUTION_AUDIT_SCHEMA_VERSION
    )
    audit_id: str = Field(pattern=r"^harness-artifact-audit-[0-9a-f]{32}$")
    grant_id: str = Field(pattern=_GRANT_ID_PATTERN)
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    grant_harness_operation_id: str | None = Field(
        default=None,
        pattern=HARNESS_OPERATION_ID_PATTERN,
    )
    presented_principal_id: str | None = Field(
        default=None,
        pattern=_PRINCIPAL_ID_PATTERN,
    )
    grant_subject_id: str | None = Field(
        default=None,
        pattern=_PRINCIPAL_ID_PATTERN,
    )
    artifact_id: str = Field(pattern=_OPAQUE_ARTIFACT_ID_PATTERN)
    artifact_type: HarnessArtifactType
    artifact_contract: HarnessContractRef
    permission: HarnessArtifactPermission
    authorization_outcome: HarnessArtifactAccessOutcome | None
    resolution_status: HarnessArtifactResolutionStatus
    evaluated_at: AwareDatetime

    @field_validator("evaluated_at", mode="before")
    @classmethod
    def require_canonical_utc_wire(cls, value: object) -> object:
        return _require_canonical_utc_wire(value)

    @model_validator(mode="after")
    def validate_decision(self) -> "HarnessArtifactResolutionAuditV1":
        require_versioned_harness_contract(self.artifact_contract)
        if self.evaluated_at.utcoffset() != timedelta(0):
            raise ValueError("harness_artifact_resolution_audit_timestamp_must_be_utc")
        if self.authorization_outcome is None:
            if self.resolution_status != HarnessArtifactResolutionStatus.SCHEMA_UNSUPPORTED:
                raise ValueError("harness_artifact_resolution_audit_decision_mismatch")
            return self
        if self.authorization_outcome == HarnessArtifactAccessOutcome.ALLOWED:
            if (
                self.grant_harness_operation_id != self.harness_operation_id
                or self.presented_principal_id is None
                or self.presented_principal_id != self.grant_subject_id
                or self.resolution_status == HarnessArtifactResolutionStatus.FORBIDDEN
            ):
                raise ValueError("harness_artifact_resolution_audit_allowed_mismatch")
            return self
        if self.authorization_outcome == HarnessArtifactAccessOutcome.EXPIRED:
            if self.resolution_status != HarnessArtifactResolutionStatus.EXPIRED:
                raise ValueError("harness_artifact_resolution_audit_expiry_mismatch")
            return self
        if self.resolution_status != HarnessArtifactResolutionStatus.FORBIDDEN:
            raise ValueError("harness_artifact_resolution_audit_forbidden_mismatch")
        return self


class HarnessArtifactPrincipalV1(_StrictModel):
    schema_name: Literal["HarnessArtifactPrincipal"] = "HarnessArtifactPrincipal"
    schema_version: Literal[
        HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION
    ] = HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION
    principal_kind: Literal[
        HarnessArtifactPrincipalKind.LOCAL_INSTALLATION
    ] = HarnessArtifactPrincipalKind.LOCAL_INSTALLATION
    principal_id: str = Field(pattern=_PRINCIPAL_ID_PATTERN)


class HarnessArtifactGrantScopeV1(_StrictModel):
    artifact_type: HarnessArtifactType
    artifact_id: str = Field(pattern=_ARTIFACT_ID_PATTERN)
    artifact_contract: HarnessContractRef
    permission: HarnessArtifactPermission

    @model_validator(mode="after")
    def require_versioned_contract(self) -> "HarnessArtifactGrantScopeV1":
        require_versioned_harness_contract(self.artifact_contract)
        return self


class HarnessArtifactGrantV1(_StrictModel):
    schema_name: Literal["HarnessArtifactGrant"] = "HarnessArtifactGrant"
    schema_version: Literal[
        HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION
    ] = HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION
    grant_id: str = Field(pattern=_GRANT_ID_PATTERN)
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    subject: HarnessArtifactPrincipalV1
    authorization_mode: Literal[
        HarnessArtifactAuthorizationMode.SERVER_RESOLVED_PRINCIPAL
    ] = HarnessArtifactAuthorizationMode.SERVER_RESOLVED_PRINCIPAL
    scopes: tuple[HarnessArtifactGrantScopeV1, ...] = Field(min_length=1, max_length=64)
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    revoked_at: AwareDatetime | None = None

    @field_validator("issued_at", "expires_at", "revoked_at", mode="before")
    @classmethod
    def require_canonical_utc_wire(cls, value: object) -> object:
        return _require_canonical_utc_wire(value)

    @field_validator("issued_at", "expires_at", "revoked_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("harness_artifact_grant_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_lifecycle_and_scope_order(self) -> "HarnessArtifactGrantV1":
        if self.expires_at <= self.issued_at:
            raise ValueError("harness_artifact_grant_expiry_invalid")
        if self.revoked_at is not None and self.revoked_at < self.issued_at:
            raise ValueError("harness_artifact_grant_revocation_invalid")
        scope_keys = [_scope_key(item) for item in self.scopes]
        if len(scope_keys) != len(set(scope_keys)):
            raise ValueError("harness_artifact_grant_scope_duplicate")
        if scope_keys != sorted(scope_keys):
            raise ValueError("harness_artifact_grant_scopes_not_sorted")
        return self


class HarnessArtifactAccessAuditV1(_StrictModel):
    schema_name: Literal[
        "HarnessArtifactAccessAudit"
    ] = "HarnessArtifactAccessAudit"
    schema_version: Literal[
        HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION
    ] = HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION
    outcome: HarnessArtifactAccessOutcome
    evaluated_at: AwareDatetime
    presented_principal_id: str | None = Field(
        default=None,
        pattern=_PRINCIPAL_ID_PATTERN,
    )
    grant_id: str = Field(pattern=_GRANT_ID_PATTERN)
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    grant_harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    grant_subject_id: str = Field(pattern=_PRINCIPAL_ID_PATTERN)
    artifact_type: HarnessArtifactType
    artifact_id: str = Field(pattern=_ARTIFACT_ID_PATTERN)
    artifact_contract: HarnessContractRef
    permission: HarnessArtifactPermission

    @field_validator("evaluated_at", mode="before")
    @classmethod
    def require_canonical_utc_wire(cls, value: object) -> object:
        return _require_canonical_utc_wire(value)

    @field_validator("evaluated_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("harness_artifact_access_timestamp_must_be_utc")
        return value

    @model_validator(mode="after")
    def validate_audit_identity(self) -> "HarnessArtifactAccessAuditV1":
        require_versioned_harness_contract(self.artifact_contract)
        if (self.presented_principal_id is None) != (
            self.outcome == HarnessArtifactAccessOutcome.PRINCIPAL_REQUIRED
        ):
            raise ValueError("harness_artifact_access_principal_outcome_mismatch")
        if self.outcome == HarnessArtifactAccessOutcome.ALLOWED and (
            self.presented_principal_id != self.grant_subject_id
            or self.harness_operation_id != self.grant_harness_operation_id
        ):
            raise ValueError("harness_artifact_access_allowed_identity_mismatch")
        return self

    @property
    def allowed(self) -> bool:
        return self.outcome == HarnessArtifactAccessOutcome.ALLOWED


class HarnessArtifactAccessCaseV1(_StrictModel):
    case_id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    presented_principal_id: str | None = Field(
        default=None,
        pattern=_PRINCIPAL_ID_PATTERN,
    )
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    artifact_id: str = Field(pattern=_ARTIFACT_ID_PATTERN)
    evaluated_at: AwareDatetime
    grant_expires_at: AwareDatetime
    grant_revoked_at: AwareDatetime | None
    expected_outcome: HarnessArtifactAccessOutcome

    @field_validator(
        "evaluated_at",
        "grant_expires_at",
        "grant_revoked_at",
        mode="before",
    )
    @classmethod
    def require_canonical_utc_wire(cls, value: object) -> object:
        return _require_canonical_utc_wire(value)

    @field_validator("evaluated_at", "grant_expires_at", "grant_revoked_at")
    @classmethod
    def require_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() != timedelta(0):
            raise ValueError("harness_artifact_access_case_timestamp_must_be_utc")
        return value


class HarnessArtifactAccessCasesV1(_StrictModel):
    schema_name: Literal[
        "HarnessArtifactAccessCases"
    ] = "HarnessArtifactAccessCases"
    schema_version: Literal[
        "harness-artifact-access-cases-v1"
    ] = "harness-artifact-access-cases-v1"
    grant_harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    cases: tuple[HarnessArtifactAccessCaseV1, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_cases(self) -> "HarnessArtifactAccessCasesV1":
        case_ids = [item.case_id for item in self.cases]
        if case_ids != sorted(case_ids):
            raise ValueError("harness_artifact_access_cases_not_sorted")
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("harness_artifact_access_case_duplicate")
        return self


class HarnessArtifactAccessGoldenV1(_StrictModel):
    schema_name: Literal[
        "HarnessArtifactAccessGolden"
    ] = "HarnessArtifactAccessGolden"
    schema_version: Literal[
        "harness-artifact-access-golden-v1"
    ] = "harness-artifact-access-golden-v1"
    principal: HarnessArtifactPrincipalV1
    grant: HarnessArtifactGrantV1
    allowed_audit: HarnessArtifactAccessAuditV1

    @model_validator(mode="after")
    def validate_identity(self) -> "HarnessArtifactAccessGoldenV1":
        if self.grant.subject != self.principal:
            raise ValueError("harness_artifact_access_golden_subject_mismatch")
        if not self.allowed_audit.allowed:
            raise ValueError("harness_artifact_access_golden_audit_not_allowed")
        scope = self.grant.scopes[0]
        if (
            self.allowed_audit.presented_principal_id != self.principal.principal_id
            or self.allowed_audit.grant_subject_id != self.principal.principal_id
            or self.allowed_audit.grant_id != self.grant.grant_id
            or self.allowed_audit.harness_operation_id
            != self.grant.harness_operation_id
            or self.allowed_audit.grant_harness_operation_id
            != self.grant.harness_operation_id
            or self.allowed_audit.artifact_type != scope.artifact_type
            or self.allowed_audit.artifact_id != scope.artifact_id
            or self.allowed_audit.artifact_contract != scope.artifact_contract
            or self.allowed_audit.permission != scope.permission
        ):
            raise ValueError("harness_artifact_access_golden_identity_mismatch")
        return self


def authorize_harness_artifact_access(
    *,
    principal: HarnessArtifactPrincipalV1 | None,
    grant: HarnessArtifactGrantV1,
    harness_operation_id: str,
    artifact_type: HarnessArtifactType,
    artifact_id: str,
    artifact_contract: HarnessContractRef,
    permission: HarnessArtifactPermission,
    evaluated_at: datetime,
) -> HarnessArtifactAccessAuditV1:
    """Evaluate one exact server-side grant without accepting bearer material."""

    if evaluated_at.utcoffset() != timedelta(0):
        raise ValueError("harness_artifact_access_timestamp_must_be_utc")
    requested_scope = HarnessArtifactGrantScopeV1(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        artifact_contract=artifact_contract,
        permission=permission,
    )
    if principal is None:
        outcome = HarnessArtifactAccessOutcome.PRINCIPAL_REQUIRED
    elif principal != grant.subject:
        outcome = HarnessArtifactAccessOutcome.FORBIDDEN
    elif harness_operation_id != grant.harness_operation_id:
        outcome = HarnessArtifactAccessOutcome.FORBIDDEN
    elif evaluated_at < grant.issued_at:
        outcome = HarnessArtifactAccessOutcome.GRANT_NOT_ACTIVE
    elif grant.revoked_at is not None and grant.revoked_at <= evaluated_at:
        outcome = HarnessArtifactAccessOutcome.REVOKED
    elif grant.expires_at <= evaluated_at:
        outcome = HarnessArtifactAccessOutcome.EXPIRED
    elif _scope_key(requested_scope) not in {_scope_key(item) for item in grant.scopes}:
        outcome = HarnessArtifactAccessOutcome.FORBIDDEN
    else:
        outcome = HarnessArtifactAccessOutcome.ALLOWED

    return HarnessArtifactAccessAuditV1(
        outcome=outcome,
        evaluated_at=evaluated_at,
        presented_principal_id=principal.principal_id if principal is not None else None,
        grant_id=grant.grant_id,
        harness_operation_id=harness_operation_id,
        grant_harness_operation_id=grant.harness_operation_id,
        grant_subject_id=grant.subject.principal_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        artifact_contract=artifact_contract,
        permission=permission,
    )


def harness_artifact_access_contract_registry_snapshot() -> dict[str, object]:
    return {
        "schema_name": "HarnessArtifactAccessContractRegistry",
        "schema_version": HARNESS_ARTIFACT_ACCESS_CONTRACT_REGISTRY_VERSION,
        "authoritative_boundary": {
            "principal_kind": HarnessArtifactPrincipalKind.LOCAL_INSTALLATION.value,
            "authorization_mode": (
                HarnessArtifactAuthorizationMode.SERVER_RESOLVED_PRINCIPAL.value
            ),
            "grant_is_bearer_secret": False,
            "grant_is_operation_scoped": True,
            "missing_principal_outcome": (
                HarnessArtifactAccessOutcome.PRINCIPAL_REQUIRED.value
            ),
        },
        "contracts": {
            "principal": {
                "name": "HarnessArtifactPrincipal",
                "version": HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION,
            },
            "grant": {
                "name": "HarnessArtifactGrant",
                "version": HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION,
            },
            "audit": {
                "name": "HarnessArtifactAccessAudit",
                "version": HARNESS_ARTIFACT_ACCESS_AUDIT_SCHEMA_VERSION,
            },
        },
        "permissions": [item.value for item in HarnessArtifactPermission],
        "outcomes": [item.value for item in HarnessArtifactAccessOutcome],
    }


def _scope_key(scope: HarnessArtifactGrantScopeV1) -> tuple[str, str, str, str, str]:
    return (
        scope.artifact_type.value,
        scope.artifact_id,
        scope.artifact_contract.name,
        scope.artifact_contract.version,
        scope.permission.value,
    )
