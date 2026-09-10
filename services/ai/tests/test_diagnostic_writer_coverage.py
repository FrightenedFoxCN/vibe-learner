from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3
import subprocess
import sys
import unittest

from app.core.diagnostics import DiagnosticStore
from app.core.diagnostic_writer_coverage import DiagnosticWriterCoverage
from app.models.diagnostic import DiagnosticEventV1


class DiagnosticWriterCoverageTests(unittest.TestCase):
    def test_clean_close_persists_overflow_and_rejects_relabeling_as_complete(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            store = DiagnosticStore(path, capacity=1)
            event = DiagnosticEventV1(event_id="one", name="request_started", source="server", timestamp="2026-09-10T00:00:00Z")
            self.assertTrue(store.enqueue(event))
            self.assertFalse(store.enqueue(event))
            store.start()
            store.close()
            view = DiagnosticWriterCoverage(path, "0" * 32).query()
            self.assertEqual(len(view["items"]), 1)
            self.assertIsNotNone(view["items"][0]["closed_at"])
            self.assertEqual(view["totals"]["observed_dropped"], 1)
            self.assertEqual(view["totals"]["unclosed_epochs"], 0)
            self.assertTrue(view["counts_are_lower_bounds"])
            self.assertTrue(view["unpersisted_queue_gap"])
            self.assertFalse(view["complete_collection_claim"])
            from app.models.diagnostic_writer import DiagnosticWriterCoverageV1
            with self.assertRaises(ValueError):
                DiagnosticWriterCoverageV1.model_validate({**view, "complete_collection_claim": True})

    def test_real_process_exit_leaves_unclosed_checkpoint_after_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            script = """
import os, sys
from pathlib import Path
from app.core.diagnostics import DiagnosticStore
store=DiagnosticStore(Path(sys.argv[1]))
store.start()
store.emit('lifecycle_started')
store.queue.join()
os._exit(7)
"""
            result = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, check=False, timeout=10)
            self.assertEqual(result.returncode, 7)
            restarted = DiagnosticStore(path)
            restarted.start()
            restarted.emit("lifecycle_started")
            restarted.queue.join()
            restarted.close()
            view = restarted.writer_coverage.query()
            self.assertEqual(view["totals"]["unclosed_epochs"], 1)
            self.assertEqual(view["unclosed_meaning"], "active_or_interrupted")
            self.assertIsNone(view["items"][0]["closed_at"])
            self.assertIsNotNone(view["items"][1]["closed_at"])

    def test_retirement_is_bounded_idempotent_and_preserves_lower_bound_totals(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            with sqlite3.connect(path) as db:
                for number in range(1, 6):
                    coverage = DiagnosticWriterCoverage(path, f"{number:032x}", max_epochs=2)
                    coverage.initialize(db)
                    coverage.observe(db, dropped=number, write_failures=0, read_failures=0, closed=number % 2 == 0)
                    coverage.initialize(db)
                db.commit()
            first = coverage.query(limit=1)
            self.assertTrue(first["has_more"])
            second = coverage.query(after=first["next_cursor"], limit=1)
            self.assertFalse(second["has_more"])
            self.assertEqual(first["totals"]["retired_epochs"], 3)
            self.assertEqual(first["totals"]["retained_epochs"], 2)
            self.assertEqual(first["totals"]["retired_unclosed"], 2)
            self.assertEqual(first["totals"]["observed_dropped"], 15)
            self.assertEqual(first["totals"], second["totals"])

    def test_corrupt_writer_payload_is_not_returned(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "events.db"
            coverage = DiagnosticWriterCoverage(path, "0" * 32)
            with sqlite3.connect(path) as db:
                coverage.initialize(db)
                db.execute("UPDATE diagnostic_writers SET epoch_id='PRIVATE_SECRET'")
                db.commit()
            with self.assertRaises(ValueError):
                coverage.query()
