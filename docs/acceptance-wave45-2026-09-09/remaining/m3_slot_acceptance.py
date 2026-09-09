"""Actual MiniMax-M3 long-slot acceptance through the production route/runtime."""
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from unittest.mock import patch

from app.api import routes
from app.models.api import PersonaSlotAssistRequest
from app.models.domain import PersonaSlot
from app.services.harness_broad_adoption import HarnessProposalRuntimeService
from app.services.local_store import LocalJsonStore
from app.services.model_provider import OpenAIModelProvider
from app.services.persona import PersonaEngine

root = Path(__file__).resolve().parent
provider = OpenAIModelProvider(api_key=os.environ["K3_API_KEY"], base_url="https://api.minimax.cn/v1", plan_model="MiniMax-M3", setting_model="MiniMax-M3", timeout_seconds=90, setting_max_tokens=4096)
request = provider._request_openai_chat_completion
calls = []
def observe(*args, **kwargs):
    started = perf_counter()
    result = request(*args, **kwargs)
    calls.append({"duration_ms": round((perf_counter() - started) * 1000), "usage": result[0].get("usage"), "finish_reason": result[0].get("choices", [{}])[0].get("finish_reason")})
    return result
provider._request_openai_chat_completion = observe
# Newly authored synthetic test data. No saved persona or user document is read.
original = PersonaSlot(
    kind="teaching_method", label="Synthetic observation method", weight=50,
    content="\n".join(
        f"第 {index} 轮合成教学示例：先请学生记录红灯下的观测时间，再说明‘假设、观察、结论’之间的区别。"
        "每轮只提出一个可验证的问题；保留学生原话中的引号，不虚构学生的经历或身份。"
        "在比较两次读数之前，检查单位和仪器刻度。若数据不足，说明还需要哪项观测，不擅自给出结论。"
        for index in range(1, 9)
    ),
)
results = []
with TemporaryDirectory() as directory:
    store = LocalJsonStore(Path(directory))
    try:
        with patch.object(routes.container, "model_provider", provider), patch.object(routes.container, "persona_engine", PersonaEngine()), patch.object(routes.container, "harness_proposal_runtime", HarnessProposalRuntimeService.from_database(store.database)):
            for index in range(3):
                started = perf_counter()
                before = len(calls)
                response = routes.assist_persona_slot(PersonaSlotAssistRequest(name="Wave45 M3 Observatory Tutor", summary="Patient astronomy tutor", slot=original, rewrite_strength=0.3))
                wire = response.model_dump(mode="json")
                results.append({"index": index, "duration_ms": round((perf_counter() - started) * 1000), "calls": calls[before:], "response": wire})
                (root / "m3-slot-result.json").write_text(json.dumps({"model": "MiniMax-M3", "samples": results}, ensure_ascii=False, indent=2))
                assert wire["slot"]["weight"] == original.weight
                print(json.dumps({"sample": index, "trace_status": wire["harness_trace"]["status"], "provider_calls": len(calls) - before, "recoveries": [item["strategy"] for item in wire["model_recoveries"]]}), flush=True)
    finally:
        store.close()
