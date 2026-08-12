from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, ClassVar
import unittest

from pydantic import BaseModel, ConfigDict, ValidationError

from app.models.harness import (
    HarnessArtifactType,
    HarnessContextEnvelope,
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessResourceType,
    HarnessSafeManifest,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
    canonical_harness_context_digest,
    validate_harness_trace,
)
from app.services.harness_context import (
    build_harness_context,
    build_snapshot_ref,
    component_registry_snapshot,
    new_harness_operation_id,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "harness"
OPERATION_ID = "harness-operation-0123456789abcdef0123456789abcdef"


class _NestedManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"participant_count", "optional_marker"}
    )

    participant_count: int
    optional_marker: str | None


class _ActorInputManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"mode", "target_persona_ids", "room_revision", "nested"}
    )

    mode: str
    target_persona_ids: list[str]
    room_revision: int
    nested: _NestedManifest


class _RoomSnapshotManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"participant_ids", "last_sequence", "prompt_hashes"}
    )

    participant_ids: list[str]
    last_sequence: int
    prompt_hashes: list[str]


class _MissingAllowlist(HarnessSafeManifest):
    value: str


class _SensitiveManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"system_prompt"})

    system_prompt: str


class _OpenObjectManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"metadata"})

    metadata: dict[str, str]


class _UnorderedManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"values"})

    values: set[str]


class _FormattedManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"created_at"})

    created_at: datetime


class _AnyManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"value"})

    value: Any


class _LooseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


def _input_manifest(*, room_revision: int = 4) -> _ActorInputManifest:
    return _ActorInputManifest(
        mode="facilitated",
        target_persona_ids=["persona-a", "persona-b"],
        room_revision=room_revision,
        nested=_NestedManifest(participant_count=2, optional_marker=None),
    )


def _snapshot(*, last_sequence: int = 9):
    return build_snapshot_ref(
        artifact_type=HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,
        artifact_id="room-1-revision-4",
        contract=HarnessContractRef(
            name="TavernRoomSnapshotManifest",
            version="tavern-room-snapshot-manifest-v1",
        ),
        payload=_RoomSnapshotManifest(
            participant_ids=["persona-a", "persona-b"],
            last_sequence=last_sequence,
            prompt_hashes=["a" * 64, "b" * 64],
        ),
    )


def _build(
    *,
    operation_id: str = OPERATION_ID,
    input_manifest: HarnessSafeManifest | None = None,
    subject_refs: list[HarnessResourceRefV3] | None = None,
    snapshot_refs: list | None = None,
    policy_version: str = "tavern-harness-v1",
    prompt_version: str = "tavern-actor-v1",
) -> HarnessContextEnvelopeV3:
    return build_harness_context(
        workflow=HarnessWorkflow.TAVERN,
        stage=HarnessStage.TAVERN_ACTOR_REPLY,
        operation_id=operation_id,
        input_contract=HarnessContractRef(
            name="TavernActorInputManifest",
            version="tavern-actor-input-manifest-v1",
        ),
        input_manifest=input_manifest or _input_manifest(),
        subject_refs=subject_refs
        if subject_refs is not None
        else [
            HarnessResourceRefV3(
                resource_type=HarnessResourceType.TAVERN_ROOM,
                resource_id="room-1",
                revision=4,
            ),
            HarnessResourceRefV3(
                resource_type=HarnessResourceType.TAVERN_MESSAGE,
                resource_id="message-9",
                revision=None,
            ),
        ],
        snapshot_refs=snapshot_refs if snapshot_refs is not None else [_snapshot()],
        policy_contract=HarnessContractRef(
            name="TavernHarnessPolicy",
            version=policy_version,
        ),
        prompt_contract=HarnessContractRef(
            name="TavernActorPrompt",
            version=prompt_version,
        ),
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


class HarnessContextV3Tests(unittest.TestCase):
    def test_registered_v2_context_fixture_remains_compatible(self) -> None:
        payload = json.loads(
            (FIXTURE_ROOT / "context_foundation_v1.json").read_text(encoding="utf-8")
        )

        self.assertEqual(
            HarnessContextEnvelope.model_validate(payload).model_dump(
                mode="json",
                exclude_none=False,
            ),
            payload,
        )

    def test_golden_context_is_stable_recomputable_and_trace_safe(self) -> None:
        expected = json.loads(
            (FIXTURE_ROOT / "context_foundation_v3.json").read_text(encoding="utf-8")
        )
        context = _build()
        wire = context.model_dump(mode="json", exclude_none=False)

        self.assertEqual(wire, expected)
        self.assertEqual(context.context_digest, canonical_harness_context_digest(wire))
        self.assertNotIn("payload", _all_keys(wire))
        self.assertNotIn("system_prompt", _all_keys(wire))
        self.assertNotIn("guidance", _all_keys(wire))

    def test_order_is_canonical_and_operation_identity_is_not_in_digest(self) -> None:
        baseline = _build()
        reordered = _build(
            operation_id="harness-operation-fedcba9876543210fedcba9876543210",
            subject_refs=list(reversed(baseline.subject_refs)),
            snapshot_refs=list(reversed(baseline.snapshot_refs)),
        )

        self.assertEqual(baseline.subject_refs, reordered.subject_refs)
        self.assertEqual(baseline.snapshot_refs, reordered.snapshot_refs)
        self.assertEqual(baseline.input_digest, reordered.input_digest)
        self.assertEqual(baseline.context_digest, reordered.context_digest)
        self.assertNotEqual(baseline.operation_id, reordered.operation_id)

    def test_visible_manifest_drift_changes_or_invalidates_context_digest(self) -> None:
        baseline = _build()
        for changed in (
            _build(input_manifest=_input_manifest(room_revision=5)),
            _build(snapshot_refs=[_snapshot(last_sequence=10)]),
            _build(policy_version="tavern-harness-v2"),
            _build(prompt_version="tavern-actor-v2"),
        ):
            self.assertNotEqual(baseline.context_digest, changed.context_digest)

        tampered = baseline.model_dump(mode="json", exclude_none=False)
        tampered["policy_contract"]["version"] = "tavern-harness-v2"
        with self.assertRaisesRegex(ValidationError, "harness_context_digest_mismatch"):
            HarnessContextEnvelopeV3.model_validate(tampered)

    def test_input_contract_and_list_order_are_bound_to_input_digest(self) -> None:
        baseline = _build()
        manifest = _input_manifest()
        reordered = manifest.model_copy(
            update={"target_persona_ids": list(reversed(manifest.target_persona_ids))}
        )
        order_changed = _build(input_manifest=reordered)
        self.assertNotEqual(baseline.input_digest, order_changed.input_digest)
        self.assertNotEqual(baseline.context_digest, order_changed.context_digest)

        context = baseline.model_dump(mode="json", exclude_none=False)
        context["input_contract"]["version"] = "tavern-actor-input-manifest-v2"
        context["context_digest"] = canonical_harness_context_digest(context)
        changed = HarnessContextEnvelopeV3.model_validate(context)
        self.assertNotEqual(baseline.context_digest, changed.context_digest)

    def test_registered_stage_and_component_set_are_enforced(self) -> None:
        context = _build().model_dump(mode="json", exclude_none=False)
        context["component_versions"] = context["component_versions"][:-1]
        context["context_digest"] = canonical_harness_context_digest(context)
        with self.assertRaisesRegex(ValidationError, "harness_context_component_set_mismatch"):
            HarnessContextEnvelopeV3.model_validate(context)

        with self.assertRaisesRegex(ValueError, "harness_stage_not_registered"):
            build_harness_context(
                workflow=HarnessWorkflow.TAVERN,
                stage=HarnessStage.PLAN_GENERATION,
                operation_id=OPERATION_ID,
                input_contract=HarnessContractRef(name="Input", version="input-v1"),
                input_manifest=_input_manifest(),
                subject_refs=[],
            )

        registry = component_registry_snapshot()
        self.assertIn(
            ("tavern_actor_prompt", "tavern_actor_prompt", "tavern-actor-v1"),
            registry,
        )

    def test_typed_refs_contract_versions_and_duplicates_are_enforced(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "harness_context_mutable_subject_revision_required",
        ):
            HarnessResourceRefV3(
                resource_type=HarnessResourceType.TAVERN_ROOM,
                resource_id="room-1",
                revision=None,
            )

        with self.assertRaises(ValidationError):
            HarnessResourceRefV3(
                resource_type="unknown_resource",
                resource_id="resource-1",
                revision=None,
            )
        for invalid_id in ("/tmp/room.json", "https://example.test/room", "room\n1"):
            with self.assertRaises(ValidationError):
                HarnessResourceRefV3(
                    resource_type=HarnessResourceType.TAVERN_ROOM,
                    resource_id=invalid_id,
                    revision=1,
                )
        with self.assertRaises(ValidationError):
            build_snapshot_ref(
                artifact_type="unknown_artifact",
                artifact_id="snapshot-1",
                contract=HarnessContractRef(name="Snapshot", version="snapshot-v1"),
                payload=_RoomSnapshotManifest(
                    participant_ids=[], last_sequence=0, prompt_hashes=[]
                ),
            )
        with self.assertRaisesRegex(ValueError, "harness_contract_version_not_adopted"):
            build_snapshot_ref(
                artifact_type=HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,
                artifact_id="snapshot-1",
                contract=HarnessContractRef(name="Snapshot", version="unknown"),
                payload=_RoomSnapshotManifest(
                    participant_ids=[], last_sequence=0, prompt_hashes=[]
                ),
            )

        duplicate = _build().subject_refs[0]
        with self.assertRaisesRegex(ValueError, "harness_context_subject_ref_duplicate"):
            _build(subject_refs=[duplicate, duplicate])
        duplicate_snapshot = _snapshot()
        with self.assertRaisesRegex(ValueError, "harness_context_snapshot_ref_duplicate"):
            _build(snapshot_refs=[duplicate_snapshot, duplicate_snapshot])

    def test_manifest_allowlist_rejects_sensitive_or_unstable_shapes(self) -> None:
        with self.assertRaisesRegex(TypeError, "harness_safe_manifest_required"):
            _build(input_manifest=_LooseInput(value="unsafe"))
        for manifest, error in (
            (_MissingAllowlist(value="unsafe"), "harness_safe_manifest_allowlist_mismatch"),
            (_SensitiveManifest(system_prompt="secret"), "harness_safe_manifest_sensitive_field_forbidden"),
            (_OpenObjectManifest(metadata={"key": "value"}), "harness_safe_manifest_permissive_object_forbidden"),
            (_UnorderedManifest(values={"b", "a"}), "harness_safe_manifest_unordered_collection_forbidden"),
            (_FormattedManifest(created_at=datetime.now(timezone.utc)), "harness_safe_manifest_formatted_scalar_forbidden"),
            (_AnyManifest(value="anything"), "harness_safe_manifest_any_forbidden"),
        ):
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValueError, error):
                    _build(input_manifest=manifest)

    def test_non_finite_values_and_operation_ids_are_rejected(self) -> None:
        payload = _input_manifest().model_dump(mode="python")
        payload["room_revision"] = float("nan")
        with self.assertRaises((ValidationError, ValueError)):
            _build(input_manifest=_ActorInputManifest.model_validate(payload))

        with self.assertRaises(ValidationError):
            _build(operation_id="caller-owned-operation")
        self.assertRegex(new_harness_operation_id(), r"^harness-operation-[0-9a-f]{32}$")

    def test_pending_component_registry_blocks_unadopted_workflow(self) -> None:
        with self.assertRaisesRegex(ValueError, "harness_contract_version_not_adopted"):
            build_harness_context(
                workflow=HarnessWorkflow.PLANNING,
                stage=HarnessStage.PLAN_GENERATION,
                operation_id=OPERATION_ID,
                input_contract=HarnessContractRef(
                    name="PlanningInputManifest",
                    version="planning-input-manifest-v1",
                ),
                input_manifest=_input_manifest(),
                subject_refs=[],
            )

    def test_v3_trace_fixture_binds_context_identity(self) -> None:
        payload = json.loads(
            (FIXTURE_ROOT / "passed_not_applicable_v3.json").read_text(
                encoding="utf-8"
            )
        )
        trace = validate_harness_trace(payload)
        self.assertIsInstance(trace, HarnessTraceV3)

        for field, value, error in (
            (
                "operation_id",
                "harness-operation-33333333333333333333333333333333",
                "harness_context_operation_mismatch",
            ),
            ("workflow", "study_chat", "harness_context_workflow_mismatch"),
            ("stage", "study_chat_reply", "harness_context_stage_mismatch"),
        ):
            changed = json.loads(json.dumps(payload))
            changed[field] = value
            with self.assertRaisesRegex(ValidationError, error):
                HarnessTraceV3.model_validate(changed)


if __name__ == "__main__":
    unittest.main()
