"""Final-candidate document Planning reproduction on the original fixture."""
import json
from pathlib import Path
from uuid import uuid4
import httpx

root = Path(__file__).parent
identity = json.loads((root / "live-wire/summary.json").read_text())["identities"]
c = httpx.Client(base_url="http://127.0.0.1:18046", timeout=300)
doc = next(item for item in c.get("/documents").json()["items"] if item["id"] == identity["document_id"])
r = c.post("/learning-plans", json={
    "client_request_id": "acceptance-final-doc-" + uuid4().hex,
    "document_id": doc["id"], "persona_id": "mentor-aurora",
    "objective": "Understand bases and linear independence.",
    "expected_document_updated_at": doc["updated_at"],
})
payload = r.json()
(root / "retest/document_plan.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2))
passed = r.status_code == 200 and payload.get("harness_trace", {}).get("commit_evidence", {}).get("status") == "committed"
print(json.dumps({"http": r.status_code, "passed": passed}), flush=True)
raise SystemExit(0 if passed else 1)
