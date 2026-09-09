"""Real local OCR, using a synthetic image-only PDF; no provider or secrets."""
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import fitz
from fastapi import UploadFile
from sqlalchemy import text

from app.services.document_parser import DocumentParser
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.study_arrangement import StudyArrangementService


ROOT = Path(__file__).resolve().parent
with fitz.open() as source, fitz.open() as scanned:
    for heading in ("Chapter 1 Observation", "Chapter 2 Comparison"):
        page = source.new_page()
        page.insert_text((40, 55), heading, fontsize=20)
        for column, lines in enumerate((
            ["Record the temperature.", "Measure the elapsed time.", "Compare both observations.", "Repeat the experiment."],
            ["Use a red lamp at night.", "Keep the notebook dry.", "Check the instrument.", "Discuss the evidence."],
        )):
            for row, line in enumerate(lines):
                page.insert_text((40 + column * 280, 100 + row * 36), line, fontsize=15)
        rendered = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        image_page = scanned.new_page()
        image_page.insert_image(image_page.rect, stream=rendered.tobytes("png"))
    pdf_bytes = scanned.tobytes()
(ROOT / "scan-two-column.pdf").write_bytes(pdf_bytes)

with TemporaryDirectory() as directory:
    store = LocalJsonStore(Path(directory))
    try:
        service = DocumentService(store, DocumentParser(runtime_temp_root=Path(directory)), StudyArrangementService())
        document = service.create_document(UploadFile(filename="scan-two-column.pdf", file=io.BytesIO(pdf_bytes)))
        started = perf_counter()
        processed = service.process_document(document.id, force_ocr=True)
        report = service.require_debug_report(document.id)
        extracted = " ".join(chunk.content for chunk in report.chunks).casefold()
        anchors = ("temperature", "elapsed", "observations", "experiment", "red lamp", "notebook", "instrument", "evidence")
        with store.database.engine.connect() as connection:
            traces = [json.loads(row[0]) if isinstance(row[0], str) else row[0] for row in connection.execute(text("SELECT terminal_trace FROM harness_runtime_executions WHERE terminal_trace IS NOT NULL"))]
        result = {
            "fixture": "two-page-image-only-two-column-english",
            "model": report.ocr_model_id,
            "ocr_status": report.ocr_status,
            "status": processed.status,
            "pages": report.page_count,
            "ocr_pages": report.ocr_applied_page_count,
            "anchor_recall": sum(anchor in extracted for anchor in anchors) / len(anchors),
            "duration_ms": round((perf_counter() - started) * 1000),
            "traces": traces,
            "limitations": ["English synthetic fixture only", "No maximum-size or multilingual claim", "Local ONNX OCR, no MiniMax call"],
        }
        (ROOT / "ocr-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({key: value for key, value in result.items() if key != "traces"}))
        assert result["ocr_pages"] == 2 and result["anchor_recall"] >= 0.875
    finally:
        store.close()
