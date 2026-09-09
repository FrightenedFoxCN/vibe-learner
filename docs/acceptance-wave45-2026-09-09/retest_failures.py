"""New requests on the original fixtures; preserve every historical outcome."""
import json
from pathlib import Path
from uuid import uuid4
import httpx

root = Path(__file__).parent
out = root / "retest"
out.mkdir(exist_ok=True)
old = json.loads((root / "live-wire/summary.json").read_text())["identities"]
client = httpx.Client(base_url="http://127.0.0.1:18046", timeout=300)
sid = old["session_id"]
session = client.get(f"/study-sessions/{sid}").json()
request_id = "acceptance-fixed-" + uuid4().hex
response = client.post(f"/study-sessions/{sid}/chat", json={
    "client_request_id": request_id, "expected_session_revision": session["revision"],
    "message": "Explain a basis in one paragraph."})
receipt = response.json()
(out / "chat.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
readback = client.get(f"/study-sessions/{sid}/chat-operations/{request_id}").json()
(out / "chat_readback.json").write_text(json.dumps(readback, ensure_ascii=False, indent=2))
print(json.dumps({"case": "study", "http": response.status_code, "status": receipt.get("status")}), flush=True)
response = client.post("/learning-plans/stream", json={
    "client_request_id": "acceptance-fixed-goal-" + uuid4().hex,
    "document_id": "", "persona_id": "mentor-aurora", "objective": "Learn introductory algebra."})
events = [json.loads(line) for line in response.text.splitlines() if line]
(out / "goal_stream.json").write_text(json.dumps(events, ensure_ascii=False, indent=2))
terminal = events[-1].get("terminal_evidence") or {}
result = {"session_id": sid, "client_request_id": request_id,
          "study_committed": receipt.get("status") == "committed" and readback == receipt,
          "goal_committed": terminal.get("commit_status") == "committed"}
(out / "summary.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result), flush=True)
raise SystemExit(0 if result["study_committed"] and result["goal_committed"] else 1)
