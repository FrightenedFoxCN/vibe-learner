"""Three real processes: crash mid-OCR, resume saved pages, query duplicate commit.

Run from services/ai: PYTHONPATH=. uv run python tests/acceptance/document_checkpoint_crash_probe.py
All files/databases stay in a temporary directory; OCR is a deterministic fixture.
"""

from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi import UploadFile
from app.services.document_parser import DocumentParser
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.ocr_engine import OcrPageResult
from app.services.study_arrangement import StudyArrangementService


def worker(root: Path, phase: str):
    store = LocalJsonStore(root)
    parser = DocumentParser(ocr_engine_name="disabled")
    service = DocumentService(store, parser, StudyArrangementService())

    def ocr(page):
        return OcrPageResult(
            text=f"Page {page.number + 1}\n"
            + "Vector definitions and linear transformations. " * 40,
            status="completed",
            engine_name="fixture",
            model_id="fixture",
        )

    if phase == "crash":
        with fitz.open() as pdf:
            for _ in range(3):
                pdf.new_page()
            contents = pdf.tobytes()
        document = service.create_document(
            UploadFile(filename="scan.pdf", file=io.BytesIO(contents))
        )
        (root / "document-id").write_text(document.id)
        parse = parser._parse_page

        def exit_second(**kwargs):
            if kwargs["page_number"] == 2:
                os._exit(72)
            return parse(**kwargs)

        with (
            patch.object(parser, "_run_ocr", side_effect=ocr),
            patch.object(parser, "_parse_page", side_effect=exit_second),
        ):
            service.process_document(document.id, force_ocr=True)
    document_id = (root / "document-id").read_text()
    if phase == "resume":
        assert service.recover_abandoned_operations() == 1
        source = service.process_repository.latest(
            document_id=document_id, validate_read_back=False
        )
        saved = service.checkpoints.public_view(source.operation_id)
        assert saved["completed_page_count"] == 1
        (root / "source-id").write_text(source.operation_id)
        with patch.object(parser, "_run_ocr", side_effect=ocr) as calls:
            result = service.process_document(
                document_id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        assert calls.call_count == 2
        (root / "result.json").write_text(result.model_dump_json())
    elif phase == "query":
        source_id = (root / "source-id").read_text()
        with patch.object(
            parser, "parse", side_effect=AssertionError("duplicate called parser")
        ):
            result = service.process_document(
                document_id, force_ocr=True, resume_from_operation_id=source_id
            )
        assert result.model_dump(mode="json") == json.loads(
            (root / "result.json").read_text()
        )
        child_id = service.checkpoints.resume_child(source_id)
        assert (
            service.checkpoints.public_view(child_id)["projection_state"] == "committed"
        )
    store.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=["crash", "resume", "query"])
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    if args.worker:
        worker(args.root, args.worker)
        return
    with TemporaryDirectory(prefix="document-checkpoint-crash-") as folder:
        for phase, expected in [("crash", 72), ("resume", 0), ("query", 0)]:
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--worker",
                    phase,
                    "--root",
                    folder,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == expected, (
                phase,
                result.returncode,
                result.stderr[-2000:],
            )
        print(
            json.dumps(
                {
                    "processes": 3,
                    "crash_exit": 72,
                    "saved_pages": 1,
                    "remaining_ocr_calls": 2,
                    "duplicate_parse_calls": 0,
                    "restart_read_back": "passed",
                }
            )
        )


if __name__ == "__main__":
    main()
