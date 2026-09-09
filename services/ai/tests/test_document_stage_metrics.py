from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import fitz

from app.services.document_parser import DocumentParser
from app.services.document_stage_metrics import collect_parser_measurements, parser_stage_evidence
from app.services.ocr_engine import OcrPageResult


class DocumentStageMetricsTests(TestCase):
    def test_real_pdf_measures_each_producer_and_isolates_requests(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "input.pdf"
            with fitz.open() as pdf:
                page = pdf.new_page()
                page.insert_text((60, 60), "Chapter 1 Observation\n" + "Record the observation and compare the evidence. " * 4)
                pdf.save(path)
            parser = DocumentParser(ocr_engine_name="disabled")
            metrics = {}
            with collect_parser_measurements(metrics):
                report = parser.parse(document_id="test", title="Observation", stored_path=str(path))
            self.assertEqual(report.page_count, 1)
            self.assertTrue(report.chunks)
            for stage in ("page_extraction", "section_detection", "chunk_building"):
                self.assertGreater(metrics[stage]["duration_ns"], 0)
                self.assertGreaterEqual(parser_stage_evidence(metrics, stage)["attempt_count"], 1)
            self.assertEqual(parser_stage_evidence(metrics, "ocr_page"), {})
            forced = {}
            with collect_parser_measurements(forced), patch.object(parser, "_run_ocr", return_value=OcrPageResult(text="Observed evidence. " * 100, status="completed")):
                parser.parse(document_id="test", title="Observation", stored_path=str(path), force_ocr=True)
            self.assertEqual(forced["ocr_page"]["attempt_count"], 1)
            self.assertNotIn("ocr_page", metrics)
