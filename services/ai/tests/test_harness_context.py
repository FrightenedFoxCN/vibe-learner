from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import json
from pathlib import Path
from typing import Annotated, Any, ClassVar
import unittest

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    ValidationError,
    WithJsonSchema,
    field_serializer,
)

from app.models.harness import (
    HARNESS_RESOURCE_EVIDENCE_POLICIES,
    HarnessArtifactType,
    HarnessCommitEvidencePolicy,
    HarnessCommitEvidenceV3,
    HarnessCommittedResourceRefV3,
    HarnessContextEvidencePolicy,
    HarnessContextEnvelope,
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessResourceEvidencePolicy,
    HarnessResourceSemantics,
    HarnessResourceType,
    HarnessRollbackEvidencePolicy,
    HarnessSafeManifest,
    HarnessSnapshotRefV3,
    HarnessStage,
    HarnessTraceV3,
    HarnessWorkflow,
    canonical_harness_context_digest,
    canonical_harness_commit_digest,
    harness_resource_evidence_policy_registry_snapshot,
    validate_harness_trace,
    validate_harness_resource_evidence_policy_registry,
)
from app.services.harness_context import (
    build_harness_context,
    build_snapshot_ref,
    component_registry_snapshot,
    new_harness_operation_id,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "harness"
POLICY_FIXTURE = (
    Path(__file__).parents[3]
    / "packages"
    / "shared"
    / "fixtures"
    / "harness"
    / "resource-evidence-policies-v1.json"
)
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


class _AliasManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"system_prompt"})

    system_prompt: str = Field(alias="mode")


class _SerializerManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"value"})

    value: str

    @field_serializer("value")
    def serialize_value(self, value: str) -> object:
        return {"system_prompt": value}


class _PlainNestedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str


class _PlainNestedManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"nested"})

    nested: _PlainNestedModel


class _DecimalManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"value"})

    value: Decimal


_AnnotatedSecret = Annotated[
    str,
    PlainSerializer(
        lambda value: {"system_prompt": value},
        return_type=dict[str, str],
    ),
    WithJsonSchema({"type": "string"}),
]


class _AnnotatedSerializerManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"value"})

    value: _AnnotatedSecret


class _PathEnum(Enum):
    SECRET = Path("/tmp/secret")


class _DecimalEnum(Enum):
    VALUE = Decimal("1.25")


class _UnsafeEnumManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset({"value"})

    value: _PathEnum | _DecimalEnum


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

        context = _build().model_dump(mode="json", exclude_none=False)
        context["component_versions"][0]["version"] = "forged-component-v999"
        context["context_digest"] = canonical_harness_context_digest(context)
        with self.assertRaisesRegex(
            ValidationError,
            "harness_context_component_version_mismatch",
        ):
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
        unversioned_room = HarnessResourceRefV3(
            resource_type=HarnessResourceType.TAVERN_ROOM,
            resource_id="room-1",
            revision=None,
        )
        with self.assertRaisesRegex(
            (ValidationError, ValueError),
            "harness_context_resource_revision_required",
        ):
            _build(subject_refs=[unversioned_room])

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
            (_AliasManifest(mode="secret"), "harness_safe_manifest_alias_forbidden"),
            (_SerializerManifest(value="secret"), "harness_safe_manifest_custom_serialization_forbidden"),
            (_PlainNestedManifest(nested=_PlainNestedModel(value="unsafe")), "harness_safe_manifest_nested_type_required"),
            (_DecimalManifest(value=Decimal("1.25")), "harness_safe_manifest_field_type_forbidden"),
            (_AnnotatedSerializerManifest(value="secret"), "harness_safe_manifest_annotated_type_forbidden"),
            (_UnsafeEnumManifest(value=_PathEnum.SECRET), "harness_safe_manifest_enum_value_forbidden"),
            (_UnsafeEnumManifest(value=_DecimalEnum.VALUE), "harness_safe_manifest_enum_value_forbidden"),
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

        changed = json.loads(json.dumps(payload))
        changed["contract"]["version"] = "unknown"
        with self.assertRaisesRegex(
            ValidationError,
            "harness_contract_version_not_adopted",
        ):
            HarnessTraceV3.model_validate(changed)

    def test_resource_evidence_policy_registry_is_exhaustive(self) -> None:
        expected = json.loads(POLICY_FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(
            set(HARNESS_RESOURCE_EVIDENCE_POLICIES),
            set(HarnessResourceType),
        )
        self.assertEqual(
            harness_resource_evidence_policy_registry_snapshot(),
            expected,
        )
        self.assertEqual(
            HARNESS_RESOURCE_EVIDENCE_POLICIES[HarnessResourceType.TAVERN_ROOM],
            HarnessResourceEvidencePolicy(
                semantics=HarnessResourceSemantics.REVISIONED_CONTROL_AGGREGATE,
                context_evidence=HarnessContextEvidencePolicy.AUTHORITATIVE_REVISION,
                commit_evidence=HarnessCommitEvidencePolicy.REVISION,
                rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
            ),
        )
        self.assertEqual(
            HARNESS_RESOURCE_EVIDENCE_POLICIES[
                HarnessResourceType.TAVERN_MESSAGE
            ].commit_evidence,
            HarnessCommitEvidencePolicy.SEQUENCE,
        )
        self.assertEqual(
            HARNESS_RESOURCE_EVIDENCE_POLICIES[
                HarnessResourceType.TAVERN_MESSAGE
            ].context_evidence,
            HarnessContextEvidencePolicy.UNSUPPORTED,
        )
        self.assertEqual(
            HARNESS_RESOURCE_EVIDENCE_POLICIES[
                HarnessResourceType.STUDY_UNIT
            ].semantics,
            HarnessResourceSemantics.PARENT_BOUND,
        )

        missing = dict(HARNESS_RESOURCE_EVIDENCE_POLICIES)
        missing.pop(HarnessResourceType.DOCUMENT)
        with self.assertRaisesRegex(
            ValueError,
            "harness_resource_evidence_policy_registry_incomplete",
        ):
            validate_harness_resource_evidence_policy_registry(missing)

        extra = dict(HARNESS_RESOURCE_EVIDENCE_POLICIES)
        extra["unknown"] = next(iter(extra.values()))
        with self.assertRaisesRegex(
            ValueError,
            "harness_resource_evidence_policy_registry_incomplete",
        ):
            validate_harness_resource_evidence_policy_registry(extra)

        invalid = dict(HARNESS_RESOURCE_EVIDENCE_POLICIES)
        invalid[HarnessResourceType.DOCUMENT] = object()
        with self.assertRaisesRegex(
            ValueError,
            "harness_resource_evidence_policy_registry_invalid",
        ):
            validate_harness_resource_evidence_policy_registry(invalid)

        inconsistent = dict(HARNESS_RESOURCE_EVIDENCE_POLICIES)
        inconsistent[HarnessResourceType.DOCUMENT] = HarnessResourceEvidencePolicy(
            semantics=HarnessResourceSemantics.UNVERSIONED_MUTABLE,
            context_evidence=HarnessContextEvidencePolicy.AUTHORITATIVE_REVISION,
            commit_evidence=HarnessCommitEvidencePolicy.REVISION,
            rollback_evidence=HarnessRollbackEvidencePolicy.UNSUPPORTED,
        )
        with self.assertRaisesRegex(
            ValueError,
            "harness_resource_evidence_policy_registry_inconsistent",
        ):
            validate_harness_resource_evidence_policy_registry(inconsistent)

    def test_context_revision_evidence_follows_resource_policy(self) -> None:
        self.assertEqual(
            HarnessResourceRefV3(
                resource_type=HarnessResourceType.TAVERN_ROOM,
                resource_id="room-1",
                revision=4,
            ).revision,
            4,
        )
        for resource_type in (
            HarnessResourceType.DOCUMENT,
            HarnessResourceType.STUDY_UNIT,
            HarnessResourceType.TAVERN_RUN,
            HarnessResourceType.TAVERN_MESSAGE,
            HarnessResourceType.FRONTEND_REQUEST,
        ):
            for revision in (None, 0):
                resource = HarnessResourceRefV3(
                    resource_type=resource_type,
                    resource_id=f"{resource_type.value}-1",
                    revision=revision,
                )
                with self.assertRaisesRegex(
                    (ValidationError, ValueError),
                    "harness_context_resource_policy_unsupported",
                ):
                    _build(subject_refs=[resource])

    def test_v3_revision_commit_requires_complete_revision_evidence(self) -> None:
        payload = {
            "status": "committed",
            "effect_batch_id": "effect-room-update-1",
            "payload_contract": {
                "name": "TavernRoomCommit",
                "version": "tavern-room-commit-v1",
            },
            "digest_algorithm": "sha256",
            "digest_scope": "committed_projection",
            "attempted_resource_refs": [
                {
                    "resource_type": "tavern_room",
                    "resource_id": "room-1",
                    "revision": 4,
                }
            ],
            "committed_resources": [
                {
                    "resource_type": "tavern_room",
                    "resource_id": "room-1",
                    "expected_revision": 4,
                    "committed_revision": None,
                    "first_sequence": None,
                    "last_sequence": None,
                    "payload_digest": "a" * 64,
                }
            ],
            "payload_digest": "a" * 64,
            "committed_at": "2026-08-12T10:00:00Z",
            "rollback_reason_code": "",
            "rolled_back_at": None,
        }
        with self.assertRaisesRegex(
            ValidationError,
            "harness_revision_commit_evidence_required",
        ):
            HarnessCommitEvidenceV3.model_validate(payload)

        committed = payload["committed_resources"][0]
        committed["committed_revision"] = 5
        committed["first_sequence"] = 1
        committed["last_sequence"] = 1
        with self.assertRaisesRegex(
            ValidationError,
            "harness_revision_commit_sequence_forbidden",
        ):
            HarnessCommitEvidenceV3.model_validate(payload)

        committed["first_sequence"] = None
        committed["last_sequence"] = None
        self.assertEqual(
            HarnessCommitEvidenceV3.model_validate(payload)
            .committed_resources[0]
            .committed_revision,
            5,
        )

        committed["committed_revision"] = 6
        with self.assertRaisesRegex(
            ValidationError,
            "harness_revision_commit_increment_invalid",
        ):
            HarnessCommitEvidenceV3.model_validate(payload)
        committed["committed_revision"] = 5

        missing_attempt_revision = {**payload}
        missing_attempt_revision["attempted_resource_refs"] = [
            {
                "resource_type": "tavern_room",
                "resource_id": "room-1",
                "revision": None,
            }
        ]
        with self.assertRaisesRegex(
            ValidationError,
            "harness_revision_commit_attempt_revision_required",
        ):
            HarnessCommitEvidenceV3.model_validate(missing_attempt_revision)

    def test_v3_sequence_commit_requires_sequence_only_evidence(self) -> None:
        base = {
            "resource_type": "tavern_message",
            "resource_id": "message-10",
            "expected_revision": None,
            "committed_revision": None,
            "first_sequence": 10,
            "last_sequence": 10,
            "payload_digest": "b" * 64,
        }
        def evidence(committed: dict[str, object]) -> dict[str, object]:
            return {
                "status": "committed",
                "effect_batch_id": "effect-message-1",
                "payload_contract": {
                    "name": "TavernMessageCommit",
                    "version": "tavern-message-commit-v1",
                },
                "digest_algorithm": "sha256",
                "digest_scope": "committed_projection",
                "attempted_resource_refs": [
                    {
                        "resource_type": "tavern_message",
                        "resource_id": "message-10",
                        "revision": None,
                    }
                ],
                "committed_resources": [committed],
                "payload_digest": "b" * 64,
                "committed_at": "2026-08-12T10:00:00Z",
                "rollback_reason_code": "",
                "rolled_back_at": None,
            }

        self.assertEqual(
            HarnessCommitEvidenceV3.model_validate(evidence(base))
            .committed_resources[0]
            .first_sequence,
            10,
        )

        missing_sequence = {**base, "first_sequence": None, "last_sequence": None}
        with self.assertRaisesRegex(
            ValidationError,
            "harness_sequence_commit_evidence_required",
        ):
            HarnessCommitEvidenceV3.model_validate(evidence(missing_sequence))

        fake_revision = {**base, "expected_revision": 0, "committed_revision": 1}
        with self.assertRaisesRegex(
            ValidationError,
            "harness_sequence_commit_revision_forbidden",
        ):
            HarnessCommitEvidenceV3.model_validate(evidence(fake_revision))

        fake_attempt = evidence(base)
        fake_attempt["attempted_resource_refs"][0]["revision"] = 0
        with self.assertRaisesRegex(
            ValidationError,
            "harness_sequence_commit_attempt_revision_forbidden",
        ):
            HarnessCommitEvidenceV3.model_validate(fake_attempt)

        sequence_range = {**base, "first_sequence": 9, "last_sequence": 10}
        with self.assertRaisesRegex(
            ValidationError,
            "harness_message_commit_sequence_must_be_single",
        ):
            HarnessCommitEvidenceV3.model_validate(evidence(sequence_range))

    def test_v3_unsupported_resources_can_record_attempt_but_not_commit_or_rollback(
        self,
    ) -> None:
        for resource_type in (
            HarnessResourceType.DOCUMENT,
            HarnessResourceType.DOCUMENT_PAGE,
            HarnessResourceType.STUDY_UNIT,
            HarnessResourceType.TAVERN_RUN,
            HarnessResourceType.FRONTEND_REQUEST,
        ):
            payload = {
                "status": "not_committed",
                "effect_batch_id": "effect-unsupported-1",
                "payload_contract": {
                    "name": "UnsupportedCommit",
                    "version": "unsupported-commit-v1",
                },
                "digest_algorithm": "sha256",
                "digest_scope": "committed_projection",
                "attempted_resource_refs": [
                    {
                        "resource_type": resource_type.value,
                        "resource_id": f"{resource_type.value}-1",
                        "revision": None,
                    }
                ],
                "committed_resources": [],
                "payload_digest": None,
                "committed_at": None,
                "rollback_reason_code": "",
                "rolled_back_at": None,
            }
            self.assertEqual(
                HarnessCommitEvidenceV3.model_validate(payload).status.value,
                "not_committed",
            )

            rolled_back = {
                **payload,
                "status": "rolled_back",
                "rollback_reason_code": "commit_failed",
                "rolled_back_at": "2026-08-12T10:00:00Z",
            }
            with self.assertRaisesRegex(
                ValidationError,
                "harness_rollback_resource_policy_unsupported",
            ):
                HarnessCommitEvidenceV3.model_validate(rolled_back)

        unsupported_committed = HarnessCommittedResourceRefV3(
            resource_type=HarnessResourceType.DOCUMENT,
            resource_id="document-1",
            expected_revision=None,
            committed_revision=None,
            first_sequence=None,
            last_sequence=None,
            payload_digest="d" * 64,
        )
        with self.assertRaisesRegex(
            ValueError,
            "harness_commit_resource_policy_unsupported",
        ):
            HarnessCommitEvidenceV3.model_construct(
                status="committed",
                effect_batch_id="effect-unsupported-committed-1",
                payload_contract=HarnessContractRef(
                    name="UnsupportedCommit",
                    version="unsupported-commit-v1",
                ),
                digest_algorithm="sha256",
                digest_scope="committed_projection",
                attempted_resource_refs=[],
                committed_resources=[unsupported_committed],
                payload_digest="d" * 64,
                committed_at=datetime.now(timezone.utc),
                rollback_reason_code="",
                rolled_back_at=None,
            ).validate_v3_contract()

        raw_committed = {
            **payload,
            "status": "committed",
            "committed_resources": [
                {
                    "resource_type": HarnessResourceType.DOCUMENT.value,
                    "resource_id": "document-1",
                    "expected_revision": None,
                    "committed_revision": None,
                    "first_sequence": None,
                    "last_sequence": None,
                    "payload_digest": "d" * 64,
                }
            ],
            "payload_digest": "d" * 64,
            "committed_at": "2026-08-12T10:00:00Z",
        }
        with self.assertRaisesRegex(
            ValidationError,
            "harness_commit_resource_policy_unsupported",
        ):
            HarnessCommitEvidenceV3.model_validate(raw_committed)

    def test_v3_policy_cannot_be_bypassed_with_model_instances(self) -> None:
        unsupported_with_fake_revision = HarnessResourceRefV3(
            resource_type=HarnessResourceType.DOCUMENT,
            resource_id="document-1",
            revision=0,
        )
        message_with_fake_revision = HarnessResourceRefV3(
            resource_type=HarnessResourceType.TAVERN_MESSAGE,
            resource_id="message-10",
            revision=0,
        )
        for attempted, error in (
            (
                unsupported_with_fake_revision,
                "harness_unsupported_commit_attempt_revision_forbidden",
            ),
            (
                message_with_fake_revision,
                "harness_sequence_commit_attempt_revision_forbidden",
            ),
        ):
            with self.assertRaisesRegex(ValidationError, error):
                HarnessCommitEvidenceV3.model_validate(
                    {
                        "status": "not_committed",
                        "effect_batch_id": "effect-model-ref-1",
                        "payload_contract": {
                            "name": "ModelRefCommit",
                            "version": "model-ref-commit-v1",
                        },
                        "digest_algorithm": "sha256",
                        "digest_scope": "committed_projection",
                        "attempted_resource_refs": [attempted],
                        "committed_resources": [],
                        "payload_digest": None,
                        "committed_at": None,
                        "rollback_reason_code": "",
                        "rolled_back_at": None,
                    }
                )

        malformed_attempts = (
            HarnessResourceRefV3.model_construct(
                resource_type=HarnessResourceType.DOCUMENT,
                resource_id="/bad",
                revision=None,
            ),
            HarnessResourceRefV3.model_construct(
                resource_type=HarnessResourceType.DOCUMENT,
                resource_id="document-1",
                revision=-1,
            ),
        )
        for attempted in malformed_attempts:
            with self.assertRaises(ValidationError):
                HarnessCommitEvidenceV3.model_validate(
                    {
                        "status": "not_committed",
                        "effect_batch_id": "effect-malformed-model-ref-1",
                        "payload_contract": {
                            "name": "ModelRefCommit",
                            "version": "model-ref-commit-v1",
                        },
                        "digest_algorithm": "sha256",
                        "digest_scope": "committed_projection",
                        "attempted_resource_refs": [attempted],
                        "committed_resources": [],
                        "payload_digest": None,
                        "committed_at": None,
                        "rollback_reason_code": "",
                        "rolled_back_at": None,
                    }
                )

        for committed in (
            HarnessCommittedResourceRefV3.model_construct(
                resource_type=HarnessResourceType.TAVERN_MESSAGE,
                resource_id="/bad",
                expected_revision=None,
                committed_revision=None,
                first_sequence=10,
                last_sequence=10,
                payload_digest="d" * 64,
            ),
            HarnessCommittedResourceRefV3.model_construct(
                resource_type=HarnessResourceType.TAVERN_MESSAGE,
                resource_id="message-10",
                expected_revision=None,
                committed_revision=None,
                first_sequence=-1,
                last_sequence=-1,
                payload_digest="d" * 64,
            ),
            HarnessCommittedResourceRefV3.model_construct(
                resource_type=HarnessResourceType.TAVERN_MESSAGE,
                resource_id="message-10",
                expected_revision=None,
                committed_revision=None,
                first_sequence=10,
                last_sequence=10,
                payload_digest="not-a-digest",
            ),
        ):
            with self.assertRaises(ValidationError):
                HarnessCommitEvidenceV3.model_validate(
                    {
                        "status": "committed",
                        "effect_batch_id": "effect-malformed-committed-ref-1",
                        "payload_contract": {
                            "name": "TavernMessageCommit",
                            "version": "tavern-message-commit-v1",
                        },
                        "digest_algorithm": "sha256",
                        "digest_scope": "committed_projection",
                        "attempted_resource_refs": [
                            HarnessResourceRefV3(
                                resource_type=HarnessResourceType.TAVERN_MESSAGE,
                                resource_id="message-10",
                                revision=None,
                            )
                        ],
                        "committed_resources": [committed],
                        "payload_digest": "d" * 64,
                        "committed_at": "2026-08-12T10:00:00Z",
                        "rollback_reason_code": "",
                        "rolled_back_at": None,
                    }
                )

        invalid_context_subject = HarnessResourceRefV3.model_construct(
            resource_type=HarnessResourceType.TAVERN_ROOM,
            resource_id="/bad",
            revision=4,
        )
        context = _build().model_dump(mode="json", exclude_none=False)
        context["subject_refs"] = [
            invalid_context_subject.model_dump(mode="json", exclude_none=False)
        ]
        context["context_digest"] = canonical_harness_context_digest(context)
        context["subject_refs"] = [invalid_context_subject]
        with self.assertRaises(ValidationError):
            HarnessContextEnvelopeV3.model_validate(context)

        for invalid_snapshot in (
            HarnessSnapshotRefV3.model_construct(
                artifact_type=HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,
                artifact_id="/bad",
                contract=HarnessContractRef(
                    name="TavernRoomSnapshotManifest",
                    version="tavern-room-snapshot-manifest-v1",
                ),
                digest_algorithm="sha256",
                payload_digest="a" * 64,
            ),
            HarnessSnapshotRefV3.model_construct(
                artifact_type=HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,
                artifact_id="snapshot-1",
                contract=HarnessContractRef(
                    name="TavernRoomSnapshotManifest",
                    version="tavern-room-snapshot-manifest-v1",
                ),
                digest_algorithm="sha256",
                payload_digest="not-a-digest",
            ),
        ):
            context = _build().model_dump(mode="json", exclude_none=False)
            context["snapshot_refs"] = [
                invalid_snapshot.model_dump(mode="json", exclude_none=False)
            ]
            context["context_digest"] = canonical_harness_context_digest(context)
            context["snapshot_refs"] = [invalid_snapshot]
            with self.assertRaises(ValidationError):
                HarnessContextEnvelopeV3.model_validate(context)

    def test_v3_room_and_message_commit_manifest_digest_is_canonical(self) -> None:
        contract = HarnessContractRef(
            name="ExampleRoomAndMessageCommitManifest",
            version="example-room-message-commit-manifest-v1",
        )
        committed = [
            HarnessCommittedResourceRefV3(
                resource_type=HarnessResourceType.TAVERN_MESSAGE,
                resource_id="message-10",
                expected_revision=None,
                committed_revision=None,
                first_sequence=10,
                last_sequence=10,
                payload_digest="a" * 64,
            ),
            HarnessCommittedResourceRefV3(
                resource_type=HarnessResourceType.TAVERN_ROOM,
                resource_id="room-1",
                expected_revision=4,
                committed_revision=5,
                first_sequence=None,
                last_sequence=None,
                payload_digest="b" * 64,
            ),
        ]
        digest = canonical_harness_commit_digest(
            payload_contract=contract,
            committed_resources=committed,
            digest_scope="committed_batch",
        )
        evidence = HarnessCommitEvidenceV3.model_validate(
            {
                "status": "committed",
                "effect_batch_id": "effect-tavern-batch-1",
                "payload_contract": contract,
                "digest_algorithm": "sha256",
                "digest_scope": "committed_batch",
                "attempted_resource_refs": [
                    HarnessResourceRefV3(
                        resource_type=HarnessResourceType.TAVERN_MESSAGE,
                        resource_id="message-10",
                        revision=None,
                    ),
                    HarnessResourceRefV3(
                        resource_type=HarnessResourceType.TAVERN_ROOM,
                        resource_id="room-1",
                        revision=4,
                    ),
                ],
                "committed_resources": committed,
                "payload_digest": digest,
                "committed_at": "2026-08-12T10:00:00Z",
                "rollback_reason_code": "",
                "rolled_back_at": None,
            }
        )
        self.assertEqual(evidence.payload_digest, digest)

    def test_v3_commit_contract_rejects_placeholder_version(self) -> None:
        changed = json.loads(
            (FIXTURE_ROOT / "passed_not_applicable_v3.json").read_text(
                encoding="utf-8"
            )
        )
        changed["commit_evidence"] = {
            "status": "not_committed",
            "effect_batch_id": "effect-1",
            "payload_contract": {"name": "CommitBatch", "version": "unknown"},
            "digest_algorithm": "sha256",
            "digest_scope": "committed_projection",
            "attempted_resource_refs": [
                {
                    "resource_type": "tavern_message",
                    "resource_id": "message-10",
                    "revision": None,
                }
            ],
            "committed_resources": [],
            "payload_digest": None,
            "committed_at": None,
            "rollback_reason_code": "",
            "rolled_back_at": None,
        }
        changed["attempt_records"].append(
            {
                "attempt_id": "attempt-commit-1",
                "attempt_index": 3,
                "phase": "commit",
                "status": "failed",
                "output_digest": None,
                "error_code": "commit_failed",
                "duration_ms": 1,
            }
        )
        changed["status"] = "failed"
        changed["output_digest"] = None
        changed["error_code"] = "commit_failed"
        changed["duration_ms"] = 9
        with self.assertRaisesRegex(
            ValidationError,
            "harness_contract_version_not_adopted",
        ):
            HarnessTraceV3.model_validate(changed)


if __name__ == "__main__":
    unittest.main()
