from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

import fitz
from fastapi import HTTPException
from app.api.routes import _map_plan_generation_error, get_document_planning_trace
from app.models.api import CreatePersonaRequest, DocumentResponse
from app.models.domain import (
    DocumentDebugRecord,
    LearningGoalInput,
    PlanGenerationTraceRecord,
    StudyUnitRecord,
)
from app.services.documents import DocumentService
from app.services.document_parser import DocumentParser, ParsedPage
from app.services.local_store import LocalJsonStore
from app.services.model_provider import (
    MockModelProvider,
    OpenAIModelProvider,
    PlanModelReply,
    PlanScheduleItem,
)
from app.services.pedagogy import PedagogyOrchestrator
from app.services.performance import PerformanceMapper
from app.services.plan_prompt import build_learning_plan_messages, read_page_range_content
from app.services.plan_prompt import load_learning_plan_prompt_template
from app.services.plans import LearningPlanService
from app.services.persona import PersonaEngine
from app.services.plan_tool_runtime import build_plan_tool_runtime, get_learning_plan_tool_specs
from app.services.study_arrangement import StudyArrangementService
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)
from app.services.study_sessions import StudySessionService


class PersonaPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        store = LocalJsonStore(Path(self.temp_dir.name))
        arrangement_service = StudyArrangementService()
        model_provider = MockModelProvider()
        self.persona_engine = PersonaEngine()
        self.document_service = DocumentService(store, DocumentParser(), arrangement_service)
        self.plan_service = LearningPlanService(store, arrangement_service, model_provider)
        self.study_session_service = StudySessionService(store)
        self.orchestrator = PedagogyOrchestrator(
            model_provider=model_provider,
            performance_mapper=PerformanceMapper(),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builtin_personas_are_available(self) -> None:
        personas = self.persona_engine.list_personas()
        self.assertGreaterEqual(len(personas), 2)
        self.assertEqual(personas[0].source, "builtin")

    def test_user_persona_creation_preserves_contract_shape(self) -> None:
        persona = self.persona_engine.create_persona(
            CreatePersonaRequest(
                name="Sora Guide",
                summary="A sharp but kind mentor.",
                system_prompt="Stay grounded in the document.",
                teaching_style=["socratic", "precise"],
                narrative_mode="light_story",
                encouragement_style="celebrate effort",
                correction_style="direct but supportive",
            )
        )
        self.assertEqual(persona.id, "sora-guide")
        self.assertEqual(persona.source, "user")
        self.assertIn("playful", persona.available_emotions)

    def test_chat_reply_returns_character_events(self) -> None:
        persona = self.persona_engine.require_persona("mentor-lyra")
        result = self.orchestrator.generate_chat_reply(
            session_id="session-1",
            persona=persona,
            message="解释牛顿第一定律",
            section_id="chapter-1",
        )
        self.assertTrue(result.reply)
        self.assertEqual(result.citations[0].section_id, "chapter-1")
        self.assertEqual(result.character_events[0].line_segment_id, "session-1:chat:0")

    def test_grading_changes_based_on_answer_length(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        short = self.orchestrator.grade_submission(
            persona=persona, exercise_id="exercise-1", answer="太短了"
        )
        long = self.orchestrator.grade_submission(
            persona=persona,
            exercise_id="exercise-1",
            answer="这是一个相对完整的回答，包含概念解释、教材例子以及一点自己的复述。",
        )
        self.assertLess(short.score, long.score)
        self.assertEqual(long.character_events[0].action, "celebrate")

    def test_plan_and_session_can_be_persisted(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "physics-notes.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Chapter 1 Mechanics", fontsize=24)
        page.insert_text(
            (72, 120),
            "Newton's first law explains inertia and stable motion.\n"
            "A body stays at rest or in uniform motion unless acted upon by a force.",
            fontsize=12,
        )
        second_page = pdf.new_page()
        second_page.insert_text((72, 72), "1.1 Inertia", fontsize=20)
        second_page.insert_text(
            (72, 120),
            "Inertia describes resistance to changes in motion.\n"
            "Use textbook examples to compare rest and constant velocity.",
            fontsize=12,
        )
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(
            filename="physics-notes.pdf",
            file=open(sample_pdf, "rb"),
        )
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        processed = self.document_service.process_document(document.id)
        persona = self.persona_engine.require_persona("mentor-aurora")
        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=processed.id,
                persona_id=persona.id,
                objective="掌握第一章",
            ),
            document=processed,
            persona_name=persona.name,
            persona=persona,
        )
        session = self.study_session_service.create_session(
            document_id=processed.id,
            persona_id=persona.id,
            section_id=processed.sections[0].id,
        )

        reply = self.orchestrator.generate_chat_reply(
            session_id=session.id,
            persona=persona,
            message="解释本章核心定义",
            section_id=processed.sections[0].id,
        )
        updated_session = self.study_session_service.append_turn(
            session_id=session.id,
            learner_message="解释本章核心定义",
            result=reply,
        )
        debug = self.document_service.require_debug_report(processed.id)

        self.assertTrue(plan.overview)
        self.assertGreaterEqual(processed.page_count, 2)
        self.assertGreaterEqual(processed.chunk_count, 1)
        self.assertTrue(debug.pages[0].text_preview)
        self.assertTrue(debug.sections)
        self.assertTrue(processed.study_units)
        self.assertTrue(plan.schedule)
        self.assertTrue(any(saved_plan.id == plan.id for saved_plan in self.plan_service.list_plans()))
        self.assertEqual(updated_session.turns[0].assistant_reply, reply.reply)
        self.assertEqual(updated_session.section_id, processed.sections[0].id)
        self.assertTrue(any(item.title.endswith("精读") for item in plan.schedule))

    def test_api_response_model_accepts_domain_dump(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "response-shape.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Section 1", fontsize=24)
        page.insert_text((72, 120), "This is enough text to build a parsed document.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(filename="response-shape.pdf", file=open(sample_pdf, "rb"))
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        processed = self.document_service.process_document(document.id)
        response = DocumentResponse.model_validate(processed.model_dump())

        self.assertEqual(response.id, processed.id)
        self.assertEqual(response.page_count, processed.page_count)

    def test_learning_plan_prompt_template_loads_from_text_file(self) -> None:
        template = load_learning_plan_prompt_template()

        self.assertIn("strict JSON only", template.system_prompt)
        self.assertIn('"course_title": string', template.system_prompt)
        self.assertGreaterEqual(len(template.user_instructions), 3)
        self.assertIn("study_units", template.user_instructions[0])

    def test_learning_plan_tool_specs_filter_by_context(self) -> None:
        all_specs = get_learning_plan_tool_specs()
        self.assertEqual(
            [spec["name"] for spec in all_specs],
            ["get_study_unit_detail", "revise_study_units", "read_page_range_content", "read_page_range_images"],
        )

        contextual_specs = get_learning_plan_tool_specs(
            detail_map={"unit-1": {"unit_id": "unit-1"}},
            debug_report=None,
        )
        self.assertEqual([spec["name"] for spec in contextual_specs], ["get_study_unit_detail"])

        multimodal_specs = get_learning_plan_tool_specs(
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Chapter 1",
                    page_start=1,
                    page_end=4,
                )
            ],
            detail_map={"unit-1": {"unit_id": "unit-1"}},
            debug_report=DocumentDebugRecord.model_validate(
                {
                    "document_id": "doc-1",
                    "parser_name": "parser",
                    "processed_at": "2026-04-09T00:00:00+00:00",
                    "page_count": 1,
                    "total_characters": 100,
                    "extraction_method": "text",
                    "ocr_applied": False,
                    "pages": [],
                    "sections": [],
                    "study_units": [],
                    "chunks": [],
                    "warnings": [],
                    "dominant_language_hint": "en",
                }
            ),
            document_path="/tmp/doc-1.pdf",
            multimodal_enabled=True,
        )
        self.assertEqual(
            [spec["name"] for spec in multimodal_specs],
            ["get_study_unit_detail", "revise_study_units", "read_page_range_content", "read_page_range_images"],
        )

    def test_multimodal_page_image_tool_creates_follow_up_message(self) -> None:
        runtime = build_plan_tool_runtime(
            document_path="/tmp/discrete-math.pdf",
            multimodal_enabled=True,
        )

        with patch(
            "app.services.plan_tool_runtime.read_page_range_images",
            return_value={
                "page_start": 4,
                "page_end": 5,
                "image_count": 2,
                "images": [
                    {
                        "page_number": 4,
                        "mime_type": "image/png",
                        "image_url": "data:image/png;base64,AAA",
                    },
                    {
                        "page_number": 5,
                        "mime_type": "image/png",
                        "image_url": "data:image/png;base64,BBB",
                    },
                ],
            },
        ):
            execution = runtime.execute_tool_call(
                {
                    "id": "call-image-1",
                    "type": "function",
                    "function": {
                        "name": "read_page_range_images",
                        "arguments": json.dumps(
                            {
                                "page_start": 4,
                                "page_end": 5,
                                "max_images": 2,
                            }
                        ),
                    },
                }
            )

        self.assertEqual(execution.tool_name, "read_page_range_images")
        self.assertEqual(execution.result["image_count"], 2)
        self.assertEqual(execution.result["page_numbers"], [4, 5])
        self.assertEqual(len(execution.follow_up_messages), 1)
        follow_up_content = execution.follow_up_messages[0]["content"]
        self.assertEqual(follow_up_content[0]["type"], "text")
        self.assertEqual(follow_up_content[1]["type"], "image_url")
        self.assertEqual(follow_up_content[1]["image_url"]["url"], "data:image/png;base64,AAA")

    def test_revise_study_units_tool_updates_active_segmentation(self) -> None:
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 1200,
                "extraction_method": "text",
                "ocr_applied": False,
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1",
                        "page_start": 1,
                        "page_end": 10,
                        "level": 1,
                    },
                    {
                        "id": "raw-2",
                        "document_id": "doc-1",
                        "title": "Chapter 2",
                        "page_start": 11,
                        "page_end": 20,
                        "level": 1,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )
        runtime = build_plan_tool_runtime(
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Combined Unit",
                    page_start=1,
                    page_end=20,
                    summary="旧划分。",
                    confidence=0.6,
                )
            ],
            debug_report=debug_report,
            detail_map={
                "unit-1": {
                    "unit_id": "unit-1",
                    "title": "Combined Unit",
                    "page_start": 1,
                    "page_end": 20,
                    "summary": "旧划分。",
                    "unit_kind": "chapter",
                    "include_in_plan": True,
                    "related_section_ids": ["raw-1", "raw-2"],
                    "subsection_titles": [],
                    "related_sections": [],
                    "chunk_count": 0,
                    "chunk_excerpts": [],
                }
            },
        )

        execution = runtime.execute_tool_call(
            {
                "id": "call-revise-1",
                "type": "function",
                "function": {
                    "name": "revise_study_units",
                    "arguments": json.dumps(
                        {
                            "study_units": [
                                {
                                    "title": "Chapter 1 Foundations",
                                    "page_start": 1,
                                    "page_end": 10,
                                },
                                {
                                    "title": "Chapter 2 Practice",
                                    "page_start": 11,
                                    "page_end": 20,
                                },
                            ],
                            "rationale": "The original segmentation merged two chapters.",
                        }
                    ),
                },
            }
        )

        self.assertTrue(execution.result["ok"])
        self.assertEqual(execution.result["study_unit_count"], 2)
        self.assertEqual(
            [unit.id for unit in runtime.current_study_units()],
            ["doc-1:study-unit:llm:1", "doc-1:study-unit:llm:2"],
        )
        self.assertIn("doc-1:study-unit:llm:1", runtime.context.detail_map)

    def test_document_planning_trace_route_wraps_trace_payload(self) -> None:
        trace = PlanGenerationTraceRecord.model_validate(
            {
                "document_id": "doc-1",
                "plan_id": "plan-1",
                "model": "gpt-test",
                "created_at": "2026-04-10T00:00:00+00:00",
                "rounds": [
                    {
                        "round_index": 0,
                        "finish_reason": "tool_calls",
                        "assistant_content": "",
                        "thinking": "Need more detail.",
                        "elapsed_ms": 120,
                        "timeout_seconds": 3,
                        "tool_calls": [
                            {
                                "tool_call_id": "call-1",
                                "tool_name": "get_study_unit_detail",
                                "arguments_json": "{\"study_unit_id\":\"unit-1\"}",
                                "result_json": "{\"ok\":true}",
                            }
                        ],
                    }
                ],
            }
        )

        with patch("app.api.routes.container.store.load_item", return_value=trace):
            response = get_document_planning_trace("doc-1")

        self.assertTrue(response.has_trace)
        self.assertIsNotNone(response.trace)
        self.assertEqual(response.summary.round_count, 1)
        self.assertEqual(response.summary.tool_call_count, 1)
        self.assertEqual(response.trace.model, "gpt-test")

    def test_document_process_stream_report_can_be_replayed_after_sync_processing(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "stream-process.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Chapter 1", fontsize=24)
        page.insert_text((72, 120), "Enough text to produce chunks and study units.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(filename="stream-process.pdf", file=open(sample_pdf, "rb"))
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        recorder = StreamReportRecorder(
            store=self.document_service.store,
            category=DOCUMENT_PROCESS_STREAM_CATEGORY,
            document_id=document.id,
            stream_kind="document_process",
        )
        processed = self.document_service.process_document(
            document.id,
            progress_callback=recorder.callback,
        )
        recorder.emit(
            "stream_completed",
            {
                "document_id": processed.id,
                "status": processed.status,
            },
        )

        report = StreamReportRecorder.load(
            store=self.document_service.store,
            category=DOCUMENT_PROCESS_STREAM_CATEGORY,
            document_id=document.id,
            stream_kind="document_process",
        )

        self.assertEqual(report.status, "completed")
        self.assertTrue(report.events)
        self.assertIn("document_processing_started", [event.stage for event in report.events])
        self.assertIn("stream_completed", [event.stage for event in report.events])

    def test_learning_plan_stream_report_can_be_replayed_after_sync_generation(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "stream-plan.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Chapter 1", fontsize=24)
        page.insert_text((72, 120), "Enough text to support a simple study plan.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(filename="stream-plan.pdf", file=open(sample_pdf, "rb"))
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        processed = self.document_service.process_document(document.id)
        persona = self.persona_engine.require_persona("mentor-aurora")
        recorder = StreamReportRecorder(
            store=self.plan_service.store,
            category=LEARNING_PLAN_STREAM_CATEGORY,
            document_id=processed.id,
            stream_kind="learning_plan",
        )
        recorder.emit(
            "learning_plan_started",
            {
                "document_id": processed.id,
                "persona_id": persona.id,
            },
        )
        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=processed.id,
                persona_id=persona.id,
                objective="掌握第一章",
            ),
            document=processed,
            persona_name=persona.name,
            persona=persona,
            progress_callback=recorder.callback,
        )
        recorder.emit(
            "stream_completed",
            {
                "document_id": processed.id,
                "plan_id": plan.id,
            },
        )

        report = StreamReportRecorder.load(
            store=self.plan_service.store,
            category=LEARNING_PLAN_STREAM_CATEGORY,
            document_id=processed.id,
            stream_kind="learning_plan",
        )

        stages = [event.stage for event in report.events]
        self.assertEqual(report.status, "completed")
        self.assertIn("learning_plan_started", stages)
        self.assertIn("heuristic_plan_built", stages)
        self.assertIn("model_plan_applied", stages)
        self.assertIn("stream_completed", stages)

    def test_parser_force_ocr_can_recover_blank_page(self) -> None:
        sample_pdf = Path(self.temp_dir.name) / "blank-scan.pdf"
        pdf = fitz.open()
        pdf.new_page()
        pdf.save(sample_pdf)
        pdf.close()

        parser = DocumentParser()
        with patch.object(
            parser,
            "_ocr_page",
            return_value="Chapter 1 Recovered\nThis page was recovered through OCR fallback.",
        ):
            report = parser.parse(
                document_id="doc-ocr",
                title="Recovered Scan",
                stored_path=str(sample_pdf),
                force_ocr=True,
            )

        self.assertTrue(report.ocr_applied)
        self.assertEqual(report.extraction_method, "ocr_forced")
        self.assertEqual(report.pages[0].extraction_source, "ocr")
        self.assertGreaterEqual(len(report.chunks), 1)

    def test_parser_filters_noisy_heading_candidates(self) -> None:
        sample_pdf = Path(self.temp_dir.name) / "heading-filter.pdf"
        pdf = fitz.open()
        page1 = pdf.new_page()
        page1.insert_text((72, 72), "nff= {x:VYEff(XEY)};", fontsize=24)
        page1.insert_text((72, 120), "Body text for the page.", fontsize=12)
        page2 = pdf.new_page()
        page2.insert_text((72, 72), "Chapter 1 Introduction", fontsize=24)
        page2.insert_text((72, 120), "A legitimate heading should survive filtering.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        parser = DocumentParser()
        report = parser.parse(
            document_id="doc-heading",
            title="Heading Filter",
            stored_path=str(sample_pdf),
        )

        titles = [section.title for section in report.sections]
        self.assertTrue(any("Chapter 1 Introduction" in title for title in titles))
        self.assertFalse(any("VYEff" in title for title in titles))

    def test_parser_extracts_bridge_style_ocr_header(self) -> None:
        parser = DocumentParser()
        candidates = parser._extract_ocr_heading_candidates(
            page_number=40,
            page_text=(
                "2. Computable Partial Functions 29 is primitive recursive. "
                "Does power(m,n)=m^n define a primitive recursive function?"
            ),
        )

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].text, "2. Computable Partial Functions")

    def test_parser_rejects_sentence_like_ocr_header(self) -> None:
        parser = DocumentParser()
        candidates = parser._extract_ocr_heading_candidates(
            page_number=84,
            page_text=(
                "2 <). = A, then there is a K-Aronszajn tree (Exercise 37). Thus, under GCH, "
                "we continue the proof on this page."
            ),
        )

        self.assertEqual(candidates, [])

    def test_parser_rejects_exercise_prompts_as_headings(self) -> None:
        parser = DocumentParser()

        self.assertTrue(parser._looks_like_noisy_heading("Exercises"))
        self.assertTrue(parser._looks_like_noisy_heading("2 Design a Turing machine, with input alphabet {0,1}"))
        self.assertTrue(parser._looks_like_noisy_heading("3 For this exercise we recall the Goldbach Conjecture"))
        self.assertFalse(parser._looks_like_noisy_heading("2. Computable Partial Functions"))

    def test_parser_normalizes_solution_heading_prefix(self) -> None:
        parser = DocumentParser()

        self.assertEqual(
            parser._normalize_heading_text("130 — Solutions to Exercises 117"),
            "Solutions to Exercises",
        )

    def test_parser_detects_and_strips_recurrent_headers_and_footers(self) -> None:
        parser = DocumentParser()
        pages = [
            ParsedPage(
                page_number=index,
                line_entries=[
                    (f"1. What Is a Turing Machine? {index + 4}", 0.0),
                    ("Core body text for this page.", 0.0),
                    (str(index + 4), 0.0),
                ],
                dominant_font_size=0.0,
                extraction_source="ocr",
                warnings=[],
                used_ocr=True,
            )
            for index in range(1, 5)
        ]

        top_patterns, bottom_patterns = parser._detect_margin_patterns(pages)
        stripped, stripped_count = parser._strip_margin_lines(
            pages[0].line_entries,
            top_patterns=top_patterns,
            bottom_patterns=bottom_patterns,
        )

        self.assertTrue(any("what is a turing machine" in pattern for pattern in top_patterns))
        self.assertIn("#", bottom_patterns)
        self.assertEqual(stripped_count, 2)
        self.assertEqual([text for text, _font_size in stripped], ["Core body text for this page."])

    def test_parser_builds_dual_sections_from_toc_and_assigns_chunk_targets(self) -> None:
        sample_pdf = Path(self.temp_dir.name) / "toc-dual.pdf"
        pdf = fitz.open()
        for index in range(1, 9):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Page {index}", fontsize=12)
            page.insert_text(
                (72, 120),
                (
                    f"Body text for page {index}. "
                    "This section includes enough explanatory prose to produce stable chunking. "
                    "We repeat this sentence to ensure the parser has usable material. "
                )
                * 6,
                fontsize=12,
            )
        pdf.set_toc(
            [
                [1, "Chapter 1", 1],
                [2, "1.1 Basics", 2],
                [2, "1.2 Advanced", 4],
                [1, "Chapter 2", 6],
                [2, "2.1 Review", 7],
                [1, "Appendix", 8],
            ]
        )
        pdf.save(sample_pdf)
        pdf.close()

        parser = DocumentParser()
        report = parser.parse(
            document_id="doc-toc-dual",
            title="Dual TOC",
            stored_path=str(sample_pdf),
        )

        level_1 = [section for section in report.sections if section.level == 1]
        level_2 = [section for section in report.sections if section.level == 2]
        chunk_section_ids = {chunk.section_id for chunk in report.chunks}

        self.assertGreaterEqual(len(level_1), 3)
        self.assertGreaterEqual(len(level_2), 3)
        self.assertTrue(any(section.title == "1.1 Basics" for section in level_2))
        self.assertTrue(any(section.title == "2.1 Review" for section in level_2))
        self.assertTrue(any(section_id.startswith("doc-toc-dual:section:l1:") for section_id in chunk_section_ids))
        self.assertTrue(any(section_id.startswith("doc-toc-dual:section:l2:") for section_id in chunk_section_ids))

    def test_study_arrangement_cleans_exercise_like_sections_before_plan(self) -> None:
        arranger = StudyArrangementService()
        document = DocumentResponse.model_validate(
            {
                "id": "doc-arrange",
                "title": "Computability",
                "original_filename": "computability.pdf",
                "stored_path": "/tmp/computability.pdf",
                "status": "processed",
                "ocr_status": "fallback_used",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [],
                "study_units": [],
                "study_unit_count": 0,
                "page_count": 30,
                "chunk_count": 12,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )
        from app.models.domain import DocumentDebugRecord

        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-arrange",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 30,
                "total_characters": 3000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [
                    {
                        "page_number": 1,
                        "char_count": 200,
                        "word_count": 30,
                        "text_preview": "1\nWhat Is a Turing Machine?\nIntro body text",
                        "dominant_font_size": 0.0,
                        "extraction_source": "ocr",
                        "heading_candidates": [],
                    },
                    {
                        "page_number": 10,
                        "char_count": 200,
                        "word_count": 30,
                        "text_preview": "2 Design a Turing machine, with input alphabet {0,1}\nBody text",
                        "dominant_font_size": 0.0,
                        "extraction_source": "ocr",
                        "heading_candidates": [],
                    },
                    {
                        "page_number": 12,
                        "char_count": 200,
                        "word_count": 30,
                        "text_preview": "2. Computable Partial Functions\nBody text",
                        "dominant_font_size": 0.0,
                        "extraction_source": "ocr",
                        "heading_candidates": [],
                    },
                ],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-arrange",
                        "title": "1 What Is a Turing Machine?",
                        "page_start": 1,
                        "page_end": 9,
                        "level": 1,
                    },
                    {
                        "id": "raw-2",
                        "document_id": "doc-arrange",
                        "title": "2 Design a Turing machine, with input alphabet {0,1}",
                        "page_start": 10,
                        "page_end": 11,
                        "level": 1,
                    },
                    {
                        "id": "raw-3",
                        "document_id": "doc-arrange",
                        "title": "2. Computable Partial Functions",
                        "page_start": 12,
                        "page_end": 30,
                        "level": 1,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        units = arranger.build_study_units(document=document, debug_report=debug_report)

        self.assertEqual([unit.title for unit in units if unit.include_in_plan], [
            "1 What Is a Turing Machine?",
            "2. Computable Partial Functions",
        ])
        self.assertEqual(units[0].page_end, 11)

    def test_learning_plan_prompt_uses_cleaned_study_units_and_constraints(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="掌握第一章",
        )
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 18,
                "total_characters": 2000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1 Foundations",
                        "page_start": 1,
                        "page_end": 18,
                        "level": 1,
                    },
                    {
                        "id": "raw-1-1",
                        "document_id": "doc-1",
                        "title": "1.1 Sets",
                        "page_start": 1,
                        "page_end": 8,
                        "level": 2,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )
        messages = build_learning_plan_messages(
            persona=persona,
            document_title="Discrete Mathematics",
            goal=goal,
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Chapter 1 Foundations",
                    page_start=1,
                    page_end=18,
                    source_section_ids=["raw-1"],
                    summary="聚焦集合与命题逻辑。",
                    confidence=0.9,
                )
            ],
            debug_report=debug_report,
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("strict JSON only", messages[0]["content"])
        self.assertIn('"course_title": string', messages[0]["content"])
        self.assertNotIn("course_outline", messages[0]["content"])
        self.assertIn("Chapter 1 Foundations", messages[1]["content"])
        self.assertIn('"detail_tool_target_id": "unit-1"', messages[1]["content"])
        self.assertIn('"study_units"', messages[1]["content"])
        self.assertNotIn('"course_outline"', messages[1]["content"])
        self.assertIn("掌握第一章", messages[1]["content"])

    def test_openai_provider_parses_json_learning_plan_response(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="掌握第一章",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
        )

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "course_title": "Discrete Mathematics / Chapter 1 Foundations",
                                            "overview": "LLM plan overview",
                                            "weekly_focus": ["Chapter 1 Foundations"],
                                            "today_tasks": ["Read Chapter 1 carefully."],
                                            "schedule": [
                                                {
                                                    "unit_id": "unit-1",
                                                    "title": "Chapter 1 Foundations 精读",
                                                    "focus": "理解定义与例题。",
                                                    "activity_type": "learn",
                                                }
                                            ],
                                        }
                                    )
                                }
                            }
                        ]
                    }
                ).encode("utf-8")

        with patch("urllib.request.urlopen", return_value=FakeResponse()) as mocked_urlopen:
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Discrete Mathematics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Chapter 1 Foundations",
                        page_start=1,
                        page_end=18,
                        summary="聚焦集合与命题逻辑。",
                        confidence=0.9,
                    )
                ],
            )

        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(reply.course_title, "Discrete Mathematics / Chapter 1 Foundations")
        self.assertEqual(reply.overview, "LLM plan overview")
        self.assertEqual(reply.schedule[0].unit_id, "unit-1")

    def test_openai_provider_can_handle_plan_tool_call_roundtrip(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="掌握第一章",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
        )
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 18,
                "total_characters": 2000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1 Foundations",
                        "page_start": 1,
                        "page_end": 18,
                        "level": 1,
                    },
                    {
                        "id": "raw-1-1",
                        "document_id": "doc-1",
                        "title": "1.1 Sets",
                        "page_start": 1,
                        "page_end": 8,
                        "level": 2,
                    },
                ],
                "study_units": [],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "section_id": "raw-1-1",
                        "page_start": 1,
                        "page_end": 3,
                        "char_count": 320,
                        "text_preview": "Sets, subsets, and membership.",
                        "content": "Sets, subsets, membership, extensionality, and simple examples.",
                    }
                ],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        class FakeResponse:
            def __init__(self, payload: dict[str, object]):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        responses = [
            FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": "I should inspect the subsection structure first.",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_study_unit_detail",
                                            "arguments": json.dumps(
                                                {
                                                    "study_unit_id": "unit-1",
                                                    "focus": "inspect subsection coverage",
                                                }
                                            ),
                                        },
                                    },
                                    {
                                        "id": "call-2",
                                        "type": "function",
                                        "function": {
                                            "name": "read_page_range_content",
                                            "arguments": json.dumps(
                                                {
                                                    "page_start": 1,
                                                    "page_end": 3,
                                                    "max_chars": 1200,
                                                }
                                            ),
                                        },
                                    },
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "reasoning_content": "I now have enough evidence to write the plan.",
                                "content": json.dumps(
                                    {
                                        "course_title": "Discrete Mathematics / Chapter 1 Foundations",
                                        "overview": "Tool-assisted plan overview",
                                        "weekly_focus": ["Chapter 1 Foundations"],
                                        "today_tasks": ["Read sets and extensionality."],
                                        "schedule": [
                                            {
                                                "unit_id": "unit-1",
                                                "title": "Chapter 1 Foundations 精读",
                                                "focus": "Cover sets, subsets, and extensionality.",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]

        with patch("urllib.request.urlopen", side_effect=responses) as mocked_urlopen:
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Discrete Mathematics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Chapter 1 Foundations",
                        page_start=1,
                        page_end=18,
                        source_section_ids=["raw-1"],
                        summary="聚焦集合与命题逻辑。",
                        confidence=0.9,
                    )
                ],
                debug_report=debug_report,
            )

        first_payload = json.loads(mocked_urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        second_payload = json.loads(mocked_urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn("tools", first_payload)
        self.assertIn(
            "get_study_unit_detail",
            [tool["function"]["name"] for tool in first_payload["tools"]],
        )
        self.assertIn(
            "read_page_range_content",
            [tool["function"]["name"] for tool in first_payload["tools"]],
        )
        tool_messages = [message for message in second_payload["messages"] if message["role"] == "tool"]
        self.assertEqual(len(tool_messages), 2)
        self.assertIn("extensionality", tool_messages[0]["content"])
        self.assertIn("membership", tool_messages[1]["content"])
        self.assertIsNotNone(reply.debug_trace)
        self.assertEqual(reply.debug_trace.model, "gpt-test")
        self.assertEqual(len(reply.debug_trace.rounds), 2)
        self.assertIn("inspect the subsection structure", reply.debug_trace.rounds[0].thinking)
        self.assertGreaterEqual(reply.debug_trace.rounds[0].elapsed_ms, 0)
        self.assertEqual(reply.debug_trace.rounds[0].timeout_seconds, 3)
        self.assertEqual(len(reply.debug_trace.rounds[0].tool_calls), 2)
        self.assertIn("enough evidence", reply.debug_trace.rounds[1].thinking)
        self.assertEqual(reply.course_title, "Discrete Mathematics / Chapter 1 Foundations")
        self.assertEqual(reply.overview, "Tool-assisted plan overview")
        self.assertEqual(reply.schedule[0].unit_id, "unit-1")

    def test_openai_provider_can_revise_study_units_before_planning(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="纠正章节划分",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
        )
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 2000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1",
                        "page_start": 1,
                        "page_end": 10,
                        "level": 1,
                    },
                    {
                        "id": "raw-2",
                        "document_id": "doc-1",
                        "title": "Chapter 2",
                        "page_start": 11,
                        "page_end": 20,
                        "level": 1,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        class FakeResponse:
            def __init__(self, payload: dict[str, object]):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        responses = [
            FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-revise-1",
                                        "type": "function",
                                        "function": {
                                            "name": "revise_study_units",
                                            "arguments": json.dumps(
                                                {
                                                    "study_units": [
                                                        {
                                                            "title": "Chapter 1 Foundations",
                                                            "page_start": 1,
                                                            "page_end": 10,
                                                        },
                                                        {
                                                            "title": "Chapter 2 Practice",
                                                            "page_start": 11,
                                                            "page_end": 20,
                                                        },
                                                    ]
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "course_title": "Discrete Mathematics / Revised",
                                        "overview": "Use the revised segmentation.",
                                        "weekly_focus": ["Chapter 1 Foundations", "Chapter 2 Practice"],
                                        "today_tasks": ["Start with the corrected first chapter."],
                                        "schedule": [
                                            {
                                                "unit_id": "doc-1:study-unit:llm:1",
                                                "title": "Chapter 1 Foundations 精读",
                                                "focus": "Study the corrected first chapter.",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]

        with patch("urllib.request.urlopen", side_effect=responses):
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Discrete Mathematics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Wrong Combined Unit",
                        page_start=1,
                        page_end=20,
                        summary="旧划分。",
                        confidence=0.7,
                    )
                ],
                debug_report=debug_report,
            )

        self.assertIsNotNone(reply.revised_study_units)
        self.assertEqual(
            [unit.id for unit in reply.revised_study_units or []],
            ["doc-1:study-unit:llm:1", "doc-1:study-unit:llm:2"],
        )
        self.assertEqual(reply.schedule[0].unit_id, "doc-1:study-unit:llm:1")

    def test_openai_provider_multimodal_tool_call_appends_page_images(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="理解图表与公式",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
            multimodal_enabled=True,
        )

        class FakeResponse:
            def __init__(self, payload: dict[str, object]):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self.payload).encode("utf-8")

        responses = [
            FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-image-1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_page_range_images",
                                            "arguments": json.dumps(
                                                {
                                                    "page_start": 2,
                                                    "page_end": 2,
                                                    "max_images": 1,
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeResponse(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "course_title": "Physics / Chapter 2 Graphs",
                                        "overview": "Use the page image to understand the diagram-heavy unit.",
                                        "weekly_focus": ["Chapter 2 Graphs"],
                                        "today_tasks": ["Inspect the textbook figure and summarize it."],
                                        "schedule": [
                                            {
                                                "unit_id": "unit-graph",
                                                "title": "Chapter 2 Graphs 精读",
                                                "focus": "Interpret the chart and connect it with the surrounding explanation.",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]

        with (
            patch("urllib.request.urlopen", side_effect=responses) as mocked_urlopen,
            patch(
                "app.services.plan_tool_runtime.read_page_range_images",
                return_value={
                    "page_start": 2,
                    "page_end": 2,
                    "image_count": 1,
                    "images": [
                        {
                            "page_number": 2,
                            "mime_type": "image/png",
                            "image_url": "data:image/png;base64,AAA",
                        }
                    ],
                },
            ),
        ):
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Physics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-graph",
                        document_id="doc-1",
                        title="Chapter 2 Graphs",
                        page_start=2,
                        page_end=4,
                        summary="聚焦图表与相关解释。",
                        confidence=0.8,
                    )
                ],
                document_path="/tmp/physics.pdf",
            )

        first_payload = json.loads(mocked_urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        second_payload = json.loads(mocked_urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn(
            "read_page_range_images",
            [tool["function"]["name"] for tool in first_payload["tools"]],
        )
        image_follow_up_messages = [
            message
            for message in second_payload["messages"]
            if message["role"] == "user" and isinstance(message["content"], list)
        ]
        self.assertEqual(len(image_follow_up_messages), 1)
        self.assertEqual(image_follow_up_messages[0]["content"][1]["type"], "image_url")
        self.assertEqual(
            image_follow_up_messages[0]["content"][1]["image_url"]["url"],
            "data:image/png;base64,AAA",
        )
        tool_messages = [message for message in second_payload["messages"] if message["role"] == "tool"]
        self.assertEqual(tool_messages[0]["name"], "read_page_range_images")
        self.assertIn('"page_numbers": [2]', tool_messages[0]["content"])
        self.assertEqual(reply.schedule[0].unit_id, "unit-graph")

    def test_read_page_range_content_joins_overlapping_chunks(self) -> None:
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 1200,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [],
                "study_units": [],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "section_id": "raw-1",
                        "page_start": 2,
                        "page_end": 3,
                        "char_count": 200,
                        "text_preview": "first preview",
                        "content": "First detailed excerpt.",
                    },
                    {
                        "id": "chunk-2",
                        "document_id": "doc-1",
                        "section_id": "raw-1",
                        "page_start": 4,
                        "page_end": 5,
                        "char_count": 200,
                        "text_preview": "second preview",
                        "content": "Second detailed excerpt.",
                    },
                ],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        content = read_page_range_content(
            debug_report=debug_report,
            page_start=3,
            page_end=4,
            max_chars=1000,
        )

        self.assertEqual(content["chunk_count"], 2)
        self.assertIn("First detailed excerpt.", content["content"])
        self.assertIn("Second detailed excerpt.", content["content"])

    def test_route_maps_rate_limit_to_service_unavailable(self) -> None:
        error = _map_plan_generation_error(RuntimeError("openai_plan_request_rate_limit"))

        self.assertIsInstance(error, HTTPException)
        self.assertEqual(error.status_code, 503)
        self.assertEqual(error.detail, "plan_model_rate_limited")

    def test_route_maps_network_error_to_bad_gateway(self) -> None:
        error = _map_plan_generation_error(RuntimeError("openai_plan_request_network_error"))

        self.assertEqual(error.status_code, 502)
        self.assertEqual(error.detail, "plan_model_network_error")

    def test_route_maps_timeout_to_gateway_timeout(self) -> None:
        error = _map_plan_generation_error(RuntimeError("openai_plan_request_timeout"))

        self.assertEqual(error.status_code, 504)
        self.assertEqual(error.detail, "plan_model_timeout")

    def test_route_maps_upstream_plan_error_to_bad_gateway(self) -> None:
        error = _map_plan_generation_error(
            RuntimeError("openai_plan_request_failed:500:rate_limit")
        )

        self.assertEqual(error.status_code, 502)
        self.assertEqual(error.detail, "plan_model_upstream_error")

    def test_plan_service_uses_model_provider_output_for_plan(self) -> None:
        arrangement_service = StudyArrangementService()
        store = LocalJsonStore(Path(self.temp_dir.name) / "plan-provider-case")
        provider = MockModelProvider()
        service = LearningPlanService(store, arrangement_service, provider)
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-plan",
                "title": "Linear Algebra",
                "original_filename": "linear-algebra.pdf",
                "stored_path": "/tmp/linear.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [
                    {
                        "id": "doc-plan:study-unit:1",
                        "document_id": "doc-plan",
                        "title": "Chapter 1 Vectors",
                        "page_start": 1,
                        "page_end": 20,
                        "level": 1,
                    }
                ],
                "study_units": [
                    {
                        "id": "doc-plan:study-unit:1",
                        "document_id": "doc-plan",
                        "title": "Chapter 1 Vectors",
                        "page_start": 1,
                        "page_end": 20,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "聚焦向量基础。",
                        "confidence": 0.9,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 20,
                "chunk_count": 5,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=PlanModelReply(
                course_title="Linear Algebra / Chapter 1 Vectors",
                overview="Model-crafted overview",
                weekly_focus=["Chapter 1 Vectors"],
                today_tasks=["完成向量定义与例题梳理。"],
                schedule=[
                    PlanScheduleItem(
                        unit_id="doc-plan:study-unit:1",
                        title="Chapter 1 Vectors 精读",
                        focus="完成向量定义与例题梳理。",
                        activity_type="learn",
                    )
                ],
            ),
        ) as mocked_plan_call:
            plan = service.create_plan(
                goal=LearningGoalInput(
                    document_id=document.id,
                    persona_id=persona.id,
                    objective="掌握向量基础",
                ),
                document=document,
                persona_name=persona.name,
                persona=persona,
            )

        mocked_plan_call.assert_called_once()
        self.assertEqual(plan.course_title, "Linear Algebra / Chapter 1 Vectors")
        self.assertEqual(plan.overview, "Model-crafted overview")
        self.assertEqual(plan.schedule[0].title, "Chapter 1 Vectors 精读")

    def test_plan_service_persists_model_revised_study_units(self) -> None:
        arrangement_service = StudyArrangementService()
        store = LocalJsonStore(Path(self.temp_dir.name) / "plan-revision-case")
        provider = MockModelProvider()
        service = LearningPlanService(store, arrangement_service, provider)
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-revise",
                "title": "Discrete Mathematics",
                "original_filename": "discrete.pdf",
                "stored_path": "/tmp/discrete.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [],
                "study_units": [
                    {
                        "id": "doc-revise:study-unit:1",
                        "document_id": "doc-revise",
                        "title": "Wrong Combined Unit",
                        "page_start": 1,
                        "page_end": 20,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "旧划分。",
                        "confidence": 0.7,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 20,
                "chunk_count": 5,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )
        store.save_list("documents", [document])
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-revise",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 2000,
                "extraction_method": "text",
                "ocr_applied": False,
                "pages": [],
                "sections": [],
                "study_units": document.study_units,
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=PlanModelReply(
                course_title="Discrete Mathematics / Revised",
                overview="Model-crafted revised overview",
                weekly_focus=["Chapter 1 Foundations", "Chapter 2 Practice"],
                today_tasks=["从修正后的第一章开始。"],
                schedule=[
                    PlanScheduleItem(
                        unit_id="doc-revise:study-unit:llm:1",
                        title="Chapter 1 Foundations 精读",
                        focus="修正后的第一章。",
                        activity_type="learn",
                    )
                ],
                revised_study_units=[
                    StudyUnitRecord(
                        id="doc-revise:study-unit:llm:1",
                        document_id="doc-revise",
                        title="Chapter 1 Foundations",
                        page_start=1,
                        page_end=10,
                        summary="第一章",
                        confidence=0.95,
                    ),
                    StudyUnitRecord(
                        id="doc-revise:study-unit:llm:2",
                        document_id="doc-revise",
                        title="Chapter 2 Practice",
                        page_start=11,
                        page_end=20,
                        summary="第二章",
                        confidence=0.95,
                    ),
                ],
            ),
        ):
            plan = service.create_plan(
                goal=LearningGoalInput(
                    document_id=document.id,
                    persona_id=persona.id,
                    objective="纠正章节划分",
                ),
                document=document,
                persona_name=persona.name,
                persona=persona,
                debug_report=debug_report,
            )

        saved_document = store.load_list("documents", DocumentResponse)[0]
        saved_debug = store.load_item("document_debug", "doc-revise", DocumentDebugRecord)
        self.assertEqual([unit.id for unit in plan.study_units], ["doc-revise:study-unit:llm:1", "doc-revise:study-unit:llm:2"])
        self.assertEqual(plan.schedule[0].unit_id, "doc-revise:study-unit:llm:1")
        self.assertEqual(saved_document.sections[0].id, "doc-revise:study-unit:llm:1")
        self.assertIsNotNone(saved_debug)
        self.assertEqual(saved_debug.study_units[1].id, "doc-revise:study-unit:llm:2")


if __name__ == "__main__":
    unittest.main()
