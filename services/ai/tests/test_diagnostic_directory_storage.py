from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import unittest

from app.core.diagnostics import DiagnosticStore
from app.services.diagnostic_directory_storage import observe_diagnostic_directory


class DiagnosticDirectoryStorageTests(unittest.TestCase):
    def test_single_inventory_counts_databases_spool_and_unknown_nested_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "events.db")
            index = SimpleNamespace(path=root / "index.db")
            files = {"events.db": 10, "events.db-wal": 5, "index.db": 7,
                     "desktop-spool/desktop-ab.json": 3, "desktop-spool/drops.count": 2,
                     "PRIVATE_NAME.txt": 11, "old/nested/PRIVATE.json": 13}
            for name, size in files.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"x" * size)
            result = observe_diagnostic_directory(store, index)
            self.assertEqual(result["status"], "observed")
            self.assertEqual((result["database_bytes"], result["spool_bytes"], result["other_bytes"], result["total_bytes"]), (22, 5, 24, 51))
            self.assertEqual((result["database_files"], result["spool_files"], result["other_files"]), (3, 2, 2))
            self.assertEqual(result["budget_state"], "within_observed_limit")
            self.assertNotIn("PRIVATE", json.dumps(result))
            for name, size in files.items():
                self.assertEqual((root / name).stat().st_size, size)

    def test_symlinks_depth_and_external_database_are_explicit_gaps(self):
        with TemporaryDirectory() as directory, TemporaryDirectory() as external:
            root = Path(directory); store = DiagnosticStore(root / "events.db")
            secret = Path(external) / "secret"; secret.write_bytes(b"PRIVATE" * 100)
            (root / "linked").symlink_to(secret)
            (root / "linked-dir").symlink_to(Path(external), target_is_directory=True)
            nested = root / "a/b/c/d/e"; nested.mkdir(parents=True)
            (nested / "unseen").write_bytes(b"private")
            result = observe_diagnostic_directory(store, SimpleNamespace(path=secret))
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(set(result["gaps"]), {"unsupported_entry", "depth_limit", "configured_database_outside_directory"})
            self.assertEqual(result["total_bytes"], 0)
            self.assertEqual(result["budget_state"], "unknown")
            self.assertEqual(result["skipped_entries"], 3)

    def test_entry_and_time_limits_never_claim_complete_under_budget(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DiagnosticStore(root / "events.db")
            for i in range(4097):
                (root / str(i)).touch()
            # Keep the independent time limit from racing the entry-limit test.
            with patch("app.services.diagnostic_directory_storage.time.monotonic", return_value=1):
                result = observe_diagnostic_directory(store, None)
            self.assertEqual(result["status"], "incomplete")
            self.assertEqual(result["scanned_entries"], 4096)
            self.assertEqual(result["gaps"], ["scan_limit"])
            self.assertEqual(result["budget_state"], "unknown")
            with patch("app.services.diagnostic_directory_storage.time.monotonic", side_effect=[1, 2]):
                result = observe_diagnostic_directory(store, None)
            self.assertEqual((result["gaps"], result["scanned_entries"]), (["time_limit"], 0))

    def test_sparse_over_budget_file_is_counted_as_length_even_with_other_gaps(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); store = DiagnosticStore(root / "events.db")
            with (root / "unknown").open("wb") as handle:
                handle.truncate(201 * 1024 * 1024)
            (root / "link").symlink_to(root / "unknown")
            result = observe_diagnostic_directory(store, None)
            self.assertEqual(result["total_bytes"], 201 * 1024 * 1024)
            self.assertEqual(result["budget_state"], "over_observed_limit")
            self.assertEqual(result["status"], "incomplete")

    def test_absence_unconfigured_and_unreadable_roots_are_not_zero_usage_success(self):
        self.assertEqual(observe_diagnostic_directory(None, None)["gaps"], ["not_configured"])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            store = DiagnosticStore(root / "missing/events.db")
            result = observe_diagnostic_directory(store, None)
            self.assertEqual((result["status"], result["budget_state"]), ("absent", "unknown"))
            self.assertEqual(list(root.iterdir()), [])
            store = DiagnosticStore(root / "events.db")
            with patch("app.services.diagnostic_directory_storage.os.open", side_effect=OSError("PRIVATE")):
                result = observe_diagnostic_directory(store, None)
            self.assertEqual(result["gaps"], ["filesystem_unavailable"])
            self.assertNotIn("PRIVATE", json.dumps(result))
