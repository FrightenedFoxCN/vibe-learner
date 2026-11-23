import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_container
from app.api.routers.planning import router
from app.core.bootstrap import Container
from app.core.settings import Settings
from tests.support.planning_operations import planning_document


class PlanningDocumentReadinessTests(TestCase):
    def test_zero_text_document_cannot_admit_a_plan(self):
        with TemporaryDirectory() as tmp:
            container = Container(
                Settings(
                    database_url=f"sqlite:///{tmp}/test.db",
                    storage_root=str(Path(tmp) / "data"),
                    auto_migrate_local_data=False,
                    plan_provider="mock",
                    ocr_engine="disabled",
                )
            )
            try:
                app = FastAPI()
                app.include_router(router)
                app.dependency_overrides[get_container] = lambda: container
                document = planning_document().model_copy(
                    update={
                        "chunk_count": 0,
                        "ocr_status": "unavailable",
                        "debug_ready": False,
                    }
                )
                container.document_service.repository.insert(document)
                goal = {
                    "document_id": document.id,
                    "persona_id": container.persona_engine.list_personas()[0].id,
                    "objective": "Learn vectors",
                    "expected_document_updated_at": document.updated_at,
                    "client_request_id": "zero-text-fixture",
                }
                with (
                    TestClient(app) as client,
                    patch.object(
                        container.model_provider, "generate_learning_plan"
                    ) as provider,
                ):
                    response = client.post("/learning-plans", json=goal)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(
                        response.json()["detail"], "document_no_extractable_text"
                    )
                    response = client.post("/learning-plans/stream", json=goal)
                    self.assertEqual(response.status_code, 200)
                    terminal = json.loads(response.text.splitlines()[-1])
                    self.assertEqual(terminal["stage"], "stream_error")
                    self.assertEqual(terminal["payload"]["status_code"], 422)
                    self.assertEqual(
                        terminal["payload"]["detail"], "document_no_extractable_text"
                    )
                    self.assertEqual(
                        terminal["terminal_evidence"]["domain_operation_status"],
                        "not_admitted",
                    )
                    self.assertEqual(
                        client.get(
                            "/learning-plan-operations/zero-text-fixture"
                        ).status_code,
                        404,
                    )
                    provider.assert_not_called()
            finally:
                container.close()
