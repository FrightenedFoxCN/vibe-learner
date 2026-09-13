from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import unittest

from pydantic import ValidationError

AI_SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services" / "ai"
sys.path.insert(0, str(AI_SERVICE_ROOT))

from app.models.persona_generation import PersonaCardBatchContentProposalV1  # noqa: E402
from vibe_learner.persona_source_capsule import (  # noqa: E402
    PersonaSourceCapsuleFixtureV1,
    PersonaSourceCapsuleInputError,
    PersonaSourceConstraintCapsuleV1,
    validate_persona_source_constraints,
)


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "persona-scene"
    / "persona-source-capsule-v1.json"
)
EXPECTED_FIXTURE_SHA256 = "bf24f623b4644765133d0a9e94fb24f96984c92252a13323f9584c0e79106a23"


def _replace_pointer(payload: dict[str, object], path: str, value: str) -> dict[str, object]:
    mutated = deepcopy(payload)
    tokens = path.removeprefix("/").split("/")
    parent: object = mutated
    for token in tokens[:-1]:
        parent = (
            parent[int(token)]
            if isinstance(parent, list)
            else parent[token]  # type: ignore[index]
        )
    leaf = tokens[-1]
    if isinstance(parent, list):
        parent[int(leaf)] = value
    else:
        parent[leaf] = value  # type: ignore[index]
    return mutated


class PersonaSourceCapsuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.fixture_bytes = FIXTURE_PATH.read_bytes()
        cls.fixture_dict = json.loads(cls.fixture_bytes)
        cls.fixture = PersonaSourceCapsuleFixtureV1.model_validate(
            cls.fixture_dict, strict=True
        )

    def test_fixture_is_stable_and_has_eight_new_unique_families(self):
        self.assertEqual(sha256(self.fixture_bytes).hexdigest(), EXPECTED_FIXTURE_SHA256)
        self.assertEqual(len(self.fixture.cases), 8)
        self.assertEqual(len({case.case_id for case in self.fixture.cases}), 8)
        legacy_fragments = ("姐姐", "姨妈", "红海", "审计", "种子库")
        serialized = self.fixture_bytes.decode("utf-8")
        for fragment in legacy_fragments:
            self.assertNotIn(fragment, serialized)

    def test_pristine_and_hard_negative_controls_pass(self):
        marker_fields: set[str] = set()
        for case in self.fixture.cases:
            self.assertEqual(
                {claim.claim_kind for claim in case.capsule.claims},
                {"relationship", "permission", "profession", "shared_history", "epistemic"},
            )
            self.assertEqual(
                {claim.polarity for claim in case.capsule.claims},
                {"asserted", "denied", "unknown"},
            )
            marker_fields.update(
                marker.field
                for transformation in case.capsule.forbidden_transformations
                for marker in transformation.markers
            )
            with self.subTest(case=case.case_id, arm="pristine"):
                proposal = PersonaCardBatchContentProposalV1.model_validate(
                    case.valid_minimal_persona_card_batch_proposal, strict=True
                )
                self.assertEqual(
                    validate_persona_source_constraints(
                        case.capsule, case.source_text, proposal
                    ),
                    [],
                )
            with self.subTest(case=case.case_id, arm="hard_negative"):
                # Exact-field matching deliberately ignores markers embedded in
                # explicit denials/quotations; this is not semantic inference.
                self.assertEqual(
                    validate_persona_source_constraints(
                        case.capsule,
                        case.source_text,
                        case.hard_negative_persona_card_batch_proposal,
                    ),
                    [],
                )
        self.assertEqual(
            marker_fields,
            {
                "summary",
                "relationship",
                "cards.title",
                "cards.label",
                "cards.content",
                "cards.tags",
                "cards.source_note",
            },
        )

    def test_every_single_pointer_mutation_hits_exactly_its_target_code(self):
        calibrated = 0
        for case in self.fixture.cases:
            self.assertEqual(len(case.single_point_mutations), 6)
            for mutation in case.single_point_mutations:
                with self.subTest(case=case.case_id, mutation=mutation.mutation_id):
                    self.assertEqual(mutation.operation, "replace")
                    mutated = _replace_pointer(
                        case.valid_minimal_persona_card_batch_proposal,
                        mutation.path,
                        mutation.value,
                    )
                    issues = validate_persona_source_constraints(
                        case.capsule, case.source_text, mutated
                    )
                    self.assertEqual([issue.code for issue in issues], [mutation.expected_code])
                    calibrated += 1
        self.assertEqual(calibrated, 48)

    def test_malformed_proposal_fails_closed(self):
        case = self.fixture.cases[0]
        malformed = deepcopy(case.valid_minimal_persona_card_batch_proposal)
        malformed["cards"][0]["unexpected"] = True
        malformed["cards"][0]["tags"] = [1]
        with self.assertRaisesRegex(
            PersonaSourceCapsuleInputError, "persona_proposal_strict_decode_failed"
        ):
            validate_persona_source_constraints(case.capsule, case.source_text, malformed)

    def test_source_and_capsule_digest_tampering_fail_closed(self):
        case = self.fixture.cases[0]
        with self.assertRaisesRegex(PersonaSourceCapsuleInputError, "source_sha256"):
            validate_persona_source_constraints(
                case.capsule,
                case.source_text + "篡改",
                case.valid_minimal_persona_card_batch_proposal,
            )
        tampered = deepcopy(self.fixture_dict)
        tampered["cases"][0]["capsule"]["claims"][0]["claim_key"] += "_tampered"
        with self.assertRaisesRegex(ValidationError, "capsule_sha256_mismatch"):
            PersonaSourceCapsuleFixtureV1.model_validate(tampered, strict=True)

        address_tampered = deepcopy(self.fixture_dict)
        address_tampered["cases"][0]["capsule"]["address_exact"] += "篡改"
        address_tampered["cases"][0]["capsule_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            ValidationError, "address_source_span_text_mismatch"
        ):
            PersonaSourceCapsuleFixtureV1.model_validate(address_tampered, strict=True)

        missing_address = deepcopy(self.fixture_dict["cases"][0])
        missing_address["source_text"] = missing_address["source_text"].replace(
            missing_address["capsule"]["address_exact"], "", 1
        )
        with self.assertRaisesRegex(PersonaSourceCapsuleInputError, "source_sha256"):
            validate_persona_source_constraints(
                PersonaSourceConstraintCapsuleV1.model_validate(
                    missing_address["capsule"], strict=True
                ),
                missing_address["source_text"],
                missing_address["valid_minimal_persona_card_batch_proposal"],
            )

    def test_wrong_unicode_or_utf8_span_and_text_digest_fail(self):
        case = deepcopy(self.fixture_dict["cases"][0])
        # Move the final span past its frozen slice. Moving an interior span
        # would correctly trip the overlap invariant before this slice check.
        case["capsule"]["claims"][-1]["source_span"]["char_start"] += 1
        case["capsule"]["claims"][-1]["source_span"]["char_end"] += 1
        # Recompute capsule digest so the source-coordinate validator, rather
        # than the outer tamper seal, is what rejects this edit.
        capsule = PersonaSourceConstraintCapsuleV1.model_validate(
            case["capsule"], strict=True
        )
        with self.assertRaisesRegex(PersonaSourceCapsuleInputError, "char_slice"):
            validate_persona_source_constraints(
                capsule, case["source_text"], case["valid_minimal_persona_card_batch_proposal"]
            )

        bad_digest = deepcopy(self.fixture_dict["cases"][0]["capsule"])
        bad_digest["claims"][0]["source_span"]["text_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "text_sha256_mismatch"):
            PersonaSourceConstraintCapsuleV1.model_validate(bad_digest, strict=True)

        bad_utf8 = deepcopy(self.fixture_dict["cases"][0]["capsule"])
        bad_utf8["claims"][-1]["source_span"]["utf8_byte_start"] += 1
        bad_utf8["claims"][-1]["source_span"]["utf8_byte_end"] += 1
        capsule = PersonaSourceConstraintCapsuleV1.model_validate(bad_utf8, strict=True)
        with self.assertRaisesRegex(PersonaSourceCapsuleInputError, "utf8_boundary"):
            validate_persona_source_constraints(
                capsule,
                self.fixture.cases[0].source_text,
                self.fixture.cases[0].valid_minimal_persona_card_batch_proposal,
            )

    def test_duplicate_overlap_contradiction_and_missing_claim_kind_rejected(self):
        capsule = deepcopy(self.fixture_dict["cases"][0]["capsule"])
        capsule["claims"][1]["claim_id"] = capsule["claims"][0]["claim_id"]
        with self.assertRaisesRegex(ValidationError, "duplicate_claim_id"):
            PersonaSourceConstraintCapsuleV1.model_validate(capsule, strict=True)

        capsule = deepcopy(self.fixture_dict["cases"][0]["capsule"])
        capsule["claims"][1]["source_span"] = deepcopy(capsule["claims"][0]["source_span"])
        with self.assertRaisesRegex(ValidationError, "overlapping_claim_source_spans"):
            PersonaSourceConstraintCapsuleV1.model_validate(capsule, strict=True)

        capsule = deepcopy(self.fixture_dict["cases"][0]["capsule"])
        conflicting = deepcopy(capsule["claims"][0])
        conflicting["claim_id"] = "conflicting-polarity"
        conflicting["polarity"] = "denied"
        # Polarity ambiguity is checked before the now-overlapping extra span.
        capsule["claims"].append(conflicting)
        with self.assertRaisesRegex(ValidationError, "contradictory_claim_polarity"):
            PersonaSourceConstraintCapsuleV1.model_validate(capsule, strict=True)

        capsule = deepcopy(self.fixture_dict["cases"][0]["capsule"])
        capsule["claims"][1]["claim_kind"] = "relationship"
        capsule["claims"][1]["claim_key"] = "another_relationship_fact"
        with self.assertRaisesRegex(ValidationError, "missing_explicit_claim_kind"):
            PersonaSourceConstraintCapsuleV1.model_validate(capsule, strict=True)

    def test_policy_marker_tamper_is_bound_by_capsule_digest(self):
        fixture = deepcopy(self.fixture_dict)
        marker = fixture["cases"][0]["capsule"]["forbidden_transformations"][0][
            "markers"
        ][0]
        marker["literal"] += "x"
        with self.assertRaisesRegex(ValidationError, "capsule_sha256_mismatch"):
            PersonaSourceCapsuleFixtureV1.model_validate(fixture, strict=True)


if __name__ == "__main__":
    unittest.main()
