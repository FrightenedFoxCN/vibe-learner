"""Actual mock-provider Tavern create/turn/read-back benchmark chain."""
from app.models.tavern import TavernRoomDetail, TavernTurnResponse, TavernRunListResponse
from tests.test_persona_lifecycle import create_request


def prepare(client, workflow):
    count = 1 if workflow == "tavern_direct" else 3
    personas = []
    for index in range(count):
        response = client.post("/personas", json=create_request(f"PRIVATE_TAVERN_PERSONA_{index}").model_dump(mode="json"))
        assert response.status_code == 200
        personas.append(response.json()["id"])
    return {"personas": personas, "mode": "direct" if count == 1 else "facilitated"}


def chain(request, headers, prepared):
    def call(method, url, action, model, **kwargs):
        response = request(method, url, headers={**headers, "X-Debug-Action-Id": action}, **kwargs)
        assert response.status_code == 200
        return model.model_validate(response.json()).model_dump(mode="json")
    room = call("POST", "/tavern/rooms", "create", TavernRoomDetail, json={
        "title": "PRIVATE_TAVERN_ROOM", "persona_ids": prepared["personas"], "idempotency_key": "benchmark-room"})
    room_id = room["room"]["id"]
    result = call("POST", f"/tavern/rooms/{room_id}/turns", "turn", TavernTurnResponse, json={
        "input": {"kind": "user_message", "content": "PRIVATE_WORKFLOW_PROMPT"},
        "guidance": "PRIVATE_TAVERN_GUIDANCE", "mode": prepared["mode"],
        "target_persona_ids": prepared["personas"], "idempotency_key": "benchmark-turn",
        "expected_room_revision": room["room"]["revision"],
    })
    assert result["run"]["status"] == "completed"
    assert [s["status"] for s in result["run"]["speaker_steps"]] == ["completed"] * len(prepared["personas"])
    assert len(result["generated_messages"]) == len(prepared["personas"])
    assert result["input_message"]["content"] == "PRIVATE_WORKFLOW_PROMPT"
    reloaded = call("GET", f"/tavern/rooms/{room_id}", "room_reload", TavernRoomDetail)
    runs = call("GET", f"/tavern/rooms/{room_id}/runs", "run_reload", TavernRunListResponse)
    assert runs["items"] == [result["run"]]
    messages = [result["input_message"], *result["generated_messages"]]
    assert reloaded["messages"] == messages
    assert reloaded["message_count"] == len(messages)
    assert [m["sequence"] for m in messages] == list(range(1, len(messages) + 1))
    assert [m["persona_id"] for m in result["generated_messages"]] == prepared["personas"]
    prepared["message_positions"] = {m["id"]: (m["sequence"], room_id) for m in messages}
    resources = {("tavern_room", room_id), ("tavern_run", result["run"]["id"])}
    resources.update(("tavern_message", m["id"]) for m in messages)
    return ({"mode": prepared["mode"], "actors": len(prepared["personas"]),
             "messages": len(messages), "run_status": result["run"]["status"],
             "room_revision": reloaded["room"]["revision"], "persisted_projections_equal": True},
            resources, {"create", "turn", "room_reload", "run_reload"})
