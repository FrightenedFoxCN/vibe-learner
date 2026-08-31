from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
import math
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin

from pydantic import BaseModel

from app.models.harness import (
    HARNESS_CONTEXT_CONTRACT_V3,
    HARNESS_CONTEXT_DIGEST_CONTRACT_V1,
    HARNESS_COMPONENT_REGISTRATIONS,
    HarnessArtifactType,
    HarnessComponentName,
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessSafeManifest,
    HarnessSnapshotRefV3,
    HarnessStage,
    HarnessWorkflow,
    canonical_harness_context_digest,
    canonical_harness_digest,
    registered_harness_stage_component_contracts,
    require_versioned_harness_contract,
)
from app.models.harness_operation import (
    HarnessOperationBindingV1,
    new_harness_operation_id,
)
from app.models.harness_manifest import (
    require_executable_workflow_manifest_entry,
    validate_harness_context_manifest_inputs,
)


def digest_safe_manifest(
    *,
    contract: HarnessContractRef,
    payload: HarnessSafeManifest,
) -> str:
    """Digest a reviewed manifest and bind the digest to its contract version."""

    _validate_safe_manifest(payload)
    _require_adopted_contract(contract)
    manifest = {
        "contract": contract.model_dump(mode="json", exclude_none=False),
        "payload": payload.model_dump(mode="json", exclude_none=False),
    }
    return canonical_harness_digest(manifest)


def build_snapshot_ref(
    *,
    artifact_type: HarnessArtifactType,
    artifact_id: str,
    contract: HarnessContractRef,
    payload: HarnessSafeManifest,
) -> HarnessSnapshotRefV3:
    """Build an integrity reference; availability and replay are not asserted."""

    return HarnessSnapshotRefV3(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        contract=contract,
        payload_digest=digest_safe_manifest(contract=contract, payload=payload),
    )


def build_harness_context(
    *,
    workflow: HarnessWorkflow,
    stage: HarnessStage,
    operation_binding: HarnessOperationBindingV1,
    input_contract: HarnessContractRef,
    input_manifest: HarnessSafeManifest,
    subject_refs: Iterable[HarnessResourceRefV3],
    snapshot_refs: Iterable[HarnessSnapshotRefV3] = (),
    policy_contract: HarnessContractRef | None = None,
    prompt_contract: HarnessContractRef | None = None,
) -> HarnessContextEnvelopeV3:
    """Build a trace-safe context from one admitted, immutable operation binding."""

    manifest_entry = require_executable_workflow_manifest_entry(workflow, stage)
    if operation_binding.workflow != workflow:
        raise ValueError("harness_context_operation_workflow_mismatch")
    component_versions = list(
        registered_harness_stage_component_contracts(workflow, stage)
    )
    for contract in (
        input_contract,
        policy_contract,
        prompt_contract,
        *component_versions,
    ):
        if contract is not None:
            _require_adopted_contract(contract)

    sorted_subjects = _sorted_unique_subjects(subject_refs)
    sorted_snapshots = _sorted_unique_snapshots(snapshot_refs)
    validate_harness_context_manifest_inputs(
        entry=manifest_entry,
        input_contract=input_contract,
        prompt_contract=prompt_contract,
        policy_contract=policy_contract,
        component_contracts=tuple(component_versions),
        artifact_types=tuple(item.artifact_type for item in sorted_snapshots),
    )
    input_digest = digest_safe_manifest(
        contract=input_contract,
        payload=input_manifest,
    )
    draft: dict[str, object] = {
        "context_contract": HARNESS_CONTEXT_CONTRACT_V3.model_dump(
            mode="json",
            exclude_none=False,
        ),
        "workflow": workflow.value,
        "stage": stage.value,
        "operation_id": operation_binding.harness_operation_id,
        "input_contract": input_contract.model_dump(mode="json", exclude_none=False),
        "subject_refs": [
            item.model_dump(mode="json", exclude_none=False)
            for item in sorted_subjects
        ],
        "component_versions": [
            item.model_dump(mode="json", exclude_none=False)
            for item in component_versions
        ],
        "snapshot_refs": [
            item.model_dump(mode="json", exclude_none=False)
            for item in sorted_snapshots
        ],
        "digest_algorithm": "sha256",
        "digest_contract": HARNESS_CONTEXT_DIGEST_CONTRACT_V1.model_dump(
            mode="json",
            exclude_none=False,
        ),
        "input_digest": input_digest,
        "context_digest": "0" * 64,
        "policy_contract": (
            policy_contract.model_dump(mode="json", exclude_none=False)
            if policy_contract
            else None
        ),
        "prompt_contract": (
            prompt_contract.model_dump(mode="json", exclude_none=False)
            if prompt_contract
            else None
        ),
    }
    draft["context_digest"] = canonical_harness_context_digest(draft)
    return HarnessContextEnvelopeV3.model_validate(draft)


def component_registry_snapshot() -> tuple[tuple[str, str, str | None], ...]:
    """Expose immutable version evidence for golden tests and audits."""

    return tuple(
        (
            key.value,
            registration.contract.name if registration.contract else key.value,
            registration.contract.version if registration.contract else None,
        )
        for key, registration in sorted(
            HARNESS_COMPONENT_REGISTRATIONS.items(),
            key=lambda item: item[0].value,
        )
    )


def _require_adopted_contract(contract: HarnessContractRef) -> None:
    require_versioned_harness_contract(contract)


def _validate_safe_manifest(payload: HarnessSafeManifest) -> None:
    if not isinstance(payload, HarnessSafeManifest):
        raise TypeError("harness_safe_manifest_required")
    if type(payload) is HarnessSafeManifest:
        raise ValueError("harness_safe_manifest_concrete_type_required")
    declared = type(payload).trace_safe_fields
    actual = frozenset(type(payload).model_fields)
    if not declared or declared != actual:
        raise ValueError("harness_safe_manifest_allowlist_mismatch")
    _reject_aliases_or_custom_serializers(type(payload))
    _validate_nested_manifest_allowlists(type(payload))
    _reject_permissive_json_objects(type(payload).model_json_schema())
    _validate_safe_field_types(type(payload))
    _reject_non_finite_numbers(
        payload.model_dump(mode="json", exclude_none=False),
    )


def _reject_aliases_or_custom_serializers(model_type: type[BaseModel]) -> None:
    for field in model_type.model_fields.values():
        if any(
            value is not None
            for value in (field.alias, field.validation_alias, field.serialization_alias)
        ):
            raise ValueError("harness_safe_manifest_alias_forbidden")
    decorators = model_type.__pydantic_decorators__
    if (
        decorators.field_serializers
        or decorators.model_serializers
        or decorators.computed_fields
    ):
        raise ValueError("harness_safe_manifest_custom_serialization_forbidden")


def _validate_nested_manifest_allowlists(model_type: type[BaseModel]) -> None:
    for field in model_type.model_fields.values():
        for candidate in _model_types(field.annotation):
            if not issubclass(candidate, HarnessSafeManifest):
                raise ValueError("harness_safe_manifest_nested_type_required")
            declared = candidate.trace_safe_fields
            actual = frozenset(candidate.model_fields)
            if not declared or declared != actual:
                raise ValueError("harness_safe_manifest_allowlist_mismatch")
            _reject_aliases_or_custom_serializers(candidate)
            _validate_nested_manifest_allowlists(candidate)


def _validate_safe_field_types(model_type: type[BaseModel]) -> None:
    for field in model_type.model_fields.values():
        if field.metadata:
            raise ValueError("harness_safe_manifest_annotated_type_forbidden")
        _validate_safe_annotation(field.annotation)


def _validate_safe_annotation(annotation: object) -> None:
    if annotation in {str, int, float, bool, type(None)}:
        return
    if isinstance(annotation, type) and issubclass(annotation, HarnessSafeManifest):
        _validate_safe_field_types(annotation)
        return
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        for member in annotation:
            if member.value is not None and type(member.value) not in {
                str,
                int,
                float,
                bool,
            }:
                raise ValueError("harness_safe_manifest_enum_value_forbidden")
            if type(member.value) is float and not math.isfinite(member.value):
                raise ValueError("harness_safe_manifest_non_finite_number_forbidden")
        return

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Annotated:
        raise ValueError("harness_safe_manifest_annotated_type_forbidden")
    if origin is list:
        if len(arguments) != 1:
            raise ValueError("harness_safe_manifest_field_type_forbidden")
        _validate_safe_annotation(arguments[0])
        return
    if origin is tuple:
        for argument in arguments:
            if argument is not Ellipsis:
                _validate_safe_annotation(argument)
        return
    if origin in {Union, UnionType}:
        for argument in arguments:
            _validate_safe_annotation(argument)
        return
    if origin is Literal:
        if not all(
            value is None or type(value) in {str, int, float, bool}
            for value in arguments
        ):
            raise ValueError("harness_safe_manifest_field_type_forbidden")
        return
    raise ValueError("harness_safe_manifest_field_type_forbidden")


def _reject_non_finite_numbers(value: object) -> None:
    if type(value) is float and not math.isfinite(value):
        raise ValueError("harness_safe_manifest_non_finite_number_forbidden")
    if isinstance(value, dict):
        for item in value.values():
            _reject_non_finite_numbers(item)
    elif isinstance(value, list):
        for item in value:
            _reject_non_finite_numbers(item)


def _model_types(annotation: object) -> tuple[type[BaseModel], ...]:
    found: list[type[BaseModel]] = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        found.append(annotation)
    for child in get_args(annotation):
        found.extend(_model_types(child))
    return tuple(found)


def _reject_permissive_json_objects(node: object) -> None:
    if isinstance(node, dict):
        if not node:
            raise ValueError("harness_safe_manifest_any_forbidden")
        if "title" in node and not any(
            key in node for key in ("type", "$ref", "anyOf", "oneOf", "allOf", "enum", "const")
        ):
            raise ValueError("harness_safe_manifest_any_forbidden")
        if node.get("type") == "object" and node.get("additionalProperties") is not False:
            raise ValueError("harness_safe_manifest_permissive_object_forbidden")
        if node.get("uniqueItems") is True:
            raise ValueError("harness_safe_manifest_unordered_collection_forbidden")
        if node.get("format"):
            raise ValueError("harness_safe_manifest_formatted_scalar_forbidden")
        properties = node.get("properties")
        if isinstance(properties, dict):
            for field_name in properties:
                if _is_sensitive_manifest_field(field_name):
                    raise ValueError("harness_safe_manifest_sensitive_field_forbidden")
        for value in node.values():
            _reject_permissive_json_objects(value)
    elif isinstance(node, list):
        for value in node:
            _reject_permissive_json_objects(value)


def _is_sensitive_manifest_field(name: str) -> bool:
    normalized = name.lower()
    if normalized in {
        "token",
        "api_token",
        "access_token",
        "auth_token",
        "bearer_token",
        "refresh_token",
    }:
        return True
    return any(
        token in normalized
        for token in (
            "api_key",
            "password",
            "secret",
            "system_prompt",
            "guidance",
            "raw_document",
            "transcript",
            "file_path",
            "filename",
            "email",
        )
    )


def _sorted_unique_subjects(
    refs: Iterable[HarnessResourceRefV3],
) -> list[HarnessResourceRefV3]:
    items = sorted(
        (item.model_copy(deep=True) for item in refs),
        key=lambda item: (item.resource_type.value, item.resource_id),
    )
    identities = [(item.resource_type.value, item.resource_id) for item in items]
    if len(identities) != len(set(identities)):
        raise ValueError("harness_context_subject_ref_duplicate")
    return items


def _sorted_unique_snapshots(
    refs: Iterable[HarnessSnapshotRefV3],
) -> list[HarnessSnapshotRefV3]:
    items = sorted(
        (item.model_copy(deep=True) for item in refs),
        key=lambda item: (item.artifact_type.value, item.artifact_id),
    )
    identities = [(item.artifact_type.value, item.artifact_id) for item in items]
    if len(identities) != len(set(identities)):
        raise ValueError("harness_context_snapshot_ref_duplicate")
    return items
