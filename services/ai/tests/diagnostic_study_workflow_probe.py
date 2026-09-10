"""Study admission, chat receipt and persisted Session benchmark chain."""
from app.models.api import StudySessionResponse, StudyChatOperationReceiptResponse
from tests.diagnostic_document_plan_probe import prepare as prepare_document


def prepare(client):
    persona_id, content = prepare_document(client)
    response = client.post("/documents", files={"file": ("PRIVATE_WORKFLOW_FILENAME.pdf", content, "application/pdf")})
    assert response.status_code == 200
    document_id = response.json()["id"]
    response = client.post(f"/documents/{document_id}/process", json={"force_ocr": False})
    assert response.status_code == 200
    document = response.json()
    assert document["study_units"]
    return {"document_id": document_id, "persona_id": persona_id,
            "study_unit_id": document["study_units"][0]["id"]}


def chain(request, headers, prepared):
    def call(method, url, action, model, **kwargs):
        response = request(method, url, headers={**headers, "X-Debug-Action-Id": action}, **kwargs)
        assert response.status_code == 200
        return model.model_validate(response.json()).model_dump(mode="json")
    initial = call("POST", "/study-sessions", "create", StudySessionResponse, json=prepared)
    session_id = initial["id"]
    client_request_id = "benchmark-study-chat"
    receipt = call("POST", f"/study-sessions/{session_id}/chat", "chat", StudyChatOperationReceiptResponse,
        json={"client_request_id": client_request_id, "expected_session_revision": initial["revision"],
              "message": "PRIVATE_WORKFLOW_PROMPT"})
    assert receipt["status"] == "committed" and receipt["result"]
    recovered = call("GET", f"/study-sessions/{session_id}/chat-operations/{client_request_id}",
                     "receipt_reload", StudyChatOperationReceiptResponse)
    assert recovered == receipt
    session = call("GET", f"/study-sessions/{session_id}", "session_reload", StudySessionResponse)
    assert session == receipt["result"]["session"]
    assert session["revision"] == initial["revision"] + 1
    assert len(session["turns"]) == len(initial["turns"]) + 1
    turn = session["turns"][-1]
    assert turn["learner_message"] == "PRIVATE_WORKFLOW_PROMPT"
    assert turn["assistant_reply"] == receipt["result"]["reply"] and turn["assistant_reply"]
    assert turn["citations"] == receipt["result"]["citations"]
    assert turn["character_events"] == receipt["result"]["character_events"]
    assert turn["id"] == receipt["committed_turn_id"]
    assert turn["sequence"] == receipt["committed_turn_sequence"] == session["last_turn_sequence"]
    assert receipt["committed_session_revision"] == session["revision"]
    assert receipt["session_id"] == session_id and receipt["client_request_id"] == client_request_id
    return ({"revision": session["revision"], "turn_count": len(session["turns"]),
             "last_turn_sequence": session["last_turn_sequence"], "operation_status": receipt["status"],
             "persisted_projections_equal": True}, {("study_session", session_id)},
            {"create", "chat", "receipt_reload", "session_reload"})
