"""Provider-free readiness checks for Tavern counterfactual twins.

This is a research-only boundary.  It neither calls a provider nor changes the
production Harness registry.  Public generator input is deliberately built by
``generator_visible_payload`` instead of serialising the fixture model: the
sealed oracle, polarity, coordinates, digests and mutation metadata therefore
cannot cross the adapter boundary by accident.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, model_validator

from app.models.tavern_integrity import persona_prompt_hash
from app.services.tavern_v3 import TavernActorProtectedSnapshotV2


Axis = Literal[
    "permission_fidelity", "relationship_fidelity", "shared_history_fidelity",
    "epistemic_provenance", "world_state_fidelity",
]
Polarity = Literal["supported", "denied", "explicitly_unknown"]
MutationCode = Literal[
    "extra_authoritative_delta", "declared_delta_pointer_mismatch",
    "source_codepoint_span_shift", "source_utf8_span_shift",
    "source_slice_digest_mismatch", "canonical_world_digest_mismatch",
]
IssueCode = MutationCode | Literal["counterfactual_insensitivity", "invalid_reply"]

CAMPAIGN_ID = "tavern-counterfactual-twins-readiness-20260913-v1"
VERSION = "tavern-counterfactual-twins-readiness-v1"
FAMILY_IDS = (
    "archive_keycard_view", "clinic_supply_inventory", "lighthouse_correspondence",
    "neighborhood_watch_intro", "pottery_fair_visit", "ferry_winch_repair",
    "radio_weather_measurement", "observatory_plate_sighting",
    "greenhouse_valve_state", "rehearsal_east_exit",
)
MUTATION_CODES = (
    "extra_authoritative_delta", "declared_delta_pointer_mismatch",
    "source_codepoint_span_shift", "source_utf8_span_shift",
    "source_slice_digest_mismatch", "canonical_world_digest_mismatch",
)
_ID = r"^[a-z0-9][a-z0-9_-]*$"
_SHA = r"^[0-9a-f]{64}$"
HISTORICAL_ANCESTRY_PATH = (
    "tools/model-quality/fixtures/persona-scene/"
    "tavern-counterfactual-twins-historical-ancestry-v1.json"
)
HISTORICAL_CAMPAIGNS = (
    "persona-source-capsule-v1",
    "scene-closed-world-v1",
    "persona-scene-tavern-confirmation-v2",
)
HISTORICAL_ARTIFACT_PATHS = {
    "persona-source-capsule-v1":
        "tools/model-quality/fixtures/persona-scene/persona-source-capsule-v1.json",
    "scene-closed-world-v1":
        "tools/model-quality/fixtures/persona-scene/scene-closed-world-v1.json",
    "persona-scene-tavern-confirmation-v2":
        "tools/model-quality/fixtures/persona-scene-tavern-confirmation-v2.json",
}
CANONICALIZATION = "canonical-json-v1-sort-keys-utf8-no-floats"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class FrozenSpanV1(_Strict):
    codepoint_start: StrictInt = Field(ge=0)
    codepoint_end: StrictInt = Field(gt=0)
    utf8_start: StrictInt = Field(ge=0)
    utf8_end: StrictInt = Field(gt=0)
    slice_sha256: StrictStr = Field(pattern=_SHA)


class TwinV1(_Strict):
    polarity: Polarity
    authoritative_value: StrictStr = Field(min_length=1)
    source_text: StrictStr = Field(min_length=1)
    source_sha256: StrictStr = Field(pattern=_SHA)
    source_span: FrozenSpanV1
    canonical_world_sha256: StrictStr = Field(pattern=_SHA)


class GoldReplyV1(_Strict):
    reply: StrictStr = Field(min_length=1)
    claim_response: StrictStr = Field(min_length=1)
    quoted_opposite_literal: StrictStr = Field(min_length=1)
    explicit_denial_of_opposite: StrictStr = Field(min_length=1)
    surface_paraphrase_copy: StrictStr = Field(min_length=1)
    nonce_decorated_copy: StrictStr = Field(min_length=1)


class FamilyOracleV1(_Strict):
    supported: GoldReplyV1
    second: GoldReplyV1
    invariant_prefix: StrictStr = Field(min_length=1)
    invariant_suffix: StrictStr = Field(min_length=1)


class TavernTwinFamilyV1(_Strict):
    family_id: StrictStr = Field(pattern=_ID)
    axis: Axis
    second_polarity: Literal["denied", "explicitly_unknown"]
    authority: Literal["participant_snapshot", "transcript_snapshot", "scene_snapshot"]
    semantic_atom: StrictStr = Field(min_length=1)
    semantic_atom_sha256: StrictStr = Field(pattern=_SHA)
    allowed_delta_json_pointer: StrictStr = Field(
        pattern=r"^/(participants/0/persona_snapshot/relationship|recent_messages/0/content|room/scene_profile/summary)$"
    )
    projection_number: StrictInt = Field(ge=1, le=10)
    common_projection_sha256: StrictStr = Field(pattern=_SHA)
    supported: TwinV1
    second: TwinV1
    oracle: FamilyOracleV1

    @model_validator(mode="after")
    def validate_binding(self) -> "TavernTwinFamilyV1":
        if self.supported.polarity != "supported":
            raise ValueError("first_polarity_not_supported")
        if self.second.polarity != self.second_polarity:
            raise ValueError("second_polarity_mismatch")
        if canonical_sha256(self.semantic_atom) != self.semantic_atom_sha256:
            raise ValueError("semantic_atom_sha256_mismatch")
        if canonical_sha256(normalized_projection(common_projection(self))) != self.common_projection_sha256:
            raise ValueError("common_projection_sha256_mismatch")
        for twin in (self.supported, self.second):
            validate_source_binding(twin)
            world = materialize_world(self, twin)
            try:
                TavernActorProtectedSnapshotV2.model_validate_json(
                    canonical_bytes(world), strict=True
                )
            except Exception as exc:
                raise ValueError("production_snapshot_strict_decode_failed") from exc
            if canonical_sha256(world) != twin.canonical_world_sha256:
                raise ValueError("canonical_world_digest_mismatch")
        differences = differing_pointers(
            normalized_projection(materialize_world(self, self.supported)),
            normalized_projection(materialize_world(self, self.second)),
        )
        if differences != [self.allowed_delta_json_pointer]:
            raise ValueError("extra_authoritative_delta")
        _validate_gold_separation(self)
        return self


class HistoricalDedupV1(_Strict):
    forbidden_family_ids: list[StrictStr]
    forbidden_source_sha256: list[StrictStr]
    forbidden_semantic_atom_sha256: list[StrictStr]
    reviewer_confirmation_required: Literal[True]


class HistoricalSourceEvidenceV1(_Strict):
    campaign_id: StrictStr
    artifact_path: StrictStr
    artifact_bytes_sha256: StrictStr = Field(pattern=_SHA)
    record_json_pointer: StrictStr = Field(pattern=r"^/cases/[0-9]+$")
    record_id: StrictStr = Field(pattern=_ID)
    canonicalization: Literal[CANONICALIZATION]
    source_preimage: dict[str, Any]
    source_sha256: StrictStr = Field(pattern=_SHA)
    semantic_preimage: dict[str, Any]
    semantic_sha256: StrictStr = Field(pattern=_SHA)
    provenance_preimage: dict[str, Any]
    provenance_sha256: StrictStr = Field(pattern=_SHA)

    @model_validator(mode="after")
    def validate_seals(self) -> "HistoricalSourceEvidenceV1":
        for preimage, digest in (
            (self.source_preimage, self.source_sha256),
            (self.semantic_preimage, self.semantic_sha256),
            (self.provenance_preimage, self.provenance_sha256),
        ):
            if canonical_sha256(preimage) != digest:
                raise ValueError("historical_ancestry_projection_digest_mismatch")
        return self


class HistoricalAncestryEntryV1(_Strict):
    family_id: StrictStr = Field(pattern=_ID)
    nearest_prior_family: StrictStr = Field(min_length=1)
    prior_sources: list[HistoricalSourceEvidenceV1] = Field(min_length=3, max_length=3)
    source_overlap: Literal[False]
    semantic_overlap: Literal[False]
    external_review_status: Literal["pending", "confirmed"]

    @model_validator(mode="after")
    def validate_digest_evidence(self) -> "HistoricalAncestryEntryV1":
        if tuple(source.campaign_id for source in self.prior_sources) != HISTORICAL_CAMPAIGNS:
            raise ValueError("historical_ancestry_campaign_catalog_mismatch")
        for source in self.prior_sources:
            if source.artifact_path != HISTORICAL_ARTIFACT_PATHS.get(source.campaign_id):
                raise ValueError("historical_ancestry_campaign_artifact_mismatch")
            binding = source.provenance_preimage
            expected_binding = {
                "comparison_family_id": self.family_id,
                "campaign_id": source.campaign_id,
                "artifact_path": source.artifact_path,
                "artifact_bytes_sha256": source.artifact_bytes_sha256,
                "record_json_pointer": source.record_json_pointer,
                "record_id": source.record_id,
                "canonicalization": source.canonicalization,
                "source_sha256": source.source_sha256,
                "semantic_sha256": source.semantic_sha256,
            }
            if binding != expected_binding:
                raise ValueError("historical_ancestry_provenance_binding_mismatch")
        if self.nearest_prior_family not in {
            source.record_id for source in self.prior_sources
        }:
            raise ValueError("historical_ancestry_nearest_record_unbound")
        return self


class HistoricalAncestryManifestV1(_Strict):
    version: Literal["tavern-counterfactual-twins-historical-ancestry-v1"]
    campaign_id: Literal[CAMPAIGN_ID]
    canonicalization: Literal[CANONICALIZATION]
    entries: list[HistoricalAncestryEntryV1] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_catalog(self) -> "HistoricalAncestryManifestV1":
        if tuple(entry.family_id for entry in self.entries) != FAMILY_IDS:
            raise ValueError("historical_ancestry_catalog_mismatch")
        return self


class HistoricalAncestryBindingV1(_Strict):
    manifest_path: Literal[HISTORICAL_ANCESTRY_PATH]
    manifest_bytes_sha256: StrictStr = Field(pattern=_SHA)
    external_review_status: Literal["pending", "confirmed"]


class GoldenVectorV1(_Strict):
    vector_id: Literal["ascii", "cjk", "emoji", "combining_mark"]
    text: StrictStr = Field(min_length=1)
    codepoint_count: StrictInt = Field(ge=1)
    utf8_count: StrictInt = Field(ge=1)
    utf8_hex: StrictStr = Field(pattern=r"^[0-9a-f]+$")
    sha256: StrictStr = Field(pattern=_SHA)


class TavernCounterfactualFixtureV1(_Strict):
    version: Literal["tavern-counterfactual-twins-fixture-v1"]
    campaign_id: Literal[CAMPAIGN_ID]
    scope: Literal["provider_free_research_readiness_only"]
    families: list[TavernTwinFamilyV1] = Field(min_length=10, max_length=10)
    historical_dedup: HistoricalDedupV1
    historical_ancestry: HistoricalAncestryBindingV1
    canonical_golden_vectors: list[GoldenVectorV1] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_complete_fixture(self) -> "TavernCounterfactualFixtureV1":
        ids = [item.family_id for item in self.families]
        if tuple(ids) != FAMILY_IDS or len(set(ids)) != 10:
            raise ValueError("family_catalog_mismatch")
        if sum(item.second_polarity == "denied" for item in self.families) != 5:
            raise ValueError("deny_family_count_mismatch")
        if sum(item.second_polarity == "explicitly_unknown" for item in self.families) != 5:
            raise ValueError("unknown_family_count_mismatch")
        if len({item.supported.source_sha256 for item in self.families}) != 10:
            raise ValueError("duplicate_source_digest")
        if len({item.common_projection_sha256 for item in self.families}) != 10:
            raise ValueError("duplicate_projection_digest")
        atoms = [_normalise_atom(item.semantic_atom) for item in self.families]
        if len(set(atoms)) != 10:
            raise ValueError("equivalent_normalized_semantic_atom")
        forbidden = self.historical_dedup
        if set(ids) & set(forbidden.forbidden_family_ids):
            raise ValueError("historical_family_overlap")
        source_digest_list = [t.source_sha256 for f in self.families for t in (f.supported, f.second)]
        if len(set(source_digest_list)) != 20:
            raise ValueError("duplicate_twin_source_digest")
        source_digests = set(source_digest_list)
        if source_digests & set(forbidden.forbidden_source_sha256):
            raise ValueError("historical_source_digest_overlap")
        atom_digests = {f.semantic_atom_sha256 for f in self.families}
        if atom_digests & set(forbidden.forbidden_semantic_atom_sha256):
            raise ValueError("historical_semantic_ancestry_overlap")
        if {v.vector_id for v in self.canonical_golden_vectors} != {
            "ascii", "cjk", "emoji", "combining_mark"
        }:
            raise ValueError("golden_vector_catalog_mismatch")
        for vector in self.canonical_golden_vectors:
            if (len(vector.text), len(vector.text.encode("utf-8"))) != (
                vector.codepoint_count, vector.utf8_count
            ):
                raise ValueError("golden_vector_coordinate_mismatch")
            if vector.text.encode("utf-8").hex() != vector.utf8_hex:
                raise ValueError("golden_vector_utf8_hex_mismatch")
            if sha256(vector.text.encode("utf-8")).hexdigest() != vector.sha256:
                raise ValueError("golden_vector_sha256_mismatch")
        return self


class TavernCounterfactualInputError(ValueError):
    """A fixture, frozen output or mutation was unusable and must fail closed."""


def reject_duplicate_json_loads(raw: bytes) -> object:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise TavernCounterfactualInputError("utf8_bom_forbidden")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise TavernCounterfactualInputError("invalid_utf8") from exc

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise TavernCounterfactualInputError("duplicate_json_key")
            result[key] = value
        return result

    def nonfinite(value: str) -> object:
        raise TavernCounterfactualInputError(f"nonfinite_number:{value}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=nonfinite)


def canonical_bytes(value: object) -> bytes:
    _reject_float(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    if isinstance(value, str):
        return sha256(value.encode("utf-8")).hexdigest()
    return sha256(canonical_bytes(value)).hexdigest()


def materialize_world(family: TavernTwinFamilyV1, twin: TwinV1) -> dict[str, object]:
    world = common_projection(family)
    if family.authority == "participant_snapshot":
        world["participants"][0]["persona_snapshot"]["relationship"] = twin.authoritative_value  # type: ignore[index]
    elif family.authority == "transcript_snapshot":
        world["recent_messages"][0]["content"] = twin.authoritative_value  # type: ignore[index]
    else:
        world["room"]["scene_profile"]["summary"] = twin.authoritative_value  # type: ignore[index]
    participant = world["participants"][0]  # type: ignore[index]
    participant["prompt_hash"] = persona_prompt_hash(participant["persona_snapshot"])  # type: ignore[index]
    world["actor"] = deepcopy(participant)
    return world


def common_projection(family: TavernTwinFamilyV1) -> dict[str, object]:
    """Construct the frozen, production-shaped direct-first-step projection."""
    number = family.projection_number
    suffix = f"{number:02}"
    actor_id = f"actor-{suffix}"
    timestamp = "2026-09-13T00:00:00Z"
    persona = {
        "id": actor_id, "revision": 1, "name": f"Actor {suffix}",
        "source": "research_fixture", "summary": f"Frozen actor {suffix}",
        "relationship": "", "learner_address": "traveler",
        "system_prompt": "Answer only from the frozen snapshot.",
        "reference_hints": [], "slots": [], "available_emotions": ["calm"],
        "available_actions": ["observe"], "default_speech_style": "plain",
    }
    participant = {
        "room_id": f"room-{suffix}", "persona_id": actor_id, "display_order": 0,
        "display_name": f"Actor {suffix}", "persona_snapshot": persona,
        "prompt_hash": persona_prompt_hash(persona), "joined_at": timestamp,
    }
    anchor_sequence = 2 if family.authority == "transcript_snapshot" else 1
    anchor = {
        "id": f"anchor-{suffix}", "room_id": f"room-{suffix}",
        "sequence": anchor_sequence, "run_id": "", "author_kind": "user",
        "persona_id": "", "persona_name": "",
        "content": f"Please answer the catalog question {suffix}.",
        "emotion": "calm", "action": "", "speech_style": "",
        "addressed_participant_ids": [actor_id], "reply_to_message_id": "",
        "client_request_id": "", "created_at": timestamp,
    }
    projection: dict[str, object] = {
        "schema_name": "TavernActorProtectedSnapshot",
        "schema_version": "tavern-actor-protected-snapshot-v2",
        "run_id": f"run-{suffix}", "run_context_digest": f"{number:016x}",
        "scheduled_participant_ids": [actor_id], "step_index": 0,
        "room": {
            "id": f"room-{suffix}", "creation_key": f"create-{suffix}",
            "creation_input_digest": f"input-{suffix}",
            "title": f"Counterfactual room {suffix}",
            "scene_profile": {"scene_name": f"Scene {suffix}", "scene_id": f"scene-{suffix}", "title": f"Scene {suffix}", "summary": "", "tags": [], "selected_path": [], "focus_object_names": [], "scene_tree": []},
            "status": "active", "revision": 1, "last_sequence": anchor_sequence,
            "created_at": timestamp, "updated_at": timestamp,
        },
        "participants": [participant], "actor": deepcopy(participant),
        "recent_messages": [anchor], "transcript_last_sequence": anchor_sequence,
        "user_message": f"Please answer the catalog question {suffix}.",
        "guidance": "", "turn_kind": "user_message",
        "required_target_id": "", "reply_anchor": deepcopy(anchor),
    }
    if family.authority == "transcript_snapshot":
        fact = {
            "id": f"fact-{suffix}", "room_id": f"room-{suffix}", "sequence": 1,
            "run_id": "", "author_kind": "system", "persona_id": "",
            "persona_name": "", "content": "", "emotion": "calm", "action": "",
            "speech_style": "", "addressed_participant_ids": [],
            "reply_to_message_id": "", "client_request_id": "", "created_at": timestamp,
        }
        projection["recent_messages"] = [fact, anchor]
    return projection


def generator_visible_payload(family: TavernTwinFamilyV1, twin: TwinV1) -> dict[str, object]:
    """Return the entire and only adapter-visible input surface."""
    return {
        "source": twin.source_text,
        "tavern_projection": normalized_projection(materialize_world(family, twin)),
    }


def build_generator_public_sample_bytes(
    family: TavernTwinFamilyV1, twin: TwinV1, *, sample_id: str
) -> bytes:
    """Trusted offline builder output for one generator process/one arm."""
    if not re.fullmatch(_ID, sample_id):
        raise TavernCounterfactualInputError("invalid_public_sample_id")
    visible = generator_visible_payload(family, twin)
    return canonical_bytes({
        "version": "tavern-counterfactual-twin-generator-sample-v1",
        "sample_id": sample_id,
        **visible,
    })


def load_tavern_counterfactual_fixture(
    raw: bytes, repository_root: Path
) -> tuple[TavernCounterfactualFixtureV1, HistoricalAncestryManifestV1]:
    """Strictly accept a fixture only after reconstructing its ancestry evidence."""
    try:
        fixture = TavernCounterfactualFixtureV1.model_validate(
            reject_duplicate_json_loads(raw), strict=True
        )
    except Exception as exc:
        raise TavernCounterfactualInputError("counterfactual_fixture_invalid") from exc
    return fixture, load_historical_ancestry(fixture, repository_root)


def load_historical_ancestry(
    fixture: TavernCounterfactualFixtureV1, repository_root: Path
) -> HistoricalAncestryManifestV1:
    """Read and reconstruct every allowlisted historical source projection."""
    manifest_path = _safe_repository_path(
        repository_root, fixture.historical_ancestry.manifest_path
    )
    raw = manifest_path.read_bytes()
    if sha256(raw).hexdigest() != fixture.historical_ancestry.manifest_bytes_sha256:
        raise TavernCounterfactualInputError("historical_ancestry_manifest_bytes_mismatch")
    try:
        manifest = HistoricalAncestryManifestV1.model_validate(
            reject_duplicate_json_loads(raw), strict=True
        )
    except Exception as exc:
        raise TavernCounterfactualInputError("historical_ancestry_manifest_invalid") from exc
    for entry in manifest.entries:
        for evidence in entry.prior_sources:
            artifact_path = _safe_repository_path(repository_root, evidence.artifact_path)
            artifact_raw = artifact_path.read_bytes()
            if sha256(artifact_raw).hexdigest() != evidence.artifact_bytes_sha256:
                raise TavernCounterfactualInputError("historical_artifact_bytes_mismatch")
            document = reject_duplicate_json_loads(artifact_raw)
            record = _resolve_json_pointer(document, evidence.record_json_pointer)
            expected_source, expected_semantic = _historical_projections(
                evidence.campaign_id, record
            )
            if not isinstance(record, dict) or _historical_record_id(record) != evidence.record_id:
                raise TavernCounterfactualInputError("historical_record_identity_mismatch")
            if evidence.source_preimage != expected_source:
                raise TavernCounterfactualInputError("historical_source_projection_mismatch")
            if evidence.semantic_preimage != expected_semantic:
                raise TavernCounterfactualInputError("historical_semantic_projection_mismatch")
    return manifest


def require_completed_ancestry_review(
    fixture: TavernCounterfactualFixtureV1,
    manifest: HistoricalAncestryManifestV1,
) -> None:
    """Fail closed: pending external review can be preregistered, never passed."""
    pending = [
        entry.family_id
        for entry in manifest.entries
        if entry.external_review_status != "confirmed"
    ]
    if fixture.historical_ancestry.external_review_status != "confirmed":
        pending.insert(0, "manifest-binding")
    if pending:
        raise TavernCounterfactualInputError(
            f"historical_ancestry_external_review_pending:{','.join(pending)}"
        )


def _safe_repository_path(repository_root: Path, relative_path: str) -> Path:
    root = repository_root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise TavernCounterfactualInputError("historical_path_escape")
    return candidate


def _resolve_json_pointer(document: object, pointer: str) -> object:
    current = document
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list) and token.isdigit() and int(token) < len(current):
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise TavernCounterfactualInputError("historical_json_pointer_unresolved")
    return current


def _historical_record_id(record: dict[str, object]) -> object:
    return record.get("case_id", record.get("id"))


def _historical_projections(
    campaign_id: str, record: object
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(record, dict):
        raise TavernCounterfactualInputError("historical_record_not_object")
    if campaign_id == "persona-source-capsule-v1":
        source = {"source_text": record.get("source_text")}
        capsule = record.get("capsule")
        if not isinstance(capsule, dict):
            raise TavernCounterfactualInputError("historical_persona_capsule_missing")
        semantic = {
            "address_exact": capsule.get("address_exact"),
            "claims": capsule.get("claims"),
            "forbidden_transformations": capsule.get("forbidden_transformations"),
        }
    elif campaign_id == "scene-closed-world-v1":
        source = {"source_text": record.get("source_text")}
        semantic = {"scene_closed_world_policy_v1": record.get("scene_closed_world_policy_v1")}
    elif campaign_id == "persona-scene-tavern-confirmation-v2":
        source = {
            "persona_input": record.get("persona_input"),
            "scene_input": record.get("scene_input"),
            "user_message": record.get("user_message"),
        }
        semantic = {"source_fidelity_constraints": record.get("source_fidelity_constraints")}
    else:
        raise TavernCounterfactualInputError("historical_campaign_not_allowlisted")
    if any(value is None for value in source.values()) or any(value is None for value in semantic.values()):
        raise TavernCounterfactualInputError("historical_projection_field_missing")
    return source, semantic


def normalized_projection(world: dict[str, object]) -> dict[str, object]:
    """Remove duplicated actor and pair-varying integrity fields."""
    projection = deepcopy(world)
    projection.pop("run_context_digest", None)
    actor = projection.pop("actor")
    projection["actor_persona_id"] = actor["persona_id"]  # type: ignore[index]
    for participant in projection["participants"]:  # type: ignore[union-attr]
        participant.pop("prompt_hash", None)
    return projection


def validate_source_binding(twin: TwinV1) -> None:
    raw = twin.source_text.encode("utf-8")
    if sha256(raw).hexdigest() != twin.source_sha256:
        raise ValueError("source_sha_mismatch")
    span = twin.source_span
    if twin.source_text[span.codepoint_start:span.codepoint_end] != twin.authoritative_value:
        raise ValueError("source_codepoint_span_shift")
    try:
        byte_slice = raw[span.utf8_start:span.utf8_end]
        decoded = byte_slice.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("source_utf8_span_shift") from exc
    if decoded != twin.authoritative_value:
        raise ValueError("source_utf8_span_shift")
    if sha256(byte_slice).hexdigest() != span.slice_sha256:
        raise ValueError("source_slice_digest_mismatch")


def differing_pointers(left: object, right: object, pointer: str = "") -> list[str]:
    if type(left) is not type(right):
        return [pointer or "/"]
    if isinstance(left, dict):
        if set(left) != set(right):
            return [pointer or "/"]
        result: list[str] = []
        for key in sorted(left):
            token = key.replace("~", "~0").replace("/", "~1")
            result.extend(differing_pointers(left[key], right[key], f"{pointer}/{token}"))
        return result
    if isinstance(left, list):
        if len(left) != len(right):
            return [pointer or "/"]
        result = []
        for index, (l_item, r_item) in enumerate(zip(left, right)):
            result.extend(differing_pointers(l_item, r_item, f"{pointer}/{index}"))
        return result
    return [] if left == right else [pointer or "/"]


def validate_reply(family: TavernTwinFamilyV1, polarity: Polarity, reply: str) -> list[IssueCode]:
    if polarity not in ("supported", family.second_polarity):
        raise TavernCounterfactualInputError("reply_polarity_not_a_frozen_twin")
    gold = family.oracle.supported if polarity == "supported" else family.oracle.second
    peer = family.oracle.second if polarity == "supported" else family.oracle.supported
    accepted = {gold.reply, gold.quoted_opposite_literal, gold.explicit_denial_of_opposite}
    if reply in accepted:
        return []
    insensitive = {peer.reply, peer.claim_response, gold.surface_paraphrase_copy, gold.nonce_decorated_copy}
    return ["counterfactual_insensitivity"] if reply in insensitive else ["invalid_reply"]


def build_hard_negatives(family: TavernTwinFamilyV1) -> dict[str, dict[str, str]]:
    return {
        "supported": {
            "quoted_opposite_literal": family.oracle.supported.quoted_opposite_literal,
            "explicit_denial_of_opposite": family.oracle.supported.explicit_denial_of_opposite,
        },
        "second": {
            "quoted_opposite_literal": family.oracle.second.quoted_opposite_literal,
            "explicit_denial_of_opposite": family.oracle.second.explicit_denial_of_opposite,
        },
    }


def build_insensitivity_controls(family: TavernTwinFamilyV1) -> dict[str, str]:
    return {
        "pair_copy_reply": family.oracle.supported.reply,
        "surface_paraphrase_copy": family.oracle.second.surface_paraphrase_copy,
        "nonce_decorated_copy": family.oracle.second.nonce_decorated_copy,
    }


def diagnose_family_document(payload: dict[str, object]) -> list[MutationCode]:
    """Classify one fixed-catalog single-point fixture mutation.

    Checks are ordered from structural delta to seals so a mutation has one
    stable code.  This helper is calibration-only and is never imported by a
    generator adapter.
    """
    declared = payload.get("allowed_delta_json_pointer")
    worlds = payload.get("worlds")
    if not isinstance(worlds, list) or len(worlds) != 2 or not all(isinstance(x, dict) for x in worlds):
        raise TavernCounterfactualInputError("invalid_mutation_document")
    differences = differing_pointers(
        normalized_projection(worlds[0]), normalized_projection(worlds[1])
    )
    if len(differences) != 1:
        return ["extra_authoritative_delta"]
    if declared != differences[0]:
        return ["declared_delta_pointer_mismatch"]
    source = payload.get("source_text")
    value = payload.get("authoritative_value")
    span = payload.get("source_span")
    if not isinstance(source, str) or not isinstance(value, str) or not isinstance(span, dict):
        raise TavernCounterfactualInputError("invalid_source_mutation_document")
    cp_start, cp_end = span.get("codepoint_start"), span.get("codepoint_end")
    utf8_start, utf8_end = span.get("utf8_start"), span.get("utf8_end")
    if not all(isinstance(item, int) for item in (cp_start, cp_end, utf8_start, utf8_end)):
        raise TavernCounterfactualInputError("invalid_source_coordinates")
    if source[cp_start:cp_end] != value:
        return ["source_codepoint_span_shift"]
    raw = source.encode("utf-8")
    try:
        byte_slice = raw[utf8_start:utf8_end]
        if byte_slice.decode("utf-8", errors="strict") != value:
            return ["source_utf8_span_shift"]
    except UnicodeDecodeError:
        return ["source_utf8_span_shift"]
    if sha256(byte_slice).hexdigest() != span.get("slice_sha256"):
        return ["source_slice_digest_mismatch"]
    if canonical_sha256(worlds[0]) != payload.get("canonical_world_sha256"):
        return ["canonical_world_digest_mismatch"]
    return []


def build_single_point_mutations(family: TavernTwinFamilyV1) -> dict[MutationCode, dict[str, object]]:
    base: dict[str, object] = {
        "allowed_delta_json_pointer": family.allowed_delta_json_pointer,
        "worlds": [materialize_world(family, family.supported), materialize_world(family, family.second)],
        "source_text": family.supported.source_text,
        "authoritative_value": family.supported.authoritative_value,
        "source_span": family.supported.source_span.model_dump(mode="python"),
        "canonical_world_sha256": family.supported.canonical_world_sha256,
    }
    result: dict[MutationCode, dict[str, object]] = {}
    extra = deepcopy(base)
    extra["worlds"][1]["room"]["title"] += "!"  # type: ignore[index]
    result["extra_authoritative_delta"] = extra
    pointer = deepcopy(base)
    pointer["allowed_delta_json_pointer"] = (
        "/room/scene_profile/summary"
        if family.authority != "scene_snapshot"
        else "/participants/0/persona_snapshot/relationship"
    )
    result["declared_delta_pointer_mismatch"] = pointer
    cp = deepcopy(base)
    cp["source_span"]["codepoint_start"] += 1  # type: ignore[index]
    result["source_codepoint_span_shift"] = cp
    utf8 = deepcopy(base)
    utf8["source_span"]["utf8_start"] += 1  # type: ignore[index]
    result["source_utf8_span_shift"] = utf8
    slice_digest = deepcopy(base)
    slice_digest["source_span"]["slice_sha256"] = "0" * 64  # type: ignore[index]
    result["source_slice_digest_mismatch"] = slice_digest
    world_digest = deepcopy(base)
    pointer_tokens = family.allowed_delta_json_pointer.strip("/").split("/")
    target: object = world_digest["worlds"][0]  # type: ignore[index]
    for token in pointer_tokens[:-1]:
        target = target[int(token)] if isinstance(target, list) else target[token]  # type: ignore[index]
    target[pointer_tokens[-1]] = f"{family.supported.authoritative_value} (tampered)"  # type: ignore[index]
    result["canonical_world_digest_mismatch"] = world_digest
    return result


def _validate_gold_separation(family: TavernTwinFamilyV1) -> None:
    left, right = family.oracle.supported, family.oracle.second
    for gold in (left, right):
        expected_reply = (
            family.oracle.invariant_prefix
            + gold.claim_response
            + family.oracle.invariant_suffix
        )
        if gold.reply != expected_reply:
            raise ValueError("gold_invariant_task_content_missing")
        if gold.claim_response not in gold.reply:
            raise ValueError("gold_claim_response_span_missing")
        candidates = [gold.reply, gold.quoted_opposite_literal, gold.explicit_denial_of_opposite]
        if len(set(candidates)) != 3:
            raise ValueError("duplicate_hard_negative_content")
        for control in candidates[1:]:
            if not _is_single_claim_span_replacement(
                gold.reply,
                control,
                prefix=family.oracle.invariant_prefix,
                suffix=family.oracle.invariant_suffix,
            ):
                raise ValueError("hard_negative_non_claim_content_delta")
    if left.reply.replace(left.claim_response, "<claim>") != right.reply.replace(right.claim_response, "<claim>"):
        raise ValueError("gold_non_claim_content_delta")
    all_controls = [
        left.quoted_opposite_literal, left.explicit_denial_of_opposite,
        right.quoted_opposite_literal, right.explicit_denial_of_opposite,
    ]
    if len({canonical_sha256(value) for value in all_controls}) != 4:
        raise ValueError("hard_negative_content_digest_duplicate")


def _normalise_atom(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _is_single_claim_span_replacement(
    baseline: str, candidate: str, *, prefix: str, suffix: str
) -> bool:
    """Require byte-identical invariant regions and one whole middle span."""
    if not baseline.startswith(prefix) or not baseline.endswith(suffix):
        return False
    if not candidate.startswith(prefix) or not candidate.endswith(suffix):
        return False
    baseline_middle = baseline[len(prefix):len(baseline) - len(suffix)]
    candidate_middle = candidate[len(prefix):len(candidate) - len(suffix)]
    return bool(baseline_middle and candidate_middle and baseline_middle != candidate_middle)


def _reject_float(value: object) -> None:
    if isinstance(value, float):
        raise TavernCounterfactualInputError("float_forbidden_in_canonical_json")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TavernCounterfactualInputError("non_string_json_key")
            _reject_float(child)
    elif isinstance(value, list):
        for child in value:
            _reject_float(child)
