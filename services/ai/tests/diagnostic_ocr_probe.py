"""Opt-in real cached-model OCR diagnostic acceptance; synthetic image-only PDF."""
import hashlib
import json
from pathlib import Path
import time
from tempfile import TemporaryDirectory

import fitz
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository


def run():
    model_paths = [Path.home() / ".cache/onnxtr/models" / name for name in
        ("db_mobilenet_v3_large-4987e7bd.onnx", "parseq-00b40714.onnx")]
    if not all(path.is_file() for path in model_paths):
        raise RuntimeError("diagnostic_ocr_cached_models_required")
    with fitz.open() as text_pdf:
        page = text_pdf.new_page()
        lines = ["Chapter 1 Scientific Observation", "PRIVATE OCR CONTENT SENTINEL",
            "Observe a sample and record the evidence.", "Compare the measurements and explain the result.",
            "Repeat the experiment to check your prediction."] * 3
        for index, line in enumerate(lines):
            page.insert_text((50, 60 + 30 * index), line, fontsize=16)
        image = page.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
        with fitz.open() as scanned:
            page = scanned.new_page()
            page.insert_image(page.rect, stream=image)
            assert not page.get_text().strip()
            content = scanned.tobytes()
    with TemporaryDirectory(prefix="diagnostic-real-ocr-") as directory:
        root = Path(directory)
        app = create_app(settings=Settings(database_url=f"sqlite:///{root / 'domain.db'}",
            storage_root=str(root / "data"), plan_provider="mock", ocr_engine="onnxtr"))
        with TestClient(app) as client:
            headers = {"X-Debug-Flow-Id": "real_ocr_flow", "X-Debug-Action-Id": "real_ocr"}
            uploaded = client.post("/documents", files={"file": ("PRIVATE_OCR_FILENAME.pdf", content, "application/pdf")}, headers=headers)
            assert uploaded.status_code == 200
            document_id = uploaded.json()["id"]
            started = time.perf_counter()
            response = client.post(f"/documents/{document_id}/process/stream", json={"force_ocr": True}, headers=headers)
            duration = time.perf_counter() - started
            assert response.status_code == 200
            terminal = json.loads(response.text.splitlines()[-1])
            assert terminal["stage"] == "stream_completed", terminal["stage"]
            document = app.state.container.document_service.require_document(document_id)
            debug = app.state.container.document_service.require_debug_report(document_id)
            assert debug.ocr_applied
            assert debug.ocr_applied_page_count == 1
            assert "Scientific Observation" in json.dumps(debug.model_dump(mode="json"))
            store = app.state.diagnostics
            store.queue.join()
            events = []
            after = 0
            while True:
                rows = store.query(after, 100, {"flow_id": "real_ocr_flow"})
                events.extend(row["event"] for row in rows)
                if len(rows) < 100:
                    break
                after = rows[-1]["sequence"]
            refs = [event["harness"] for event in events if event.get("harness")]
            assert refs
            runtime = HarnessRuntimeRepository(app.state.container.database)
            traces = [trace for operation in {ref["operation_id"] for ref in refs} for trace in runtime.list_operation_traces(operation)]
            assert {ref["trace_id"] for ref in refs if ref["trace_id"]}.issubset({trace.trace_id for trace in traces})
            assert any(trace.stage.value == "ocr_page" and trace.terminal_trace for trace in traces)
            assert any(trace.stage.value == "document_parse" and trace.terminal_trace.commit_evidence.status.value == "committed" for trace in traces if trace.terminal_trace)
            assert any(event.get("resource", {}) and event["resource"]["resource_id"] == document_id and event["request_id"] == response.headers["x-request-id"] for event in events)
            for secret in ("PRIVATE_OCR_FILENAME", "PRIVATE OCR CONTENT SENTINEL", "Observe a sample", "Scientific Observation"):
                assert secret not in json.dumps(events)
            return {"schema_version": "diagnostic-real-ocr-probe-v1", "ocr_applied": debug.ocr_applied, "model_id": debug.ocr_model_id,
                "ocr_status": document.ocr_status, "duration_seconds": round(duration, 3), "event_count": len(events),
                "stages": sorted({trace.stage.value for trace in traces}),
                "models": [{"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in model_paths],
                "scope": "One synthetic image-only page; real local cached OCR models; no model-quality or latency gate claim."}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(), indent=2) + "\n")
