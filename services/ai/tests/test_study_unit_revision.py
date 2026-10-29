import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.models.study_unit_revision import StudyUnitSuggestionsV1
from app.persistence.document_repository import DocumentRepository
from app.persistence.study_unit_revision_repository import StudyUnitRevisionRepository
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.persona import PersonaEngine
from app.services.plans import LearningPlanService
from app.services.study_arrangement import StudyArrangementService
from app.services.study_unit_revision import StudyUnitRevisionService
from tests.support.planning_operations import (
    planning_debug,
    planning_document,
    planning_goal,
    planning_reply,
)


class StudyUnitRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp.name))
        self.document = planning_document()
        self.debug = planning_debug(self.document)
        DocumentRepository(self.store.database).insert(self.document)
        self.store.save_item("document_debug", self.document.id, self.debug)
        self.persona = PersonaEngine(self.store).require_persona("mentor-aurora")
        self.provider = MockModelProvider()
        self.plans = LearningPlanService(
            self.store, StudyArrangementService(), self.provider
        )
        self.repository = StudyUnitRevisionRepository(self.store.database)
        self.service = StudyUnitRevisionService(
            self.repository, self.plans.harness_service, self.store
        )

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def preview(self, request_id="unit-revision-source"):
        reply = planning_reply(self.document)
        reply.study_unit_suggestions = StudyUnitSuggestionsV1.model_validate(
            {
                "rationale": "Separate definitions from applications",
                "study_units": [
                    {"title": "Definitions", "page_start": 1, "page_end": 5},
                    {"title": "Applications", "page_start": 6, "page_end": 12},
                ],
            }
        )
        with patch.object(self.provider, "generate_learning_plan", return_value=reply):
            plan = self.plans.create_plan(
                goal=planning_goal(self.document, request_id, self.persona.id),
                document=self.document.model_copy(deep=True),
                persona_name=self.persona.name,
                persona=self.persona,
                debug_report=self.debug.model_copy(deep=True),
            )
        return plan, self.repository.get(plan.id)

    def test_suggestions_do_not_change_document_or_conservative_plan_until_confirmed(
        self,
    ):
        plan, record = self.preview()
        self.assertEqual(plan.study_units, self.document.study_units)
        self.assertEqual(
            DocumentRepository(self.store.database).get(self.document.id), self.document
        )
        self.assertEqual(
            self.store.load_item("document_debug", self.document.id, type(self.debug)),
            self.debug,
        )
        accepted = self.service.decide(plan.id, record.preview.operation_id, "accept")
        self.assertEqual(accepted.status, "accepted")
        self.assertEqual(accepted.result.revision, self.document.revision + 1)
        self.assertEqual(accepted.planning_context_revision, accepted.result.revision)
        self.assertEqual(
            [unit.title for unit in accepted.result.study_units],
            ["Definitions", "Applications"],
        )
        self.assertEqual(
            DocumentRepository(self.store.database).get(self.document.id),
            accepted.result,
        )
        self.assertEqual(
            self.service.decide(plan.id, record.preview.operation_id, "accept"),
            accepted,
        )

    def test_reject_is_idempotent_and_keeps_all_projections(self):
        from fastapi import HTTPException

        plan, record = self.preview()
        rejected = self.service.decide(plan.id, record.preview.operation_id, "reject")
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(
            self.service.decide(plan.id, record.preview.operation_id, "reject"),
            rejected,
        )
        with self.assertRaises(HTTPException):
            self.service.decide(plan.id, record.preview.operation_id, "accept")
        self.assertEqual(
            DocumentRepository(self.store.database).get(self.document.id), self.document
        )
        self.assertEqual(
            self.store.load_item("document_debug", self.document.id, type(self.debug)),
            self.debug,
        )

    def test_document_or_debug_change_prevents_acceptance(self):
        from app.persistence.models import DocumentDebugRow

        for target in ("document", "debug"):
            with self.subTest(target=target):
                # Each branch needs an independently admitted parent operation.
                if target == "debug":
                    self.tearDown()
                    self.setUp()
                plan, record = self.preview()
                if target == "document":
                    DocumentRepository(self.store.database).rename_study_unit(
                        document_id=self.document.id,
                        study_unit_id=self.document.study_units[0].id,
                        title="Concurrent edit",
                        expected_revision=self.document.revision,
                    )
                else:
                    with self.store.database.session() as session:
                        row = session.get(DocumentDebugRow, self.document.id)
                        row.payload = {**row.payload, "parser_name": "changed-parser"}
                before = DocumentRepository(self.store.database).get_with_debug(
                    self.document.id
                )
                result = self.service.decide(
                    plan.id, record.preview.operation_id, "accept"
                )
                self.assertEqual(result.status, "conflict")
                self.assertEqual(
                    DocumentRepository(self.store.database).get_with_debug(
                        self.document.id
                    ),
                    before,
                )

    def test_commit_faults_roll_back_document_debug_receipt_and_trace(self):
        from app.persistence.models import (
            HarnessRuntimeExecutionRow,
            StudyUnitRevisionOperationRow,
        )
        from sqlalchemy import select

        for stage in (
            "after_document_projection",
            "after_debug_projection",
            "before_terminal_commit",
        ):
            with self.subTest(stage=stage):
                if stage != "after_document_projection":
                    self.tearDown()
                    self.setUp()
                plan, record = self.preview()

                def fail(at):
                    if at == stage:
                        raise RuntimeError("injected_transaction_failure")

                self.repository.fault_injector = fail
                with self.assertLogs("app.services.study_unit_revision", level="ERROR"):
                    result = self.service.decide(
                        plan.id, record.preview.operation_id, "accept"
                    )
                self.assertEqual(result.status, "failed")
                self.assertEqual(
                    DocumentRepository(self.store.database).get_with_debug(
                        self.document.id
                    ),
                    (self.document, self.debug),
                )
                with self.store.database.session() as session:
                    row = session.get(
                        StudyUnitRevisionOperationRow, record.preview.operation_id
                    )
                    self.assertIsNone(row.decision_receipt)
                    runtime = session.scalar(
                        select(HarnessRuntimeExecutionRow).where(
                            HarnessRuntimeExecutionRow.harness_operation_id
                            == row.harness_operation_id
                        )
                    )
                    self.assertEqual(runtime.state, "terminal")
                    self.assertEqual(
                        runtime.terminal_trace["commit_evidence"]["status"],
                        "not_committed",
                    )

    def test_accept_and_reject_race_have_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        from fastapi import HTTPException

        plan, record = self.preview()
        barrier = Barrier(2)

        def decide(action):
            barrier.wait()
            try:
                return self.service.decide(
                    plan.id, record.preview.operation_id, action
                ).status
            except HTTPException as exc:
                return exc.status_code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, ("accept", "reject")))
        result = self.repository.get(plan.id)
        self.assertIn(result.status, {"accepted", "rejected"}, results)
        current = DocumentRepository(self.store.database).get(self.document.id)
        self.assertEqual(
            current.revision, self.document.revision + (result.status == "accepted")
        )
        self.assertEqual(result.result is not None, result.status == "accepted")

    def test_accept_read_back_survives_restart_and_does_not_replay(self):
        plan, record = self.preview()
        accepted = self.service.decide(plan.id, record.preview.operation_id, "accept")
        self.store.close()
        self.store = LocalJsonStore(Path(self.temp.name))
        restarted = StudyUnitRevisionRepository(self.store.database)
        self.assertEqual(restarted.get(plan.id), accepted)
        current, debug = DocumentRepository(self.store.database).get_with_debug(
            self.document.id
        )
        self.assertEqual(current.revision, accepted.planning_context_revision)
        self.assertEqual(current.study_units, debug.study_units)

    def test_query_times_out_interrupted_acceptance_and_fences_late_commit(self):
        from datetime import datetime, timedelta, timezone

        from app.persistence.models import StudyUnitRevisionOperationRow
        from fastapi import HTTPException

        plan, record = self.preview()
        with patch.object(
            self.repository, "commit", side_effect=SystemExit("process_stopped")
        ):
            with self.assertRaises(SystemExit):
                self.service.decide(plan.id, record.preview.operation_id, "accept")
        with self.store.database.session() as session:
            row = session.get(
                StudyUnitRevisionOperationRow, record.preview.operation_id
            )
            row.updated_at = (
                datetime.now(timezone.utc) - timedelta(minutes=5)
            ).isoformat()
        self.assertEqual(self.repository.get(plan.id).status, "failed")
        with self.assertRaises(HTTPException):
            self.service.decide(plan.id, record.preview.operation_id, "accept")
        self.assertEqual(
            DocumentRepository(self.store.database).get(self.document.id), self.document
        )

    def test_prepared_output_from_another_operation_cannot_write(self):
        from fastapi import HTTPException

        plan, record = self.preview()
        captured = {}

        def capture(plan_id, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("capture_prepared")

        with (
            patch.object(self.repository, "commit", side_effect=capture),
            self.assertLogs("app.services.study_unit_revision", level="ERROR"),
        ):
            self.service.decide(plan.id, record.preview.operation_id, "accept")
        # The original failed admission cannot be revived by a stale prepared claim.
        with self.assertRaises(HTTPException):
            self.repository.commit(plan.id, **captured)
        other_plan, other_record = self.preview("another-preview")
        self.assertTrue(
            self.repository.begin_accept(
                other_plan.id, other_record.preview.operation_id
            )
        )
        with self.assertRaisesRegex(ValueError, "runtime_binding_mismatch"):
            self.repository.commit(other_plan.id, **captured)
        self.repository.fail(other_plan.id, status="failed")
        self.assertEqual(
            DocumentRepository(self.store.database).get(self.document.id), self.document
        )
