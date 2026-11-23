"""Regression tests for the bounded diagnostic link retention and export."""

from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.diagnostic_routes import router
from app.core.diagnostics import DiagnosticStore
from app.models.diagnostic import (
    DiagnosticHarnessReferenceV1,
    DiagnosticOperationLinkV1,
)
from app.models.harness import HarnessStage, HarnessWorkflow


OPERATION = "harness-operation-" + "1" * 32
OTHER_OPERATION = "harness-operation-" + "2" * 32
REQUEST = "request-a"


class DiagnosticOperationLinkTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(TemporaryDirectory())
        self.store = DiagnosticStore(Path(root) / "events.sqlite3")
        self.store.start()
        self.addCleanup(self.store.close)
        app = FastAPI()
        app.include_router(router)
        app.state.diagnostics = self.store
        self.client = self.enterContext(TestClient(app))
        # Force initialization before reading or seeding legacy records.
        self.store.emit("lifecycle_started")
        self.store.queue.join()

    def emit_stage(
        self,
        stage,
        *,
        op=OPERATION,
        workflow=HarnessWorkflow.DOCUMENT_PARSE,
    ):
        self.store.emit(
            "harness_reference",
            request_id=REQUEST,
            harness=DiagnosticHarnessReferenceV1(
                operation_id=op, workflow=workflow, stage=stage
            ),
        )
        self.store.queue.join()

    def export(self, **filters):
        result = self.client.post("/diagnostics/export", json=filters)
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def test_stage_export_preserves_same_request_and_counts_one_retained_link(self):
        for stage in (
            HarnessStage.DOCUMENT_PARSE,
            HarnessStage.PAGE_EXTRACTION,
            HarnessStage.SECTION_DETECTION,
            HarnessStage.SECTION_DETECTION,
        ):
            self.emit_stage(stage)
        self.store.emit("request_started", request_id=REQUEST)
        self.store.queue.join()

        for stage in ("document_parse", "page_extraction", "section_detection"):
            with self.subTest(stage=stage):
                data = self.export(workflow="document_parse", stage=stage)
                self.assertEqual(data["link_retention"]["retained_rows"], 1)
                self.assertEqual(len(data["operation_links"]), 1)
                self.assertEqual(data["operation_links"][0]["stage"], stage)
                self.assertNotIn("observed_stages", data["operation_links"][0])
                events = [row["event"] for row in data["events"]]
                self.assertIn("request_started", [event["name"] for event in events])
                self.assertEqual(
                    {e["harness"]["stage"] for e in events if e["harness"]}, {stage}
                )
                query = self.client.get("/diagnostics/events", params={"stage": stage})
                self.assertEqual(query.status_code, 200)
                self.assertEqual(query.json()["items"], data["events"])
        links = self.client.get(
            "/diagnostics/operation-links", params={"operation_id": OPERATION}
        ).json()
        self.assertEqual(len(links["items"]), 1)
        self.assertEqual(links["items"][0]["stage"], "section_detection")
        self.assertNotIn("observed_stages", links["items"][0])
        with closing(sqlite3.connect(self.store.path)) as db:
            count, size = db.execute(
                "SELECT count(*), sum(length(cast(payload as blob))) FROM operation_links"
            ).fetchone()
            self.assertEqual(count, 1)
            self.assertEqual(
                self.store.link_retention.coverage(db)["retained_payload_bytes"], size
            )

    def test_filters_cannot_join_unrelated_operations_sharing_request(self):
        self.emit_stage(HarnessStage.PAGE_EXTRACTION)
        self.emit_stage(
            HarnessStage.PLAN_GENERATION,
            op=OTHER_OPERATION,
            workflow=HarnessWorkflow.PLANNING,
        )
        self.store.emit("request_started", request_id=REQUEST)
        self.store.queue.join()
        args = {
            "operation_id": OPERATION,
            "workflow": "planning",
            "stage": "plan_generation",
        }
        result = self.client.get("/diagnostics/events", params=args)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["items"], [])
        self.assertEqual(
            self.export(workflow="document_parse", stage="plan_generation")[
                "operation_links"
            ],
            [],
        )

    def test_legacy_link_remains_readable_and_keeps_observed_stage_after_update(self):
        legacy = DiagnosticOperationLinkV1(
            operation_id=OPERATION,
            request_id=REQUEST,
            workflow=HarnessWorkflow.DOCUMENT_PARSE,
            stage=HarnessStage.DOCUMENT_PARSE,
        )
        with (
            closing(sqlite3.connect(self.store.path)) as db,
            self.store.quota.transaction(db),
        ):
            db.execute(
                "INSERT INTO operation_links(operation_id,request_id,payload) VALUES (?,?,?)",
                (OPERATION, REQUEST, legacy.model_dump_json(exclude_unset=True)),
            )
        self.assertEqual(
            self.export(stage="document_parse")["operation_links"][0]["stage"],
            "document_parse",
        )
        self.emit_stage(HarnessStage.PAGE_EXTRACTION)
        self.assertEqual(
            self.export(stage="document_parse")["operation_links"][0]["stage"],
            "document_parse",
        )
