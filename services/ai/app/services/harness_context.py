from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import get_args
from uuid import uuid4

from pydantic import BaseModel

from app.models.harness import (
    HARNESS_CONTEXT_CONTRACT_V3,
    HARNESS_CONTEXT_DIGEST_CONTRACT_V1,
    HarnessArtifactType,
    HarnessComponentName,
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessSafeManifest,
    HarnessSnapshotRefV3,
    HarnessStage,
    HarnessWorkflow,
    HARNESS_STAGE_COMPONENT_NAMES,
    canonical_harness_context_digest,
    canonical_harness_digest,
    require_versioned_harness_contract,
)


# A registry entry records a known code surface, not Harness adoption. Placeholder
# versions remain deliberately unusable until the owning workflow assigns a
# truthful version and completes its own migration task.
_COMPONENT_REGISTRY = MappingProxyType(
    {
        HarnessComponentName.DOCUMENT_PARSER: HarnessContractRef(
            name="document_parser",
            version="pending-document-parser-version-v1",
        ),
        HarnessComponentName.OCR_ENGINE: HarnessContractRef(
            name="ocr_engine",
            version="pending-ocr-engine-version-v1",
        ),
        HarnessComponentName.STUDY_UNIT_CLEANER: HarnessContractRef(
            name="study_unit_cleaner",
            version="pending-study-unit-cleaner-version-v1",
        ),
        HarnessComponentName.PLANNING_PROMPT: HarnessContractRef(
            name="planning_prompt",
            version="pending-planning-prompt-version-v1",
        ),
        HarnessComponentName.PLANNING_TOOLSET: HarnessContractRef(
            name="planning_toolset",
            version="pending-planning-toolset-version-v1",
        ),
        HarnessComponentName.PERSONA_COMPILER: HarnessContractRef(
            name="persona_compiler",
            version="pending-persona-compiler-version-v1",
        ),
        HarnessComponentName.SCENE_COMPILER: HarnessContractRef(
            name="scene_compiler",
            version="pending-scene-compiler-version-v1",
        ),
        HarnessComponentName.STUDY_CHAT_PROMPT: HarnessContractRef(
            name="study_chat_prompt",
            version="pending-study-chat-prompt-version-v1",
        ),
        HarnessComponentName.STUDY_CHAT_TOOLSET: HarnessContractRef(
            name="study_chat_toolset",
            version="pending-study-chat-toolset-version-v1",
        ),
        HarnessComponentName.TAVERN_PERSONA_COMPILER: HarnessContractRef(
            name="tavern_persona_compiler",
            version="tavern-persona-compiler-v1",
        ),
        HarnessComponentName.TAVERN_ACTOR_PROMPT: HarnessContractRef(
            name="tavern_actor_prompt",
            version="tavern-actor-v1",
        ),
        HarnessComponentName.TAVERN_SCHEDULER: HarnessContractRef(
            name="tavern_scheduler",
            version="tavern-schedule-v1",
        ),
        HarnessComponentName.FRONTEND_DECODER: HarnessContractRef(
            name="frontend_decoder",
            version="pending-frontend-decoder-version-v1",
        ),
    }
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
    operation_id: str,
    input_contract: HarnessContractRef,
    input_manifest: HarnessSafeManifest,
    subject_refs: Iterable[HarnessResourceRefV3],
    snapshot_refs: Iterable[HarnessSnapshotRefV3] = (),
    policy_contract: HarnessContractRef | None = None,
    prompt_contract: HarnessContractRef | None = None,
) -> HarnessContextEnvelopeV3:
    """Build a trace-safe context from registered stage components."""

    component_keys = HARNESS_STAGE_COMPONENT_NAMES.get((workflow, stage))
    if component_keys is None:
        raise ValueError("harness_stage_not_registered")
    component_versions = sorted(
        (_COMPONENT_REGISTRY[item].model_copy(deep=True) for item in component_keys),
        key=lambda item: item.name,
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
        "operation_id": operation_id,
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


def component_registry_snapshot() -> tuple[tuple[str, str, str], ...]:
    """Expose immutable version evidence for golden tests and audits."""

    return tuple(
        (key.value, contract.name, contract.version)
        for key, contract in sorted(_COMPONENT_REGISTRY.items(), key=lambda item: item[0].value)
    )


def new_harness_operation_id() -> str:
    """Allocate a server-owned logical operation identity."""

    return f"harness-operation-{uuid4().hex}"


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
    _validate_nested_manifest_allowlists(type(payload))
    _reject_permissive_json_objects(type(payload).model_json_schema())


def _validate_nested_manifest_allowlists(model_type: type[BaseModel]) -> None:
    for field in model_type.model_fields.values():
        for candidate in _model_types(field.annotation):
            if issubclass(candidate, HarnessSafeManifest):
                declared = candidate.trace_safe_fields
                actual = frozenset(candidate.model_fields)
                if not declared or declared != actual:
                    raise ValueError("harness_safe_manifest_allowlist_mismatch")
                _validate_nested_manifest_allowlists(candidate)


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
