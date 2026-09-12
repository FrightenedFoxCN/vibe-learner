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
    "source-time-modality": {
        "proposed-neris-acoustic",
        "scheduled-orchid-ventilation",
        "planned-lumen-antenna",
        "proposed-sorrel-transfer",
        "scheduled-pyre-turbine",
        "planned-selene-water-sample",
    },
    "complete-source-span": {
        "proposed-neris-acoustic",
        "scheduled-orchid-ventilation",
        "planned-lumen-antenna",
        "proposed-sorrel-transfer",
        "scheduled-pyre-turbine",
        "planned-selene-water-sample",
        "docked-brindle-service-berth",
        "measured-elara-spectrum",
        "listed-cirrus-fan",
    },
    "epistemic-workflow-regression": {
        "measured-elara-spectrum",
        "listed-cirrus-fan",
        "reported-vela-pump",
        "observed-pelican-shadow",
        "recorded-lyra-detector",
    },
}

EXPECTED = {
    "proposed-neris-acoustic": ({"proposed_activity": "acoustic survey", "survey_site": "Inlet Cedar", "proposed_day": "Thursday", "proposed_time": "07:25", "proposed_lead": "Ivo", "suggested_equipment": "towed hydrophone array Neris-40"}, 12, 3),
    "scheduled-orchid-ventilation": ({"scheduled_activity": "ventilation test", "location": "Conservatory Wing Orchid", "scheduled_date": "2027-04-19", "scheduled_time": "06:40", "assigned_engineer": "Sena", "calendar_status": "scheduled"}, 9, 2),
    "planned-lumen-antenna": ({"planned_activity": "antenna alignment", "site": "Ridge Lumen", "planned_day": "Monday", "coordinator": "Pavo", "named_equipment": "dual-band dish antenna Corax-18"}, 13, 2),
    "proposed-sorrel-transfer": ({"folio": "specimen folio Heron-63", "origin": "Reading Room Sorrel", "proposed_destination": "Archive Vault Umber", "proposed_date": "2027-05-03", "proposed_carrier": "insulated document case Vale-22", "sheet_state": "proposed"}, 6, 1),
    "scheduled-pyre-turbine": ({"scheduled_activity": "inspection", "device": "ventilation turbine Pyre-27", "scheduled_for": "2027-05-11 14:10", "assigned_name": "Kala", "board_label": "scheduled"}, 10, 2),
    "planned-selene-water-sample": ({"planned_activity": "groundwater sampling", "site": "Monitoring Well Selene", "planned_day": "Friday", "planned_time": "08:35", "lead": "Runa", "specified_device": "low-flow sampling pump Aven-9"}, 15, 3),
    "docked-brindle-service-berth": ({"vessel": "cargo tug Brindle-52", "berth": "Service Berth Lilac", "docked_at": "02:18", "mooring_minutes": "37", "harbor_clerk": "Osa"}, 8, 2),
    "measured-elara-spectrum": ({"instrument": "portable Raman spectrometer Elara-14", "measured_peak": "812", "peak_unit": "cm⁻¹", "measured_at": "11:32", "operator": "Toma", "note_status": "retained"}, 11, 2),
    "listed-cirrus-fan": ({"asset": "emergency ventilation fan Cirrus-8", "listed_status": "available", "location": "Mechanical Bay Violet", "custodian": "Eren", "entry_date": "2027-05-16"}, 5, 1),
    "reported-vela-pump": ({"reporter": "Mira", "reported_subject": "circulation pump Vela-31", "reported_event": "made two clicking sounds", "transcriber": "Noa", "transcribed_at": "17:46"}, 14, 3),
    "observed-pelican-shadow": ({"observer": "Aru", "first_event": "a cloud shadow crossed Lagoon Pelican", "later_event": "three terns settled beside Marker Post Sienna", "observation_count": "1"}, 7, 1),
    "recorded-lyra-detector": ({"instrument": "ultraviolet flame detector Lyra-6", "recorded_event": "one alert", "recorded_at": "04:52", "display_code": "F2", "recorder_status": "active"}, 16, 3),
}


class RoundFivePreparationTests(unittest.TestCase):
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
        script = Path(__file__).parents[1] / "examples" / "prepare_text_iteration_round5.py"
        subprocess.run(
            [sys.executable, str(script), "--budget-from", str(budget), "--output", str(output)],
            check=True,
            cwd=script.parents[1],
        )
        return temporary, budget_payload, json.loads(output.read_text())

    def test_campaign_is_disjoint_balanced_development_and_single_wire(self):
        temporary, budget, data = self.prepare()
        with temporary:
            self.assertEqual(data["id"], "m3-text-iteration-20260913-round5")
            self.assertEqual(data["transport"], "minimax")
            self.assertEqual(data["budget"], budget)
            self.assertEqual(data["concurrency"], 2)
            self.assertEqual(data["seed"], 913)
            self.assertEqual(data["repetitions"], 1)
            self.assertEqual(data["sample_wire_limit"], 1)
            self.assertEqual(
                ["source-minimal-v2", "source-minimal-v3"],
                [variant["id"] for variant in data["variants"]],
            )
            expected_ids = set(EXPECTED)
            self.assertEqual({case["id"] for case in data["cases"]}, expected_ids)
            self.assertEqual(len(data["cases"]), 12)
            self.assertTrue(all(case["id"] == case["family"] for case in data["cases"]))
            self.assertTrue(all(case["split"] == "development" for case in data["cases"]))
            self.assertIn("not an independent holdout", data["purpose"])
            self.assertIn("not semantic quality", data["purpose"])
            self.assertIn("clause-by-clause manual semantic review", data["purpose"])

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
                "valve-pine-card", "tram-dwell-nacre", "batch-cooling-saffron",
                "rehearsal-span-echo", "barge-unloading-tern", "proposed-marsh-survey",
                "scheduled-mural-cleaning", "planned-mesa-core", "proposed-case-relocation",
                "reported-solace-tones", "listed-thistle-condition", "observed-wren-sequence",
                "recorded-aster-spike",
            }
            self.assertTrue(previously_exposed.isdisjoint(expected_ids))
            self.assertEqual(len(CLUSTERS["source-time-modality"]), 6)
            self.assertEqual(len(CLUSTERS["complete-source-span"]), 9)
            self.assertEqual(len(CLUSTERS["epistemic-workflow-regression"]), 5)
            self.assertEqual(set().union(*CLUSTERS.values()), expected_ids)

            from model_quality.protocol import Campaign

            Campaign.model_validate(data)

    def test_gold_schedule_and_task_does_not_leak_manual_rules(self):
        temporary, _, data = self.prepare()
        with temporary:
            cases = {case["id"]: case for case in data["cases"]}
            for case_id, (facts, minutes, activity_count) in EXPECTED.items():
                self.assertEqual(
                    json.loads(cases[case_id]["gold"]),
                    {
                        "facts": facts,
                        "minutes": minutes,
                        "activity_count": activity_count,
                        "forbidden": [],
                    },
                )
                self.assertTrue(cases[case_id]["request"].endswith(TASK_BOUNDARY))

            leaked_rules = (
                "not yet", "still unperformed", "remains unperformed", "later unperformed",
                "do not perform", "never perform", "do not simulate", "do not verify",
                "complete source span", "location prefix", "equipment prefix", "type prefix",
                "submission workflow", "handoff workflow", "approval workflow",
                "follow-up workflow", "real-world operation",
            )
            for case in cases.values():
                request = case["request"].casefold()
                self.assertFalse(any(phrase in request for phrase in leaked_rules))
                self.assertIn("chart_questions must be empty", request)


class SourceMinimalV3WireTests(unittest.TestCase):
    def test_v3_is_one_wire_and_semantics_remain_manual(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def request(payload, call_kind):
                calls.append((call_kind, payload))
                return envelope(json.dumps({
                    "facts": {"device": "ventilation turbine Pyre-27"},
                    "activities": [4, 6],
                    "learner_prompt": "According to the source, state the scheduled device.",
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
                id="round5-wire-check",
                source="Inspection of ventilation turbine Pyre-27 is scheduled. Learning budget: 10 minutes.",
                request="Create exactly 2 positive-duration activities totaling 10 minutes." + TASK_BOUNDARY,
                gold=json.dumps({
                    "facts": {"device": "ventilation turbine Pyre-27"},
                    "minutes": 10,
                    "activity_count": 2,
                    "forbidden": [],
                }),
                rubric="role-exact-v1",
            )
            result = run_sample(context, case, SimpleNamespace(id="source-minimal-v3"))
            evidence = json.loads((Path(directory) / "role-evidence.json").read_text())

            self.assertEqual(result["status"], "completed")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], "generation")
            system_prompt = calls[0][1]["messages"][0]["content"]
            self.assertEqual(system_prompt.count(GENERATION_VARIANTS["source-minimal-v3"]), 1)
            self.assertFalse(evidence["learner_prompt_semantics_graded"])
            self.assertTrue(evidence["manual_semantic_review_required"])
            self.assertEqual(
                evidence["automated_grade_scope"],
                "strict structured fields and prompt presence only",
            )


if __name__ == "__main__":
    unittest.main()
