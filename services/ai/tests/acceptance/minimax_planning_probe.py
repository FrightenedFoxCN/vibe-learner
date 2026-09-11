"""Real MiniMax planning with synthetic material and admitted commit evidence."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.models.api import LearningPlanCreateResponse, LearningPlanResponse
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.provider_sdk import ProviderRequestAdapter
from tests.acceptance.minimax_study_probe import SOURCE
from tests.test_persona_lifecycle import create_request


CASES = {
    "document": "用中文安排一元一次方程的学习，先理解等式变形，再练习，最后代入检验。",
    "source_boundary": "只依据教材安排学习，不要编造教材作者、出版年份或未出现的章节。重点区分 a 非零和 a=0 的情况。",
    "goal_only": "我想从零学习 Python 列表与字典，先做列表练习再学字典。用中文，不要假设我已经掌握循环。",
}


def planning_outcomes(readback_equal, operation_status, traces, execution_count):
    generation = [t for t in traces if t["stage"] == "plan_generation"]
    tools = [t for t in traces if t["stage"] == "planning_tool_execution"]
    complete = bool(traces) and len(traces) == execution_count
    return {
        "boundary_success": bool(readback_equal) and operation_status == "committed" and complete
            and len(generation) == 1 and generation[0]["status"] in {"passed", "repaired"}
            and generation[0]["commit_evidence"]["status"] == "committed",
        "tool_attempts": len(tools),
        "tool_failures": sum(t["status"] not in {"passed", "repaired"} for t in tools),
        "tool_error_codes": [t["error_code"] for t in tools if t["status"] not in {"passed", "repaired"}],
    }


PLANNING_BUDGET_CANDIDATE = (
    "\n工具调用预算：同名工具在同一轮最多调用一次、整个计划生成过程最多调用四次。"
    "多个独立单元需要同名详情工具时，分轮核查；同轮可以调用不同名称的工具。"
    "预算拒绝后不要原样重复请求。只在证据仍有缺口时继续工具调用，证据充分时输出计划。"
)


def run(root, repetitions, budget_candidate=False, selected_case=None):
    root.mkdir(parents=True, exist_ok=False)
    settings = Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}",
        plan_provider="litellm", ocr_engine="disabled", openai_api_key=os.environ["K3_API_KEY"],
        openai_base_url="https://api.minimax.cn/v1", openai_plan_model="MiniMax-M3",
        openai_setting_model="MiniMax-M3", openai_chat_model="MiniMax-M3",
        openai_setting_web_search_enabled=False, openai_timeout_seconds=90)
    calls = []
    original = ProviderRequestAdapter.request_chat_completion

    def observe(adapter, payload, *, request_kind, model):
        if budget_candidate:
            payload = {**payload, "messages": [{**message,
                "content": message["content"] + PLANNING_BUDGET_CANDIDATE}
                if message.get("role") == "system" else message
                for message in payload.get("messages", [])]}
        call = {"kind": request_kind, "model": model, "max_tokens": payload.get("max_tokens")}
        calls.append(call)
        start = time.perf_counter()
        try:
            raw, elapsed = original(adapter, payload, request_kind=request_kind, model=model)
            choices = raw.get("choices", [])
            call["usage"] = raw.get("usage")
            call["finish_reason"] = choices[0].get("finish_reason") if choices else None
            call["requested_tools"] = [c.get("function", {}).get("name")
                for c in (choices[0].get("message", {}).get("tool_calls") or [])] if choices else []
            call["tool_envelope_shapes"] = [{"keys": sorted(c),
                "function_keys": sorted(c.get("function", {})),
                "index_type": type(c.get("index")).__name__,
                "index": c.get("index") if type(c.get("index")) is int else None}
                for c in (choices[0].get("message", {}).get("tool_calls") or [])] if choices else []
            return raw, elapsed
        except Exception as exc:
            call["error_class"] = type(exc).__name__
            status = str(getattr(exc, "status_code", ""))
            if status.isdigit() and len(status) == 3:
                call["upstream_http_status"] = int(status)
            raise
        finally:
            call["elapsed_ms"] = round((time.perf_counter() - start) * 1000)

    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    app = create_app(settings=settings)
    with patch.object(ProviderRequestAdapter, "request_chat_completion", observe), TestClient(app) as client:
        persona = client.post("/personas", json=create_request("顾言").model_dump(mode="json"))
        persona.raise_for_status()
        persona_id = persona.json()["id"]
        with fitz.open() as pdf:
            page = pdf.new_page()
            assert page.insert_textbox((55, 55, 540, 750), SOURCE, fontsize=12) >= 0
            uploaded = client.post("/documents", files={"file": ("planning.pdf", pdf.tobytes(), "application/pdf")})
        uploaded.raise_for_status()
        document_id = uploaded.json()["id"]
        processed = client.post(f"/documents/{document_id}/process", json={"force_ocr": False})
        processed.raise_for_status()
        document = processed.json()
        runtime = HarnessRuntimeRepository(app.state.container.database)
        with (root / "report.jsonl").open("x", encoding="utf-8") as stream:
            for repetition in range(repetitions):
                for case_id, objective in CASES.items():
                    if selected_case is not None and selected_case != case_id:
                        continue
                    calls.clear()
                    request_id = f"quality-plan-{case_id}-{repetition}"
                    payload = {"client_request_id": request_id, "persona_id": persona_id, "objective": objective}
                    if case_id != "goal_only":
                        payload.update(document_id=document_id, expected_document_updated_at=document["updated_at"])
                    row = {"scope": "live_planning_admission_commit_readback", "fixture_version": "planning-quality-v1",
                        "git_revision": revision, "case_id": case_id, "repetition": repetition,
                        "model": "MiniMax-M3", "objective": objective, "calls": calls, "boundary_success": False}
                    row["prompt_variant"] = "planning-budget-experiment-v1" if budget_candidate else "production"
                    if budget_candidate:
                        row["experimental_prompt_suffix"] = PLANNING_BUDGET_CANDIDATE
                        row["trace_limitation"] = "Experimental prompt override; traces prove lifecycle only, not production prompt adoption."
                    start = time.perf_counter()
                    try:
                        response = client.post("/learning-plans", json=payload)
                        row["http_status"] = response.status_code
                        if response.status_code == 200:
                            result = LearningPlanCreateResponse.model_validate(response.json())
                            row["result"] = result.model_dump(mode="json")
                            # Snapshot each operation before a later plan replaces
                            # the document-scoped latest debug trace. Keep only
                            # content-free tool status, never arguments/reasoning.
                            trace_path = root / "data" / "planning_trace" / f"{payload.get('document_id') or result.id}.json"
                            if trace_path.exists():
                                debug = json.loads(trace_path.read_text())
                                row["tool_diagnostics"] = []
                                for round_record in debug.get("rounds", []):
                                    for tool in round_record.get("tool_calls", []):
                                        result_summary = json.loads(tool["result_json"])
                                        row["tool_diagnostics"].append({
                                            "tool_name": tool["tool_name"],
                                            "ok": result_summary.get("ok"),
                                            "error": result_summary.get("error") if result_summary.get("content_free") is True else None,
                                        })
                            readback = client.get(f"/learning-plans/{result.id}")
                            row["readback_equal"] = readback.status_code == 200 and readback.json() == LearningPlanResponse.model_validate(result.model_dump()).model_dump(mode="json")
                        operation = app.state.container.plan_service.operation_repository.get_by_client_request_id(client_request_id=request_id)
                        if operation is not None:
                            row["operation_status"] = operation.status
                            binding = app.state.container.plan_service.operation_repository.require_harness_operation(operation.operation_id)
                            row["harness_operation_id"] = binding.harness_operation_id
                            executions = runtime.list_operation_traces(binding.harness_operation_id)
                            row["terminal_traces"] = [e.terminal_trace.model_dump(mode="json") for e in executions if e.terminal_trace]
                            row.update(planning_outcomes(row.get("readback_equal"), operation.status,
                                row["terminal_traces"], len(executions)))
                    except Exception as exc:
                        row["error_class"] = type(exc).__name__
                    row["elapsed_ms"] = round((time.perf_counter() - start) * 1000)
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                    stream.flush()
                    print(json.dumps({k: row[k] for k in ("case_id", "repetition", "boundary_success", "elapsed_ms")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--budget-candidate", action="store_true")
    parser.add_argument("--case", choices=CASES)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("repetitions must be between 1 and 20")
    run(args.root.resolve(), args.repetitions, args.budget_candidate, args.case)
