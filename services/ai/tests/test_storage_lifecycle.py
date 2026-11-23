from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from app.services.local_store import LocalJsonStore
from app.services.storage_lifecycle import StorageLifecycleService
from app.services.token_usage import TokenUsageService


class StorageLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = LocalJsonStore(Path(temp.name) / "store")
        self.addCleanup(self.store.close)
        self.usage = Mock(spec=TokenUsageService)
        self.usage.clear.return_value = 2
        self.lifecycle = StorageLifecycleService(self.store, self.usage)

    def test_unsupported_bucket_rejects_entire_batch_before_cleanup(self) -> None:
        marker = self.store.runtime_temp_root / "keep.txt"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("keep", encoding="utf-8")

        with self.assertRaisesRegex(
            ValueError, "^cleanup_bucket_not_supported:uploads$"
        ):
            self.lifecycle.cleanup(buckets=[" runtime_temp ", "token_usage", "uploads"])

        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
        self.usage.clear.assert_not_called()

    def test_valid_and_empty_batches_preserve_existing_semantics(self) -> None:
        self.assertEqual(self.lifecycle.cleanup(buckets=["", "  "]), [])
        self.usage.clear.assert_not_called()
        self.assertEqual(
            self.lifecycle.cleanup(buckets=["  token_usage  "]),
            [{"bucket": "token_usage", "removed_count": 2}],
        )
        self.usage.clear.assert_called_once_with()
