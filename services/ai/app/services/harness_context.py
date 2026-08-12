from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.models.harness import (
    HarnessContextEnvelope,
    HarnessContractRef,
    HarnessResourceRef,
    HarnessSnapshotRef,
    HarnessWorkflow,
    canonical_harness_digest,
)


HARNESS_CONTEXT_SCHEMA_NAME = "HarnessContextEnvelope"
HARNESS_CONTEXT_SCHEMA_VERSION = "harness-context-v1"


@dataclass(frozen=True, slots=True)
class HarnessSnapshotMaterial:
    """Ephemeral source material used only to derive a persisted snapshot reference."""

    artifact_type: str
    artifact_id: str
    schema_version: str
    payload: Any


def build_harness_context(
    *,
    workflow: HarnessWorkflow,
    operation_id: str,
    schema_name: str,
    schema_version: str,
    typed_input: BaseModel,
    subject_refs: Sequence[HarnessResourceRef],
    component_versions: Mapping[str, str],
    snapshot_materials: Sequence[HarnessSnapshotMaterial],
    policy_version: str | None,
    prompt_version: str | None,
) -> HarnessContextEnvelope:
    """Build deterministic context evidence without retaining source payloads.

    The envelope proves the identity of supplied context. Replay still depends on
    each workflow retaining protected source artifacts and declaring truthful
    parser, prompt, model, tool, and policy versions.
    """

    _require_strict_typed_input(typed_input)
    input_digest = canonical_harness_digest(typed_input)
    canonical_subject_refs = _canonical_subject_refs(subject_refs)
    canonical_component_versions = _canonical_component_versions(component_versions)
    canonical_snapshot_refs = _canonical_snapshot_refs(snapshot_materials)

    context_manifest = {
        "schema_name": schema_name,
        "schema_version": schema_version,
        "workflow": workflow.value,
        "subject_refs": [
            item.model_dump(mode="json", exclude_none=False)
            for item in canonical_subject_refs
        ],
        "component_versions": [
            item.model_dump(mode="json", exclude_none=False)
            for item in canonical_component_versions
        ],
        "snapshot_refs": [
            item.model_dump(mode="json", exclude_none=False)
            for item in canonical_snapshot_refs
        ],
        "input_digest": input_digest,
        "policy_version": policy_version,
        "prompt_version": prompt_version,
    }

    return HarnessContextEnvelope(
        schema_name=schema_name,
        schema_version=schema_version,
        workflow=workflow,
        operation_id=operation_id,
        subject_refs=canonical_subject_refs,
        component_versions=canonical_component_versions,
        snapshot_refs=canonical_snapshot_refs,
        input_digest=input_digest,
        context_digest=canonical_harness_digest(context_manifest),
        policy_version=policy_version,
        prompt_version=prompt_version,
    )


def _require_strict_typed_input(typed_input: BaseModel) -> None:
    if not isinstance(typed_input, BaseModel):
        raise TypeError("harness_context_input_pydantic_model_required")
    if typed_input.model_config.get("extra") != "forbid":
        raise ValueError("harness_context_input_extra_forbid_required")


def _canonical_subject_refs(
    subject_refs: Sequence[HarnessResourceRef],
) -> list[HarnessResourceRef]:
    by_identity: dict[tuple[str, str], HarnessResourceRef] = {}
    for candidate in subject_refs:
        item = HarnessResourceRef.model_validate(candidate)
        identity = (item.resource_type, item.resource_id)
        existing = by_identity.get(identity)
        if existing is not None and existing != item:
            raise ValueError("harness_context_subject_ref_conflict")
        by_identity[identity] = item
    return [by_identity[key] for key in sorted(by_identity)]


def _canonical_component_versions(
    component_versions: Mapping[str, str],
) -> list[HarnessContractRef]:
    return [
        HarnessContractRef(name=name, version=component_versions[name])
        for name in sorted(component_versions)
    ]


def _canonical_snapshot_refs(
    snapshot_materials: Sequence[HarnessSnapshotMaterial],
) -> list[HarnessSnapshotRef]:
    by_identity: dict[tuple[str, str], HarnessSnapshotRef] = {}
    for material in snapshot_materials:
        item = HarnessSnapshotRef(
            artifact_type=material.artifact_type,
            artifact_id=material.artifact_id,
            schema_version=material.schema_version,
            payload_digest=canonical_harness_digest(material.payload),
        )
        identity = (item.artifact_type, item.artifact_id)
        existing = by_identity.get(identity)
        if existing is not None and existing != item:
            raise ValueError("harness_context_snapshot_ref_conflict")
        by_identity[identity] = item
    return [by_identity[key] for key in sorted(by_identity)]
