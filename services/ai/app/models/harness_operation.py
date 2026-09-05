from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.models.harness import HarnessStage, HarnessWorkflow


HARNESS_OPERATION_BINDING_SCHEMA_NAME = "HarnessOperationBindingV1"
HARNESS_OPERATION_BINDING_SCHEMA_VERSION = "harness-operation-binding-v1"
HARNESS_OPERATION_ID_PATTERN = r"^harness-operation-[0-9a-f]{32}$"
DOMAIN_OPERATION_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$"


class HarnessDomainOperationKind(StrEnum):
    DOCUMENT_PROCESS = "document_process"
    DOCUMENT_OCR = "document_ocr"
    STUDY_UNIT_CLEANUP = "study_unit_cleanup"
    LEARNING_PLAN_GENERATION = "learning_plan_generation"
    PERSONA_GENERATION = "persona_generation"
    SCENE_GENERATION = "scene_generation"
    STUDY_CHAT = "study_chat"
    TAVERN_RUN = "tavern_run"


HARNESS_DOMAIN_OPERATION_ROUTES = MappingProxyType(
    {
        HarnessDomainOperationKind.DOCUMENT_PROCESS: (
            HarnessWorkflow.DOCUMENT_PARSE,
            HarnessStage.DOCUMENT_PARSE,
        ),
        HarnessDomainOperationKind.DOCUMENT_OCR: (
            HarnessWorkflow.OCR,
            HarnessStage.OCR_PAGE,
        ),
        HarnessDomainOperationKind.STUDY_UNIT_CLEANUP: (
            HarnessWorkflow.STUDY_UNIT_CLEANUP,
            HarnessStage.STUDY_UNIT_CLEANUP,
        ),
        HarnessDomainOperationKind.LEARNING_PLAN_GENERATION: (
            HarnessWorkflow.PLANNING,
            HarnessStage.PLAN_GENERATION,
        ),
        HarnessDomainOperationKind.PERSONA_GENERATION: (
            HarnessWorkflow.PERSONA,
            HarnessStage.PERSONA_GENERATION,
        ),
        HarnessDomainOperationKind.SCENE_GENERATION: (
            HarnessWorkflow.SCENE,
            HarnessStage.SCENE_GENERATION,
        ),
        HarnessDomainOperationKind.STUDY_CHAT: (
            HarnessWorkflow.STUDY_CHAT,
            HarnessStage.STUDY_CHAT_REPLY,
        ),
        HarnessDomainOperationKind.TAVERN_RUN: (
            HarnessWorkflow.TAVERN,
            HarnessStage.TAVERN_ACTOR_REPLY,
        ),
    }
)


class HarnessOperationResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    LEGACY_UNBOUND = "legacy_unbound"
    NOT_FOUND = "not_found"


class _HarnessOperationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class HarnessOperationBindingV1(_HarnessOperationModel):
    """Immutable server-owned mapping from a domain admission to Harness identity."""

    schema_name: Literal["HarnessOperationBindingV1"] = (
        HARNESS_OPERATION_BINDING_SCHEMA_NAME
    )
    schema_version: Literal["harness-operation-binding-v1"] = (
        HARNESS_OPERATION_BINDING_SCHEMA_VERSION
    )
    harness_operation_id: str = Field(pattern=HARNESS_OPERATION_ID_PATTERN)
    domain_operation_kind: HarnessDomainOperationKind
    domain_operation_id: str = Field(pattern=DOMAIN_OPERATION_ID_PATTERN)
    workflow: HarnessWorkflow
    entry_stage: HarnessStage
    parent_harness_operation_id: str | None = Field(
        default=None,
        pattern=HARNESS_OPERATION_ID_PATTERN,
    )
    admitted_at: AwareDatetime

    @model_validator(mode="after")
    def validate_binding(self) -> "HarnessOperationBindingV1":
        if self.admitted_at.utcoffset() != timedelta(0):
            raise ValueError("harness_operation_admitted_at_must_be_utc")
        expected_route = HARNESS_DOMAIN_OPERATION_ROUTES.get(
            self.domain_operation_kind
        )
        if expected_route != (self.workflow, self.entry_stage):
            raise ValueError("harness_operation_domain_route_mismatch")
        if self.parent_harness_operation_id == self.harness_operation_id:
            raise ValueError("harness_operation_parent_self_reference")
        if (
            self.parent_harness_operation_id is not None
            and self.domain_operation_kind != HarnessDomainOperationKind.TAVERN_RUN
        ):
            raise ValueError("harness_operation_parent_kind_invalid")
        return self


class HarnessOperationResolutionV1(_HarnessOperationModel):
    """Typed lookup result; absence never causes an identity to be fabricated."""

    status: HarnessOperationResolutionStatus
    domain_operation_kind: HarnessDomainOperationKind
    domain_operation_id: str = Field(pattern=DOMAIN_OPERATION_ID_PATTERN)
    binding: HarnessOperationBindingV1 | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> "HarnessOperationResolutionV1":
        if self.status == HarnessOperationResolutionStatus.RESOLVED:
            if self.binding is None:
                raise ValueError("harness_operation_resolution_binding_required")
            if (
                self.binding.domain_operation_kind != self.domain_operation_kind
                or self.binding.domain_operation_id != self.domain_operation_id
            ):
                raise ValueError("harness_operation_resolution_identity_mismatch")
        elif self.binding is not None:
            raise ValueError("harness_operation_unresolved_has_binding")
        return self


def utc_datetime(value: datetime | str) -> datetime:
    """Strictly normalize a binding timestamp without accepting naive values."""

    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("harness_operation_admitted_at_must_be_utc")
    return parsed


def new_harness_operation_id() -> str:
    """Allocate one server-owned logical operation identity."""

    return f"harness-operation-{uuid4().hex}"
