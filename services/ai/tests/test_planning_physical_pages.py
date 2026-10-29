"""Real PDF/HTTP regression: printed labels cannot redefine physical bounds."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.models.domain import LearningGoalInput, PlanningIntentV1
from app.models.pdf_page_scope import PhysicalPageScopeViolation
from app.models.planning import (
    LearningPlanOperationRequestV1,
    PlanContentSliceProposalV1,
)
from app.persistence.models import LearningPlanRow, LearningPlanOperationRow
from app.services.model_provider import MockModelProvider
from app.services.plan_prompt import build_learning_plan_messages
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.provider_capabilities import PlanModelReply, PlanScheduleItem
from app.services.provider_planning import (
    _decode_learning_plan_proposal,
    _validate_learning_plan_proposal_refs,
)
from tests.support.planning_samples import valid_proposal_payload


def explicit():
    return PlanningIntentV1.model_validate(
        {
            "pdf_page_ranges": {
                "status": "user_explicit",
                "value": [{"page_start": 100, "page_end": 103}],
            }
        }
    )


class ProbeProvider(MockModelProvider):
    calls = 0
    wrong_printed_pages = False

    def generate_learning_plan(self, **kwargs):
        self.calls += 1
        intent = kwargs["goal"].planning_intent
        messages = build_learning_plan_messages(
            persona=kwargs["persona"],
            document_title=kwargs["document_title"],
            goal=kwargs["goal"],
            study_units=kwargs["study_units"],
            debug_report=kwargs["debug_report"],
        )
        assert json.loads(messages[1]["content"])["learning_goal"]["planning_intent"][
            "pdf_page_ranges"
        ]["value"] == [{"page_start": 100, "page_end": 103}]
        runtime = build_plan_tool_runtime(
            study_units=kwargs["study_units"],
            debug_report=kwargs["debug_report"],
            document_path=kwargs["document_path"],
            multimodal_enabled=True,
            planning_intent=intent,
        )

        def tool(name, start, end):
            runtime.begin_round()
            return runtime.execute_tool_call(
                {
                    "id": f"physical-{start}",
                    "type": "function",
                    "function": {
                        "name": name,
                        "arguments": json.dumps({"page_start": start, "page_end": end}),
                    },
                }
            )

        assert not tool("read_page_range_content", 70, 73).result["ok"]
        assert not tool("read_page_range_images", 70, 73).result["ok"]
        text = tool("read_page_range_content", 100, 103)
        assert text.result["ok"] and "PHYSICAL100" in text.result["content"]
        assert tool("read_page_range_images", 100, 103).result["page_numbers"] == [
            100,
            101,
            102,
        ]
        start, end = (70, 73) if self.wrong_printed_pages else (100, 103)
        proposal = valid_proposal_payload()
        proposal["schedule"][0]["schedule_chapters"] = [
            {
                "title": "Vectors",
                "anchor_page_start": start,
                "anchor_page_end": end,
                "source_section_ids": [],
                "content_slices": [
                    {"page_start": start, "page_end": end, "source_section_ids": []}
                ],
            }
        ]
        decoded = _decode_learning_plan_proposal(json.dumps(proposal))
        _validate_learning_plan_proposal_refs(decoded, kwargs["study_units"], intent)
        item = decoded.schedule[0]
        return PlanModelReply(
            course_title=decoded.course_title,
            overview=decoded.overview,
            today_tasks=decoded.today_tasks,
            output_language=decoded.output_language,
            schedule=[
                PlanScheduleItem(
                    unit_id=kwargs["study_units"][0].id,
                    title=item.title,
                    focus=item.focus,
                    activity_type=item.activity_type,
                    duration_minutes=item.duration_minutes,
                    coverage_mode=item.coverage_mode,
                    workload_rationale=item.workload_rationale,
                    schedule_chapters=list(item.schedule_chapters),
                )
            ],
        )


class ProbeContainer(Container):
    def _build_model_provider(self, settings):
        return ProbeProvider()


class PlanningPhysicalPagesTests(unittest.TestCase):
    def test_http_tools_proposal_commit_labels_and_restart(self):
        with fitz.open() as pdf:
            for index in range(104):
                page = pdf.new_page()
                page.insert_text((50, 50), f"Vectors PHYSICAL{index + 1}")
                page.insert_textbox(
                    fitz.Rect(50, 80, 550, 700),
                    "\n".join(
                        f"Example {n}: Vectors have magnitude and direction. Linear maps preserve addition."
                        for n in range(20)
                    ),
                    fontsize=10,
                )
            pdf.set_toc([[1, "Vector foundations", 1]])
            pdf.set_page_labels(
                [
                    {"startpage": 0, "style": "D", "firstpagenum": 1},
                    {"startpage": 30, "style": "D", "firstpagenum": 1},
                ]
            )
            pdf_bytes = pdf.tobytes()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            settings = Settings(
                database_url=f"sqlite:///{root / 'app.db'}",
                storage_root=str(root / "data"),
                plan_provider="mock",
                auto_migrate_local_data=False,
                ocr_engine="disabled",
            )
            app = create_app(settings=settings, container_factory=ProbeContainer)
            with TestClient(app, raise_server_exceptions=False) as client:

                def ok(response):
                    self.assertEqual(response.status_code, 200, response.text[:1000])
                    return response.json()

                document = ok(
                    client.post(
                        "/documents",
                        files={"file": ("labels.pdf", pdf_bytes, "application/pdf")},
                    )
                )
                document = ok(client.post(f"/documents/{document['id']}/process"))
                labels = ok(
                    client.get(
                        f"/documents/{document['id']}/page-numbering",
                        params=[("page_numbers", 100), ("page_numbers", 103)],
                    )
                )
                self.assertEqual(
                    [p["printed_page"]["label"] for p in labels["pages"]], ["70", "73"]
                )
                self.assertEqual(
                    [p["physical_pdf_page"] for p in labels["pages"]], [100, 103]
                )
                request = {
                    "document_id": document["id"],
                    "persona_id": "mentor-aurora",
                    "objective": "Study selected pages",
                    "client_request_id": "physical-pages-http",
                    "expected_document_updated_at": document["updated_at"],
                    "planning_intent": explicit().model_dump(mode="json"),
                }
                plan = ok(client.post("/learning-plans", json=request))
                self.assertEqual(
                    plan["schedule"][0]["schedule_chapters"][0]["anchor_page_start"],
                    100,
                )
                self.assertEqual(
                    ok(client.post("/learning-plans", json=request))["id"], plan["id"]
                )
                self.assertEqual(app.state.container.model_provider.calls, 1)

                def changed(start, end, key):
                    return {
                        **request,
                        "client_request_id": key,
                        "planning_intent": {
                            **request["planning_intent"],
                            "pdf_page_ranges": {
                                "status": "user_explicit",
                                "value": [{"page_start": start, "page_end": end}],
                            },
                        },
                    }

                self.assertEqual(
                    client.post(
                        "/learning-plans", json=changed(70, 73, "physical-pages-http")
                    ).status_code,
                    409,
                )
                self.assertEqual(
                    client.post(
                        "/learning-plans", json=changed(100, 105, "outside-document")
                    ).status_code,
                    422,
                )
                self.assertEqual(app.state.container.model_provider.calls, 1)
                app.state.container.model_provider.wrong_printed_pages = True
                self.assertNotEqual(
                    client.post(
                        "/learning-plans",
                        json={**request, "client_request_id": "printed-as-physical"},
                    ).status_code,
                    200,
                )
                record = ok(client.get("/learning-plan-operations/printed-as-physical"))
                self.assertEqual(record["status"], "not_committed")
                self.assertIsNone(record["plan"])
                self.assertEqual(len(ok(client.get("/learning-plans"))["items"]), 1)
            with TestClient(create_app(settings=settings)) as client:
                restored = client.get(
                    "/learning-plan-operations/physical-pages-http"
                ).json()["plan"]
                self.assertEqual(restored["id"], plan["id"])
                self.assertEqual(
                    restored["planning_intent"], request["planning_intent"]
                )
                self.assertEqual(
                    restored["resolved_planning_intent"]["pdf_page_ranges"]["value"],
                    [{"page_start": 100, "page_end": 103}],
                )

                root = Path(__file__).resolve().parents[3]
                numbering_decoder = (
                    root / "apps/web/lib/document-page-numbering-decode.ts"
                ).as_uri()
                plan_decoder = (root / "apps/web/lib/planning-decode.ts").as_uri()
                script = f"""
                    import {{ readFileSync }} from 'node:fs';
                    import {{ decodeDocumentPageNumbering }} from {json.dumps(numbering_decoder)};
                    import {{ decodeLearningPlan }} from {json.dumps(plan_decoder)};
                    const raw = JSON.parse(readFileSync(0, 'utf8'));
                    const numbering = decodeDocumentPageNumbering(raw.labels, raw.plan.document_id, [100, 103]);
                    const plan = decodeLearningPlan(raw.plan);
                    if (numbering.pages[0].printedPage.label !== '70' || plan.schedule[0].scheduleChapters[0].anchorPageStart !== 100) throw new Error('coordinate mismatch');
                """
                decoded = subprocess.run(
                    [
                        "node",
                        "--experimental-strip-types",
                        "--input-type=module",
                        "-e",
                        script,
                    ],
                    input=json.dumps({"labels": labels, "plan": restored}),
                    text=True,
                    capture_output=True,
                    cwd=root,
                    timeout=30,
                )
                self.assertEqual(decoded.returncode, 0, decoded.stderr)

    def test_commit_boundary_rechecks_manually_built_candidate(self):
        from app.services.local_store import LocalJsonStore
        from app.services.plans import LearningPlanService
        from app.services.persona import PersonaEngine
        from app.services.study_arrangement import StudyArrangementService
        from app.persistence.document_repository import DocumentRepository
        from tests.support.planning_operations import (
            planning_document,
            planning_debug,
            planning_reply,
        )

        with TemporaryDirectory() as temp:
            store = LocalJsonStore(Path(temp))
            try:
                document = planning_document()
                document.page_count = 104
                document.study_units[0].page_end = 104
                debug = planning_debug(document)
                DocumentRepository(store.database).insert(document)
                store.save_item("document_debug", document.id, debug)
                provider = MockModelProvider()
                service = LearningPlanService(
                    store, StudyArrangementService(), provider
                )
                persona = PersonaEngine(store).require_persona("mentor-aurora")
                request = LearningPlanOperationRequestV1(
                    client_request_id="scope-candidate",
                    document_id=document.id,
                    persona_id=persona.id,
                    objective="Learn",
                    expected_document_updated_at=document.updated_at,
                    planning_intent=explicit(),
                )
                operation, _ = service.operation_repository.admit(request=request)
                reply = planning_reply(document)
                chapter = reply.schedule[0].schedule_chapters[0]
                chapter.anchor_page_start = 100
                chapter.anchor_page_end = 103
                chapter.content_slices = [
                    PlanContentSliceProposalV1(
                        page_start=100, page_end=103, source_section_ids=["raw-1"]
                    )
                ]
                with patch.object(
                    provider, "generate_learning_plan", return_value=reply
                ):
                    plan, doc, report, trace, _ = service._build_plan_candidate(
                        goal=LearningGoalInput(
                            document_id=document.id,
                            persona_id=persona.id,
                            objective="Learn",
                            planning_intent=explicit(),
                        ),
                        document=document,
                        persona_name=persona.name,
                        persona=persona,
                        debug_report=debug,
                    )
                plan.schedule[0].schedule_chapters[0].anchor_page_start = 70
                with self.assertRaises(PhysicalPageScopeViolation):
                    service.operation_repository.commit_success(
                        operation_id=operation.operation_id,
                        plan=plan,
                        document=doc,
                        debug_report=report,
                        trace=trace,
                    )
                with store.database.session() as session:
                    self.assertIsNone(session.get(LearningPlanRow, plan.id))
                    self.assertEqual(
                        session.get(
                            LearningPlanOperationRow, operation.operation_id
                        ).status,
                        "running",
                    )
            finally:
                store.close()
