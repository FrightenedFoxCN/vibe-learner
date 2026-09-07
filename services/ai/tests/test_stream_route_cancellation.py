from __future__ import annotations

import asyncio
import io
import json
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi import UploadFile

from app.api import routes
from app.models.api import LearningPlanCreateRequest, ProcessDocumentRequest
from app.models.stream import (
    TERMINAL_STREAM_STAGES,
    StreamEventRecord,
    StreamReportRecord,
)
from app.services.document_parser import DocumentParser
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.persona import PersonaEngine
from app.services.plans import LearningPlanService
from app.services.stream_interrupts import StreamInterruptRegistry
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)
from app.services.study_arrangement import StudyArrangementService


async def _read_stream(response) -> list[dict[str, object]]:
    content = ""
    async for chunk in response.body_iterator:
        content += chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
    return [json.loads(line) for line in content.splitlines() if line.strip()]


class StreamRouteCancellationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp_dir.name))
        arrangement = StudyArrangementService()
        self.document_service = DocumentService(
            self.store,
            DocumentParser(),
            arrangement,
        )
        self.plan_service = LearningPlanService(
            self.store,
            arrangement,
            MockModelProvider(),
        )
        self.persona_engine = PersonaEngine(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_goal_only_plan_routes_use_safe_report_keys_and_commit(self) -> None:
        sync_request = LearningPlanCreateRequest(
            document_id="",
            persona_id="mentor-aurora",
            client_request_id="goal-only/sync request",
            objective="Learn introductory algebra",
        )
        stream_request = LearningPlanCreateRequest(
            document_id="",
            persona_id="mentor-aurora",
            client_request_id="goal-only/stream request",
            objective="Learn introductory geometry",
        )
        registry = StreamInterruptRegistry()
        with (
            patch.object(routes.container, "store", self.store),
            patch.object(routes.container, "plan_service", self.plan_service),
            patch.object(routes.container, "persona_engine", self.persona_engine),
            patch.object(routes.container, "stream_interrupt_registry", registry),
        ):
            sync_result = routes.create_learning_plan(sync_request)
            stream_response = routes.create_learning_plan_stream(stream_request)
            stream_frames = asyncio.run(_read_stream(stream_response))

        self.assertEqual(sync_result.creation_mode, "goal_only")
        self.assertEqual(sync_result.document_id, "")
        self.assertEqual(stream_frames[-1]["stage"], "stream_completed")
        self.assertEqual(
            stream_frames[-1]["committed_projection"]["creation_mode"],
            "goal_only",
        )
        for request in (sync_request, stream_request):
            storage_id = routes._learning_plan_stream_storage_id(request)
            self.assertRegex(storage_id, r"^learning-plan-request-[0-9a-f]{24}$")
            report = StreamReportRecorder.load(
                store=self.store,
                category=LEARNING_PLAN_STREAM_CATEGORY,
                document_id=storage_id,
                stream_kind="learning_plan",
            )
            self.assertEqual(report.status, "completed")
            self.assertEqual(report.subject.subject_type, "learning_plan_request")
            self.assertEqual(report.subject.subject_id, request.client_request_id)

    def test_confirmed_plan_cancel_wins_over_later_provider_runtime_error(self) -> None:
        document = self._processed_document("plan-cancel.pdf")
        provider_entered = threading.Event()
        release_provider = threading.Event()

        def fail_after_cancel(**kwargs: object):
            progress_callback = kwargs["progress_callback"]
            assert callable(progress_callback)
            progress_callback(
                "model_round_started",
                {"document_id": document.id, "round_index": 0},
            )
            provider_entered.set()
            if not release_provider.wait(timeout=5):
                raise RuntimeError("provider_test_release_timeout")
            raise RuntimeError("openai_plan_request_failed:provider_unavailable")

        registry = StreamInterruptRegistry()
        request = LearningPlanCreateRequest(
            document_id=document.id,
            persona_id="mentor-aurora",
            client_request_id="stream-plan-cancel-race",
            expected_document_updated_at=document.updated_at,
            objective="Master the cancellation boundary",
        )
        try:
            with (
                patch.object(routes.container, "store", self.store),
                patch.object(
                    routes.container,
                    "document_service",
                    self.document_service,
                ),
                patch.object(routes.container, "plan_service", self.plan_service),
                patch.object(
                    routes.container,
                    "persona_engine",
                    self.persona_engine,
                ),
                patch.object(
                    routes.container,
                    "stream_interrupt_registry",
                    registry,
                ),
                patch.object(
                    self.plan_service.model_provider,
                    "generate_learning_plan",
                    side_effect=fail_after_cancel,
                ),
            ):
                response = routes.create_learning_plan_stream(request)
                self.assertTrue(provider_entered.wait(timeout=5))
                running_report = self._load_report(
                    category=LEARNING_PLAN_STREAM_CATEGORY,
                    document_id=document.id,
                    stream_kind="learning_plan",
                )
                self.assertEqual(running_report.events[-1].stage, "model_round_started")
                assert running_report.operation_id is not None
                cancel_result = routes.cancel_stream_run(running_report.operation_id)
                self.assertTrue(cancel_result["cancelled"])
                release_provider.set()
                frames = asyncio.run(_read_stream(response))
                report = self._load_report(
                    category=LEARNING_PLAN_STREAM_CATEGORY,
                    document_id=document.id,
                    stream_kind="learning_plan",
                )
        finally:
            release_provider.set()

        terminal = self._assert_single_terminal(frames, report)
        self.assertEqual(terminal.stage, "stream_cancelled")
        self.assertEqual(report.status, "cancelled")
        assert terminal.terminal_evidence is not None
        self.assertEqual(terminal.terminal_evidence.commit_status, "uncertain")
        self.assertEqual(terminal.terminal_evidence.domain_operation_status, "uncertain")

    def test_uncancelled_plan_provider_failure_stays_error_and_fences_late_cancel(self) -> None:
        document = self._processed_document("plan-error.pdf")
        provider_entered = threading.Event()

        def fail_provider(**kwargs: object):
            progress_callback = kwargs["progress_callback"]
            assert callable(progress_callback)
            progress_callback(
                "model_round_started",
                {"document_id": document.id, "round_index": 0},
            )
            provider_entered.set()
            raise RuntimeError("openai_plan_request_failed:provider_unavailable")

        registry = StreamInterruptRegistry()
        request = LearningPlanCreateRequest(
            document_id=document.id,
            persona_id="mentor-aurora",
            client_request_id="stream-plan-provider-error",
            expected_document_updated_at=document.updated_at,
            objective="Preserve the provider error terminal",
        )
        with (
            patch.object(routes.container, "store", self.store),
            patch.object(routes.container, "document_service", self.document_service),
            patch.object(routes.container, "plan_service", self.plan_service),
            patch.object(routes.container, "persona_engine", self.persona_engine),
            patch.object(routes.container, "stream_interrupt_registry", registry),
            patch.object(
                self.plan_service.model_provider,
                "generate_learning_plan",
                side_effect=fail_provider,
            ),
        ):
            response = routes.create_learning_plan_stream(request)
            self.assertTrue(provider_entered.wait(timeout=5))
            frames = asyncio.run(_read_stream(response))
            report = self._load_report(
                category=LEARNING_PLAN_STREAM_CATEGORY,
                document_id=document.id,
                stream_kind="learning_plan",
            )
            assert report.operation_id is not None
            late_cancel = routes.cancel_stream_run(report.operation_id)

        terminal = self._assert_single_terminal(frames, report)
        self.assertEqual(terminal.stage, "stream_error")
        self.assertEqual(report.status, "error")
        self.assertFalse(late_cancel["cancelled"])
        assert terminal.terminal_evidence is not None
        self.assertEqual(terminal.terminal_evidence.commit_status, "uncertain")
        self.assertEqual(terminal.terminal_evidence.domain_operation_status, "uncertain")

    def test_confirmed_document_cancel_wins_over_later_parser_error(self) -> None:
        document = self._create_document("document-cancel.pdf")
        parser_entered = threading.Event()
        release_parser = threading.Event()

        def fail_after_cancel(**_kwargs: object):
            parser_entered.set()
            if not release_parser.wait(timeout=5):
                raise RuntimeError("parser_test_release_timeout")
            raise RuntimeError("parser_failed_after_cancel")

        registry = StreamInterruptRegistry()
        try:
            with (
                patch.object(routes.container, "store", self.store),
                patch.object(
                    routes.container,
                    "document_service",
                    self.document_service,
                ),
                patch.object(
                    routes.container,
                    "stream_interrupt_registry",
                    registry,
                ),
                patch.object(
                    self.document_service.parser,
                    "parse",
                    side_effect=fail_after_cancel,
                ),
            ):
                response = routes.process_document_stream(
                    document.id,
                    ProcessDocumentRequest(force_ocr=False),
                )
                self.assertTrue(parser_entered.wait(timeout=5))
                running_report = self._load_report(
                    category=DOCUMENT_PROCESS_STREAM_CATEGORY,
                    document_id=document.id,
                    stream_kind="document_process",
                )
                assert running_report.operation_id is not None
                cancel_result = routes.cancel_stream_run(running_report.operation_id)
                self.assertTrue(cancel_result["cancelled"])
                release_parser.set()
                frames = asyncio.run(_read_stream(response))
                report = self._load_report(
                    category=DOCUMENT_PROCESS_STREAM_CATEGORY,
                    document_id=document.id,
                    stream_kind="document_process",
                )
        finally:
            release_parser.set()

        terminal = self._assert_single_terminal(frames, report)
        self.assertEqual(terminal.stage, "stream_cancelled")
        self.assertEqual(report.status, "cancelled")
        assert terminal.terminal_evidence is not None
        self.assertEqual(terminal.terminal_evidence.commit_status, "not_committed")
        self.assertEqual(terminal.terminal_evidence.domain_operation_status, "failed")

    def _processed_document(self, filename: str):
        document = self._create_document(filename)
        return self.document_service.process_document(document.id)

    def _create_document(self, filename: str):
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Chapter 1", fontsize=24)
        page.insert_text(
            (72, 120),
            "Enough text to build a deterministic planning fixture.",
            fontsize=12,
        )
        pdf_bytes = pdf.tobytes()
        pdf.close()
        return self.document_service.create_document(
            UploadFile(
                filename=filename,
                file=io.BytesIO(pdf_bytes),
                headers={"content-type": "application/pdf"},
            )
        )

    def _load_report(
        self,
        *,
        category: str,
        document_id: str,
        stream_kind: str,
    ) -> StreamReportRecord:
        return StreamReportRecorder.load(
            store=self.store,
            category=category,
            document_id=document_id,
            stream_kind=stream_kind,
        )

    def _assert_single_terminal(
        self,
        frames: list[dict[str, object]],
        report: StreamReportRecord,
    ) -> StreamEventRecord:
        decoded = [StreamEventRecord.model_validate(frame) for frame in frames]
        terminals = [event for event in decoded if event.stage in TERMINAL_STREAM_STAGES]
        self.assertEqual(len(terminals), 1)
        terminal = terminals[0]
        self.assertEqual(decoded[-1], terminal)
        self.assertEqual(report.events[-1], terminal)
        self.assertEqual(report.operation_id, terminal.operation_id)
        self.assertEqual(report.subject, terminal.subject)
        self.assertEqual(
            [event.event_sequence for event in decoded],
            list(range(1, len(decoded) + 1)),
        )
        return terminal


if __name__ == "__main__":
    unittest.main()
