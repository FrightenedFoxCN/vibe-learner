"""Synthetic partial-run failure followed by real M3 scoped child retry."""
import json
import os
from datetime import datetime, UTC
from pathlib import Path
from tempfile import TemporaryDirectory
from fastapi import HTTPException

from app.models.tavern import TavernRoomRecord, TavernHarnessPolicy, TavernTurnRequest, RetryTavernRunRequest
from app.persistence.tavern_repository import TavernRepository
from app.services.harness_performance_benchmark import tavern_fixture
from app.services.local_store import LocalJsonStore
from app.services.model_provider import OpenAIModelProvider
from app.services.persona import PersonaEngine
from app.services.tavern import TavernService

root = Path(__file__).resolve().parent
fixture = tavern_fixture()  # Explicitly synthetic, never desktop records.
provider = OpenAIModelProvider(api_key=os.environ["K3_API_KEY"], base_url="https://api.minimax.cn/v1", plan_model="MiniMax-M3", chat_model="MiniMax-M3", chat_max_tokens=2048, timeout_seconds=60)
calls = []
request = provider._request_openai_chat_completion
def observed(*args, **kwargs):
    if len(calls) >= 10:
        raise RuntimeError("acceptance_call_ceiling")
    calls.append({})
    response = request(*args, **kwargs)
    calls[-1] = {"usage": response[0].get("usage")}
    return response
provider._request_openai_chat_completion = observed
actor = provider.generate_tavern_actor_reply
injected = False
def generate(**kwargs):
    global injected
    if kwargs["persona"].id == "benchmark-persona-1" and not injected:
        injected = True
        raise RuntimeError("acceptance_injected_before_provider")
    return actor(**kwargs)
provider.generate_tavern_actor_reply = generate

with TemporaryDirectory() as directory:
    store = LocalJsonStore(Path(directory))
    try:
        repository = TavernRepository(store.database)
        service = TavernService(repository=repository, persona_engine=PersonaEngine(store), model_provider=provider)
        now = datetime.now(UTC).isoformat()
        room = TavernRoomRecord(id="benchmark-room", title="Synthetic retry acceptance", scene_profile=fixture["scene_profile"], harness_policy=TavernHarnessPolicy(context_message_limit=40), last_sequence=40, created_at=now, updated_at=now)
        repository.create_room(room=room, participants=fixture["participants"], messages=fixture["recent_messages"])
        payload = TavernTurnRequest.model_validate({"input": {"kind": "user_message", "content": "请简短讨论古城路线。"}, "mode": "facilitated", "target_persona_ids": [f"benchmark-persona-{i}" for i in range(3)], "guidance": "只回应自己的角色，正文不超过100字。", "idempotency_key": "synthetic-retry-root", "expected_room_revision": 0})
        try:
            service.run_turn(room_id=room.id, payload=payload)
        except HTTPException as exc:
            assert exc.status_code == 502
        source = repository.list_runs(room.id)[0]
        assert [s.status.value for s in source.speaker_steps] == ["completed", "failed", "blocked"]
        first_id = source.speaker_steps[0].message_id
        first = repository.get_message(first_id).model_dump(mode="json")
        retry = RetryTavernRunRequest(expected_room_revision=repository.require_room(room.id).room.revision, idempotency_key="synthetic-retry-child")
        service.retry_run(room_id=room.id, source_run_id=source.id, payload=retry)
        child = repository.get_retry_child(source.id)
        assert child is not None and child.status.value == "completed"
        assert [s.persona_id for s in child.speaker_steps] == ["benchmark-persona-1", "benchmark-persona-2"]
        assert repository.get_message(first_id).model_dump(mode="json") == first
        before = len(calls)
        service.retry_run(room_id=room.id, source_run_id=source.id, payload=retry)
        assert len(calls) == before
        result = {"passed": True, "injected_failure": "before second actor provider call", "original_status": source.status.value, "child_status": child.status.value, "completed_message_unchanged": True, "retry_targets": [s.persona_id for s in child.speaker_steps], "replay_provider_calls": 0, "provider_calls": calls}
        (root / "tavern-retry-result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps({k: v for k, v in result.items() if k != "provider_calls"}))
    finally:
        store.close()
