"""Versioned upload/page boundaries and lossless oversized-unit behavior."""

from __future__ import annotations

import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi import HTTPException, UploadFile
from fastapi.testclient import TestClient

from app.api.document_upload_limit import DocumentUploadLimitMiddleware
from app.app_factory import create_app
from app.core.settings import Settings
from app.models.document_input_limits import (
    DocumentInputLimitsV1,
    DocumentInputLimitError,
    DOCUMENT_MAX_TEXT_UNIT_CHARS,
)
from app.models.domain import DocumentSection
from app.services.document_input_validation import read_bounded_upload
from app.services.document_parser import DocumentParser
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.study_arrangement import StudyArrangementService


def pdf_bytes(pages):
    with fitz.open() as pdf:
        for _ in range(pages):
            pdf.new_page()
        return pdf.tobytes()


class DocumentInputLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = LocalJsonStore(self.root)
        self.parser = DocumentParser(ocr_engine_name="disabled")
        self.service = DocumentService(
            self.store, self.parser, StudyArrangementService()
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_shared_limits_and_byte_boundary_use_bounded_reads(self):
        repo = Path(__file__).resolve().parents[3]
        self.assertEqual(
            DocumentInputLimitsV1().model_dump(),
            json.loads(
                (
                    repo / "packages/shared/fixtures/document-input-limits-v1.json"
                ).read_text()
            ),
        )

        class Stream(io.BytesIO):
            def read(self, size=-1):
                assert 0 < size <= 65536
                return super().read(size)

        with patch(
            "app.services.document_input_validation.DOCUMENT_UPLOAD_MAX_BYTES", 128
        ):
            self.assertEqual(len(read_bounded_upload(Stream(b"a" * 128))), 128)
            with self.assertRaises(DocumentInputLimitError):
                read_bounded_upload(Stream(b"a" * 129))
            with self.assertRaises(HTTPException) as exc:
                self.service.create_document(
                    UploadFile(filename="large.pdf", file=Stream(b"a" * 129))
                )
        self.assertEqual(exc.exception.status_code, 413)
        self.assertEqual(exc.exception.detail["code"], "document_upload_too_large")
        self.assertEqual(self.service.list_documents(), [])
        self.assertEqual(list(self.store.upload_root.iterdir()), [])

    def test_real_pdf_page_boundary_rejects_before_record_or_ocr_and_allows_recovery(
        self,
    ):
        self.service.create_document(
            UploadFile(filename="limit.pdf", file=io.BytesIO(pdf_bytes(512)))
        )
        files = set(self.store.upload_root.iterdir())
        ids = [d.id for d in self.service.list_documents()]
        with patch.object(
            self.parser, "_run_ocr", side_effect=AssertionError("over-limit OCR")
        ):
            with self.assertRaises(HTTPException) as exc:
                self.service.create_document(
                    UploadFile(filename="too-many.pdf", file=io.BytesIO(pdf_bytes(513)))
                )
        self.assertEqual(exc.exception.status_code, 413)
        self.assertEqual(exc.exception.detail["actual"], 513)
        self.assertEqual(set(self.store.upload_root.iterdir()), files)
        self.assertEqual([d.id for d in self.service.list_documents()], ids)
        small = self.service.create_document(
            UploadFile(filename="recovered.pdf", file=io.BytesIO(pdf_bytes(1)))
        )
        self.assertEqual(small.status, "uploaded")

    def test_legacy_file_over_limit_has_zero_admission_or_checkpoint_mutations(self):
        document = self.service.create_document(
            UploadFile(filename="old.pdf", file=io.BytesIO(pdf_bytes(1)))
        )
        Path(document.stored_path).write_bytes(pdf_bytes(513))
        with self.assertRaises(HTTPException):
            self.service.process_document(document.id)
        self.assertIsNone(
            self.service.process_repository.latest(document_id=document.id)
        )
        self.assertEqual(self.service.require_document(document.id), document)

    def test_indivisible_text_is_preserved_until_its_separate_hard_limit(self):
        section = DocumentSection(
            id="section",
            document_id="doc",
            title="Source",
            page_start=1,
            page_end=1,
            level=1,
        )
        long = "汉" * 2000
        chunks = self.parser._build_chunks(
            document_id="doc", sections=[section], page_texts=[long]
        )
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].content, long)
        self.assertEqual(chunks[0].char_count, 2000)
        self.assertEqual(
            self.parser._split_text_units("汉" * DOCUMENT_MAX_TEXT_UNIT_CHARS),
            ["汉" * DOCUMENT_MAX_TEXT_UNIT_CHARS],
        )
        with self.assertRaises(DocumentInputLimitError):
            self.parser._split_text_units("汉" * (DOCUMENT_MAX_TEXT_UNIT_CHARS + 1))

    def test_processing_preserves_oversized_unit_and_reports_warning(self):
        document = self.service.create_document(
            UploadFile(filename="long.pdf", file=io.BytesIO(pdf_bytes(1)))
        )
        text = "汉" * 2000
        with patch.object(
            self.parser, "_extract_text_lines", return_value=([(text, 10.0)], 10.0)
        ):
            processed = self.service.process_document(document.id)
        self.assertEqual(processed.status, "processed")
        report = self.service.require_debug_report(document.id)
        self.assertEqual([chunk.content for chunk in report.chunks], [text])
        self.assertIn(
            "oversized_text_unit_preserved",
            [warning.code for warning in report.warnings],
        )

    def test_processing_hard_text_limit_keeps_pages_without_claiming_commit(self):
        document = self.service.create_document(
            UploadFile(filename="unsplittable.pdf", file=io.BytesIO(pdf_bytes(1)))
        )
        text = "汉" * (DOCUMENT_MAX_TEXT_UNIT_CHARS + 1)
        with patch.object(
            self.parser, "_extract_text_lines", return_value=([(text, 10.0)], 10.0)
        ):
            with self.assertRaises(HTTPException) as rejected:
                self.service.process_document(document.id)
        self.assertEqual(rejected.exception.status_code, 413)
        self.assertEqual(
            rejected.exception.detail["code"], "document_text_unit_too_large"
        )
        operation = self.service.process_repository.latest(
            document_id=document.id, validate_read_back=False
        )
        self.assertEqual(operation.status, "failed")
        self.assertEqual(operation.error_code, "document_text_unit_too_large")
        checkpoint = self.service.checkpoints.public_view(operation.operation_id)
        self.assertEqual(checkpoint["completed_page_count"], 1)
        self.assertEqual(checkpoint["projection_state"], "checkpoint_only")
        self.assertIsNone(checkpoint["result"])
        current = self.service.require_document(document.id)
        self.assertNotEqual(current.status, "processed")
        self.assertFalse(current.debug_ready)
        self.assertEqual(current.chunk_count, 0)
        self.assertIsNone(self.service.repository.get_with_debug(document.id)[1])

    def test_actual_http_rejects_bad_pages_and_accepts_the_next_upload(self):
        settings = Settings(
            database_url=f"sqlite:///{self.root / 'http.db'}",
            storage_root=str(self.root / "http"),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        )
        with TestClient(create_app(settings=settings)) as client:
            limits = client.get("/documents/input-limits")
            self.assertEqual(limits.status_code, 200)
            self.assertEqual(limits.json()["max_physical_pages"], 512)
            rejected = client.post(
                "/documents",
                files={"file": ("large.pdf", pdf_bytes(513), "application/pdf")},
            )
            self.assertEqual(rejected.status_code, 413, rejected.text)
            self.assertEqual(
                rejected.json()["detail"]["recovery_action"], "split_or_reexport_pdf"
            )
            self.assertEqual(client.get("/documents").json()["items"], [])
            accepted = client.post(
                "/documents",
                files={"file": ("small.pdf", pdf_bytes(1), "application/pdf")},
            )
            self.assertEqual(accepted.status_code, 200, accepted.text)
            with (
                patch("app.api.document_upload_limit.DOCUMENT_UPLOAD_MAX_BYTES", 128),
                patch(
                    "app.api.document_upload_limit.DOCUMENT_MULTIPART_OVERHEAD_BYTES", 0
                ),
            ):
                rejected_body = client.post(
                    "/documents",
                    content=b"x" * 129,
                    headers={"origin": "http://localhost:3000"},
                )
            self.assertEqual(rejected_body.status_code, 413)
            self.assertEqual(
                rejected_body.headers["access-control-allow-origin"],
                "http://localhost:3000",
            )
            self.assertTrue(rejected_body.headers["x-request-id"])
            self.assertEqual(len(client.get("/documents").json()["items"]), 1)

    def test_stream_limit_failure_has_readable_recovery_and_no_committed_projection(
        self,
    ):
        settings = Settings(
            database_url=f"sqlite:///{self.root / 'stream.db'}",
            storage_root=str(self.root / "stream"),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        )
        app = create_app(settings=settings)
        with TestClient(app) as client:
            uploaded = client.post(
                "/documents",
                files={"file": ("long.pdf", pdf_bytes(1), "application/pdf")},
            ).json()
            document_id = uploaded["id"]
            parser = app.state.container.document_service.parser
            text = "汉" * (DOCUMENT_MAX_TEXT_UNIT_CHARS + 1)
            with patch.object(
                parser, "_extract_text_lines", return_value=([(text, 10.0)], 10.0)
            ):
                response = client.post(
                    f"/documents/{document_id}/process/stream", json={}
                )
            self.assertEqual(response.status_code, 200)
            events = [json.loads(line) for line in response.text.splitlines()]
            self.assertEqual(events[-1]["stage"], "stream_error")
            self.assertIn("65,536", events[-1]["payload"]["error"])
            self.assertIn("重新导出", events[-1]["payload"]["error"])
            self.assertFalse(
                any(event["stage"] == "stream_completed" for event in events)
            )
            checkpoint = client.get(f"/documents/{document_id}/checkpoint").json()
            self.assertEqual(checkpoint["projection_state"], "checkpoint_only")
            self.assertEqual(checkpoint["completed_page_count"], 1)
            self.assertEqual(
                client.get(f"/documents/{document_id}/debug").status_code, 404
            )


class UploadBodyLimitTests(unittest.IsolatedAsyncioTestCase):
    async def request(self, chunks, headers=()):
        sent = []
        called = []
        reads = 0

        async def receive():
            nonlocal reads
            if reads >= len(chunks):
                return {"type": "http.disconnect"}
            body = chunks[reads]
            reads += 1
            return {
                "type": "http.request",
                "body": body,
                "more_body": reads < len(chunks),
            }

        async def send(value):
            sent.append(value)

        async def app(scope, receive, send):
            parts = []
            while True:
                value = await receive()
                parts.append(value["body"])
                if not value.get("more_body"):
                    break
            called.append(b"".join(parts))
            from starlette.responses import JSONResponse

            await JSONResponse({"ok": True})(scope, receive, send)

        with (
            patch("app.api.document_upload_limit.DOCUMENT_UPLOAD_MAX_BYTES", 5),
            patch("app.api.document_upload_limit.DOCUMENT_MULTIPART_OVERHEAD_BYTES", 0),
        ):
            await DocumentUploadLimitMiddleware(app)(
                {
                    "type": "http",
                    "method": "POST",
                    "path": "/documents",
                    "headers": headers,
                },
                receive,
                send,
            )
        return sent, called, reads

    async def test_chunked_body_and_lying_length_are_counted_before_multipart_allocation(
        self,
    ):
        for headers in ([], [(b"content-length", b"1")]):
            sent, called, reads = await self.request([b"123", b"456"], headers)
            self.assertEqual(sent[0]["status"], 413)
            self.assertEqual(called, [])
            self.assertEqual(reads, 2)
        sent, called, _ = await self.request([b"123", b"45"])
        self.assertEqual(sent[0]["status"], 200)
        self.assertEqual(called, [b"12345"])
        sent, called, reads = await self.request(
            [b"not consumed"], [(b"content-length", b"6")]
        )
        self.assertEqual(sent[0]["status"], 413)
        self.assertEqual(called, [])
        self.assertEqual(reads, 0)
