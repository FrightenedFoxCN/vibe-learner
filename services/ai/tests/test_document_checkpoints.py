"""Durable OCR checkpoints across budget failure, process loss and explicit resume."""

from __future__ import annotations

import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi import HTTPException, UploadFile

from app.models.domain import DocumentRecord
from app.services.document_parser import DocumentParser
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.ocr_engine import OcrPageResult
from app.services.study_arrangement import StudyArrangementService


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = LocalJsonStore(self.root)
        self.parser = DocumentParser(ocr_engine_name="disabled")
        self.service = DocumentService(
            self.store, self.parser, StudyArrangementService()
        )
        with fitz.open() as pdf:
            for _ in range(3):
                pdf.new_page()
            content = pdf.tobytes()
        self.document = self.service.create_document(
            UploadFile(filename="scan.pdf", file=io.BytesIO(content))
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def ocr(self, page):
        return OcrPageResult(
            text=f"Page {page.number + 1}\n"
            + "Vector foundations and linear transformations. " * 40,
            status="completed",
            engine_name="fixture",
            model_id="fixture-v1",
        )

    def test_page_checkpoint_survives_failure_and_resume_skips_completed_ocr(self):
        def fail_second(page):
            if page.number == 1:
                raise RuntimeError("injected_page_failure")
            return self.ocr(page)

        with patch.object(self.parser, "_run_ocr", side_effect=fail_second):
            with self.assertRaises(RuntimeError):
                self.service.process_document(self.document.id, force_ocr=True)
        source = self.service.process_repository.latest(
            document_id=self.document.id, validate_read_back=False
        )
        saved = self.service.checkpoints.public_view(source.operation_id)
        self.assertEqual(saved["completed_page_count"], 1)
        self.assertEqual(saved["projection_state"], "checkpoint_only")
        with patch.object(self.parser, "_run_ocr", side_effect=self.ocr) as ocr:
            result = self.service.process_document(
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(result.status, "processed")
        with patch.object(
            self.parser,
            "parse",
            side_effect=AssertionError("duplicate resume replayed parser"),
        ):
            again = self.service.process_document(
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        self.assertEqual(again, result)

    def test_completed_output_survives_parent_budget_expiry_and_resume_only_commits(
        self,
    ):
        original = self.service.checkpoints.save_stage
        expired = False

        def save(*args, **kwargs):
            nonlocal expired
            original(*args, **kwargs)
            if len(args) > 2 and args[2] is not None:
                expired = True

        # The outer runtime checks again after generate returns its completed output.
        from app.services.harness_runtime import (
            HarnessOperationRuntime,
            HarnessRuntimeError,
        )

        check = HarnessOperationRuntime._ensure_within_budget

        def budget(runtime, deadline):
            if expired:
                raise HarnessRuntimeError("harness_runtime_wall_time_budget_exceeded")
            return check(runtime, deadline)

        with (
            patch.object(self.parser, "_run_ocr", side_effect=self.ocr),
            patch.object(self.service.checkpoints, "save_stage", side_effect=save),
            patch.object(HarnessOperationRuntime, "_ensure_within_budget", budget),
        ):
            with self.assertRaisesRegex(RuntimeError, "wall_time_budget_exceeded"):
                self.service.process_document(self.document.id, force_ocr=True)
        source = self.service.process_repository.latest(
            document_id=self.document.id, validate_read_back=False
        )
        checkpoint = self.service.checkpoints.public_view(source.operation_id)
        self.assertEqual(checkpoint["stage"], "study_units")
        self.assertTrue(checkpoint["study_units"])
        self.assertEqual(checkpoint["completed_page_count"], 3)
        with (
            patch.object(
                self.parser,
                "parse",
                side_effect=AssertionError("completed parser replayed"),
            ),
            patch.object(
                self.service.arrangement_service,
                "build_study_units",
                side_effect=AssertionError("cleanup replayed"),
            ),
        ):
            result = self.service.process_document(
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        self.assertEqual(result.status, "processed")
        self.assertEqual(len(result.study_units), len(checkpoint["study_units"]))

    def test_restart_keeps_partial_pages_and_fences_old_writer(self):
        original = self.parser._parse_page

        def crash(**kwargs):
            if kwargs["page_number"] == 2:
                raise SystemExit("process_crash")
            return original(**kwargs)

        with (
            patch.object(self.parser, "_run_ocr", side_effect=self.ocr),
            patch.object(self.parser, "_parse_page", side_effect=crash),
        ):
            with self.assertRaises(SystemExit):
                self.service.process_document(self.document.id, force_ocr=True)
        source = self.service.process_repository.latest(
            document_id=self.document.id, validate_read_back=False
        )
        self.store.close()
        self.store = LocalJsonStore(self.root)
        self.service = DocumentService(
            self.store, self.parser, StudyArrangementService()
        )
        self.assertEqual(self.service.recover_abandoned_operations(), 1)
        self.assertEqual(
            self.service.checkpoints.public_view(source.operation_id)[
                "completed_page_count"
            ],
            1,
        )
        with self.assertRaises(HTTPException):
            self.service.checkpoints.set_page_count(source.operation_id, 3)
        with patch.object(self.parser, "_run_ocr", side_effect=self.ocr) as ocr:
            result = self.service.process_document(
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(self.store.load_list("documents", DocumentRecord)[0], result)

    def partial(self):
        def stop(page):
            if page.number == 1:
                raise RuntimeError("partial-stop")
            return self.ocr(page)

        with patch.object(self.parser, "_run_ocr", side_effect=stop):
            with self.assertRaises(RuntimeError):
                self.service.process_document(self.document.id, force_ocr=True)
        return self.service.process_repository.latest(
            document_id=self.document.id, validate_read_back=False
        )

    def test_changed_input_and_corrupt_checkpoint_fail_closed(self):
        from app.persistence.models import DocumentCheckpointPageRow

        source = self.partial()
        with self.assertRaises(HTTPException):
            self.service.process_document(
                self.document.id,
                force_ocr=False,
                resume_from_operation_id=source.operation_id,
            )
        self.parser.ocr_engine_name = "changed"
        with self.assertRaises(HTTPException):
            self.service.process_document(
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        self.parser.ocr_engine_name = "disabled"
        path = Path(self.document.stored_path)
        original = path.read_bytes()
        path.write_bytes(original + b"\nchanged")
        with self.assertRaises(HTTPException):
            self.service.process_document(
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        path.write_bytes(original)
        with self.store.database.session() as session:
            row = session.get(DocumentCheckpointPageRow, (source.operation_id, 1))
            row.payload = {**row.payload, "used_ocr": False}
        with self.assertRaisesRegex(
            HTTPException, "document_checkpoint_digest_mismatch"
        ):
            self.service.checkpoints.snapshot(source.operation_id)

    def test_capacity_is_bounded_and_reports_saved_prefix_honestly(self):
        with patch(
            "app.persistence.document_checkpoint_repository.CHECKPOINT_MAX_BYTES", 128
        ):
            source = self.partial()
        saved = self.service.checkpoints.public_view(source.operation_id)
        self.assertTrue(saved["storage_limited"])
        self.assertEqual(saved["completed_page_count"], 0)
        self.assertEqual(saved["pages"], [])
        from app.persistence.models import DocumentCheckpointRow

        with self.store.database.session() as session:
            self.assertLessEqual(
                session.get(DocumentCheckpointRow, source.operation_id).byte_count, 128
            )

    def test_concurrent_same_resume_admits_one_child_without_repeating_ocr(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from sqlalchemy import select
        from app.persistence.models import DocumentCheckpointResumeRow

        source = self.partial()
        entered = Event()
        release = Event()

        def pause(page):
            entered.set()
            release.wait(timeout=5)
            return self.ocr(page)

        with (
            patch.object(self.parser, "_run_ocr", side_effect=pause) as ocr,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(
                self.service.process_document,
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
            self.assertTrue(entered.wait(timeout=5))
            try:
                with self.assertRaises(HTTPException):
                    self.service.process_document(
                        self.document.id,
                        force_ocr=True,
                        resume_from_operation_id=source.operation_id,
                    )
            finally:
                release.set()
            result = first.result(timeout=10)
        self.assertEqual(ocr.call_count, 2)
        self.assertEqual(result.status, "processed")
        with self.store.database.session() as session:
            self.assertEqual(
                len(session.scalars(select(DocumentCheckpointResumeRow)).all()), 1
            )

    def test_failed_ocr_pages_are_retried_instead_of_reusing_degraded_stage_output(
        self,
    ):
        with patch.object(
            self.parser,
            "_run_ocr",
            return_value=OcrPageResult(text="", status="failed", engine_name="fixture"),
        ):
            with self.assertRaises(RuntimeError):
                self.service.process_document(self.document.id, force_ocr=True)
        source = self.service.process_repository.latest(
            document_id=self.document.id, validate_read_back=False
        )
        self.assertEqual(
            self.service.checkpoints.public_view(source.operation_id)["stage"], "parsed"
        )
        with patch.object(self.parser, "_run_ocr", side_effect=self.ocr) as ocr:
            result = self.service.process_document(
                self.document.id,
                force_ocr=True,
                resume_from_operation_id=source.operation_id,
            )
        self.assertEqual(ocr.call_count, 3)
        self.assertEqual(result.status, "processed")

    def test_a_later_document_revision_blocks_old_checkpoint_admission(self):
        from app.persistence.document_repository import replace_document_in_session

        source = self.partial()
        document = self.service.require_document(self.document.id)
        changed = document.model_copy(
            update={"revision": document.revision + 1, "title": "newer"}
        )
        with self.store.database.session() as session:
            replace_document_in_session(
                session, changed, expected_revision=document.revision
            )
        with patch.object(
            self.parser, "parse", side_effect=AssertionError("stale parser started")
        ):
            with self.assertRaises(HTTPException):
                self.service.process_document(
                    self.document.id,
                    force_ocr=True,
                    resume_from_operation_id=source.operation_id,
                )

    def test_http_restart_and_browser_decoder_read_back(self):
        import json
        import subprocess
        from fastapi.testclient import TestClient
        from app.app_factory import create_app
        from app.core.settings import Settings

        settings = Settings(
            database_url=self.store.database.url,
            storage_root=str(self.root),
            plan_provider="mock",
            auto_migrate_local_data=False,
            ocr_engine="disabled",
        )
        app = create_app(settings=settings)

        def stop(page):
            if page.number == 1:
                raise RuntimeError("http-checkpoint-stop")
            return self.ocr(page)

        with TestClient(app, raise_server_exceptions=False) as client:
            with patch.object(
                app.state.container.document_parser, "_run_ocr", side_effect=stop
            ):
                failed = client.post(
                    f"/documents/{self.document.id}/process", json={"force_ocr": True}
                )
            self.assertEqual(failed.status_code, 500)
            response = client.get(f"/documents/{self.document.id}/checkpoint")
            self.assertEqual(response.status_code, 200, response.text)
            saved = response.json()
            self.assertEqual(saved["completed_page_count"], 1)
            source_id = saved["operation_id"]
        with TestClient(create_app(settings=settings)) as client:
            current = client.app.state.container
            with patch.object(
                current.document_parser, "_run_ocr", side_effect=self.ocr
            ) as ocr:
                result = client.post(
                    f"/documents/{self.document.id}/process",
                    json={"force_ocr": True, "resume_from_operation_id": source_id},
                )
            self.assertEqual(result.status_code, 200, result.text)
            self.assertEqual(ocr.call_count, 2)
            with patch.object(
                current.document_parser,
                "parse",
                side_effect=AssertionError("duplicate HTTP replayed parse"),
            ):
                duplicate = client.post(
                    f"/documents/{self.document.id}/process",
                    json={"force_ocr": True, "resume_from_operation_id": source_id},
                )
            self.assertEqual(duplicate.status_code, 200, duplicate.text)
            restored = client.get(f"/documents/{self.document.id}/checkpoint").json()
            self.assertEqual(restored["operation_status"], "committed")
            repo = Path(__file__).resolve().parents[3]
            decoder = (repo / "apps/web/lib/document-checkpoint-decode.ts").as_uri()
            script = f"import {{readFileSync}} from 'node:fs'; import {{decodeDocumentCheckpoint}} from {json.dumps(decoder)}; const x=JSON.parse(readFileSync(0,'utf8')); for(const raw of x) decodeDocumentCheckpoint(raw,raw.document_id);"
            decoded = subprocess.run(
                [
                    "node",
                    "--experimental-strip-types",
                    "--input-type=module",
                    "-e",
                    script,
                ],
                input=json.dumps([saved, restored]),
                text=True,
                capture_output=True,
                cwd=repo,
                timeout=30,
            )
            self.assertEqual(decoded.returncode, 0, decoded.stderr)

    def test_complete_stage_compacts_raw_pages_to_stay_inside_the_byte_budget(self):
        from sqlalchemy import select
        from app.persistence.models import (
            DocumentCheckpointPageRow,
            DocumentCheckpointRow,
        )

        from app.persistence.document_checkpoint_repository import byte_size

        save = self.service.checkpoints.save_stage
        limits = []

        def compact(operation_id, report, output=None):
            # The complete stage fits exactly; keeping the raw OCR rows cannot.
            limit = (
                byte_size(report.model_dump(mode="json") if output is None else None)
                + byte_size(output.model_dump(mode="json") if output else None)
                + 1
            )
            limits.append(limit)
            with patch(
                "app.persistence.document_checkpoint_repository.CHECKPOINT_MAX_BYTES",
                limit,
            ):
                save(operation_id, report, output)

        with (
            patch.object(self.service.checkpoints, "save_stage", side_effect=compact),
            patch.object(self.parser, "_run_ocr", side_effect=self.ocr),
        ):
            self.service.process_document(self.document.id, force_ocr=True)
        operation = self.service.process_repository.latest(document_id=self.document.id)
        snapshot = self.service.checkpoints.snapshot(operation.operation_id)
        self.assertIsNotNone(snapshot.output)
        self.assertEqual(snapshot.report.page_count, 3)
        with self.store.database.session() as session:
            row = session.get(DocumentCheckpointRow, operation.operation_id)
            self.assertLessEqual(row.byte_count, limits[-1])
            self.assertEqual(
                session.scalars(
                    select(DocumentCheckpointPageRow).where(
                        DocumentCheckpointPageRow.operation_id == operation.operation_id
                    )
                ).all(),
                [],
            )
