"""Real HTTP/parser fault acceptance for diagnostic correlation and safe evidence."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import fitz
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository


class DiagnosticDocumentFlowTests(TestCase):
    def test_stream_faults_keep_real_operation_identity_without_saved_resource_claims(self):
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((60, 60), "PRIVATE_DOCUMENT_CONTENT " * 8)
            valid_pdf = pdf.tobytes()
        for name, content, force_ocr in (
            ("PRIVATE_CORRUPT_FILENAME.pdf", b"PRIVATE_CORRUPT_DOCUMENT", False),
            ("PRIVATE_OCR_FILENAME.pdf", valid_pdf, True),
        ):
            with self.subTest(name=name), TemporaryDirectory() as directory:
                root = Path(directory)
                app = create_app(settings=Settings(database_url=f"sqlite:///{root / 'domain.db'}",
                    storage_root=str(root / "data"), plan_provider="mock", ocr_engine="disabled"))
                with TestClient(app) as client:
                    headers = {"X-Debug-Flow-Id": "document_fault_flow", "X-Debug-Action-Id": "upload"}
                    uploaded = client.post("/documents", files={"file": (name, content, "application/pdf")}, headers=headers)
                    self.assertEqual(uploaded.status_code, 200, uploaded.text)
                    document_id = uploaded.json()["id"]
                    processed = client.post(f"/documents/{document_id}/process/stream", json={"force_ocr": force_ocr},
                        headers={**headers, "X-Debug-Action-Id": "process"})
                    self.assertEqual(processed.status_code, 200)
                    stream = [json.loads(line) for line in processed.text.splitlines()]
                    self.assertEqual(stream[-1]["stage"], "stream_error")
                    persisted = client.get(f"/documents/{document_id}/status").json()
                    self.assertEqual(persisted["status"], "failed")
                    store = app.state.diagnostics
                    store.queue.join()
                    events = [row["event"] for row in store.query(0, 100, {"action_id": "process"})]
                    self.assertTrue(events)
                    self.assertLess(len(events), 100)
                    self.assertTrue(all(event["flow_id"] == headers["X-Debug-Flow-Id"] for event in events))
                    self.assertTrue(all(event["request_id"] == processed.headers["x-request-id"] for event in events))
                    self.assertFalse(any(event.get("resource") for event in events))
                    refs = [event["harness"] for event in events if event.get("harness")]
                    self.assertTrue(refs)
                    operation_ids = {ref["operation_id"] for ref in refs}
                    repo = HarnessRuntimeRepository(app.state.container.database)
                    traces = [trace for operation_id in operation_ids for trace in repo.list_operation_traces(operation_id)]
                    terminal = [item.terminal_trace for item in traces if item.terminal_trace]
                    self.assertTrue(terminal)
                    parent = [trace for trace in terminal if trace.stage.value == "document_parse"]
                    self.assertEqual(len(parent), 1)
                    self.assertEqual(parent[0].commit_evidence.status.value, "not_committed")
                    self.assertEqual(parent[0].status.value, "failed")
                    self.assertTrue({ref["trace_id"] for ref in refs if ref["trace_id"]}.issubset({item.trace_id for item in traces}))
                    serialized = json.dumps(events)
                    for secret in (name, "PRIVATE_DOCUMENT_CONTENT", "PRIVATE_CORRUPT_DOCUMENT"):
                        self.assertNotIn(secret, serialized)
                    if force_ocr:
                        retried = client.post(f"/documents/{document_id}/process/stream", json={"force_ocr": False},
                            headers={**headers, "X-Debug-Action-Id": "retry"})
                        self.assertEqual(retried.status_code, 200)
                        self.assertEqual(json.loads(retried.text.splitlines()[-1])["stage"], "stream_completed")
                        store.queue.join()
                        retry_events = [row["event"] for row in store.query(0, 100, {"action_id": "retry"})]
                        self.assertLess(len(retry_events), 100)
                        resources = [event["resource"] for event in retry_events if event.get("resource")]
                        self.assertEqual(len(resources), 1)
                        self.assertEqual(resources[0]["resource_id"], document_id)
                        self.assertTrue(all(event["flow_id"] == headers["X-Debug-Flow-Id"] for event in retry_events))
                        retry_operations = {event["harness"]["operation_id"] for event in retry_events if event.get("harness")}
                        self.assertTrue(retry_operations)
                        self.assertTrue(retry_operations.isdisjoint(operation_ids))
                        retry_traces = [trace for operation_id in retry_operations for trace in repo.list_operation_traces(operation_id)]
                        retry_parent = [item.terminal_trace for item in retry_traces if item.stage.value == "document_parse" and item.terminal_trace]
                        self.assertEqual(len(retry_parent), 1)
                        self.assertEqual(retry_parent[0].commit_evidence.status.value, "committed")
                        self.assertNotIn("PRIVATE_DOCUMENT_CONTENT", json.dumps(retry_events))
                        self.assertNotIn(name, json.dumps(retry_events))
