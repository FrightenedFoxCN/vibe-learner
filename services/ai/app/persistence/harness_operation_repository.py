from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models.harness_operation import (
    HARNESS_DOMAIN_OPERATION_ROUTES,
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
    HarnessOperationResolutionStatus,
    HarnessOperationResolutionV1,
    new_harness_operation_id,
    utc_datetime,
)
from app.persistence.database import Database
from app.persistence.models import (
    DocumentProcessOperationRow,
    HarnessOperationBindingRow,
    HarnessWorkflowOperationRow,
    LearningPlanOperationRow,
    PlanRevisionOperationRow,
    StudyChatOperationRow,
    TavernRunRow,
)


_DOMAIN_ROW_TYPES = {
    HarnessDomainOperationKind.FRONTEND_DECODE: HarnessWorkflowOperationRow,
    HarnessDomainOperationKind.DOCUMENT_PROCESS: DocumentProcessOperationRow,
    HarnessDomainOperationKind.DOCUMENT_OCR: HarnessWorkflowOperationRow,
    HarnessDomainOperationKind.STUDY_UNIT_CLEANUP: HarnessWorkflowOperationRow,
    HarnessDomainOperationKind.LEARNING_PLAN_GENERATION: LearningPlanOperationRow,
    HarnessDomainOperationKind.LEARNING_PLAN_REVISION: PlanRevisionOperationRow,
    HarnessDomainOperationKind.PERSONA_GENERATION: HarnessWorkflowOperationRow,
    HarnessDomainOperationKind.SCENE_GENERATION: HarnessWorkflowOperationRow,
    HarnessDomainOperationKind.STUDY_CHAT: StudyChatOperationRow,
    HarnessDomainOperationKind.TAVERN_RUN: TavernRunRow,
}


class HarnessOperationBindingRepository:
    """Append-only server boundary for durable Harness operation identity."""

    def __init__(
        self,
        database: Database,
        *,
        operation_id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.database = database
        self._operation_id_factory = operation_id_factory or new_harness_operation_id

    def _admit_domain_in_session(
        self,
        session: Session,
        *,
        domain_row: object,
        domain_operation_kind: HarnessDomainOperationKind,
        domain_operation_id: str,
        admitted_at: datetime | str,
        parent_harness_operation_id: str | None = None,
    ) -> HarnessOperationBindingV1:
        row_kind, row_id = _domain_row_identity(domain_operation_kind, domain_row)
        if row_kind != domain_operation_kind or row_id != domain_operation_id:
            raise HarnessOperationDomainRowMismatch(
                domain_operation_kind,
                domain_operation_id,
            )
        if getattr(domain_row, "harness_operation_id", None) is not None:
            raise HarnessOperationDomainAlreadyBound(
                domain_operation_kind,
                domain_operation_id,
                str(getattr(domain_row, "harness_operation_id")),
            )

        existing = session.scalar(
            select(HarnessOperationBindingRow).where(
                HarnessOperationBindingRow.domain_operation_kind
                == domain_operation_kind.value,
                HarnessOperationBindingRow.domain_operation_id == domain_operation_id,
            )
        )
        if existing is not None:
            raise HarnessOperationDomainAlreadyBound(
                domain_operation_kind,
                domain_operation_id,
                existing.harness_operation_id,
            )

        if parent_harness_operation_id is not None:
            if domain_operation_kind != HarnessDomainOperationKind.TAVERN_RUN:
                raise HarnessOperationParentKindInvalid(domain_operation_kind)
            parent = session.get(
                HarnessOperationBindingRow,
                parent_harness_operation_id,
            )
            if parent is None:
                raise HarnessOperationParentNotFound(parent_harness_operation_id)
            if parent.domain_operation_kind != HarnessDomainOperationKind.TAVERN_RUN.value:
                raise HarnessOperationParentKindInvalid(domain_operation_kind)

        workflow, entry_stage = HARNESS_DOMAIN_OPERATION_ROUTES[domain_operation_kind]
        normalized_admitted_at = utc_datetime(admitted_at)
        binding = HarnessOperationBindingV1(
            harness_operation_id=self._operation_id_factory(),
            domain_operation_kind=domain_operation_kind,
            domain_operation_id=domain_operation_id,
            workflow=workflow,
            entry_stage=entry_stage,
            parent_harness_operation_id=parent_harness_operation_id,
            admitted_at=normalized_admitted_at,
        )
        domain_state = inspect(domain_row)
        if domain_state.persistent:
            raise HarnessOperationDomainRowMismatch(
                domain_operation_kind,
                domain_operation_id,
            )
        if domain_state.pending:
            session.expunge(domain_row)
        session.add(_to_row(binding))
        session.flush()
        setattr(domain_row, "harness_operation_id", binding.harness_operation_id)
        session.add(domain_row)
        session.flush()
        return binding

    def resolve_domain_in_session(
        self,
        session: Session,
        *,
        domain_operation_kind: HarnessDomainOperationKind,
        domain_operation_id: str,
    ) -> HarnessOperationResolutionV1:
        domain_row = session.get(
            _DOMAIN_ROW_TYPES[domain_operation_kind],
            domain_operation_id,
        )
        if domain_row is None:
            return HarnessOperationResolutionV1(
                status=HarnessOperationResolutionStatus.NOT_FOUND,
                domain_operation_kind=domain_operation_kind,
                domain_operation_id=domain_operation_id,
            )

        harness_operation_id = getattr(domain_row, "harness_operation_id", None)
        if harness_operation_id is None:
            return HarnessOperationResolutionV1(
                status=HarnessOperationResolutionStatus.LEGACY_UNBOUND,
                domain_operation_kind=domain_operation_kind,
                domain_operation_id=domain_operation_id,
            )

        row = session.scalar(
            select(HarnessOperationBindingRow).where(
                HarnessOperationBindingRow.domain_operation_kind
                == domain_operation_kind.value,
                HarnessOperationBindingRow.domain_operation_id == domain_operation_id,
            )
        )
        if row is None:
            raise HarnessOperationBindingCorrupt(
                domain_operation_kind,
                domain_operation_id,
                "reverse_binding_missing",
            )
        if row.harness_operation_id != harness_operation_id:
            raise HarnessOperationBindingCorrupt(
                domain_operation_kind,
                domain_operation_id,
                "bidirectional_identity_mismatch",
            )
        if domain_operation_kind == HarnessDomainOperationKind.TAVERN_RUN:
            self._validate_tavern_parent_lineage(
                session,
                run_row=domain_row,
                binding_row=row,
            )
        return HarnessOperationResolutionV1(
            status=HarnessOperationResolutionStatus.RESOLVED,
            domain_operation_kind=domain_operation_kind,
            domain_operation_id=domain_operation_id,
            binding=_from_row(row),
        )

    def resolve_domain(
        self,
        *,
        domain_operation_kind: HarnessDomainOperationKind,
        domain_operation_id: str,
    ) -> HarnessOperationResolutionV1:
        with self.database.session() as session:
            return self.resolve_domain_in_session(
                session,
                domain_operation_kind=domain_operation_kind,
                domain_operation_id=domain_operation_id,
            )

    def require_domain_in_session(
        self,
        session: Session,
        *,
        domain_operation_kind: HarnessDomainOperationKind,
        domain_operation_id: str,
    ) -> HarnessOperationBindingV1:
        resolution = self.resolve_domain_in_session(
            session,
            domain_operation_kind=domain_operation_kind,
            domain_operation_id=domain_operation_id,
        )
        if resolution.status == HarnessOperationResolutionStatus.NOT_FOUND:
            raise HarnessOperationDomainNotFound(
                domain_operation_kind,
                domain_operation_id,
            )
        if resolution.binding is None:
            raise HarnessOperationLegacyUnbound(
                domain_operation_kind,
                domain_operation_id,
            )
        return resolution.binding

    def require_domain(
        self,
        *,
        domain_operation_kind: HarnessDomainOperationKind,
        domain_operation_id: str,
    ) -> HarnessOperationBindingV1:
        with self.database.session() as session:
            return self.require_domain_in_session(
                session,
                domain_operation_kind=domain_operation_kind,
                domain_operation_id=domain_operation_id,
            )

    def resolve_harness_id(
        self,
        *,
        harness_operation_id: str,
    ) -> HarnessOperationBindingV1 | None:
        """Resolve the immutable admission, including after domain retention purge."""

        with self.database.session() as session:
            row = session.get(HarnessOperationBindingRow, harness_operation_id)
            if row is None:
                return None
            return _from_row(row)

    def get(self, *, harness_operation_id: str) -> HarnessOperationBindingV1 | None:
        """Compatibility alias for the authoritative identity resolver."""

        return self.resolve_harness_id(harness_operation_id=harness_operation_id)

    def _validate_tavern_parent_lineage(
        self,
        session: Session,
        *,
        run_row: TavernRunRow,
        binding_row: HarnessOperationBindingRow,
    ) -> None:
        if run_row.parent_run_id is None:
            if binding_row.parent_harness_operation_id is not None:
                raise HarnessOperationBindingCorrupt(
                    HarnessDomainOperationKind.TAVERN_RUN,
                    run_row.id,
                    "unexpected_parent_binding",
                )
            return
        parent_row = session.get(TavernRunRow, run_row.parent_run_id)
        if parent_row is None:
            raise HarnessOperationBindingCorrupt(
                HarnessDomainOperationKind.TAVERN_RUN,
                run_row.id,
                "parent_run_missing",
            )
        if (
            parent_row.harness_operation_id is None
            or binding_row.parent_harness_operation_id
            != parent_row.harness_operation_id
        ):
            raise HarnessOperationBindingCorrupt(
                HarnessDomainOperationKind.TAVERN_RUN,
                run_row.id,
                "parent_run_binding_mismatch",
            )
        parent_binding = session.get(
            HarnessOperationBindingRow,
            parent_row.harness_operation_id,
        )
        if (
            parent_binding is None
            or parent_binding.domain_operation_kind
            != HarnessDomainOperationKind.TAVERN_RUN.value
            or parent_binding.domain_operation_id != parent_row.id
        ):
            raise HarnessOperationBindingCorrupt(
                HarnessDomainOperationKind.TAVERN_RUN,
                run_row.id,
                "parent_binding_not_authoritative",
            )


class HarnessOperationBindingError(RuntimeError):
    pass


class HarnessOperationDomainAlreadyBound(HarnessOperationBindingError):
    def __init__(
        self,
        kind: HarnessDomainOperationKind,
        domain_operation_id: str,
        harness_operation_id: str,
    ) -> None:
        self.kind = kind
        self.domain_operation_id = domain_operation_id
        self.harness_operation_id = harness_operation_id
        super().__init__(
            "harness_operation_domain_already_bound:"
            f"{kind.value}:{domain_operation_id}:{harness_operation_id}"
        )


class HarnessOperationIdentityCollision(HarnessOperationBindingError):
    def __init__(self) -> None:
        super().__init__("harness_operation_identity_collision")


class HarnessOperationDomainRowMismatch(HarnessOperationBindingError):
    def __init__(
        self,
        kind: HarnessDomainOperationKind,
        domain_operation_id: str,
    ) -> None:
        super().__init__(
            f"harness_operation_domain_row_mismatch:{kind.value}:{domain_operation_id}"
        )


class HarnessOperationDomainNotFound(HarnessOperationBindingError):
    def __init__(
        self,
        kind: HarnessDomainOperationKind,
        domain_operation_id: str,
    ) -> None:
        self.kind = kind
        self.domain_operation_id = domain_operation_id
        super().__init__(
            f"harness_operation_domain_not_found:{kind.value}:{domain_operation_id}"
        )


class HarnessOperationBindingCorrupt(HarnessOperationBindingError):
    def __init__(
        self,
        kind: HarnessDomainOperationKind,
        domain_operation_id: str,
        reason: str,
    ) -> None:
        self.kind = kind
        self.domain_operation_id = domain_operation_id
        self.reason = reason
        super().__init__(
            "harness_operation_binding_corrupt:"
            f"{kind.value}:{domain_operation_id}:{reason}"
        )


class HarnessOperationParentNotFound(HarnessOperationBindingError):
    def __init__(self, parent_harness_operation_id: str) -> None:
        super().__init__(
            "harness_operation_parent_not_found:"
            f"{parent_harness_operation_id}"
        )


class HarnessOperationParentKindInvalid(HarnessOperationBindingError):
    def __init__(self, kind: HarnessDomainOperationKind) -> None:
        super().__init__(f"harness_operation_parent_kind_invalid:{kind.value}")


class HarnessOperationLegacyUnbound(HarnessOperationBindingError):
    def __init__(
        self,
        kind: HarnessDomainOperationKind,
        domain_operation_id: str,
    ) -> None:
        self.kind = kind
        self.domain_operation_id = domain_operation_id
        super().__init__(
            f"harness_operation_legacy_unbound:{kind.value}:{domain_operation_id}"
        )


def _to_row(binding: HarnessOperationBindingV1) -> HarnessOperationBindingRow:
    payload = binding.model_dump(mode="json")
    return HarnessOperationBindingRow(**payload)


def _from_row(row: HarnessOperationBindingRow) -> HarnessOperationBindingV1:
    return HarnessOperationBindingV1(
        schema_name=row.schema_name,
        schema_version=row.schema_version,
        harness_operation_id=row.harness_operation_id,
        domain_operation_kind=row.domain_operation_kind,
        domain_operation_id=row.domain_operation_id,
        workflow=row.workflow,
        entry_stage=row.entry_stage,
        parent_harness_operation_id=row.parent_harness_operation_id,
        admitted_at=row.admitted_at,
    )


def _domain_row_identity(
    kind: HarnessDomainOperationKind,
    row: object,
) -> tuple[HarnessDomainOperationKind, str]:
    expected_type = _DOMAIN_ROW_TYPES[kind]
    if not isinstance(row, expected_type):
        return kind, ""
    if isinstance(row, HarnessWorkflowOperationRow):
        if row.domain_operation_kind != kind.value:
            return kind, ""
        return kind, str(row.operation_id)
    operation_id = row.id if kind == HarnessDomainOperationKind.TAVERN_RUN else row.operation_id
    return kind, str(operation_id)
