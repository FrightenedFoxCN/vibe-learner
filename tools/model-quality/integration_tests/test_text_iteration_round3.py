import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from vibe_learner.common import envelope
from vibe_learner.role_exploration import GENERATION_VARIANTS, run_sample


TASK_BOUNDARY = (
    " Keep learner_prompt within the source and requested activity; do not add source-external "
    "facts or unstated delivery arrangements. This is text-only; chart_questions must be empty."
)

SOURCE_MINIMAL_POLICY = (
    'Write learner_prompt as a concise, executable teaching instruction fully supported by the SOURCE and TASK. '
    'State a concrete learner action and the expected response. Include only source facts needed to make the '
    'activity answerable, preserving their wording and relationships. Do not add, specialize, rename, or imply '
    'any entity, role, attribute, event, provenance, workflow step, timer, submission mechanism, evaluation '
    'criterion, causal claim, or reliability claim that the SOURCE or TASK does not establish. Preserve temporal, '
    'modal, epistemic, speaker, and exception distinctions exactly. Prefer neutral references such as “the source” '
    'or “the requested facts” when added context is unnecessary. Return only the final proposal.'
)


class RoundThreePreparationTests(unittest.TestCase):
    def prepare(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        budget = root / "budget.json"
        output = root / "campaign.json"
        budget.write_text(
            json.dumps(
                {
                    "budget": {
                        "token_limit": 10_000_000,
                        "wire_limit": 100,
                        "rpm": 100,
                        "tpm": 1_000_000,
                        "max_inflight": 4,
                        "expires_at": time.time() + 3600,
                    }
                }
            )
        )
        script = Path(__file__).parents[1] / "examples" / "prepare_text_iteration_round3.py"
        subprocess.run(
            [
                sys.executable,
                str(script),
                "--budget-from",
                str(budget),
                "--output",
                str(output),
            ],
            check=True,
            cwd=script.parents[1],
        )
        return temporary, json.loads(output.read_text())

    def test_campaign_has_twelve_new_families_two_arms_and_one_wire(self):
        temporary, data = self.prepare()
        with temporary:
            self.assertEqual(data["id"], "m3-text-iteration-20260913-round3")
            self.assertEqual(data["transport"], "minimax")
            self.assertEqual(data["concurrency"], 2)
            self.assertEqual(data["sample_wire_limit"], 1)
            self.assertEqual(
                ["baseline", "source-minimal"],
                [variant["id"] for variant in data["variants"]],
            )
            self.assertEqual(len(data["cases"]), 12)
            self.assertEqual(len({case["family"] for case in data["cases"]}), 12)

            previously_exposed = {
                "plan-pages",
                "plan-scope",
                "media-chart",
                "media-question",
                "condition-window",
                "appendix-page-map",
                "unknown-denominator",
                "third-party-speakers",
                "cancellation-access",
                "policy-effective-time",
                "observational-claim",
                "source-priority",
                "cold-chain-replica-exception",
                "roof-endorsement-scope",
                "ferry-authority-waiver",
                "refurbished-pack-exclusion",
                "tariff-recorded-effective",
                "license-entry-suspension",
                "dispatcher-relayed-report",
                "supplier-delay-attribution",
                "quarantine-bin-unknown",
                "appointment-room-only-correction",
                "pallet-mass-amendment",
                "single-salinity-no-chart",
            }
            new_families = {case["family"] for case in data["cases"]}
            self.assertTrue(previously_exposed.isdisjoint(new_families))
            self.assertTrue(all(case["id"] == case["family"] for case in data["cases"]))
            self.assertTrue(all(case["split"] == "development" for case in data["cases"]))
            self.assertTrue(all(case["request"].endswith(TASK_BOUNDARY) for case in data["cases"]))
            self.assertIn("Automated results cover structure and exact fields", data["purpose"])
            self.assertIn("not semantic quality", data["purpose"])
            self.assertIn("every complete Draft requires clause-by-clause manual semantic review", data["purpose"])

            from model_quality.protocol import Campaign

            Campaign.model_validate(data)

    def test_gold_preserves_registered_facts_times_and_manual_review_boundary(self):
        temporary, data = self.prepare()
        with temporary:
            cases = {case["id"]: case for case in data["cases"]}
            expected_ids = {
                "register-cardinal-slip",
                "register-bracken-file",
                "recorded-umber-signal",
                "recorded-marlin-message",
                "inspection-pending-entry",
                "visit-willow-fragment",
                "reported-quill-lamp",
                "observed-delta-vireo",
                "scheduled-cobalt-filter",
                "planned-rill-count",
                "glossary-floral-whorls",
                "valve-pine-card",
            }
            self.assertEqual(set(cases), expected_ids)
            gold = {case_id: json.loads(case["gold"]) for case_id, case in cases.items()}
            self.assertTrue(all(value["forbidden"] == [] for value in gold.values()))
            self.assertTrue(all("chart_questions must be empty" in case["request"] for case in cases.values()))
            self.assertEqual(
                gold["recorded-umber-signal"]["facts"],
                {
                    "signal": "Umber-2",
                    "recorded_at": "07:14",
                    "acknowledgement_by": "Tavi",
                    "acknowledgement_at": "07:19",
                    "current_label": "waiting",
                },
            )
            self.assertEqual(gold["recorded-marlin-message"]["facts"]["recorded_date"], "2026-12-04")
            self.assertEqual(gold["inspection-pending-entry"]["facts"]["occurred_at"], "13:25")
            self.assertEqual(gold["visit-willow-fragment"]["facts"]["visit_at"], "10:05")
            self.assertEqual(gold["reported-quill-lamp"]["facts"]["entered_at"], "18:05")
            self.assertEqual(gold["observed-delta-vireo"]["facts"]["observation_count"], "1")
            self.assertEqual(
                gold["scheduled-cobalt-filter"]["facts"]["scheduled_for"],
                "2026-12-08 11:20",
            )
            self.assertEqual(gold["planned-rill-count"]["facts"]["planned_time"], "06:30")
            self.assertEqual(gold["register-cardinal-slip"]["facts"]["office_field"], "Blue")
            self.assertEqual(gold["register-bracken-file"]["facts"]["office_field"], "East Window")
            self.assertEqual(gold["glossary-floral-whorls"]["facts"]["second_definition"], "inner floral whorl")
            self.assertEqual(gold["valve-pine-card"]["facts"]["card_revision"], "R3")

            expected_schedule = {
                "register-cardinal-slip": (9, 2),
                "register-bracken-file": (7, 1),
                "recorded-umber-signal": (10, 2),
                "recorded-marlin-message": (11, 2),
                "inspection-pending-entry": (8, 2),
                "visit-willow-fragment": (6, 1),
                "reported-quill-lamp": (12, 3),
                "observed-delta-vireo": (13, 2),
                "scheduled-cobalt-filter": (14, 3),
                "planned-rill-count": (15, 3),
                "glossary-floral-whorls": (5, 1),
                "valve-pine-card": (16, 2),
            }
            self.assertEqual(
                {case_id: (value["minutes"], value["activity_count"]) for case_id, value in gold.items()},
                expected_schedule,
            )


class SourceMinimalWireTests(unittest.TestCase):
    def test_source_minimal_is_injected_exactly_once_and_requires_manual_semantic_review(self):
        self.assertEqual(GENERATION_VARIANTS["source-minimal"], SOURCE_MINIMAL_POLICY)
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def request(payload, call_kind):
                calls.append((call_kind, payload))
                return envelope(
                    json.dumps(
                        {
                            "facts": {"recorded_at": "07:14"},
                            "activities": [4, 6],
                            "learner_prompt": "Compare the recorded time with the requested fact and state the time.",
                            "chart_questions": [],
                        }
                    )
                )

            context = SimpleNamespace(
                storage=Path(directory),
                transport=SimpleNamespace(
                    campaign=SimpleNamespace(model="MiniMax-M3", max_output_tokens=4096, temperature=0.1),
                    request=request,
                ),
            )
            case = SimpleNamespace(
                id="recorded-wire-check",
                source="Signal Umber-2 was recorded at 07:14.",
                request="Create two activities totaling 10 minutes." + TASK_BOUNDARY,
                gold=json.dumps(
                    {
                        "facts": {"recorded_at": "07:14"},
                        "minutes": 10,
                        "activity_count": 2,
                        "forbidden": [],
                    }
                ),
                rubric="role-exact-v1",
            )
            result = run_sample(context, case, SimpleNamespace(id="source-minimal"))
            evidence = json.loads((Path(directory) / "role-evidence.json").read_text())

            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "generation")
            system_prompt = calls[0][1]["messages"][0]["content"]
            self.assertEqual(system_prompt.count(SOURCE_MINIMAL_POLICY), 1)
            self.assertNotIn("silently turn every explicit task constraint", system_prompt)
            self.assertFalse(evidence["learner_prompt_semantics_graded"])
            self.assertTrue(evidence["manual_semantic_review_required"])
            self.assertEqual(
                evidence["automated_grade_scope"],
                "strict structured fields and prompt presence only",
            )


if __name__ == "__main__":
    unittest.main()
