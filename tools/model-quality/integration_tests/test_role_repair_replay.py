import hashlib
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from model_quality.protocol import Campaign
from vibe_learner.common import envelope
from vibe_learner.role_repair_replay import RUBRIC, run_sample


EXPECTED_INITIAL = {
    "planned-rill-count": {
        "facts": {
            "activity": "shoreline count",
            "site": "Cove Rill",
            "planned_day": "Friday",
            "planned_time": "06:30",
            "lead": "Tomas",
            "method": "walking transect",
        },
        "activities": [5, 5, 5],
        "learner_prompt": (
            "Review the planned shoreline count at Cove Rill on Friday at 06:30. The lead is Tomas and the method is "
            "a walking transect. In your response, summarise what is being surveyed, who is leading the count, when it "
            "is scheduled, and how the walking transect method will be carried out during the 15-minute study window."
        ),
        "chart_questions": [],
    },
    "recorded-umber-signal": {
        "facts": {
            "signal": "Umber-2",
            "recorded_at": "07:14",
            "acknowledgement_by": "Tavi",
            "acknowledgement_at": "07:19",
            "current_label": "waiting",
        },
        "activities": [5, 5],
        "learner_prompt": (
            "A note records signal Umber-2 at 07:14, acknowledged by Tavi at 07:19. The current label is waiting. "
            "Use this 10-minute study window to review the event note, compare the recorded and acknowledgement times, "
            "and decide what action the waiting label requires."
        ),
        "chart_questions": [],
    },
}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class RoleRepairPreparationTests(unittest.TestCase):
    def prepare(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        budget_path = root / "budget.json"
        output = root / "manifest.json"
        budget = {
            "token_limit": 10_000_000,
            "wire_limit": 100,
            "rpm": 100,
            "tpm": 1_000_000,
            "max_inflight": 4,
            "expires_at": time.time() + 3600,
        }
        budget_path.write_text(json.dumps({"budget": budget}))
        script = Path(__file__).parents[1] / "examples" / "prepare_role_repair_replay.py"
        subprocess.run(
            [sys.executable, str(script), "--budget-from", str(budget_path), "--output", str(output)],
            check=True,
            cwd=script.parents[1],
        )
        return temporary, budget, json.loads(output.read_text())

    def test_manifest_freezes_actual_two_bad_drafts_and_matched_two_wire_arms(self):
        temporary, budget, data = self.prepare()
        with temporary:
            Campaign.model_validate(data)
            self.assertEqual(data["budget"], budget)
            self.assertEqual(data["concurrency"], 2)
            self.assertEqual(data["sample_wire_limit"], 2)
            self.assertEqual(
                ["self-revise-twice", "specialist-review-revise"],
                [variant["id"] for variant in data["variants"]],
            )
            self.assertEqual(set(EXPECTED_INITIAL), {case["id"] for case in data["cases"]})
            self.assertIn("manual semantic review", data["purpose"])
            for case in data["cases"]:
                self.assertEqual(case["rubric"], RUBRIC)
                self.assertEqual(json.loads(case["gold"])["initial_draft"], EXPECTED_INITIAL[case["id"]])


class RoleRepairAdapterTests(unittest.TestCase):
    def case(self):
        initial = EXPECTED_INITIAL["recorded-umber-signal"]
        return SimpleNamespace(
            id="recorded-umber-signal",
            source=(
                "Event note: signal Umber-2 was recorded at 07:14. Tavi acknowledged the note at 07:19. "
                "Current label: waiting. Available study time is 10 minutes."
            ),
            request="Create exactly 2 positive-duration activities totaling 10 minutes. This is text-only.",
            gold=json.dumps(
                {
                    "initial_draft": initial,
                    "facts": initial["facts"],
                    "minutes": 10,
                    "activity_count": 2,
                }
            ),
            rubric=RUBRIC,
        )

    def context(self, directory, responder):
        calls = []

        def request(payload, call_kind):
            calls.append((call_kind, payload))
            return responder(len(calls), call_kind, payload)

        context = SimpleNamespace(
            storage=Path(directory),
            transport=SimpleNamespace(
                campaign=SimpleNamespace(model="MiniMax-M3", max_output_tokens=4096, temperature=0.1),
                request=request,
            ),
        )
        return context, calls

    def repaired(self, suffix=""):
        initial = EXPECTED_INITIAL["recorded-umber-signal"]
        return {
            **initial,
            "learner_prompt": "Compare the two recorded times and report the current label." + suffix,
        }

    def test_both_arms_use_exactly_two_wires_and_keep_the_same_frozen_hash(self):
        frozen_hash = hashlib.sha256(canonical(EXPECTED_INITIAL["recorded-umber-signal"]).encode()).hexdigest()
        for variant_id, expected_kinds in (
            ("self-revise-twice", ["repair", "repair"]),
            ("specialist-review-revise", ["critic", "repair"]),
        ):
            with self.subTest(variant=variant_id), tempfile.TemporaryDirectory() as directory:
                def responder(number, call_kind, payload):
                    if call_kind == "critic":
                        return envelope(json.dumps({"issues": ["The action is unsupported."], "revision_guidance": "Remove it."}))
                    return envelope(json.dumps(self.repaired(str(number))))

                context, calls = self.context(directory, responder)
                result = run_sample(context, self.case(), SimpleNamespace(id=variant_id))
                evidence = json.loads((Path(directory) / "role-repair-evidence.json").read_text())
                self.assertEqual(result["status"], "completed")
                self.assertEqual([kind for kind, _ in calls], expected_kinds)
                self.assertEqual(len(calls), 2)
                self.assertEqual(evidence["initial_draft"], EXPECTED_INITIAL["recorded-umber-signal"])
                self.assertEqual(evidence["initial_draft_sha256"], frozen_hash)
                self.assertEqual(evidence["automated_semantic_verdict"], "not_assessed")
                self.assertFalse(evidence["learner_prompt_semantics_graded"])
                self.assertTrue(evidence["manual_semantic_review_required"])
                self.assertEqual(
                    set(evidence["metrics"]),
                    {"facts_exact", "minutes_valid", "chart_questions_empty"},
                )
                self.assertEqual(len(evidence["wire_prompts"]), 2)
                self.assertTrue(all(len(item["messages_sha256"]) == 64 for item in evidence["wire_prompts"]))
                self.assertTrue(all(len(item["draft_sha256"]) == 64 for item in evidence["drafts"]))

    def test_critic_payload_cannot_overwrite_or_be_promoted_as_a_repaired_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            def responder(number, call_kind, payload):
                # A Draft-shaped critic response must fail the strict Review
                # boundary; the repair wire must never be issued.
                return envelope(json.dumps(self.repaired()))

            context, calls = self.context(directory, responder)
            result = run_sample(context, self.case(), SimpleNamespace(id="specialist-review-revise"))
            evidence = json.loads((Path(directory) / "role-repair-evidence.json").read_text())
            self.assertEqual(result["status"], "candidate_failed")
            self.assertEqual([kind for kind, _ in calls], ["critic"])
            self.assertEqual(evidence["failure_stage"], "critic")
            self.assertTrue(evidence["frozen_draft_unchanged"])
            self.assertEqual(evidence["initial_draft"], EXPECTED_INITIAL["recorded-umber-signal"])
            self.assertEqual(evidence["drafts"], [])
            self.assertNotIn("final_draft", evidence)

    def test_unknown_rubric_and_variant_fail_before_any_wire(self):
        with tempfile.TemporaryDirectory() as directory:
            context, calls = self.context(directory, lambda *_: self.fail("wire must not be called"))
            wrong_rubric = self.case()
            wrong_rubric.rubric = "role-exact-v1"
            rubric_result = run_sample(context, wrong_rubric, SimpleNamespace(id="self-revise-twice"))
            self.assertEqual(rubric_result["error_code"], "unknown_role_repair_rubric")
            self.assertEqual(calls, [])

            variant_result = run_sample(context, self.case(), SimpleNamespace(id="unregistered-repair"))
            self.assertEqual(variant_result["error_code"], "unknown_role_repair_variant")
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
