"""Developer regression for confirmed Study Unit projection, without provider calls."""

from __future__ import annotations

import json
from uuid import uuid4

from app.models.api import LearningPlanCreateRequest
from app.models.domain import DocumentDebugRecord, DocumentRecord, StudyUnitRecord
from app.models.harness import HarnessContractRef, canonical_harness_digest
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.study_unit_revision import (
    StudyUnitRevisionPreviewV1,
    StudyUnitSuggestionsV1,
    apply_unit_suggestions,
)
from app.persistence.document_repository import DocumentRepository
from app.persistence.study_unit_revision_repository import StudyUnitRevisionRepository
from app.services.harness_stage_evals import (
    ROOT,
    StageAuthority,
    build_harness_stage_runner,
    close_stage_runner,
    gate_execution,
)
from app.services.model_provider import MockModelProvider
from app.services.persona import PersonaEngine
from app.services.plans import LearningPlanService
from app.services.study_arrangement import StudyArrangementService

SUITE = HarnessContractRef(
    name="study_unit_revision_regression", version="study-unit-revision-regression-v1"
)
CATALOG = (
    ROOT / "packages/shared/fixtures/harness/study-unit-revision-regression-v1.json"
)


def fixture():
    unit = StudyUnitRecord(
        id="saved-unit",
        document_id="revision-eval-doc",
        title="Saved unit",
        page_start=1,
        page_end=10,
    )
    document = DocumentRecord(
        id=unit.document_id,
        title="Textbook",
        original_filename="synthetic.pdf",
        stored_path="",
        status="processed",
        ocr_status="not_required",
        created_at="2026-10-29T00:00:00Z",
        updated_at="2026-10-29T00:00:00Z",
        study_units=[unit],
        study_unit_count=1,
        page_count=10,
        debug_ready=True,
    )
    debug = DocumentDebugRecord(
        document_id=document.id,
        parser_name="synthetic",
        processed_at=document.updated_at,
        page_count=10,
        total_characters=0,
        extraction_method="text",
        study_units=[unit],
        pages=[],
        sections=[],
        chunks=[],
        warnings=[],
        dominant_language_hint="en",
    )
    return document, debug


def suggestions():
    return {"study_units": [{"title": "Revised unit", "page_start": 1, "page_end": 10}]}


class _PreviewProvider(MockModelProvider):
    def generate_learning_plan(self, **kwargs):
        reply = super().generate_learning_plan(**kwargs)
        reply.study_unit_suggestions = StudyUnitSuggestionsV1.model_validate(
            suggestions()
        )
        return reply


class RevisionAuthority(StageAuthority):
    def __init__(self, store):
        super().__init__(store)
        self.revisions = StudyUnitRevisionRepository(store.database)

    def admit(self, **_):
        document, debug = fixture()
        document.id += "-" + uuid4().hex
        for unit in document.study_units:
            unit.document_id = document.id
        debug.document_id = document.id
        debug.study_units = document.study_units
        DocumentRepository(self.store.database).insert(document)
        self.store.save_item("document_debug", document.id, debug)
        persona = PersonaEngine(self.store).require_persona("mentor-aurora")
        service = LearningPlanService(
            self.store, StudyArrangementService(), _PreviewProvider()
        )
        plan = service.create_plan(
            goal=LearningPlanCreateRequest(
                document_id=document.id,
                persona_id=persona.id,
                objective="Review saved unit",
                client_request_id="eval-" + uuid4().hex,
                expected_document_updated_at=document.updated_at,
            ),
            document=document,
            debug_report=debug,
            persona=persona,
            persona_name=persona.name,
        )
        preview = self.revisions.get(plan.id).preview
        return self.revisions.bindings.require_domain(
            domain_operation_kind=HarnessDomainOperationKind.STUDY_UNIT_REVISION,
            domain_operation_id=preview.operation_id,
        )

    def finish(self, binding, success):
        # The measured stage is projection only; no acceptance commit is claimed.
        from app.persistence.models import StudyUnitRevisionOperationRow

        with self.store.database.session() as session:
            row = session.get(
                StudyUnitRevisionOperationRow, binding.domain_operation_id
            )
            plan_id = row.plan_id
        self.revisions.reject(plan_id, binding.domain_operation_id)


def execute_revision(stage, payload):
    if stage != "study_unit_revision":
        raise ValueError("study_unit_revision_eval_stage_mismatch")
    document, debug = fixture()
    raw = suggestions()
    scenario = payload["scenario"]
    if scenario == "split":
        raw["study_units"] = [
            {"title": "First", "page_start": 1, "page_end": 5},
            {"title": "Second", "page_start": 6, "page_end": 10},
        ]
    elif scenario == "exclude_front_matter":
        raw["study_units"] = [
            {
                "title": "Preface",
                "page_start": 1,
                "page_end": 2,
                "unit_kind": "front_matter",
                "include_in_plan": False,
            },
            {"title": "Chapter", "page_start": 3, "page_end": 10},
        ]
    elif scenario == "overlap":
        raw["study_units"].append({"title": "Overlap", "page_start": 9, "page_end": 10})
    elif scenario == "outside_document":
        raw["study_units"][0]["page_end"] = 11
    elif scenario == "owned_id":
        raw["study_units"][0]["id"] = "model-owned"
    elif scenario == "no_plannable":
        raw["study_units"][0]["include_in_plan"] = False
    elif scenario == "blank_title":
        raw["study_units"][0]["title"] = "  "
    elif scenario != "retain_identity":
        raise ValueError("study_unit_revision_eval_scenario_unknown")
    try:
        preview = StudyUnitRevisionPreviewV1(
            operation_id="eval-unit-revision",
            parent_operation_id="eval-parent",
            plan_id="eval-plan",
            base_document=document,
            base_debug_digest=canonical_harness_digest(debug),
            suggestions=StudyUnitSuggestionsV1.model_validate(raw),
        )
        output = apply_unit_suggestions(preview, debug, "2026-10-29T01:00:00Z")
    except ValueError:
        return {"accepted": False}
    return {
        "accepted": True,
        "revision_advanced_once": output.document.revision == document.revision + 1,
        "base_unchanged": document.study_units[0].title == "Saved unit"
        and document.revision == 0,
        "debug_matches": output.document.study_units == output.debug_report.study_units,
        "identity_retained": output.document.study_units[0].id
        == document.study_units[0].id,
        "excluded_from_sections": all(
            unit.include_in_plan
            for unit in output.document.study_units
            if any(section.id == unit.id for section in output.document.sections)
        ),
    }


def build_study_unit_revision_runner():
    return build_harness_stage_runner(
        catalog_path=CATALOG,
        suites={"planning:study_unit_revision": SUITE},
        authority_factory=RevisionAuthority,
        execute_case=execute_revision,
    )


def main():
    runner = build_study_unit_revision_runner()
    try:
        execution = runner.run(
            runner.stage_runs[SUITE.name],
            runner.stage_cases[SUITE.name],
            selected_suites=[SUITE],
            release_gate=True,
            deterministic_gate=True,
        )
        passed = gate_execution(execution, 8)
        print(
            json.dumps(
                {
                    "suite": SUITE.name,
                    "samples": len(execution.raw_samples),
                    "gate": "passed" if passed else "failed",
                    "failures": [
                        failure.failure_code
                        for sample in execution.raw_samples
                        for failure in sample.failures
                    ],
                }
            )
        )
        return 0 if passed else 1
    finally:
        close_stage_runner(runner)


if __name__ == "__main__":
    raise SystemExit(main())
