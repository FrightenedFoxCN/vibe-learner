import unittest
from app.services.diagnostic_benchmark import run, summary


class DiagnosticBenchmarkTests(unittest.TestCase):
    def test_nearest_rank_keeps_signed_paired_deltas(self):
        result = summary([-2, -1, 0, 1, 2])
        self.assertEqual((result["p50_ms"], result["p95_ms"], result["sample_count"]), (0, 2, 5))

    def test_report_exercises_production_paths_and_discloses_measurement_scope(self):
        result = run(samples=2, event_count=100, trace_count=2)
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(result["http"]["summaries"]["baseline"]["sample_count"], 2)
        self.assertGreater(result["http"]["stalled_health"]["dropped"], 0)
        self.assertEqual(result["http"]["writer_health"]["write_failures"], 0)
        storage = result["storage"]
        self.assertEqual(storage["event_retention"]["retained_events"], 100)
        self.assertEqual(storage["index_retention"]["retained_rows"], 2)
        self.assertEqual(storage["full_export"]["outcome"], "completed")
        self.assertEqual(storage["health"]["dropped"], 0)
        self.assertTrue(result["diagnostic_source_sha256"])
        pinned = result["pinned_reader"]
        self.assertGreater(pinned["maintenance_busy"], 0)
        self.assertGreater(pinned["reader_pinned"]["wal_bytes"], pinned["reader_released"]["wal_bytes"])
        self.assertEqual(pinned["reader_released"]["wal_bytes"], 0)
        self.assertFalse(pinned["production_quota_claim"])
