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


TASK_BOUNDARY = " This is text-only; chart_questions must be empty."

CLUSTERS = {
    "study-time-scope": {
        "tram-dwell-nacre",
        "batch-cooling-saffron",
        "rehearsal-span-echo",
        "barge-unloading-tern",
    },
    "unperformed-modality": {
        "proposed-marsh-survey",
        "scheduled-mural-cleaning",
        "planned-mesa-core",
        "proposed-case-relocation",
    },
    "epistemic-workflow-boundary": {
        "reported-solace-tones",
        "listed-thistle-condition",
        "observed-wren-sequence",
        "recorded-aster-spike",
    },
}


class RoundFourPreparationTests(unittest.TestCase):
    def prepare(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        budget = root / "budget.json"
        output = root / "campaign.json"
        budget_payload = {
            "token_limit": 10_000_000,
            "wire_limit": 100,
            "rpm": 60,
            "tpm": 1_000_000,
            "max_inflight": 2,
            "expires_at": time.time() + 3600,
        }
        budget.write_text(json.dumps({"budget": budget_payload}))
        script = Path(__file__).parents[1] / "examples" / "prepare_text_iteration_round4.py"
        subprocess.run(
            [sys.executable, str(script), "--budget-from", str(budget), "--output", str(output)],
            check=True,
            cwd=script.parents[1],
        )
        return temporary, budget_payload, json.loads(output.read_text())

    def test_campaign_is_disjoint_balanced_and_single_wire(self):
        temporary, budget, data = self.prepare()
        with temporary:
            self.assertEqual(data["id"], "m3-text-iteration-20260913-round4")
            self.assertEqual(data["transport"], "minimax")
            self.assertEqual(data["budget"], budget)
            self.assertEqual(data["concurrency"], 2)
            self.assertEqual(data["seed"], 913)
            self.assertEqual(data["repetitions"], 1)
            self.assertEqual(data["sample_wire_limit"], 1)
            self.assertEqual(
                ["source-minimal", "source-minimal-v2"],
                [variant["id"] for variant in data["variants"]],
            )
            self.assertEqual({name: len(ids) for name, ids in CLUSTERS.items()}, {
                "study-time-scope": 4,
                "unperformed-modality": 4,
                "epistemic-workflow-boundary": 4,
            })
            expected_ids = set().union(*CLUSTERS.values())
            self.assertEqual({case["id"] for case in data["cases"]}, expected_ids)
            self.assertEqual(len(data["cases"]), 12)
            self.assertEqual(len({case["family"] for case in data["cases"]}), 12)

            previously_exposed = {
                "plan-pages", "plan-scope", "media-chart", "media-question",
                "condition-window", "appendix-page-map", "unknown-denominator",
                "third-party-speakers", "cancellation-access", "policy-effective-time",
                "observational-claim", "source-priority", "cold-chain-replica-exception",
                "roof-endorsement-scope", "ferry-authority-waiver", "refurbished-pack-exclusion",
                "tariff-recorded-effective", "license-entry-suspension", "dispatcher-relayed-report",
                "supplier-delay-attribution", "quarantine-bin-unknown",
                "appointment-room-only-correction", "pallet-mass-amendment",
                "single-salinity-no-chart", "register-cardinal-slip", "register-bracken-file",
                "recorded-umber-signal", "recorded-marlin-message", "inspection-pending-entry",
                "visit-willow-fragment", "reported-quill-lamp", "observed-delta-vireo",
                "scheduled-cobalt-filter", "planned-rill-count", "glossary-floral-whorls",
                "valve-pine-card",
            }
            self.assertTrue(previously_exposed.isdisjoint(expected_ids))
            self.assertTrue(all(case["id"] == case["family"] for case in data["cases"]))
            self.assertTrue(all(case["split"] == "development" for case in data["cases"]))
            self.assertIn("not semantic quality", data["purpose"])
            self.assertIn("clause-by-clause manual semantic review", data["purpose"])

            from model_quality.protocol import Campaign

            Campaign.model_validate(data)

    def test_gold_schedule_task_boundary_and_no_answer_leaking_prohibitions(self):
        temporary, _, data = self.prepare()
        with temporary:
            cases = {case["id"]: case for case in data["cases"]}
            expected = {
                "tram-dwell-nacre": ({"tram": "Nacre-12", "platform": "Platform Moss", "dwell_start": "05:48", "dwell_end": "06:17", "dwell_minutes": "29"}, 8, 2),
                "batch-cooling-saffron": ({"batch": "Saffron-21", "start_temperature": "110", "end_temperature": "24", "temperature_unit": "°C", "cooling_minutes": "75"}, 7, 1),
                "rehearsal-span-echo": ({"rehearsal": "Echo-17", "start_time": "19:10", "end_time": "20:35", "duration_minutes": "85", "conductor": "Luma"}, 11, 2),
                "barge-unloading-tern": ({"barge": "Tern-44", "quay": "Quay Amber", "unloading_start": "03:12", "unloading_minutes": "44", "foreperson": "Kes"}, 9, 3),
                "proposed-marsh-survey": ({"proposed_activity": "aerial survey", "site": "Marsh Fenwick", "proposed_day": "next Tuesday", "proposed_time": "09:15", "proposed_lead": "Oren", "suggested_instrument": "magnetometer"}, 12, 3),
                "scheduled-mural-cleaning": ({"activity": "mural cleaning", "location": "Gallery Sable", "scheduled_date": "2027-01-09", "scheduled_time": "08:00", "assigned_person": "Niva", "calendar_state": "scheduled"}, 10, 2),
                "planned-mesa-core": ({"planned_activity": "soil-core collection", "site": "Mesa Dray", "planned_day": "Monday", "coordinator": "Yara", "named_equipment": "rotary corer"}, 13, 2),
                "proposed-case-relocation": ({"case": "Kite-28", "origin": "Bay Linen", "proposed_destination": "Vault Pecan", "proposed_date": "2027-02-18", "proposal_owner": "Dev", "proposal_status": "proposed"}, 6, 1),
                "reported-solace-tones": ({"reporter": "Niko", "reported_subject": "beacon Solace-3", "reported_event": "emitted three short tones", "scribe": "Pera", "note_time": "21:06"}, 14, 3),
                "listed-thistle-condition": ({"specimen": "Thistle-26", "listed_condition": "brittle", "drawer": "Quartz", "cataloguer": "Rafi", "entry_date": "2027-03-02"}, 5, 1),
                "observed-wren-sequence": ({"observer": "Zuri", "first_event": "a wake crossed channel Wren", "later_event": "reeds bend", "observation_count": "1", "viewing_point": "Dock Juniper"}, 8, 2),
                "recorded-aster-spike": ({"instrument": "gauge Aster-15", "recorded_event": "pressure spike", "recorded_at": "04:27", "peak_value": "18", "peak_unit": "kPa", "ledger_state": "retained"}, 15, 3),
            }
            for case_id, (facts, minutes, activity_count) in expected.items():
                gold = json.loads(cases[case_id]["gold"])
                self.assertEqual(gold, {
                    "facts": facts,
                    "minutes": minutes,
                    "activity_count": activity_count,
                    "forbidden": [],
                })
                self.assertTrue(cases[case_id]["request"].endswith(TASK_BOUNDARY))

            leaked_prohibitions = (
                "do not perform", "never perform", "remains unperformed", "do not simulate",
                "do not verify", "do not submit", "submission workflow", "handoff workflow",
                "compliance workflow", "do not treat study time", "real-world operation",
            )
            for case in cases.values():
                request = case["request"].casefold()
                self.assertFalse(any(phrase in request for phrase in leaked_prohibitions))
                self.assertIn("chart_questions must be empty", request)


class SourceMinimalV2WireTests(unittest.TestCase):
    def test_v2_is_one_wire_and_semantics_remain_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def request(payload, call_kind):
                calls.append((call_kind, payload))
                return envelope(json.dumps({
                    "facts": {"proposal_status": "proposed"},
                    "activities": [6],
                    "learner_prompt": "According to the source, state the proposal status.",
                    "chart_questions": [],
                }))

            context = SimpleNamespace(
                storage=Path(directory),
                transport=SimpleNamespace(
                    campaign=SimpleNamespace(model="MiniMax-M3", max_output_tokens=4096, temperature=0.1),
                    request=request,
                ),
            )
            case = SimpleNamespace(
                id="round4-wire-check",
                source="Proposal status: proposed. Available learning time: 6 minutes.",
                request="Create exactly one 6-minute activity." + TASK_BOUNDARY,
                gold=json.dumps({
                    "facts": {"proposal_status": "proposed"},
                    "minutes": 6,
                    "activity_count": 1,
                    "forbidden": [],
                }),
                rubric="role-exact-v1",
            )
            result = run_sample(context, case, SimpleNamespace(id="source-minimal-v2"))
            evidence = json.loads((Path(directory) / "role-evidence.json").read_text())

            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "generation")
            system_prompt = calls[0][1]["messages"][0]["content"]
            self.assertEqual(system_prompt.count(GENERATION_VARIANTS["source-minimal-v2"]), 1)
            self.assertFalse(evidence["learner_prompt_semantics_graded"])
            self.assertTrue(evidence["manual_semantic_review_required"])
            self.assertEqual(evidence["automated_grade_scope"], "strict structured fields and prompt presence only")


if __name__ == "__main__":
    unittest.main()
