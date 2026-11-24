import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_container
from app.api.routers.documents import router as documents_router
from app.api.routers.planning import router
from app.core.settings import Settings
from app.core.bootstrap import Container
from app.models.domain import VersionedLearningPlanRecord
from app.models.planning import planning_projection_digest
from app.persistence.models import LearningPlanRevisionRow
from tests.support.planning_operations import (
    planning_debug,
    planning_document,
    planning_goal,
    planning_reply,
)


class PlanningAdmissionSnapshotTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.container = Container(
            Settings(
                database_url=f"sqlite:///{temp.name}/test.db",
                storage_root=str(Path(temp.name) / "data"),
                auto_migrate_local_data=False,
                plan_provider="mock",
                ocr_engine="disabled",
            )
        )
        self.addCleanup(self.container.close)
        app = FastAPI()
        app.include_router(router)
        app.include_router(documents_router)
        app.dependency_overrides[get_container] = lambda: self.container
        client = TestClient(app, raise_server_exceptions=False)
        self.client = self.enterContext(client)
        self.persona_id = self.container.persona_engine.list_personas()[0].id
        self.documents = self.container.document_service.repository
        self.operations = self.container.plan_service.operation_repository

    def payload(self, document, request_id):
        return planning_goal(document, request_id, self.persona_id).model_dump(
            mode="json"
        )

    def terminal(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        events = [json.loads(line) for line in response.text.splitlines()]
        self.assertEqual(
            sum(
                "terminal_evidence" in event and event["terminal_evidence"] is not None
                for event in events
            ),
            1,
        )
        return events[-1]

    def assert_not_admitted(self, document, request_id, code, detail):
        payload = self.payload(document, request_id)
        sync = self.client.post("/learning-plans", json=payload)
        self.assertEqual(sync.status_code, code, sync.text)
        self.assertEqual(sync.json()["detail"], detail)
        terminal = self.terminal(
            self.client.post("/learning-plans/stream", json=payload)
        )
        self.assertEqual(terminal["stage"], "stream_error")
        self.assertEqual(terminal["payload"]["status_code"], code)
        self.assertEqual(terminal["payload"]["detail"], detail)
        self.assertEqual(
            terminal["terminal_evidence"]["domain_operation_status"], "not_admitted"
        )
        self.assertIsNone(
            self.operations.get_by_client_request_id(client_request_id=request_id)
        )

    def test_preconditions_do_not_admit_or_invoke_provider(self):
        document = planning_document()
        with patch.object(
            self.container.model_provider, "generate_learning_plan"
        ) as provider:
            self.assert_not_admitted(
                document, "missing-document", 404, "document_not_found"
            )
            self.documents.insert(document)
            stale = document.model_copy(
                update={"updated_at": "2026-01-01T00:00:00+00:00"}
            )
            self.assert_not_admitted(
                stale, "stale-document", 409, "learning_plan_stale_document"
            )
            self.assert_not_admitted(
                document, "missing-debug", 404, "document_debug_not_found"
            )
            provider.assert_not_called()

    def test_sync_and_stream_replay_admitted_inputs_without_reading_current_debug(self):
        for first_endpoint in ("/learning-plans", "/learning-plans/stream"):
            with self.subTest(first_endpoint=first_endpoint):
                mode = "stream" if first_endpoint.endswith("/stream") else "sync"
                document = planning_document(document_id=f"fixture-{mode}")
                debug = planning_debug(document)
                self.documents.insert(document)
                self.container.store.save_item("document_debug", document.id, debug)
                payload = self.payload(document, f"replay-{mode}")
                with (
                    patch.object(
                        self.container.document_service,
                        "require_document",
                        side_effect=AssertionError("unexpected router preview read"),
                    ),
                    patch.object(
                        self.container.document_service,
                        "require_debug_report",
                        side_effect=AssertionError("unexpected debug preview read"),
                    ),
                    patch.object(
                        self.container.model_provider,
                        "generate_learning_plan",
                        return_value=planning_reply(document),
                    ) as provider,
                ):
                    initial = self.client.post(first_endpoint, json=payload)
                    self.assertEqual(initial.status_code, 200, initial.text)
                    operation = self.operations.get_by_client_request_id(
                        client_request_id=payload["client_request_id"]
                    )
                    self.assertEqual(operation.status.value, "committed")
                    self.assertEqual(
                        operation.base_document_digest,
                        planning_projection_digest(document.model_dump(mode="json")),
                    )
                    self.assertEqual(
                        operation.base_debug_digest,
                        planning_projection_digest(debug.model_dump(mode="json")),
                    )
                    self.container.store.delete_item("document_debug", document.id)
                    replay = self.client.post("/learning-plans", json=payload)
                    self.assertEqual(replay.status_code, 200, replay.text)
                    terminal = self.terminal(
                        self.client.post("/learning-plans/stream", json=payload)
                    )
                    self.assertEqual(terminal["stage"], "stream_completed")
                    self.assertEqual(
                        terminal["terminal_evidence"]["domain_operation_id"],
                        operation.operation_id,
                    )
                    self.assertEqual(
                        terminal["committed_projection"]["id"], operation.plan_id
                    )
                    provider.assert_called_once()

    def test_document_changed_after_admission_cannot_commit_plan(self):
        for endpoint in ("/learning-plans", "/learning-plans/stream"):
            with self.subTest(endpoint=endpoint):
                mode = "stream" if endpoint.endswith("/stream") else "sync"
                document = planning_document(document_id=f"changed-{mode}")
                debug = planning_debug(document)
                self.documents.insert(document)
                self.container.store.save_item("document_debug", document.id, debug)
                payload = self.payload(document, f"stale-commit-{mode}")
                admit = self.operations.admit
                latest = []

                def advance_document(**kwargs):
                    admitted = admit(**kwargs)
                    renamed, _ = self.documents.rename_study_unit(
                        document_id=document.id,
                        study_unit_id=document.study_units[0].id,
                        title="Updated after admission",
                        expected_revision=document.revision,
                    )
                    latest.append(renamed)
                    return admitted

                with (
                    patch.object(
                        self.operations, "admit", side_effect=advance_document
                    ),
                    patch.object(
                        self.container.model_provider,
                        "generate_learning_plan",
                        return_value=planning_reply(document),
                    ) as provider,
                ):
                    response = self.client.post(endpoint, json=payload)
                provider.assert_called_once()
                if mode == "stream":
                    terminal = self.terminal(response)
                    self.assertEqual(terminal["stage"], "stream_error")
                    self.assertEqual(
                        terminal["terminal_evidence"]["commit_status"], "not_committed"
                    )
                else:
                    self.assertNotEqual(response.status_code, 200, response.text)
                operation = self.operations.get_by_client_request_id(
                    client_request_id=payload["client_request_id"]
                )
                self.assertEqual(operation.status.value, "not_committed")
                self.assertTrue(
                    operation.error_code.startswith(
                        "learning_plan_learning_plan_stale_document"
                    )
                )
                self.assertIsNone(operation.committed_projection)
                self.assertEqual(self.documents.get(document.id), latest[0])

    def seed_rename(self):
        document = planning_document()
        self.documents.insert(document)
        self.container.store.save_item(
            "document_debug", document.id, planning_debug(document)
        )
        unit = document.study_units[0]
        repository = self.container.plan_service.repository
        plans = [
            VersionedLearningPlanRecord(
                id=plan_id,
                document_id=document_id,
                persona_id=self.persona_id,
                course_title="Linear Algebra",
                objective="Master vectors",
                overview="Synthetic plan",
                today_tasks=[],
                study_units=[unit.model_copy(deep=True)] if has_unit else [],
                created_at=document.created_at,
            )
            for plan_id, document_id, has_unit in (
                ("linked-a", document.id, True),
                ("linked-b", document.id, True),
                ("unlinked-document", "another-document", True),
                ("unlinked-unit", document.id, False),
            )
        ]
        repository.import_legacy(plans)
        return document, repository

    def rename(self, document, title, revision):
        unit_id = document.study_units[0].id
        return self.client.patch(
            f"/documents/{document.id}/study-units/{unit_id}",
            json={"title": title, "expected_revision": revision},
        )

    def test_stale_chapter_rename_cannot_replay_an_old_title_into_plans(self):
        document, repository = self.seed_rename()
        service = self.container.document_service
        mirror = service._mirror_current_document_projection
        newer = []
        in_newer_rename = False

        def interleave(*args, **kwargs):
            nonlocal in_newer_rename
            if not in_newer_rename:
                in_newer_rename = True
                # The first request is delayed after the document DB commit;
                # the second completes before the first request can return.
                newer.append(self.rename(document, "New title", 1))
            return mirror(*args, **kwargs)

        with patch.object(
            service, "_mirror_current_document_projection", side_effect=interleave
        ):
            first = self.rename(document, "First title", 0)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(len(newer), 1)
        second = newer[0]
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["document"]["revision"], 2)
        self.assertEqual(
            {plan["id"]: plan["revision"] for plan in second.json()["plans"]},
            {"linked-a": 2, "linked-b": 2},
        )
        stale = self.rename(document, "First title", 0)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(stale.json()["detail"], "document_revision_conflict")
        current, debug = self.documents.get_with_debug(document.id)
        self.assertEqual(current.study_units[0].title, "New title")
        self.assertEqual(debug.study_units[0].title, "New title")
        for plan_id in ("linked-a", "linked-b"):
            plan = repository.require(plan_id)
            self.assertEqual(plan.revision, 2)
            self.assertEqual(plan.study_units[0].title, "New title")
            self.assertEqual(plan.study_unit_progress[0].title, "New title")
            with repository.database.session() as session:
                archived = session.get(LearningPlanRevisionRow, (plan_id, 1))
                self.assertEqual(
                    archived.payload["study_units"][0]["title"], "First title"
                )
        self.assertEqual(repository.require("unlinked-document").revision, 0)
        self.assertEqual(repository.require("unlinked-unit").revision, 0)

    def test_linked_plan_cas_failure_rolls_back_every_chapter_projection(self):
        document, repository = self.seed_rename()
        # Make only the second scoped CAS fail, after the document and first plan
        # were written. A split or per-plan commit leaks those writes.
        with repository.database.engine.begin() as connection:
            connection.exec_driver_sql(
                """CREATE TRIGGER skip_linked_b_update BEFORE UPDATE ON learning_plans
                WHEN OLD.id = 'linked-b' BEGIN SELECT RAISE(IGNORE); END"""
            )
        failed = self.rename(document, "Must not commit", document.revision)
        self.assertEqual(failed.status_code, 409, failed.text)
        self.assertEqual(failed.json()["detail"], "learning_plan_revision_conflict")
        current, debug = self.documents.get_with_debug(document.id)
        self.assertEqual(current, document)
        self.assertEqual(debug, planning_debug(document))
        for plan_id in ("linked-a", "linked-b"):
            self.assertEqual(repository.require(plan_id).revision, 0)
            self.assertEqual(
                repository.require(plan_id).study_units[0].title, "Vectors"
            )
            with repository.database.session() as session:
                self.assertIsNone(session.get(LearningPlanRevisionRow, (plan_id, 1)))
