from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import sqlite3
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.diagnostic_routes import router
from app.core.diagnostics import DiagnosticStore
from app.models.diagnostic import DiagnosticEventV1, DiagnosticHarnessReferenceV1
from app.models.diagnostic_export import DiagnosticExportFiltersV1, DiagnosticExportV1
from app.models.harness import HarnessWorkflow, HarnessStage
from app.services.diagnostic_export import build_diagnostic_export
from app.services.diagnostic_index import DiagnosticHarnessIndex

OP = "harness-operation-" + "a" * 32


class DiagnosticExportTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = DiagnosticStore(Path(directory.name) / "events.sqlite3")
        self.addCleanup(self.store.close)
        self.store.start()
        self.store.enqueue(DiagnosticEventV1(event_id="reference", source="server", name="harness_reference",
            timestamp="2026-09-10T00:00:00Z", request_id="request", harness=DiagnosticHarnessReferenceV1(
                operation_id=OP, workflow=HarnessWorkflow("persona"), stage=HarnessStage("persona_generation"))))
        self.store.queue.join()
        self.store.close()
        self.index = DiagnosticHarnessIndex(None, Path(directory.name) / "index.sqlite3")
        with self.index._connect() as db:
            from app.models.diagnostic_index import DiagnosticHarnessIndexV1
            trace = DiagnosticHarnessIndexV1.model_validate_json(json.dumps(dict(trace_id="trace", operation_id=OP,
                workflow="persona", stage="persona_generation", state="terminal", status="passed", commit_status="committed", duration_ms=40,
                components=[], attempts=[])))
            db.execute("INSERT INTO projections VALUES (?,?,?,?,?,?)", ("trace", OP, "persona", "persona_generation", trace.model_dump_json(), 0))
            db.commit()
        app = FastAPI(version="0.3.1")
        app.state.diagnostics = self.store
        app.state.diagnostic_index = self.index
        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def export(self, **filters):
        return DiagnosticExportV1.model_validate_json(build_diagnostic_export(self.store, self.index,
            DiagnosticExportFiltersV1.model_validate_json(json.dumps(filters)), "0.3.1"))

    def test_export_attachment_scope_audit_and_missing_index(self):
        response = self.client.post("/diagnostics/export", json={"request_id": "request"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("attachment", response.headers["content-disposition"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        report = DiagnosticExportV1.model_validate_json(response.content)
        self.assertEqual(len(report.events), 1)
        self.assertEqual(len(report.operation_links), 1)
        self.assertEqual(report.index_coverage.scope, "related_operations")
        self.assertEqual(report.audit.groups[0].p95_ms, 40)
        self.assertEqual(report.audit.commit_claim, "none")
        self.assertFalse(report.complete_collection_claim)
        self.assertEqual(self.export(request_id="absent").index, [])
        self.assertEqual(len(self.export().index), 1)
        self.client.app.state.diagnostic_index = None
        report = self.client.post("/diagnostics/export", json={}).json()
        self.assertEqual(report["index_coverage"]["freshness"], "unavailable")
        self.assertEqual(report["index_coverage"]["missing_operation_count"], 1)

    def test_concurrent_prune_links_and_writer_updates_do_not_mix_snapshots(self):
        original = self.store.retention.coverage
        def capture_then_write(db, after):
            coverage = original(db, after)
            with sqlite3.connect(self.store.path) as writer:
                writer.execute("DELETE FROM events")
                writer.execute("DELETE FROM operation_links")
                writer.execute("UPDATE diagnostic_writers SET observed_dropped=17")
            return coverage
        with patch.object(self.store.retention, "coverage", side_effect=capture_then_write):
            report = self.export()
        self.assertEqual(len(report.events), report.retention.retained_events)
        self.assertEqual(len(report.events), 1)
        self.assertEqual(len(report.operation_links), 1)
        self.assertEqual(report.writer_pages[0].totals.observed_dropped, 0)
        current = self.export()
        self.assertEqual(current.events, [])
        self.assertEqual(current.retention.removed_events, 1)
        self.assertEqual(current.writer_pages[0].totals.observed_dropped, 17)

    def test_invalid_private_payloads_and_identity_mismatch_fail_closed(self):
        for table, assignment in (("events", "payload=json_set(payload,'$.private','PRIVATE_SECRET')"),
                                   ("operation_links", "payload=json_set(payload,'$.private','PRIVATE_SECRET')"),
                                   ("projections", "payload=json_set(payload,'$.private','PRIVATE_SECRET')"),
                                   ("events", "event_id='other'"),
                                   ("operation_links", "payload=json_set(payload,'$.request_id','other')"),
                                   ("projections", "payload=json_set(payload,'$.trace_id','other')")):
            path = self.index.path if table == "projections" else self.store.path
            with sqlite3.connect(path) as db:
                saved = db.execute("SELECT * FROM " + table).fetchone()
                columns = [row[1] for row in db.execute("PRAGMA table_info(" + table + ")")]
                db.execute("UPDATE " + table + " SET " + assignment)
            response = self.client.post("/diagnostics/export", json={})
            self.assertEqual(response.status_code, 503, (table, response.text))
            self.assertNotIn("PRIVATE", response.text)
            with sqlite3.connect(path) as db:
                db.execute("UPDATE " + table + " SET " + ",".join(column + "=?" for column in columns), saved)

    def test_limits_and_invalid_filters_never_return_partial_or_echo_input(self):
        for name in ("MAX_INPUT_BYTES", "MAX_EXPORT_BYTES"):
            with patch("app.services.diagnostic_export." + name, 1):
                response = self.client.post("/diagnostics/export", json={})
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()["detail"], "diagnostic_export_too_large")
        for value in ({"private": "PRIVATE_SECRET"}, {"since": "2026-09-10"},
                      {"since": "2026-09-11T00:00:00Z", "until": "2026-09-10T00:00:00Z"}):
            response = self.client.post("/diagnostics/export", json=value)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn("PRIVATE", response.text)
        self.assertEqual(self.client.post("/diagnostics/export", content=b" " * 8193).status_code, 413)

    def test_schema_fixture_and_index_snapshot_do_not_drift(self):
        fixture = Path(__file__).parents[3] / "packages/shared/fixtures/diagnostics/export-schema-v1.json"
        self.assertEqual(json.loads(fixture.read_text()), DiagnosticExportV1.model_json_schema())
        DiagnosticExportV1.model_validate_json(fixture.with_name("export-sample-v1.json").read_text())
        from app.services.diagnostic_export import _connect
        index_path = self.index.path
        class ConcurrentIndexWrite:
            def __init__(self, db):
                self.db = db
            def execute(self, sql, args=()):
                cursor = self.db.execute(sql, args)
                if sql.startswith("SELECT cursor,sweeps"):
                    with sqlite3.connect(index_path) as writer:
                        writer.execute("UPDATE projections SET payload=json_set(payload,'$.duration_ms',900)")
                        writer.execute("UPDATE checkpoint SET sweeps=99")
                return cursor
            def close(self):
                self.db.close()
        def connect(path, deadline):
            db = _connect(path, deadline)
            return ConcurrentIndexWrite(db) if path == index_path else db
        with patch("app.services.diagnostic_export._connect", side_effect=connect):
            report = self.export()
        self.assertEqual(report.index[0].duration_ms, 40)
        self.assertEqual(report.index_coverage.completed_sweeps, 0)
        self.assertEqual(self.export().index[0].duration_ms, 900)

    def test_writer_pages_remain_on_one_snapshot(self):
        with sqlite3.connect(self.store.path) as db:
            for i in range(200):
                db.execute("INSERT INTO diagnostic_writers(epoch_id,started_at,observed_at,closed_at,observed_dropped,observed_write_failures,observed_read_failures) VALUES (?,1,1,NULL,0,0,0)", (f"{i:032x}",))
        original = self.store.writer_coverage.read_snapshot
        def page_then_mutate(db, after=0, limit=100):
            page = original(db, after, limit)
            if after == 0:
                with sqlite3.connect(self.store.path) as writer:
                    writer.execute("UPDATE diagnostic_writers SET observed_dropped=1")
            return page
        with patch.object(self.store.writer_coverage, "read_snapshot", side_effect=page_then_mutate):
            report = self.export()
        self.assertEqual([len(page.items) for page in report.writer_pages], [100, 100, 1])
        self.assertTrue(all(page.totals.observed_dropped == 0 for page in report.writer_pages))
        self.assertTrue(all(item.observed_dropped == 0 for page in report.writer_pages for item in page.items))

    def test_retained_links_export_even_after_events_expire(self):
        with sqlite3.connect(self.store.path) as db:
            db.execute("DELETE FROM events")
        for filters in ({}, {"workflow": "persona"}, {"operation_id": OP}):
            report = self.export(**filters)
            self.assertEqual(report.events, [])
            self.assertEqual(len(report.operation_links), 1)
            self.assertEqual(len(report.index), 1)
            self.assertEqual(report.retention.removed_events, 1)
