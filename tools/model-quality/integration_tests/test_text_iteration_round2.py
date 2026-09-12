import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


class RoundTwoPreparationTests(unittest.TestCase):
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
        script = Path(__file__).parents[1] / "examples" / "prepare_text_iteration_round2.py"
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

    def test_campaign_has_twelve_disjoint_development_families_and_two_arms(self):
        temporary, data = self.prepare()
        with temporary:
            self.assertEqual(data["id"], "m3-text-iteration-20260913-round2")
            self.assertEqual(data["transport"], "minimax")
            self.assertEqual(data["concurrency"], 2)
            self.assertEqual(
                ["baseline", "constraint-checklist"],
                [variant["id"] for variant in data["variants"]],
            )
            self.assertEqual(len(data["cases"]), 12)
            self.assertEqual(len({case["family"] for case in data["cases"]}), 12)
            historical = {
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
            }
            self.assertTrue(historical.isdisjoint({case["family"] for case in data["cases"]}))
            self.assertTrue(all(case["split"] == "development" for case in data["cases"]))
            self.assertTrue(all(case["provenance"] == "synthetic-authored" for case in data["cases"]))
            self.assertIn("not semantic-quality scores", data["purpose"])
            self.assertIn("not independently reviewed evidence", data["purpose"])

            from model_quality.protocol import Campaign

            Campaign.model_validate(data)

    def test_gold_and_requests_preserve_exact_round_two_constraints(self):
        temporary, data = self.prepare()
        with temporary:
            cases = {case["id"]: case for case in data["cases"]}
            expected_ids = {
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
            self.assertEqual(set(cases), expected_ids)
            gold = {case_id: json.loads(case["gold"]) for case_id, case in cases.items()}
            self.assertTrue(all(not value["forbidden"] for value in gold.values()))
            self.assertEqual(gold["cold-chain-replica-exception"]["facts"]["dispatch_eligible"], "no")
            self.assertEqual(gold["roof-endorsement-scope"]["facts"]["access_eligible"], "no")
            self.assertEqual(gold["ferry-authority-waiver"]["facts"]["fee_due"], "no")
            self.assertEqual(gold["refurbished-pack-exclusion"]["facts"]["warranty_eligible"], "no")
            self.assertEqual(
                gold["tariff-recorded-effective"]["facts"],
                {
                    "recorded_at": "2026-11-03 09:10",
                    "approved_at": "2026-11-03 09:30",
                    "effective_at": "2026-11-03 12:00",
                    "order_q7_price": "64",
                },
            )
            self.assertEqual(
                gold["license-entry-suspension"]["facts"]["inspection_at"],
                "2026-05-07 16:20",
            )
            self.assertEqual(gold["dispatcher-relayed-report"]["facts"]["report_source"], "Hugo")
            self.assertEqual(gold["supplier-delay-attribution"]["facts"]["recorder"], "Inez")
            self.assertEqual(gold["quarantine-bin-unknown"]["facts"]["all_bins_total"], "unknown")
            self.assertEqual(gold["appointment-room-only-correction"]["facts"]["visit_time"], "08:20")
            self.assertEqual(gold["pallet-mass-amendment"]["facts"]["mass_kg"], "408")
            self.assertEqual(gold["single-salinity-no-chart"]["facts"]["salinity"], "7")

            chart_empty = {
                case_id
                for case_id, case in cases.items()
                if "chart_questions must be empty" in case["request"]
            }
            self.assertEqual(
                chart_empty,
                {"quarantine-bin-unknown", "single-salinity-no-chart"},
            )
            self.assertIn("YYYY-MM-DD HH:MM", cases["tariff-recorded-effective"]["request"])
            self.assertIn("YYYY-MM-DD HH:MM", cases["license-entry-suspension"]["request"])
            self.assertIn("exactly as HH:MM", cases["appointment-room-only-correction"]["request"])


if __name__ == "__main__":
    unittest.main()
