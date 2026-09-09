from __future__ import annotations

from collections.abc import Callable, Iterable
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.harness import HarnessArtifactType, HarnessContractRef
from app.models.harness_artifact_access import (
    HARNESS_ARTIFACT_CONTRACT_REGISTRATION_SCHEMA_VERSION,
    HARNESS_ARTIFACT_GRANT_SCHEMA_VERSION,
    HARNESS_ARTIFACT_PRINCIPAL_SCHEMA_VERSION,
    HARNESS_ARTIFACT_REGISTRATION_SCHEMA_VERSION,
    HARNESS_ARTIFACT_RESOLUTION_AUDIT_SCHEMA_VERSION,
    HarnessArtifactAccessOutcome,
    HarnessArtifactBatchResolutionV1,
    HarnessArtifactContractRegistrationV1,
    HarnessArtifactGrantScopeV1,
    HarnessArtifactGrantV1,
    HarnessArtifactPermission,
    HarnessArtifactPrincipalV1,
    HarnessArtifactRegistrationV1,
    HarnessArtifactResolutionStatus,
    HarnessArtifactResolutionAuditV1,
    HarnessArtifactResolutionV1,
    HarnessArtifactResolveRequestV1,
    authorize_harness_artifact_access,
)
from app.persistence.database import Database
from app.persistence.models import (
    HarnessArtifactAccessAuditRow,
    HarnessArtifactContractRow,
    HarnessArtifactGrantRow,
    HarnessArtifactGrantScopeRow,
    HarnessArtifactPrincipalRow,
    HarnessArtifactRow,
    HarnessOperationBindingRow,
)


_UTC = timezone.utc
_INSTALLATION_SLOT = "local-installation-v1"


def _utc_wire(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("harness_artifact_timestamp_must_be_utc")
    return value.isoformat().replace("+00:00", "Z")


def _now(value: datetime | None) -> datetime:
    return value if value is not None else datetime.now(_UTC)


def _from_wire(value: str) -> datetime:
    return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")


def _artifact_id() -> str:
    return f"harness-artifact-{secrets.token_hex(16)}"


def _grant_id() -> str:
    return f"harness-artifact-grant-{secrets.token_hex(16)}"


def _principal_id() -> str:
    return f"local-installation-{secrets.token_hex(16)}"


class HarnessArtifactRepository:
    """Durable protected-artifact boundary.

    Callers can name a grant but cannot choose a principal.  This repository
    always resolves the installation principal from durable server state before
    it reads an artifact payload.
    """

    def __init__(
        self,
        database: Database,
        *,
        artifact_id_factory: Callable[[], str] | None = None,
        grant_id_factory: Callable[[], str] | None = None,
        principal_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.database = database
        self._artifact_id_factory = artifact_id_factory or _artifact_id
        self._grant_id_factory = grant_id_factory or _grant_id
        self._principal_id_factory = principal_id_factory or _principal_id

    def local_installation_principal(
        self, *, now: datetime | None = None
    ) -> HarnessArtifactPrincipalV1:
        evaluated_at = _now(now)
        _utc_wire(evaluated_at)
        candidate = HarnessArtifactPrincipalV1(
            principal_id=self._principal_id_factory(),
        )
        try:
            with self.database.session() as session:
                row = session.get(HarnessArtifactPrincipalRow, _INSTALLATION_SLOT)
                if row is None:
                    row = HarnessArtifactPrincipalRow(
                        installation_slot=_INSTALLATION_SLOT,
                        principal_id=candidate.principal_id,
                        schema_name=candidate.schema_name,
                        schema_version=candidate.schema_version,
                        created_at=_utc_wire(evaluated_at),
                    )
                    session.add(row)
                    session.flush()
                return self._principal_from_row(row)
        except IntegrityError:
            # A second process can win creation of the one installation slot.
            # Re-read the durable winner; an unrelated uniqueness failure is
            # not converted into a successful principal resolution.
            with self.database.session() as session:
                row = session.get(HarnessArtifactPrincipalRow, _INSTALLATION_SLOT)
                if row is None:
                    raise
                return self._principal_from_row(row)

    def register_contract(
        self,
        *,
        artifact_contract: HarnessContractRef,
        now: datetime | None = None,
    ) -> HarnessArtifactContractRegistrationV1:
        registered_at = _now(now)
        wire = _utc_wire(registered_at)
        registration = HarnessArtifactContractRegistrationV1(
            artifact_contract=artifact_contract, registered_at=registered_at
        )
        try:
            with self.database.session() as session:
                row = session.get(
                    HarnessArtifactContractRow,
                    (artifact_contract.name, artifact_contract.version),
                )
                if row is None:
                    session.add(
                        HarnessArtifactContractRow(
                            contract_name=artifact_contract.name,
                            contract_version=artifact_contract.version,
                            schema_name=registration.schema_name,
                            schema_version=registration.schema_version,
                            registered_at=wire,
                        )
                    )
                    session.flush()
                    return registration
                return self._contract_from_row(row)
        except IntegrityError:
            with self.database.session() as session:
                row = session.get(
                    HarnessArtifactContractRow,
                    (artifact_contract.name, artifact_contract.version),
                )
                if row is None:
                    raise
                return self._contract_from_row(row)

    def register_artifact(
        self,
        *,
        artifact_type: HarnessArtifactType,
        artifact_contract: HarnessContractRef,
        content: bytes,
        expires_at: datetime | None = None,
        now: datetime | None = None,
    ) -> HarnessArtifactRegistrationV1:
        registered_at = _now(now)
        _utc_wire(registered_at)
        if expires_at is not None:
            _utc_wire(expires_at)
        self.register_contract(artifact_contract=artifact_contract, now=registered_at)
        principal = self.local_installation_principal(now=registered_at)
        registration = HarnessArtifactRegistrationV1(
            artifact_type=artifact_type,
            artifact_id=self._artifact_id_factory(),
            artifact_contract=artifact_contract,
            payload_digest=hashlib.sha256(content).hexdigest(),
            registered_at=registered_at,
            expires_at=expires_at,
        )
        with self.database.session() as session:
            session.add(
                HarnessArtifactRow(
                    artifact_id=registration.artifact_id,
                    artifact_type=artifact_type.value,
                    contract_name=artifact_contract.name,
                    contract_version=artifact_contract.version,
                    digest_algorithm="sha256",
                    payload_digest=registration.payload_digest,
                    payload=content,
                    expires_at=_utc_wire(expires_at) if expires_at else None,
                    deleted_at=None,
                    registered_principal_id=principal.principal_id,
                    schema_name=registration.schema_name,
                    schema_version=registration.schema_version,
                    registered_at=_utc_wire(registered_at),
                )
            )
            try:
                session.flush()
            except IntegrityError as error:
                raise HarnessArtifactIdentityConflict(
                    registration.artifact_id
                ) from error
        return registration

    def delete_artifact(
        self,
        *,
        artifact_id: str,
        now: datetime | None = None,
    ) -> bool:
        """Remove protected bytes while retaining the immutable ID tombstone."""

        deleted_at = _now(now)
        wire = _utc_wire(deleted_at)
        principal = self.local_installation_principal(now=deleted_at)
        with self.database.session() as session:
            row = session.get(HarnessArtifactRow, artifact_id)
            if row is None or row.deleted_at is not None:
                return False
            if row.registered_principal_id != principal.principal_id:
                raise HarnessArtifactScopeMismatch(artifact_id)
            row.payload = b""
            row.deleted_at = wire
            session.flush()
            return True

    def issue_grant(
        self,
        *,
        harness_operation_id: str,
        scopes: Iterable[HarnessArtifactGrantScopeV1],
        expires_at: datetime,
        now: datetime | None = None,
    ) -> HarnessArtifactGrantV1:
        issued_at = _now(now)
        _utc_wire(issued_at)
        _utc_wire(expires_at)
        principal = self.local_installation_principal(now=issued_at)
        scope_tuple = tuple(scopes)
        grant = HarnessArtifactGrantV1(
            grant_id=self._grant_id_factory(),
            harness_operation_id=harness_operation_id,
            subject=principal,
            scopes=scope_tuple,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        with self.database.session() as session:
            if session.get(HarnessOperationBindingRow, harness_operation_id) is None:
                raise HarnessArtifactOperationNotFound(harness_operation_id)
            for scope in scope_tuple:
                artifact = session.get(HarnessArtifactRow, scope.artifact_id)
                if artifact is None or artifact.deleted_at is not None:
                    raise HarnessArtifactNotRegistered(scope.artifact_id)
                if (
                    artifact.artifact_type != scope.artifact_type.value
                    or artifact.contract_name != scope.artifact_contract.name
                    or artifact.contract_version != scope.artifact_contract.version
                ):
                    raise HarnessArtifactScopeMismatch(scope.artifact_id)
                if artifact.registered_principal_id != principal.principal_id:
                    raise HarnessArtifactScopeMismatch(scope.artifact_id)
                contract_row = session.get(
                    HarnessArtifactContractRow,
                    (scope.artifact_contract.name, scope.artifact_contract.version),
                )
                if contract_row is None:
                    raise HarnessArtifactSchemaUnsupported(scope.artifact_id)
                self._contract_from_row(contract_row)
                if artifact.expires_at is not None:
                    artifact_expires_at = _from_wire(artifact.expires_at)
                    if artifact_expires_at <= issued_at:
                        raise HarnessArtifactNotRegistered(scope.artifact_id)
                    if expires_at > artifact_expires_at:
                        raise HarnessArtifactGrantExceedsRetention(scope.artifact_id)
            session.add(
                HarnessArtifactGrantRow(
                    grant_id=grant.grant_id,
                    harness_operation_id=grant.harness_operation_id,
                    principal_id=principal.principal_id,
                    issued_at=_utc_wire(grant.issued_at),
                    expires_at=_utc_wire(grant.expires_at),
                    revoked_at=None,
                    schema_name=grant.schema_name,
                    schema_version=grant.schema_version,
                )
            )
            for scope in scope_tuple:
                session.add(
                    HarnessArtifactGrantScopeRow(
                        grant_id=grant.grant_id,
                        artifact_id=scope.artifact_id,
                        artifact_type=scope.artifact_type.value,
                        contract_name=scope.artifact_contract.name,
                        contract_version=scope.artifact_contract.version,
                        permission=scope.permission.value,
                    )
                )
            try:
                session.flush()
            except IntegrityError as error:
                raise HarnessArtifactGrantIdentityConflict(grant.grant_id) from error
        return grant

    def revoke_grant(self, *, grant_id: str, now: datetime | None = None) -> bool:
        revoked_at = _now(now)
        _utc_wire(revoked_at)
        with self.database.session() as session:
            row = session.get(HarnessArtifactGrantRow, grant_id)
            if row is None:
                return False
            if row.revoked_at is None:
                if revoked_at < _from_wire(row.issued_at):
                    raise ValueError("harness_artifact_grant_revocation_invalid")
                row.revoked_at = _utc_wire(revoked_at)
                session.flush()
            return True

    def resolve(
        self,
        request: HarnessArtifactResolveRequestV1,
        *,
        now: datetime | None = None,
        _session: Session | None = None,
    ) -> HarnessArtifactResolutionV1:
        resolved_at = _now(now)
        _utc_wire(resolved_at)
        # All authorization (including operation binding and scope) happens
        # before querying the protected row/payload below.
        with (self.database.session() if _session is None else nullcontext(_session)) as session:
            grant_row = session.get(HarnessArtifactGrantRow, request.grant_id)
            principal_row = session.get(HarnessArtifactPrincipalRow, _INSTALLATION_SLOT)
            if grant_row is None:
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    HarnessArtifactResolutionStatus.FORBIDDEN,
                    authorization_outcome=HarnessArtifactAccessOutcome.FORBIDDEN,
                )
            try:
                grant = self._grant_from_rows(session, grant_row)
                principal = (
                    self._principal_from_row(principal_row)
                    if principal_row is not None
                    else None
                )
            except (TypeError, ValueError, ValidationError):
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    HarnessArtifactResolutionStatus.SCHEMA_UNSUPPORTED,
                    authorization_outcome=None,
                )
            audit = authorize_harness_artifact_access(
                principal=principal,
                grant=grant,
                harness_operation_id=request.harness_operation_id,
                artifact_type=request.artifact_type,
                artifact_id=request.artifact_id,
                artifact_contract=request.artifact_contract,
                permission=request.permission,
                evaluated_at=resolved_at,
            )
            if not audit.allowed:
                status = (
                    HarnessArtifactResolutionStatus.EXPIRED
                    if audit.outcome == HarnessArtifactAccessOutcome.EXPIRED
                    else HarnessArtifactResolutionStatus.FORBIDDEN
                )
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    status,
                    grant=grant,
                    principal=principal,
                    authorization_outcome=audit.outcome,
                )

            artifact = session.get(HarnessArtifactRow, request.artifact_id)
            if artifact is None or artifact.deleted_at is not None:
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    HarnessArtifactResolutionStatus.NOT_FOUND,
                    grant=grant,
                    principal=principal,
                    authorization_outcome=audit.outcome,
                )
            try:
                registration = self._artifact_registration_from_row(artifact)
                contract_row = session.get(
                    HarnessArtifactContractRow,
                    (request.artifact_contract.name, request.artifact_contract.version),
                )
                if contract_row is None:
                    raise ValueError("harness_artifact_contract_missing")
                registered_contract = self._contract_from_row(contract_row)
            except (TypeError, ValueError, ValidationError):
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    HarnessArtifactResolutionStatus.SCHEMA_UNSUPPORTED,
                    grant=grant,
                    principal=principal,
                    authorization_outcome=audit.outcome,
                )
            if (
                registration.artifact_type != request.artifact_type
                or registration.artifact_contract != request.artifact_contract
                or registered_contract.artifact_contract != request.artifact_contract
                or artifact.registered_principal_id != principal.principal_id
            ):
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    HarnessArtifactResolutionStatus.SCHEMA_UNSUPPORTED,
                    grant=grant,
                    principal=principal,
                    authorization_outcome=audit.outcome,
                )
            if artifact.expires_at is not None and _from_wire(artifact.expires_at) <= resolved_at:
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    HarnessArtifactResolutionStatus.EXPIRED,
                    grant=grant,
                    principal=principal,
                    authorization_outcome=audit.outcome,
                )
            actual_digest = hashlib.sha256(artifact.payload).hexdigest()
            if artifact.digest_algorithm != "sha256" or actual_digest != artifact.payload_digest:
                return self._terminal(
                    session,
                    request,
                    resolved_at,
                    HarnessArtifactResolutionStatus.DIGEST_MISMATCH,
                    grant=grant,
                    principal=principal,
                    authorization_outcome=audit.outcome,
                )
            result = HarnessArtifactResolutionV1(
                status=HarnessArtifactResolutionStatus.RESOLVED,
                artifact_id=request.artifact_id,
                artifact_type=request.artifact_type,
                artifact_contract=request.artifact_contract,
                permission=request.permission,
                payload_digest=actual_digest,
                resolved_at=resolved_at,
                content=(
                    artifact.payload
                    if request.permission == HarnessArtifactPermission.READ
                    else None
                ),
            )
            self._audit(
                session,
                request,
                resolved_at,
                result.status,
                grant=grant,
                principal=principal,
                authorization_outcome=audit.outcome,
            )
            return result

    def resolve_batch(
        self,
        requests: Iterable[HarnessArtifactResolveRequestV1],
        *,
        now: datetime | None = None,
    ) -> HarnessArtifactBatchResolutionV1:
        request_tuple = tuple(requests)
        if not 1 <= len(request_tuple) <= 64:
            raise ValueError("harness_artifact_batch_size_invalid")
        resolved_at = _now(now)
        _utc_wire(resolved_at)
        # One transaction for the batch; each item still performs its
        # own authorization before touching protected content, in input order.
        with self.database.session() as session:
            return HarnessArtifactBatchResolutionV1(
                results=tuple(self.resolve(item, now=resolved_at, _session=session) for item in request_tuple)
            )

    def list_resolution_audits(self) -> tuple[HarnessArtifactResolutionAuditV1, ...]:
        with self.database.session() as session:
            rows = session.scalars(
                select(HarnessArtifactAccessAuditRow).order_by(
                    HarnessArtifactAccessAuditRow.evaluated_at,
                    HarnessArtifactAccessAuditRow.audit_id,
                )
            ).all()
            return tuple(self._audit_from_row(row) for row in rows)

    def _grant_from_rows(self, session, row: HarnessArtifactGrantRow) -> HarnessArtifactGrantV1:
        scopes = session.scalars(
            select(HarnessArtifactGrantScopeRow)
            .where(HarnessArtifactGrantScopeRow.grant_id == row.grant_id)
            .order_by(
                HarnessArtifactGrantScopeRow.artifact_type,
                HarnessArtifactGrantScopeRow.artifact_id,
                HarnessArtifactGrantScopeRow.contract_name,
                HarnessArtifactGrantScopeRow.contract_version,
                HarnessArtifactGrantScopeRow.permission,
            )
        ).all()
        return HarnessArtifactGrantV1(
            schema_name=row.schema_name,
            schema_version=row.schema_version,
            grant_id=row.grant_id,
            harness_operation_id=row.harness_operation_id,
            subject=HarnessArtifactPrincipalV1(principal_id=row.principal_id),
            scopes=tuple(
                HarnessArtifactGrantScopeV1(
                    artifact_type=HarnessArtifactType(item.artifact_type),
                    artifact_id=item.artifact_id,
                    artifact_contract=HarnessContractRef(
                        name=item.contract_name, version=item.contract_version
                    ),
                    permission=HarnessArtifactPermission(item.permission),
                )
                for item in scopes
            ),
            issued_at=datetime.fromisoformat(row.issued_at.removesuffix("Z") + "+00:00"),
            expires_at=datetime.fromisoformat(row.expires_at.removesuffix("Z") + "+00:00"),
            revoked_at=(
                datetime.fromisoformat(row.revoked_at.removesuffix("Z") + "+00:00")
                if row.revoked_at
                else None
            ),
        )

    def _terminal(
        self,
        session,
        request,
        now,
        status,
        *,
        grant=None,
        principal=None,
        authorization_outcome=None,
    ):
        result = HarnessArtifactResolutionV1(
            status=status,
            artifact_id=request.artifact_id,
            artifact_type=request.artifact_type,
            artifact_contract=request.artifact_contract,
            permission=request.permission,
            resolved_at=now,
        )
        self._audit(
            session,
            request,
            now,
            status,
            grant=grant,
            principal=principal,
            authorization_outcome=authorization_outcome,
        )
        return result

    @staticmethod
    def _audit(
        session,
        request,
        evaluated_at,
        status,
        *,
        grant=None,
        principal=None,
        authorization_outcome=None,
    ) -> None:
        audit = HarnessArtifactResolutionAuditV1(
            audit_id=f"harness-artifact-audit-{secrets.token_hex(16)}",
            grant_id=request.grant_id,
            harness_operation_id=request.harness_operation_id,
            grant_harness_operation_id=(grant.harness_operation_id if grant else None),
            presented_principal_id=(principal.principal_id if principal else None),
            grant_subject_id=(grant.subject.principal_id if grant else None),
            artifact_id=request.artifact_id,
            artifact_type=request.artifact_type,
            artifact_contract=request.artifact_contract,
            permission=request.permission,
            authorization_outcome=authorization_outcome,
            resolution_status=status,
            evaluated_at=evaluated_at,
        )
        session.add(HarnessArtifactAccessAuditRow(
            audit_id=audit.audit_id,
            grant_id=audit.grant_id,
            harness_operation_id=audit.harness_operation_id,
            grant_harness_operation_id=audit.grant_harness_operation_id,
            presented_principal_id=audit.presented_principal_id,
            grant_subject_id=audit.grant_subject_id,
            artifact_id=audit.artifact_id,
            artifact_type=audit.artifact_type.value,
            contract_name=audit.artifact_contract.name,
            contract_version=audit.artifact_contract.version,
            permission=audit.permission.value,
            authorization_outcome=(
                audit.authorization_outcome.value
                if audit.authorization_outcome is not None
                else None
            ),
            resolution_status=audit.resolution_status.value,
            schema_name=audit.schema_name,
            schema_version=audit.schema_version,
            evaluated_at=_utc_wire(audit.evaluated_at),
        ))

    @staticmethod
    def _principal_from_row(row: HarnessArtifactPrincipalRow) -> HarnessArtifactPrincipalV1:
        return HarnessArtifactPrincipalV1(
            schema_name=row.schema_name,
            schema_version=row.schema_version,
            principal_id=row.principal_id,
        )

    @staticmethod
    def _contract_from_row(
        row: HarnessArtifactContractRow,
    ) -> HarnessArtifactContractRegistrationV1:
        return HarnessArtifactContractRegistrationV1(
            schema_name=row.schema_name,
            schema_version=row.schema_version,
            artifact_contract=HarnessContractRef(
                name=row.contract_name,
                version=row.contract_version,
            ),
            registered_at=_from_wire(row.registered_at),
        )

    @staticmethod
    def _artifact_registration_from_row(
        row: HarnessArtifactRow,
    ) -> HarnessArtifactRegistrationV1:
        if row.schema_version != HARNESS_ARTIFACT_REGISTRATION_SCHEMA_VERSION:
            raise ValueError("harness_artifact_schema_unsupported")
        return HarnessArtifactRegistrationV1(
            schema_name=row.schema_name,
            schema_version=row.schema_version,
            artifact_type=HarnessArtifactType(row.artifact_type),
            artifact_id=row.artifact_id,
            artifact_contract=HarnessContractRef(
                name=row.contract_name,
                version=row.contract_version,
            ),
            payload_digest=row.payload_digest,
            registered_at=_from_wire(row.registered_at),
            expires_at=_from_wire(row.expires_at) if row.expires_at else None,
        )

    @staticmethod
    def _audit_from_row(
        row: HarnessArtifactAccessAuditRow,
    ) -> HarnessArtifactResolutionAuditV1:
        return HarnessArtifactResolutionAuditV1(
            schema_name=row.schema_name,
            schema_version=row.schema_version,
            audit_id=row.audit_id,
            grant_id=row.grant_id,
            harness_operation_id=row.harness_operation_id,
            grant_harness_operation_id=row.grant_harness_operation_id,
            presented_principal_id=row.presented_principal_id,
            grant_subject_id=row.grant_subject_id,
            artifact_id=row.artifact_id,
            artifact_type=HarnessArtifactType(row.artifact_type),
            artifact_contract=HarnessContractRef(
                name=row.contract_name,
                version=row.contract_version,
            ),
            permission=HarnessArtifactPermission(row.permission),
            authorization_outcome=(
                HarnessArtifactAccessOutcome(row.authorization_outcome)
                if row.authorization_outcome is not None
                else None
            ),
            resolution_status=HarnessArtifactResolutionStatus(row.resolution_status),
            evaluated_at=_from_wire(row.evaluated_at),
        )


class HarnessArtifactOperationNotFound(LookupError):
    pass


class HarnessArtifactNotRegistered(LookupError):
    pass


class HarnessArtifactScopeMismatch(ValueError):
    pass


class HarnessArtifactSchemaUnsupported(ValueError):
    pass


class HarnessArtifactGrantExceedsRetention(ValueError):
    pass


class HarnessArtifactIdentityConflict(RuntimeError):
    pass


class HarnessArtifactGrantIdentityConflict(RuntimeError):
    pass
