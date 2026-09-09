"""Fresh HTTP fixtures for Wave 4/5 acceptance against the isolated mock server."""
import argparse
import json
from pathlib import Path
from uuid import uuid4
import httpx
import fitz

parser=argparse.ArgumentParser()
parser.add_argument("--output",type=Path,required=True)
parser.add_argument("--resume-after-chat",action="store_true")
parser.add_argument("--base-url",default="http://127.0.0.1:18045")
args=parser.parse_args()
out=args.output
out.mkdir(parents=True,exist_ok=True)
client=httpx.Client(base_url=args.base_url,timeout=300)
observations=[]
suffix=uuid4().hex[:8]
def call(name,method,url,**kwargs):
    response=client.request(method,url,**kwargs)
    observations.append({"case":name,"status":response.status_code})
    print(json.dumps(observations[-1]),flush=True)
    try: data=response.json()
    except ValueError: data={"stream":[json.loads(line) for line in response.text.splitlines() if line]}
    (out/f"{name}.json").write_text(json.dumps(data,ensure_ascii=False,indent=2))
    return response.status_code,data

if not args.resume_after_chat:
    pdf=fitz.open()
    for number in range(3):
        page=pdf.new_page()
        page.insert_textbox(fitz.Rect(50,50,550,780),
            f"Chapter {number+1}: Linear algebra\n"+
            "A vector space is closed under addition and scalar multiplication. A basis is linearly independent and spans the space.\n"*18,
            fontsize=11)
    status,doc=call("upload","POST","/documents",files={"file":("synthetic-algebra.pdf",pdf.tobytes(),"application/pdf")})
    assert status==200
    docid=doc["id"]
    status,processed=call("process","POST",f"/documents/{docid}/process",json={})
    assert status==200
    assert processed["harness_trace"]["commit_evidence"]["status"]=="committed"
    call("document_debug","GET",f"/documents/{docid}/debug")
    call("document_context","GET",f"/documents/{docid}/planning-context")
    call("document_process_events","GET",f"/documents/{docid}/process-events")
    status,plan=call("plan","POST","/learning-plans",json={"client_request_id":"acceptance-plan-"+suffix,
        "document_id":docid,"persona_id":"mentor-aurora","objective":"Understand bases and linear independence.",
        "expected_document_updated_at":processed["updated_at"]})
    assert status==200
    assert plan["harness_trace"]["commit_evidence"]["status"]=="committed"
    call("plan_readback","GET",f"/learning-plans/{plan['id']}")
    call("goal_plan_stream","POST","/learning-plans/stream",json={"client_request_id":"acceptance-goal-"+suffix,
        "document_id":"","persona_id":"mentor-aurora","objective":"Learn introductory algebra."})
    for name,url,body in [
        ("persona","/persona-cards/generate",{"mode":"long_text","input_text":"A patient mapmaker who speaks calmly.","count":2}),
        ("scene","/scene-setup/generate",{"mode":"long_text","input_text":"A quiet library with a map table.","layer_count":2})]:
        status,data=call(name,"POST",url,json=body)
        assert status==200
        assert data["harness_trace"]["trace_schema_version"]=="harness-trace-v3"
        assert data["harness_trace"]["commit_evidence"]["status"]=="not_applicable"
    status,scene_before=call("scene_library_before","GET","/scene-library")
    call("scene_invalid","POST","/scene-setup/generate",json={"mode":"long_text","input_text":"x","layer_count":9})
    status,scene_after=call("scene_library_after","GET","/scene-library")
    assert scene_before==scene_after
    unit=processed["study_units"][0]["id"]
    status,session=call("session","POST","/study-sessions",json={"document_id":docid,"persona_id":"mentor-aurora","study_unit_id":unit})
    assert status==200
    request_id="acceptance-chat-"+suffix
    status,chat=call("chat","POST",f"/study-sessions/{session['id']}/chat",json={"client_request_id":request_id,
        "expected_session_revision":session["revision"],"message":"Explain a basis in one paragraph."})
    assert status==200
    observations.append({"case":"chat_commit","status":chat["status"],"passed":chat["status"]=="committed"})
else:
    doc=json.loads((out/"upload.json").read_text())
    docid=doc["id"]
    session=json.loads((out/"session.json").read_text())
    chat=json.loads((out/"chat.json").read_text())
    request_id=chat["client_request_id"]
call("chat_readback","GET",f"/study-sessions/{session['id']}/chat-operations/{request_id}")
personas=[]
for i in range(6):
    status,p=call(f"cast_{i}","POST","/personas",json={"name":f"Observer {i}","summary":"A patient cartographer.",
        "relationship":"同行者","learner_address":"你","system_prompt":"Only speak for yourself.","slots":[]})
    assert status==200
    personas.append(p["id"])
status,room=call("room","POST","/tavern/rooms",json={"title":"Wave45 acceptance "+suffix,"persona_ids":personas,"idempotency_key":"acceptance-room-"+suffix})
assert status==200
for i,batch in enumerate((personas[:4],personas[4:])):
    payload={"input":{"kind":"user_message","content":"Discuss the map briefly."},"mode":"facilitated",
        "target_persona_ids":list(reversed(batch)),"guidance":"Keep your own identity.",
        "idempotency_key":f"acceptance-turn-{suffix}-{i}","expected_room_revision":room["room"]["revision"]}
    status,result=call(f"tavern_turn_{i}","POST",f"/tavern/rooms/{room['room']['id']}/turns",json=payload)
    assert status==200 and result["run"]["status"]=="completed"
    assert result["run"]["scheduled_participant_ids"]==batch
    status,replay=call(f"tavern_replay_{i}","POST",f"/tavern/rooms/{room['room']['id']}/turns",json=payload)
    assert result["run"]["id"]==replay["run"]["id"]
    _,room=call(f"room_readback_{i}","GET",f"/tavern/rooms/{room['room']['id']}?tail=true&limit=40")
identities={"session_id":session["id"],"client_request_id":request_id,"room_id":room["room"]["id"],"document_id":docid}
(out/"summary.json").write_text(json.dumps({"observations":observations,"identities":identities},indent=2))
print(json.dumps(identities))

# Transport success alone never closes a model workflow gate.
goal=json.loads((out/"goal_plan_stream.json").read_text())["stream"]
checks={"goal_plan_committed":bool(goal) and goal[-1].get("terminal_evidence",{}).get("commit_status")=="committed",
        "study_chat_committed":chat["status"]=="committed"}
(out/"outcomes.json").write_text(json.dumps(checks,indent=2)+"\n")
raise SystemExit(0 if all(checks.values()) else 1)
