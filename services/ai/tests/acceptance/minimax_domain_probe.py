"""Opt-in MiniMax M3 Persona/Scene admission, generation, save and read-back.

Synthetic inputs only. Keep the isolated data directory for local replay; never
commit the database or diagnostic logs. This is exploratory quality evidence,
not an independently calibrated eval gate.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.provider_sdk import ProviderRequestAdapter
from tests.test_persona_lifecycle import create_request


CASES = {
    "persona": [
        {"mode": "keywords", "input_text": "沈舟，温厚寡言的修伞匠，与用户是同行朋友，称用户阿岚。用克制的干幽默，不贬低用户，不设定共同往事。", "count": 3},
        {"mode": "long_text", "input_text": "角色：林澈。身份：严谨的植物学研究员。用户是合作研究者，称呼小顾，不是学生或亲属。习惯先区分观察与猜测。未知材料不伪装成亲眼所见。", "count": 3},
    ],
    "scene": [
        {"mode": "keywords", "input_text": "山间茶馆，包含茶室与檐下两个区域。无电器，无魔法，不含人物已发生的行为。用简洁中文。", "layer_count": 2},
        {"mode": "long_text", "input_text": "深夜天文台只有观测室与资料室。观测室有光学望远镜和红色弱光灯，资料室有星图。窗外阴天，不能直接看见星星。不要添加地下层或第三个空间。", "layer_count": 2},
    ],
}


def generation_boundary_success(readback_equal: bool, traces: list[dict]) -> bool:
    return readback_equal and bool(traces) and all(
        t["status"] in {"passed", "repaired"} and t["commit_evidence"]["status"] == "not_applicable"
        for t in traces
    )


def run(root: Path, repetitions: int, selected_domain: str | None = None) -> None:
    root.mkdir(parents=True, exist_ok=False)
    key = os.environ["K3_API_KEY"]
    endpoint = "https://api.minimax.cn/v1"
    settings = Settings(
        storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}",
        plan_provider="litellm", ocr_engine="disabled", openai_api_key=key,
        openai_base_url=endpoint, openai_plan_model="MiniMax-M3",
        openai_setting_model="MiniMax-M3", openai_chat_model="MiniMax-M3",
        openai_setting_web_search_enabled=False, openai_setting_max_tokens=4096,
        openai_chat_max_tokens=2048, openai_timeout_seconds=90,
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    app = create_app(settings=settings)
    active_calls = []
    original_request = ProviderRequestAdapter.request_chat_completion

    def observe_request(adapter, payload, *, request_kind, model):
        started = time.perf_counter()
        call = {"request_kind": request_kind, "model": model,
                "max_tokens": payload.get("max_tokens"), "temperature": payload.get("temperature")}
        active_calls.append(call)
        try:
            raw, elapsed = original_request(adapter, payload, request_kind=request_kind, model=model)
            choices = raw.get("choices", [])
            call.update(usage=raw.get("usage"), finish_reason=choices[0].get("finish_reason") if choices else None)
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            try:
                candidate = json.loads(content)
                if isinstance(candidate, dict):
                    call["candidate_json"] = candidate
            except (TypeError, ValueError):
                call["candidate_json_valid"] = False
            return raw, elapsed
        except Exception as exc:
            call["exception_class"] = type(exc).__name__
            raise
        finally:
            call["elapsed_ms"] = round((time.perf_counter()-started)*1000)

    with patch.object(ProviderRequestAdapter, "request_chat_completion", observe_request), TestClient(app) as client, (root / "report.jsonl").open("x", encoding="utf-8") as report:
        runtime = HarnessRuntimeRepository(app.state.container.database)
        for repetition in range(repetitions):
            for domain, cases in CASES.items():
                if selected_domain is not None and domain != selected_domain:
                    continue
                for index, payload in enumerate(cases):
                    active_calls.clear()
                    before = set(runtime.list_trace_ids(limit=100))
                    row = {"scope": "live_domain_admission_save_readback", "domain": domain,
                           "case_id": f"{domain}-{index}", "repetition": repetition,
                           "fixture_version": "minimax-domain-exploration-v1", "git_revision": revision,
                           "model": "MiniMax-M3", "setting_max_tokens": 4096,
                           "web_search_enabled": False, "input": payload}
                    started = time.perf_counter()
                    try:
                        url = "/persona-cards/generate" if domain == "persona" else "/scene-setup/generate"
                        response = client.post(url, json=payload)
                        row["generation_http_status"] = response.status_code
                        if response.status_code != 200:
                            row["success"] = False
                        else:
                            generated = response.json()
                            row["generated"] = generated
                            if domain == "persona":
                                save_payload = create_request(f"合成人格 {index}").model_dump(mode="json")
                                save_payload.update(summary=generated["summary"], relationship=generated["relationship"], learner_address=generated["learner_address"])
                                save_payload["slots"] = [{"kind": card["kind"], "label": card["label"], "content": card["content"],
                                    "weight": 50, "locked": False, "sort_order": i} for i, card in enumerate(generated["items"])]
                                saved_response = client.post("/personas", json=save_payload)
                                row["save_http_status"] = saved_response.status_code
                                if saved_response.status_code == 200:
                                    saved = saved_response.json()
                                    reloaded_response = client.get("/personas")
                                    row["readback_http_status"] = reloaded_response.status_code
                                    row["readback_equal"] = reloaded_response.status_code == 200 and next((p for p in reloaded_response.json()["items"] if p["id"] == saved["id"]), None) == saved
                            else:
                                save_payload = {k: generated[k] for k in ("scene_name", "scene_summary", "scene_layers", "selected_layer_id")}
                                save_payload.update(contract_version="scene-committed-save-v1", expected_revision=0, collapsed_layer_ids=[])
                                saved_response = client.post("/scene-library", json=save_payload)
                                row["save_http_status"] = saved_response.status_code
                                if saved_response.status_code == 200:
                                    saved = saved_response.json()
                                    reloaded_response = client.get(f"/scene-library/{saved['scene_id']}")
                                    row["readback_http_status"] = reloaded_response.status_code
                                    row["readback_equal"] = reloaded_response.status_code == 200 and reloaded_response.json() == saved
                            row["success"] = row.get("readback_equal", False)
                    except Exception as exc:
                        row["success"] = False
                        row["exception_class"] = type(exc).__name__
                    row["elapsed_ms"] = round((time.perf_counter()-started)*1000)
                    row["provider_calls"] = list(active_calls)
                    traces = [runtime.get(t) for t in runtime.list_trace_ids(limit=100) if t not in before]
                    row["terminal_traces"] = [t.terminal_trace.model_dump(mode="json") for t in traces if t.terminal_trace]
                    # These generation routes return proposals; user-authored
                    # saves are a separate boundary. Their registered v3 policy
                    # correctly reports not_applicable, not a domain commit.
                    row["expected_generation_commit_status"] = "not_applicable"
                    row["generation_repaired"] = any(t["status"] == "repaired" for t in row["terminal_traces"])
                    row["success"] = generation_boundary_success(bool(row.get("readback_equal")), row["terminal_traces"])
                    report.write(json.dumps(row, ensure_ascii=False) + "\n")
                    report.flush()
                    print(json.dumps({k: row[k] for k in ("case_id", "repetition", "success", "elapsed_ms")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--domain", choices=CASES)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 30:
        parser.error("repetitions must be between 1 and 30")
    run(args.root.resolve(), args.repetitions, args.domain)
