"""Real streamed Document/Planning chain for the opt-in diagnostic benchmark."""
import json

import fitz

from app.models.stream import StreamEventRecord

PRIVATE_TEXT = "PRIVATE_DOCUMENT_CONTENT"
PRIVATE_FILENAME = "PRIVATE_WORKFLOW_FILENAME.pdf"


def prepare(client):
    personas = client.get("/personas")
    assert personas.status_code == 200
    persona_id = personas.json()["items"][0]["id"]
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 60), "Chapter 1 Algebra")
        page.insert_textbox((60, 90, 550, 700),
            ("Linear equations relate variables and constants. " + PRIVATE_TEXT + "\n") * 12)
        content = pdf.tobytes()
    return persona_id, content


def chain(request, headers, prepared):
    persona_id, content = prepared
    def call(method, url, action, **kwargs):
        response = request(method, url, headers={**headers, "X-Debug-Action-Id": action}, **kwargs)
        assert response.status_code == 200
        return response
    def terminal(response):
        events = [StreamEventRecord.model_validate_json(line) for line in response.text.splitlines()]
        assert events and events[-1].stage == "stream_completed"
        event = events[-1].model_dump(mode="json")
        assert event["terminal_evidence"]["commit_status"] == "committed"
        return event["committed_projection"]
    uploaded = call("POST", "/documents", "upload",
        files={"file": (PRIVATE_FILENAME, content, "application/pdf")}).json()
    document_id = uploaded["id"]
    processed = terminal(call("POST", f"/documents/{document_id}/process/stream", "process",
                              json={"force_ocr": False}))
    document = call("GET", f"/documents/{document_id}/status", "document_reload").json()
    assert document == {k: v for k, v in processed.items() if k != "harness_trace"}
    assert document["page_count"] == 1 and document["study_units"] and document["chunk_count"] > 0
    assert PRIVATE_TEXT in json.dumps(document)
    plan = terminal(call("POST", "/learning-plans/stream", "plan", json={
        "document_id": document_id, "persona_id": persona_id,
        "objective": "PRIVATE_WORKFLOW_PROMPT", "client_request_id": "synthetic-plan",
        "expected_document_updated_at": document["updated_at"],
    }))
    saved = call("GET", f"/learning-plans/{plan['id']}", "plan_reload").json()
    assert saved == {k: v for k, v in plan.items() if k != "harness_trace"}
    assert saved["document_id"] == document_id and saved["persona_id"] == persona_id
    assert saved["study_units"] and saved["schedule"]
    return ({"document_status": document["status"], "pages": document["page_count"],
             "chunks": document["chunk_count"], "study_units": len(document["study_units"]),
             "plan_study_units": len(saved["study_units"]), "schedule_entries": len(saved["schedule"]),
             "persisted_projections_equal": True},
            {("document", document_id), ("learning_plan", saved["id"])},
            {"upload", "process", "document_reload", "plan", "plan_reload"})
