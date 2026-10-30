"""Probe correctness without neural inference, network or user data."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import fitz

from tests.acceptance import ocr_stress_probe as probe


class OcrStressProbeTests(TestCase):
    def test_resume_checkpoint_prefix_is_distinct_from_new_ocr_calls(self):
        attempt = {
            "read_back": {
                "operation": {"operation_id": "child"},
                "checkpoint": {"completed_page_count": 3},
            },
            "page_checkpoint_writes": [
                {
                    "page_number": n,
                    "durable_page_count": n,
                    "operation_id": "child",
                    "storage_limited": False,
                }
                for n in (1, 2, 3)
            ],
            "ocr_pages": [{"page_number": 3}],
        }
        self.assertTrue(probe.checkpoints_cover_calls(attempt))
        attempt["ocr_pages"] = [{"page_number": 4}]
        self.assertFalse(probe.checkpoints_cover_calls(attempt))
        attempt["ocr_pages"] = [{"page_number": 3}]
        attempt["page_checkpoint_writes"][2]["operation_id"] = "foreign"
        self.assertFalse(probe.checkpoints_cover_calls(attempt))

    def test_full_ground_truth_scores_edits_not_keyword_presence(self):
        score = probe.character_score("kitten", "sitting")
        self.assertEqual(score["edit_distance"], 3)
        self.assertAlmostEqual(score["cer"], 0.5)
        self.assertEqual(score["aligned_exact_matches"], 4)
        full = "\n".join(probe.TEXTS["en"])
        self.assertGreater(probe.character_score(full, "sunrise")["cer"], 0.95)

    def test_unicode_whitespace_and_insertions_are_explicit(self):
        self.assertEqual(
            probe.character_score("café\n bleu", "cafe\u0301  bleu")["cer"], 0
        )
        self.assertEqual(probe.character_score("é", "e")["cer"], 1)
        self.assertEqual(probe.character_score("A", "a")["cer"], 1)
        self.assertEqual(probe.character_score("ab", "")["cer"], 1)
        self.assertEqual(probe.character_score("a", "aaaa")["cer"], 3)
        self.assertEqual(
            probe.character_score("中文", "Latin")["character_match_rate"], 0
        )
        with self.assertRaises(ValueError):
            probe.character_score("", "arbitrary output")

    def test_scan_has_only_images_and_fixed_original_ground_truth(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            languages = list(probe.TEXTS) * 4
            content, truth = probe.make_scan(root, languages)
            with fitz.open(stream=content, filetype="pdf") as pdf:
                self.assertEqual(pdf.page_count, 16)
                for page in pdf:
                    self.assertEqual(page.get_text(), "")
                    self.assertTrue(page.get_images())
            self.assertEqual(
                json.loads((root / "ground-truth.json").read_text()), truth
            )
            for expected, language in zip(truth, languages, strict=True):
                self.assertEqual(expected["text"], "\n".join(probe.TEXTS[language]))

    def test_dense_scan_preserves_all_forty_lines_for_scoring(self):
        with TemporaryDirectory() as folder:
            content, truth = probe.make_scan(Path(folder), ["fr", "zh"], "dense")
            for item in truth:
                self.assertEqual(len(item["text"].splitlines()), 40)
                self.assertEqual(
                    item["text"], "\n".join(probe.TEXTS[item["fixture_language"]] * 5)
                )
            with fitz.open(stream=content, filetype="pdf") as pdf:
                self.assertTrue(
                    all(not page.get_text() and page.get_images() for page in pdf)
                )

    def test_hash_verification_rejects_missing_changed_and_symlink_files(self):
        content = b"small local integrity fixture, never an ONNX model"
        digest = hashlib.sha256(content).hexdigest()
        name = f"fixture-{digest[:8]}.onnx"
        with (
            TemporaryDirectory() as folder,
            patch.object(probe, "MODEL_HASHES", {name: digest}),
        ):
            root = Path(folder)
            (root / "models").mkdir()
            path = root / "models" / name
            with self.assertRaisesRegex(ValueError, "missing_or_symlink"):
                probe.verify_models(root)
            path.write_bytes(content)
            self.assertEqual(probe.verify_models(root)[0]["sha256"], digest)
            path.write_bytes(content + b"changed")
            with self.assertRaisesRegex(ValueError, "untrusted_model_digest"):
                probe.verify_models(root)
            path.unlink()
            (root / "source").write_bytes(content)
            path.symlink_to(root / "source")
            with self.assertRaisesRegex(ValueError, "missing_or_symlink"):
                probe.verify_models(root)
