"""Bounded MiniMax M3 acceptance through the production Tavern service."""
import argparse
from dataclasses import asdict
from datetime import UTC, datetime
import json
import logging
import math
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import time

from app.models.tavern import TavernRoomRecord, TavernHarnessPolicy, TavernTurnRequest
from app.services.harness_performance_benchmark import tavern_fixture
from app.services.local_store import LocalJsonStore
from app.services.model_provider import OpenAIModelProvider
from app.services.persona import PersonaEngine
from app.persistence.tavern_repository import TavernRepository
from app.services.tavern import TavernService
from app.models.harness_performance import canonical_byte_count
from app.services.tavern_prompt import preflight_tavern_actor_prompt

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
logging.disable(logging.CRITICAL)
samples = []
runs = []
preflights = []
provider = OpenAIModelProvider(api_key=os.environ["K3_API_KEY"],
    base_url="https://api.minimax.cn/v1", plan_model="MiniMax-M3", chat_model="MiniMax-M3",
    chat_max_tokens=2048, timeout_seconds=60, setting_web_search_enabled=False)
original = provider._request_openai_chat_completion

def observed(payload, **kwargs):
    if len(samples) >= 15:
        raise RuntimeError("acceptance_provider_call_ceiling")
    sample = {"index": len(samples), "prompt_bytes": canonical_byte_count(payload["messages"]),
              "response_format": payload.get("response_format", {}).get("type"),
              "max_tokens": payload.get("max_tokens"), "tool_calls": 0}
    samples.append(sample)
    started = time.perf_counter()
    try:
        result, elapsed = original(payload, **kwargs)
        sample.update(status="success", usage=result.get("usage"),
                      returned_model=result.get("model"),
                      finish_reasons=[c.get("finish_reason") for c in result.get("choices", [])])
        return result, elapsed
    except Exception as error:
        sample.update(status="error", error_type=type(error).__name__,
                      error_code=str(error)[:160], http_status=getattr(error, "status_code", None))
        raise
    finally:
        sample["latency_ms"] = (time.perf_counter() - started) * 1000
        print(json.dumps(sample), flush=True)

provider._request_openai_chat_completion = observed
fixture = tavern_fixture()
with TemporaryDirectory(prefix="wave45-live-tavern-") as root:
    store = LocalJsonStore(Path(root))
    repository = TavernRepository(store.database)
    engine = PersonaEngine(store)
    service = TavernService(repository=repository, persona_engine=engine, model_provider=provider)
    now = datetime.now(UTC).isoformat()
    room = TavernRoomRecord(id="benchmark-room", title="Synthetic acceptance only",
        scene_profile=fixture["scene_profile"], harness_policy=TavernHarnessPolicy(context_message_limit=40),
        last_sequence=40, created_at=now, updated_at=now)
    repository.create_room(room=room, participants=fixture["participants"], messages=fixture["recent_messages"])
    original_actor = provider.generate_tavern_actor_reply
    def observed_actor(**kwargs):
        from app.models.tavern import TavernActorReply
        preflight = preflight_tavern_actor_prompt(**{k:v for k,v in kwargs.items() if k != "should_continue"},
            actor_reply_schema=json.dumps(TavernActorReply.transport_json_schema(), ensure_ascii=False, sort_keys=True))
        preflights.append(asdict(preflight.report))
        return original_actor(**kwargs)
    provider.generate_tavern_actor_reply = observed_actor
    try:
        for batch in (fixture["participants"][:4], fixture["participants"][4:]):
            detail = repository.require_room(room.id)
            request = TavernTurnRequest.model_validate({
                "input": {"kind": "user_message", "content": "请依次简短讨论古城地图，保留各自立场。"},
                "mode": "facilitated", "target_persona_ids": [p.persona_id for p in batch],
                "guidance": "只扮演自己的角色，以中文回复，正文不超过100字。",
                "idempotency_key": f"acceptance-live-{len(runs)}",
                "expected_room_revision": detail.room.revision})
            started = time.perf_counter()
            http_error = None
            try:
                service.run_turn(room_id=room.id, payload=request)
            except Exception as error:
                http_error = {"type": type(error).__name__, "status": getattr(error,"status_code",None)}
            record = repository.list_runs(room.id)[0]
            before_replay = len(samples)
            try:
                service.run_turn(room_id=room.id, payload=request)
            except Exception:
                pass
            assert len(samples) == before_replay, "replay issued another upstream request"
            runs.append({"run": record.model_dump(mode="json"), "http_error": http_error,
                         "latency_ms": (time.perf_counter()-started)*1000,
                         "replay_provider_calls": len(samples)-before_replay})
            print(json.dumps({"run_status":record.status.value,"steps":[s.status.value for s in record.speaker_steps]}),flush=True)
    finally:
        store.close()

latencies = sorted(s["latency_ms"] for s in samples)
report = {"base_commit": subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
    "measured_at": datetime.now(UTC).isoformat(), "model":"MiniMax-M3", "endpoint":"https://api.minimax.cn/v1",
    "temperature":0.35,"max_tokens":2048,"timeout_seconds":60,"thinking":"provider_default",
    "fixture":"six personas, 40 x 8000-character messages, facilitated 4+2 (server limit four per run)",
    "samples": samples,"runs":runs,"preflights":preflights,
    "p50_ms":latencies[math.ceil(len(latencies)*.5)-1] if latencies else None,
    "p95_ms":latencies[math.ceil(len(latencies)*.95)-1] if latencies else None,
    "statistical_scope":"small-sample smoke; no population p95 or quality-rate acceptance",
    "passed":len(preflights)==6 and all(r["run"]["status"]=="completed" for r in runs)}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
print(json.dumps({"passed":report["passed"],"provider_calls":len(samples)}))
