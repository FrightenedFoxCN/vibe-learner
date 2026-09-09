"""Stage regression executors. No test modules, provider calls, or private data.

Only deterministic stage behavior is measured. Neural OCR/model quality and
full workflow persistence require separately reviewed suites.
"""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from app.models.domain import (
    DocumentRecord,
    DocumentSection,
    LearningGoalInput,
    PersonaSlot,
    StudyUnitRecord,
)
from app.models.scene import decode_scene_tree_proposal, project_scene_tree_proposal
from app.services.document_parser import DocumentParser
from app.models.document_processing import (
    DocumentProcessRuntimeOutputV1,
)
from app.models.persona_generation import (
    PersonaGenerationProposalV1,
)
from app.services.provider_sdk import ProviderSDK
from app.services.model_provider import (
    OpenAIModelProvider,
    PlanningProposalDecodeError,
    _decode_learning_plan_proposal,
    _validate_learning_plan_proposal_refs,
)
from app.services.ocr_engine import OcrPageResult
from app.services.persona import PersonaEngine
from app.services.study_arrangement import StudyArrangementService
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[4]


def document(document_id: str = "eval-document") -> DocumentRecord:
    return DocumentRecord(
        id=document_id,
        title="Vector Spaces",
        original_filename="synthetic.pdf",
        stored_path="",
        status="uploaded",
        ocr_status="pending",
        created_at="2026-09-09T00:00:00Z",
        updated_at="2026-09-09T00:00:00Z",
    )


def _parsed(scenario: str):
    """Generate real searchable PDF bytes, then run the production parser."""
    with TemporaryDirectory() as folder:
        path = Path(folder) / "synthetic.pdf"
        with fitz.open() as pdf:
            for i in range(2):
                page = pdf.new_page()
                page.insert_text(
                    (72, 85), ["1 Vector Spaces", "2 Linear Maps"][i], fontsize=18
                )
                for j in range(8):
                    page.insert_text(
                        (72, 125 + j * 24),
                        f"{'ALPHA' if i == 0 else 'BETA'} Example {j}: basis vectors span the space and preserve linear structure.",
                    )
            if scenario != "no_toc":
                pdf.set_toc([[1, "1 Vector Spaces", 1], [1, "2 Linear Maps", 2]])
            pdf.save(path)
        parser = DocumentParser(ocr_engine_name="disabled")
        return parser.parse(
            document_id="eval-document", title="Vector Spaces", stored_path=str(path)
        )


def _document_stage(stage: str, scenario: str) -> dict:
    report = _parsed(scenario)
    if stage == "page_extraction":
        return {
            "page_count": len(report.pages),
            "ordered": [p.page_number for p in report.pages] == [1, 2],
            "anchors": all(
                anchor in "\n".join(c.content for c in report.chunks)
                for anchor in ("ALPHA", "BETA")
            ),
            "ocr_applied": report.ocr_applied,
        }
    if stage == "section_detection":
        return {
            "nonempty": bool(report.sections),
            "bounded": all(
                1 <= s.page_start <= s.page_end <= 2 for s in report.sections
            ),
            "unique": len({s.id for s in report.sections}) == len(report.sections),
            "toc_titles": [s.title for s in report.sections]
            == ["1 Vector Spaces", "2 Linear Maps"],
        }
    if scenario == "missing_page":
        report.pages.pop()
    elif scenario == "duplicate_page":
        report.pages[1].page_number = 1
    elif scenario == "foreign_section":
        report.sections[0].document_id = "other-document"
    elif scenario == "foreign_chunk":
        report.chunks[0].section_id = "missing-section"
    elif scenario == "chunk_out_of_bounds":
        report.chunks[0].page_end = 3
    try:
        DocumentProcessRuntimeOutputV1.model_validate(
            {"debug_report": report.model_dump(mode="json"), "study_units": []}
        )
    except ValidationError:
        return {"accepted": False}
    return {"accepted": True}


def _chunks(scenario: str) -> dict:
    parser = DocumentParser(ocr_engine_name="disabled")
    sections = [
        DocumentSection(
            id="s1",
            document_id="eval-document",
            title="Vectors",
            page_start=1,
            page_end=2,
            level=1,
        )
    ]
    pages = [
        "ALPHA " + ("A vector spans a space. " * 100),
        "BETA " + ("A map preserves sums. " * 100),
    ]
    if scenario == "empty":
        pages = ["", ""]
    if scenario == "nested":
        sections.append(
            DocumentSection(
                id="s2",
                document_id="eval-document",
                title="Maps",
                page_start=2,
                page_end=2,
                level=2,
            )
        )
    if scenario == "unicode":
        pages = ["向量张成空间。" * 300, "线性映射保留加法。" * 300]
    chunks = parser._build_chunks(
        document_id="eval-document", sections=sections, page_texts=pages
    )
    joined = "".join(c.content for c in chunks)
    expected = "".join(pages)
    return {
        "nonempty": bool(chunks),
        "bounded": all(1 <= c.page_start <= c.page_end <= 2 for c in chunks),
        "unique": len({c.id for c in chunks}) == len(chunks),
        "attributed": all(c.section_id in {s.id for s in sections} for c in chunks),
        "text_preserved": "".join(joined.split()) == "".join(expected.split()),
        "counts_match": all(c.char_count == len(c.content) for c in chunks),
    }


class FixtureOcrEngine:
    engine_name = "fixture-ocr"
    model_id = "deterministic-ocr-result-v1"

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def extract_page_text(self, page):
        self.calls += 1
        return self.result


def _ocr(scenario: str) -> dict:
    parser = DocumentParser(ocr_engine_name="disabled")
    text = "ALPHA " + ("A vector spans the space. " * 20)
    engine = FixtureOcrEngine(
        OcrPageResult(
            text=text if scenario in {"gain", "no_gain", "text_bypass"} else "",
            status="completed"
            if scenario in {"gain", "no_gain", "text_bypass"}
            else scenario,
            engine_name="fixture-ocr",
        )
    )
    parser.ocr_engine = engine
    with fitz.open() as pdf:
        page = pdf.new_page()
        if scenario in {"no_gain", "text_bypass"}:
            for i in range(15):
                page.insert_text(
                    (72, 72 + i * 20),
                    "Original native text remains available and contains more information.",
                )
        result = parser._parse_page(
            page_number=1, page=page, force_ocr=scenario != "text_bypass"
        )
    return {
        "used_ocr": result.used_ocr,
        "calls": engine.calls,
        "source": result.extraction_source,
        "has_text": bool(result.line_entries),
        "warned": any(
            w.code in {"ocr_failed", "ocr_unavailable"} for w in result.warnings
        ),
    }


def _cleanup(scenario: str) -> dict:
    report = _parsed("standard")
    if scenario == "no_sections":
        report.sections = []
    elif scenario == "backmatter":
        report.sections[-1].title = "References"
    doc = document()
    doc.page_count = 2
    doc.sections = report.sections
    units = StudyArrangementService().build_study_units(
        document=doc, debug_report=report
    )
    allowed = {s.id for s in report.sections}
    return {
        "nonempty": bool(units),
        "bounded": all(1 <= u.page_start <= u.page_end <= 2 for u in units),
        "attributed": all(
            u.document_id == doc.id
            and all(
                s in allowed or s.startswith(doc.id + ":study-anchor:")
                for s in u.source_section_ids
            )
            for u in units
        ),
        "backmatter_excluded": all(
            not u.include_in_plan for u in units if u.unit_kind == "backmatter"
        ),
    }


def _plan(payload: dict) -> dict:
    scenario = payload["scenario"]
    if scenario == "goal_only":
        plan = StudyArrangementService().build_goal_only_plan(
            goal=LearningGoalInput(
                persona_id="mentor", objective="Understand vectors, then linear maps."
            ),
            base_document_id="goal",
            persona_name="Tutor",
        )
        return {
            "accepted": True,
            "grounded": bool(plan.study_units)
            and all(
                s.unit_id in {u.id for u in plan.study_units} for s in plan.schedule
            ),
        }
    try:
        proposal = _decode_learning_plan_proposal(json.dumps(payload["input"]))
        unit = StudyUnitRecord(
            id="u1",
            document_id="eval-document",
            title="Vectors",
            page_start=1,
            page_end=2,
            source_section_ids=["s1"],
            summary="Vector basis",
        )
        _validate_learning_plan_proposal_refs(proposal, [unit])
    except PlanningProposalDecodeError:
        return {"accepted": False, "grounded": False}
    return {"accepted": True, "grounded": True}


class FixtureSettingProvider(OpenAIModelProvider):
    """Exercise real bounded decode/repair, replacing only network transport."""

    def __init__(self, responses):
        self.responses = responses
        self.fixture_calls = 0
        super().__init__(
            api_key="synthetic-not-a-credential",
            base_url="https://example.invalid/v1",
            plan_model="fixture",
            setting_model="fixture",
            timeout_seconds=1,
            sdk=ProviderSDK(completion=self._fixture_completion),
        )

    def _fixture_completion(self, **kwargs):
        if self.fixture_calls >= len(self.responses):
            raise RuntimeError("stage_eval_transport_budget_exceeded")
        response = self.responses[self.fixture_calls]
        self.fixture_calls += 1
        return {
            "choices": [
                {"finish_reason": "stop", "message": {"content": json.dumps(response)}}
            ]
        }


def _persona(payload: dict) -> dict:
    scenario = payload["scenario"]
    if scenario.startswith("fallback_"):
        slot = PersonaSlot.model_validate(payload["input"])
        engine = PersonaEngine()
        once = engine.assist_slot(
            name="Synthetic tutor",
            summary="Evidence teacher",
            slot=slot,
            rewrite_strength=0.3,
        )
        twice = engine.assist_slot(
            name="Synthetic tutor",
            summary="Evidence teacher",
            slot=once,
            rewrite_strength=0.3,
        )
        return {
            "idempotent": once == twice,
            "controls_preserved": (once.kind, once.weight, once.locked, once.sort_order)
            == (slot.kind, slot.weight, slot.locked, slot.sort_order),
            "unchanged": once == slot,
        }
    if scenario in {"structured_repair", "exhausted_repair", "provider_controls"}:
        slot = PersonaSlot(
            kind="teaching_method",
            label="Method",
            content="Observe.",
            weight=73,
            sort_order=20,
        )
        valid = {
            "slot": {
                "kind": "wrong-kind",
                "label": "Method",
                "content": "Observe then compare.",
                "weight": 1.0,
                "locked": True,
                "sort_order": 0,
            }
        }
        invalid = {
            "slot": {"kind": "teaching_method", "label": "Method", "content": 17}
        }
        responses = (
            [valid]
            if scenario == "provider_controls"
            else [invalid, valid]
            if scenario == "structured_repair"
            else [invalid, invalid]
        )
        provider = FixtureSettingProvider(responses)
        try:
            output = provider.assist_persona_slot(
                name="Synthetic", summary="Tutor", slot=slot, rewrite_strength=0.3
            )["slot"]
        except RuntimeError as exc:
            if str(exc) != "setting_model_invalid_payload":
                raise
            return {
                "accepted": False,
                "fixture_calls": provider.fixture_calls,
                "controls_preserved": False,
            }
        return {
            "accepted": True,
            "fixture_calls": provider.fixture_calls,
            "controls_preserved": output["kind"] == slot.kind
            and output["weight"] == slot.weight
            and output["locked"] == slot.locked
            and output["sort_order"] == slot.sort_order,
        }
    try:
        PersonaGenerationProposalV1.model_validate(payload["input"])
    except ValidationError:
        return {"accepted": False}
    return {"accepted": True}


def _scene(payload: dict) -> dict:
    try:
        proposal = decode_scene_tree_proposal(copy.deepcopy(payload["input"]))
        projection = project_scene_tree_proposal(proposal, allowed_reusable_nodes={})
    except ValueError as exc:
        if str(exc) != "scene_reusable_node_ref_not_allowed":
            raise
        return {"accepted": False}
    except RuntimeError as exc:
        if not str(exc).startswith(
            ("setting_scene_proposal_invalid:", "setting_scene_reuse_")
        ):
            raise
        return {"accepted": False}
    ids = []

    def visit(layers):
        for layer in layers:
            ids.append(layer.id)
            ids.extend(o.id for o in layer.objects)
            visit(layer.children)

    visit(projection.scene_layers)
    return {
        "accepted": True,
        "application_ids": bool(ids) and len(set(ids)) == len(ids),
    }


def execute_stage(stage: str, payload: dict) -> dict:
    scenario = payload["scenario"]
    if stage in {"document_parse", "page_extraction", "section_detection"}:
        return _document_stage(stage, scenario)
    if stage == "chunk_building":
        return _chunks(scenario)
    if stage == "ocr_page":
        return _ocr(scenario)
    if stage == "study_unit_cleanup":
        return _cleanup(scenario)
    if stage == "plan_generation":
        return _plan(payload)
    if stage == "persona_generation":
        return _persona(payload)
    if stage == "scene_generation":
        return _scene(payload)
    if stage == "response_decode":
        result = subprocess.run(
            [
                "node",
                "--experimental-strip-types",
                str(ROOT / "apps/web/scripts/harness-stage-decode.ts"),
            ],
            input=json.dumps(payload["input"]),
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
        return json.loads(result.stdout)
    raise ValueError("stage_eval_unknown_stage")
