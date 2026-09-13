"""Provider-free, research-only Persona source-constraint calibration.

Capsules are manually authored from a frozen source.  Nothing in this module
infers policy from prose, calls a provider, changes a production schema, or
proves semantic fidelity.  Exact-marker findings are synthetic calibration
signals only; author-injected literals do not establish that natural live
output would emit or trigger them.  A Persona proposal has no product commit
at this boundary (``not_applicable``); saving a Persona is a separate
user-authored boundary.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationError,
    model_validator,
)

from app.models.persona_generation import PersonaCardBatchContentProposalV1


ClaimKind = Literal[
    "relationship", "permission", "profession", "shared_history", "epistemic"
]
ClaimPolarity = Literal["asserted", "denied", "unknown"]
TransformationCode = Literal[
    "teacherized_relationship",
    "permission_upgrade",
    "unknown_profession_assertion",
    "shared_history_invention",
    "epistemic_laundering",
]
MarkerField = Literal[
    "summary",
    "relationship",
    "cards.title",
    "cards.label",
    "cards.content",
    "cards.tags",
    "cards.source_note",
]
PersonaSourceIssueCode = Literal[
    "wrong_address",
    "teacherized_relationship",
    "permission_upgrade",
    "unknown_profession_assertion",
    "shared_history_invention",
    "epistemic_laundering",
]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PersonaSourceSpanV1(_StrictModel):
    """An exact frozen-source slice in both code-point and UTF-8 coordinates."""

    char_start: StrictInt = Field(ge=0)
    char_end: StrictInt = Field(gt=0)
    utf8_byte_start: StrictInt = Field(ge=0)
    utf8_byte_end: StrictInt = Field(gt=0)
    text: StrictStr = Field(min_length=1)
    text_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_ranges_and_text_digest(self) -> "PersonaSourceSpanV1":
        if self.char_end <= self.char_start:
            raise ValueError("source_span_invalid_char_range")
        if self.utf8_byte_end <= self.utf8_byte_start:
            raise ValueError("source_span_invalid_utf8_range")
        if self.char_end - self.char_start != len(self.text):
            raise ValueError("source_span_char_length_mismatch")
        if self.utf8_byte_end - self.utf8_byte_start != len(self.text.encode("utf-8")):
            raise ValueError("source_span_utf8_length_mismatch")
        if _sha256_text(self.text) != self.text_sha256:
            raise ValueError("source_span_text_sha256_mismatch")
        return self


class PersonaSourceClaimV1(_StrictModel):
    claim_id: StrictStr = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    claim_kind: ClaimKind
    claim_key: StrictStr = Field(min_length=1)
    polarity: ClaimPolarity
    source_span: PersonaSourceSpanV1


class PersonaForbiddenLiteralMarkerV1(_StrictModel):
    field: MarkerField
    literal: StrictStr = Field(min_length=1)


class PersonaForbiddenTransformationV1(_StrictModel):
    code: TransformationCode
    markers: list[PersonaForbiddenLiteralMarkerV1] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_markers(self) -> "PersonaForbiddenTransformationV1":
        pairs = [(marker.field, marker.literal) for marker in self.markers]
        if len(set(pairs)) != len(pairs):
            raise ValueError("duplicate_forbidden_marker")
        return self


class PersonaSourceConstraintCapsuleV1(_StrictModel):
    """Human-authored constraints for one source/candidate calibration case."""

    version: Literal["persona-source-constraint-capsule-v1"] = (
        "persona-source-constraint-capsule-v1"
    )
    case_id: StrictStr = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    source_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    address_exact: StrictStr = Field(min_length=1)
    address_source_span: PersonaSourceSpanV1
    claims: list[PersonaSourceClaimV1] = Field(min_length=5)
    forbidden_transformations: list[PersonaForbiddenTransformationV1] = Field(
        min_length=5
    )
    research_only: Literal[True]
    proposal_commit_evidence: Literal["not_applicable"]
    save_boundary: Literal["separate_user_authored_save"]

    @model_validator(mode="after")
    def validate_unambiguous_authoring(self) -> "PersonaSourceConstraintCapsuleV1":
        if self.address_source_span.text != self.address_exact:
            raise ValueError("address_source_span_text_mismatch")
        claim_ids = [claim.claim_id for claim in self.claims]
        if len(set(claim_ids)) != len(claim_ids):
            raise ValueError("duplicate_claim_id")
        kinds = Counter(claim.claim_kind for claim in self.claims)
        missing = set(ClaimKind.__args__) - set(kinds)  # type: ignore[attr-defined]
        if missing:
            raise ValueError("missing_explicit_claim_kind")
        polarity_by_key: dict[tuple[str, str], str] = {}
        for claim in self.claims:
            key = (claim.claim_kind, claim.claim_key)
            prior = polarity_by_key.setdefault(key, claim.polarity)
            if prior != claim.polarity:
                raise ValueError("contradictory_claim_polarity")
        spans = sorted(
            [
                (
                    self.address_source_span.char_start,
                    self.address_source_span.char_end,
                    "address_exact",
                )
            ]
            + [
                (
                    claim.source_span.char_start,
                    claim.source_span.char_end,
                    claim.claim_id,
                )
                for claim in self.claims
            ]
        )
        for previous, current in zip(spans, spans[1:]):
            if current[0] < previous[1]:
                raise ValueError("overlapping_claim_source_spans")
        utf8_spans = sorted(
            [
                (
                    self.address_source_span.utf8_byte_start,
                    self.address_source_span.utf8_byte_end,
                    "address_exact",
                )
            ]
            + [
                (
                    claim.source_span.utf8_byte_start,
                    claim.source_span.utf8_byte_end,
                    claim.claim_id,
                )
                for claim in self.claims
            ]
        )
        for previous, current in zip(utf8_spans, utf8_spans[1:]):
            if current[0] < previous[1]:
                raise ValueError("overlapping_claim_utf8_source_spans")
        codes = [item.code for item in self.forbidden_transformations]
        required_codes = set(TransformationCode.__args__)  # type: ignore[attr-defined]
        if len(set(codes)) != len(codes):
            raise ValueError("duplicate_forbidden_transformation")
        if set(codes) != required_codes:
            raise ValueError("forbidden_transformation_codes_mismatch")
        all_markers = [
            (marker.field, marker.literal)
            for transformation in self.forbidden_transformations
            for marker in transformation.markers
        ]
        if len(set(all_markers)) != len(all_markers):
            raise ValueError("marker_ambiguous_across_transformations")
        return self


class PersonaSourceCapsuleCaseV1(_StrictModel):
    case_id: StrictStr
    source_text: StrictStr = Field(min_length=1)
    capsule_sha256: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    capsule: PersonaSourceConstraintCapsuleV1
    valid_minimal_persona_card_batch_proposal: dict[str, Any]
    hard_negative_persona_card_batch_proposal: dict[str, Any]
    single_point_mutations: list["PersonaSourceCapsuleMutationV1"] = Field(
        min_length=6, max_length=6
    )

    @model_validator(mode="after")
    def validate_case_binding(self) -> "PersonaSourceCapsuleCaseV1":
        if self.case_id != self.capsule.case_id:
            raise ValueError("case_id_capsule_mismatch")
        if capsule_sha256(self.capsule) != self.capsule_sha256:
            raise ValueError("capsule_sha256_mismatch")
        validate_capsule_source(self.capsule, self.source_text)
        mutation_ids = [mutation.mutation_id for mutation in self.single_point_mutations]
        expected_codes = set(PersonaSourceIssueCode.__args__)  # type: ignore[attr-defined]
        if len(set(mutation_ids)) != len(mutation_ids):
            raise ValueError("duplicate_mutation_id")
        if {
            mutation.expected_code for mutation in self.single_point_mutations
        } != expected_codes:
            raise ValueError("mutation_expected_codes_mismatch")
        return self


class PersonaSourceCapsuleMutationV1(_StrictModel):
    mutation_id: StrictStr = Field(min_length=1)
    operation: Literal["replace"]
    path: StrictStr = Field(
        pattern=(
            r"^/(summary|relationship|learner_address|"
            r"cards/\d+/(title|label|content|source_note|tags/\d+))$"
        )
    )
    value: StrictStr
    expected_code: PersonaSourceIssueCode


class PersonaSourceCapsuleFixtureV1(_StrictModel):
    version: Literal["persona-source-capsule-fixture-v1"]
    policy_provenance: Literal["manually_authored_research_only"]
    cases: list[PersonaSourceCapsuleCaseV1] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def validate_unique_cases(self) -> "PersonaSourceCapsuleFixtureV1":
        case_ids = [case.case_id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("duplicate_fixture_case_id")
        return self


class PersonaSourceConstraintIssueV1(_StrictModel):
    code: PersonaSourceIssueCode
    path: StrictStr
    expected: StrictStr | None = None
    observed: StrictStr | None = None


class PersonaSourceCapsuleInputError(ValueError):
    """Capsule/source/proposal input was unusable and must fail closed."""


def capsule_sha256(capsule: PersonaSourceConstraintCapsuleV1) -> str:
    canonical = json.dumps(
        capsule.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(canonical).hexdigest()


def validate_capsule_source(
    capsule: PersonaSourceConstraintCapsuleV1,
    source_text: str,
) -> None:
    """Bind every registered span to exact Unicode and UTF-8 source slices."""

    if _sha256_text(source_text) != capsule.source_sha256:
        raise PersonaSourceCapsuleInputError("capsule_source_sha256_mismatch")
    encoded = source_text.encode("utf-8")
    bound_spans = [("address_exact", capsule.address_source_span)] + [
        (claim.claim_id, claim.source_span) for claim in capsule.claims
    ]
    for span_id, span in bound_spans:
        if source_text[span.char_start : span.char_end] != span.text:
            raise PersonaSourceCapsuleInputError(
                f"capsule_source_char_slice_mismatch:{span_id}"
            )
        try:
            byte_text = encoded[span.utf8_byte_start : span.utf8_byte_end].decode(
                "utf-8", errors="strict"
            )
        except UnicodeDecodeError as exc:
            raise PersonaSourceCapsuleInputError(
                f"capsule_source_utf8_boundary_mismatch:{span_id}"
            ) from exc
        if byte_text != span.text:
            raise PersonaSourceCapsuleInputError(
                f"capsule_source_utf8_slice_mismatch:{span_id}"
            )
        expected_byte_start = len(source_text[: span.char_start].encode("utf-8"))
        expected_byte_end = len(source_text[: span.char_end].encode("utf-8"))
        if (span.utf8_byte_start, span.utf8_byte_end) != (
            expected_byte_start,
            expected_byte_end,
        ):
            raise PersonaSourceCapsuleInputError(
                f"capsule_source_coordinate_mismatch:{span_id}"
            )


def validate_persona_source_constraints(
    capsule: PersonaSourceConstraintCapsuleV1,
    source_text: str,
    proposal: Mapping[str, object] | BaseModel,
) -> list[PersonaSourceConstraintIssueV1]:
    """Run narrow address and exact-field-marker checks.

    Exact equality is intentional: quoted or negated appearances embedded in a
    larger field are hard-negative controls, not findings.  This function does
    not perform free-text entailment or semantic certification.
    """

    validate_capsule_source(capsule, source_text)
    decoded = _decode_proposal(proposal)
    issues: list[PersonaSourceConstraintIssueV1] = []
    if decoded.learner_address != capsule.address_exact:
        issues.append(
            PersonaSourceConstraintIssueV1(
                code="wrong_address",
                path="learner_address",
                expected=capsule.address_exact,
                observed=decoded.learner_address,
            )
        )
    values = _field_values(decoded)
    for transformation in capsule.forbidden_transformations:
        for marker in transformation.markers:
            for path, value in values[marker.field]:
                if value == marker.literal:
                    issues.append(
                        PersonaSourceConstraintIssueV1(
                            code=transformation.code,
                            path=path,
                            observed=value,
                        )
                    )
    return issues


def _decode_proposal(
    proposal: Mapping[str, object] | BaseModel,
) -> PersonaCardBatchContentProposalV1:
    payload: object = (
        proposal.model_dump(mode="python")
        if isinstance(proposal, BaseModel)
        else proposal
    )
    if not isinstance(payload, Mapping):
        raise PersonaSourceCapsuleInputError(
            "persona_proposal_must_be_mapping_or_model"
        )
    try:
        return PersonaCardBatchContentProposalV1.model_validate(payload, strict=True)
    except ValidationError as exc:
        raise PersonaSourceCapsuleInputError(
            "persona_proposal_strict_decode_failed"
        ) from exc


def _field_values(
    proposal: PersonaCardBatchContentProposalV1,
) -> dict[str, list[tuple[str, str]]]:
    values: dict[str, list[tuple[str, str]]] = {
        "summary": [("summary", proposal.summary)],
        "relationship": [("relationship", proposal.relationship)],
        "cards.title": [],
        "cards.label": [],
        "cards.content": [],
        "cards.tags": [],
        "cards.source_note": [],
    }
    for index, card in enumerate(proposal.cards):
        prefix = f"cards[{index}]"
        values["cards.title"].append((f"{prefix}.title", card.title))
        values["cards.label"].append((f"{prefix}.label", card.label))
        values["cards.content"].append((f"{prefix}.content", card.content))
        values["cards.source_note"].append((f"{prefix}.source_note", card.source_note))
        values["cards.tags"].extend(
            (f"{prefix}.tags[{tag_index}]", tag)
            for tag_index, tag in enumerate(card.tags)
        )
    return values


def _sha256_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
