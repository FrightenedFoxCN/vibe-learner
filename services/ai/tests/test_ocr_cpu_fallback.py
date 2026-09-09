from unittest import TestCase
from unittest.mock import patch

from app.services.ocr_engine import OnnxtrOcrEngine


class OcrCpuFallbackTests(TestCase):
    def test_accelerator_failure_retries_once_and_caches_cpu_predictor(self):
        predictor = object()
        with patch("onnxtr.models.ocr_predictor", side_effect=[RuntimeError("unsupported graph"), predictor]) as build, patch("onnxruntime.get_available_providers", return_value=["CoreMLExecutionProvider", "CPUExecutionProvider"]):
            engine = OnnxtrOcrEngine()
            self.assertIs(engine._ensure_predictor(), predictor)
            self.assertIs(engine._ensure_predictor(), predictor)
            self.assertEqual(build.call_count, 2)
            self.assertEqual(build.call_args.kwargs["reco_engine_cfg"].providers, ["CPUExecutionProvider"])
            self.assertEqual(engine._initialization_warning, "onnxtr_cpu_fallback")

    def test_cpu_failure_is_bounded_and_remains_unavailable(self):
        with patch("onnxtr.models.ocr_predictor", side_effect=RuntimeError("broken model")) as build, patch("onnxruntime.get_available_providers", return_value=["CoreMLExecutionProvider", "CPUExecutionProvider"]):
            engine = OnnxtrOcrEngine()
            self.assertIsNone(engine._ensure_predictor())
            self.assertIsNone(engine._ensure_predictor())
            self.assertEqual(build.call_count, 2)
