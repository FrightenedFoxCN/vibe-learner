from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from sqlalchemy import text

from app.models.harness import HarnessArtifactType, HarnessStage, canonical_harness_digest
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.models.planning import LearningPlanOperationRequestV1, LearningPlanOperationStatus
from app.services.documents import DocumentService
from app.models.domain import DocumentSection
from app.models.document_processing import (
    DocumentProcessInputManifest,
    DocumentProcessRuntimeOutputV1,
    DocumentStageEvidenceV1,
    DocumentStageInputManifest,
)
from app.models.planning_runtime import (
    LearningPlanInputManifest,
    LearningPlanRuntimeOutputV1,
    PlanningToolExecutionEvidenceV1,
    PlanningToolExecutionInputManifest,
)
from app.models.persona_generation import (
    PersonaGenerationInputManifest,
    PersonaGenerationProposalV1,
    PersonaSlotContentProposalV1,
)
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.persona import PersonaEngine
from app.services.plans import LearningPlanService
from app.services.study_arrangement import StudyArrangementService
from tests import test_document_process_operation as document_fixtures
from tests.test_document_process_operation import (
    _FakeArrangement,
    _FakeParser,
    _debug_report,
)
from tests.test_learning_plan_operation import _debug, _document, _goal_for, _reply


class HarnessBroadCommitBindingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp.name))
        self.documents = DocumentService(self.store, _FakeParser(), _FakeArrangement())
        self.provider = MockModelProvider()
        self.plans = LearningPlanService(
            self.store, StudyArrangementService(), self.provider
        )
        self.persona = PersonaEngine(self.store).require_persona("mentor-aurora")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def _snapshot(self):
        tables = (
            "documents", "document_debug_records", "document_process_operations",
            "learning_plans", "planning_traces", "learning_plan_operations",
            "harness_runtime_executions",
        )
        with self.store.database.engine.connect() as connection:
            return {
                table: [tuple(row) for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY 1"))]
                for table in tables
            }

    def _prepare_document(self, name):
        document = document_fixtures.DocumentProcessOperationTests._create_document(self.documents, f"{name}.pdf")
        operation, document = self.documents.process_repository.admit(
            document_id=document.id, force_ocr=False
        )
        binding = self.documents.process_repository.require_harness_operation(operation.operation_id)
        output = DocumentProcessRuntimeOutputV1(
            debug_report=_debug_report(document.id), study_units=[]
        )
        prepared, runtime = self.documents.harness_service.prepare_document(
            operation_binding=binding,
            manifest=DocumentProcessInputManifest(document_id=document.id, force_ocr=False),
            protected_input={"document": document.model_dump(mode="json")},
            generate=lambda _: output,
        )
        report = output.debug_report.model_copy(deep=True)
        document.status = "processed"
        document.ocr_status = report.ocr_status
        document.study_units = []
        document.sections = []
        document.study_unit_count = 0
        document.page_count = report.page_count
        document.chunk_count = len(report.chunks)
        document.preview_excerpt = report.pages[0].text_preview
        document.debug_ready = True
        return operation, document, report, prepared, runtime

    def _commit_document(self, case, *, prepared=None, document=None, report=None):
        operation, expected_document, expected_report, expected_prepared, runtime = case
        return self.documents.process_repository.commit_success(
            operation_id=operation.operation_id,
            document=document or expected_document,
            debug_report=report or expected_report,
            harness_runtime=runtime,
            runtime_prepared=prepared or expected_prepared,
        )

    def _prepare_plan(self, name):
        document = _document(document_id=f"doc-{name}")
        debug = _debug(document)
        existing = self.store.load_list("documents", type(document))
        self.store.save_list("documents", [*existing, document])
        self.store.save_item("document_debug", document.id, debug)
        goal = _goal_for(document, f"request-{name}", self.persona.id)
        operation, _ = self.plans.operation_repository.admit(
            request=LearningPlanOperationRequestV1(
                client_request_id=goal.client_request_id,
                document_id=document.id,
                persona_id=self.persona.id,
                objective=goal.objective,
                expected_document_updated_at=document.updated_at,
            )
        )
        binding = self.plans.operation_repository.require_harness_operation(operation.operation_id)
        with patch.object(self.provider, "generate_learning_plan", return_value=_reply(document)):
            candidate = self.plans._build_plan_candidate(
                goal=goal, document=document.model_copy(deep=True),
                persona_name=self.persona.name, persona=self.persona,
                debug_report=debug.model_copy(deep=True),
            )
        output = LearningPlanRuntimeOutputV1(
            plan=candidate[0], document=candidate[1], debug_report=candidate[2], trace=candidate[3]
        )
        prepared, runtime = self.plans.harness_service.prepare_plan(
            operation_binding=binding,
            manifest=LearningPlanInputManifest(
                client_request_id=goal.client_request_id, document_id=document.id,
                persona_id=self.persona.id, creation_mode="document",
            ),
            protected_input={"goal": goal.model_dump(mode="json")},
            generate=lambda _: output,
        )
        return operation, output, prepared, runtime

    def _commit_plan(self, case, *, prepared=None, output=None):
        operation, expected_output, expected_prepared, runtime = case
        output = output or expected_output
        return self.plans.operation_repository.commit_success(
            operation_id=operation.operation_id, plan=output.plan,
            document=output.document, debug_report=output.debug_report, trace=output.trace,
            harness_runtime=runtime, runtime_prepared=prepared or expected_prepared,
        )

    def test_document_cross_operation_commit_and_failure_are_zero_write(self):
        first = self._prepare_document("first")
        second = self._prepare_document("second")
        before = self._snapshot()
        with self.assertRaisesRegex(ValueError, "runtime_binding_mismatch"):
            self._commit_document(second, prepared=first[3])
        self.assertEqual(before, self._snapshot())
        with self.assertRaisesRegex(ValueError, "runtime_binding_mismatch"):
            self.documents.process_repository.mark_failed(
                operation_id=second[0].operation_id, error_code="injected_failure",
                harness_runtime=first[4], runtime_prepared=first[3],
            )
        self.assertEqual(before, self._snapshot())

    def test_document_replaced_output_or_projection_is_zero_write(self):
        case = self._prepare_document("replacement")
        original = case[3]
        altered = original.output.model_copy(deep=True)
        altered.debug_report.chunks[0].content = "unvalidated replacement"
        before = self._snapshot()
        for digest in (original.output_digest, canonical_harness_digest(altered)):
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, "runtime_output_mismatch"):
                self._commit_document(case, prepared=replace(original, output=altered, output_digest=digest))
            self.assertEqual(before, self._snapshot())
        with self.assertRaisesRegex(ValueError, "runtime_projection_mismatch"):
            self._commit_document(case, report=altered.debug_report)
        self.assertEqual(before, self._snapshot())
        altered_document = case[1].model_copy(update={"stored_path": "/unvalidated/source.pdf"})
        with self.assertRaisesRegex(ValueError, "runtime_projection_mismatch"):
            self._commit_document(case, document=altered_document)
        self.assertEqual(before, self._snapshot())
        self.assertEqual(self._commit_document(case).status.value, "committed")

    def test_plan_cross_operation_commit_and_failure_are_zero_write(self):
        first = self._prepare_plan("first-plan")
        second = self._prepare_plan("second-plan")
        before = self._snapshot()
        with self.assertRaisesRegex(ValueError, "runtime_binding_mismatch"):
            self._commit_plan(second, prepared=first[2])
        self.assertEqual(before, self._snapshot())
        with self.assertRaisesRegex(ValueError, "runtime_binding_mismatch"):
            self.plans.operation_repository.mark_terminal(
                operation_id=second[0].operation_id, status=LearningPlanOperationStatus.NOT_COMMITTED,
                error_code="injected_failure", harness_runtime=first[3], runtime_prepared=first[2],
            )
        self.assertEqual(before, self._snapshot())

    def test_plan_replaced_output_or_projection_is_zero_write(self):
        case = self._prepare_plan("replacement-plan")
        original = case[2]
        altered = original.output.model_copy(deep=True)
        altered.plan.overview = "unvalidated replacement"
        before = self._snapshot()
        for digest in (original.output_digest, canonical_harness_digest(altered)):
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, "runtime_output_mismatch"):
                self._commit_plan(case, prepared=replace(original, output=altered, output_digest=digest))
            self.assertEqual(before, self._snapshot())
        for field in ("plan", "document", "debug_report", "trace"):
            changed = original.output.model_copy(deep=True)
            item = getattr(changed, field)
            if field == "plan":
                item.overview = "changed"
            elif field == "document":
                item.preview_excerpt = "changed"
            elif field == "debug_report":
                item.total_characters += 1
            else:
                item.model = "changed"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "runtime_projection_mismatch"):
                self._commit_plan(case, output=changed)
            self.assertEqual(before, self._snapshot())
        self.assertEqual(self._commit_plan(case).status.value, "committed")

    def test_persona_local_fallback_emits_repaired_trace_evidence(self):
        proposal = PersonaGenerationProposalV1(
            request_kind="setting_assist",
            slots=[
                PersonaSlotContentProposalV1(
                    kind="custom-tone",
                    label="Tone",
                    content="Patient",
                    weight=1,
                    locked=False,
                    sort_order=0,
                )
            ],
            system_prompt_suggestion="Stay grounded.",
            recovery_strategy="local_fallback",
        )
        generated, trace = self.documents.harness_service.run_persona(
            manifest=PersonaGenerationInputManifest(
                request_kind="setting_assist",
                mode="keywords",
                requested_count=1,
                input_char_count=8,
            ),
            protected_input={"mode": "keywords", "input_text": "mentor"},
            generate=lambda _: proposal,
        )
        self.assertEqual(generated.recovery_strategy, "local_fallback")
        self.assertEqual(trace.status.value, "repaired")
        self.assertTrue(any(item.status.value == "warning" for item in trace.checks))

    def test_current_structured_retry_is_repaired_but_prior_recovery_is_not(self):
        from app.services.model_recovery import record_model_recovery, reset_model_recovery_state

        proposal = PersonaGenerationProposalV1(
            request_kind="slot_assist",
            slot=PersonaSlotContentProposalV1(kind="custom", label="Tone", content="Patient"),
        )
        def generate(_):
            record_model_recovery(category="semantic_retry", reason="setting_model_invalid_payload", strategy="retry_structured_json", attempts=2)
            return proposal

        reset_model_recovery_state()
        try:
            for callback, expected in ((generate, "repaired"), (lambda _: proposal, "passed")):
                _, trace = self.documents.harness_service.run_persona(
                    manifest=PersonaGenerationInputManifest(request_kind="slot_assist", mode="assist", requested_count=1, input_char_count=8),
                    protected_input={"synthetic": "patient"},
                    generate=callback,
                )
                self.assertEqual(trace.status.value, expected)
        finally:
            reset_model_recovery_state()

    def test_document_child_stage_trace_is_fenced_to_parent(self):
        operation, document, report, prepared, _runtime = self._prepare_document("child-stage")
        binding = self.documents.process_repository.require_harness_operation(operation.operation_id)
        trace = self.documents.harness_service.emit_document_stage_evidence(
            operation_binding=binding,
            parent_trace_id=prepared.execution.trace_id,
            stage=HarnessStage.PAGE_EXTRACTION,
            trace_slot=1,
            input_manifest=DocumentStageInputManifest(
                document_id=document.id,
                stage="page_extraction",
                item_count=report.page_count,
            ),
            evidence=DocumentStageEvidenceV1(
                stage="page_extraction",
                outcome="passed",
                item_count=report.page_count,
                warning_count=len(report.warnings),
                source_digest=canonical_harness_digest(
                    [item.model_dump(mode="json") for item in report.pages]
                ),
            ),
            artifact_type=HarnessArtifactType.DOCUMENT_UPLOAD,
        )
        self.assertEqual(trace.stage, HarnessStage.PAGE_EXTRACTION)
        self.assertEqual(trace.parent_trace_id, prepared.execution.trace_id)
        traces = HarnessRuntimeRepository(self.store.database).list_operation_traces(
            binding.harness_operation_id
        )
        self.assertEqual([item.stage for item in traces], [HarnessStage.DOCUMENT_PARSE, HarnessStage.PAGE_EXTRACTION])

    def test_failed_child_stage_trace_is_terminally_failed(self):
        operation, document, report, prepared, _runtime = self._prepare_document("child-stage-failed")
        binding = self.documents.process_repository.require_harness_operation(operation.operation_id)
        trace = self.documents.harness_service.emit_document_stage_evidence(
            operation_binding=binding,
            parent_trace_id=prepared.execution.trace_id,
            stage=HarnessStage.PAGE_EXTRACTION,
            trace_slot=1,
            input_manifest=DocumentStageInputManifest(
                document_id=document.id,
                stage="page_extraction",
                item_count=report.page_count,
            ),
            evidence=DocumentStageEvidenceV1(
                stage="page_extraction",
                outcome="failed",
                item_count=report.page_count,
                warning_count=0,
                source_digest=canonical_harness_digest(
                    [item.model_dump(mode="json") for item in report.pages]
                ),
            ),
            artifact_type=HarnessArtifactType.DOCUMENT_UPLOAD,
        )
        self.assertEqual(trace.status.value, "failed")
        self.assertTrue(any(item.status.value == "failed" for item in trace.checks))

    def test_document_runtime_output_rejects_malformed_section_bounds(self):
        report = _debug_report("doc-bounds")
        report.sections = [
            DocumentSection(
                id="doc-bounds:section:1",
                document_id="doc-bounds",
                title="Chapter 1",
                page_start=0,
                page_end=1,
                level=1,
            )
        ]
        with self.assertRaises(ValueError):
            DocumentProcessRuntimeOutputV1(debug_report=report, study_units=[])

    def test_planning_tool_stage_trace_records_validated_result_digest(self):
        operation, output, prepared, _runtime = self._prepare_plan("tool-stage")
        binding = self.plans.operation_repository.require_harness_operation(operation.operation_id)
        arguments_json = '{"unit_id":"doc-tool:study-unit:1"}'
        result_json = '{"ok":true,"tool_name":"get_study_unit_detail"}'
        trace = self.plans.harness_service.emit_planning_tool_evidence(
            operation_binding=binding,
            parent_trace_id=prepared.execution.trace_id,
            trace_slot=1,
            input_manifest=PlanningToolExecutionInputManifest(
                document_id=output.plan.document_id,
                tool_name="get_study_unit_detail",
                tool_call_id="tool-call-fixture",
            ),
            evidence=PlanningToolExecutionEvidenceV1(
                tool_name="get_study_unit_detail",
                tool_call_id="tool-call-fixture",
                result_contract_version="planning-tool-result-v1",
                arguments_digest=canonical_harness_digest(arguments_json),
                result_digest=canonical_harness_digest({"ok": True, "tool_name": "get_study_unit_detail"}),
                outcome="validated",
            ),
            protected_input={
                "arguments_json": arguments_json,
                "result_json": result_json,
            },
        )
        self.assertEqual(trace.stage, HarnessStage.PLANNING_TOOL_EXECUTION)
        self.assertEqual(trace.parent_trace_id, prepared.execution.trace_id)


if __name__ == "__main__":
    unittest.main()
