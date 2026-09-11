"""Synthetic real PDF -> Study Chat -> durable receipt/read-back quality probe."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.app_factory import create_app
from app.core.settings import Settings
from app.models.api import StudyChatOperationReceiptResponse, StudySessionResponse
from app.models.study_chat_reply import StudyChatReplyProposalV1
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.provider_sdk import ProviderRequestAdapter
from app.services.provider_study import (
    CHAT_PRIVATE_GRADING_KEY_RE,
    _decode_study_chat_reply_proposal,
    _study_chat_public_proposal_texts,
    _chat_prompt_sections,
)
from tests.test_persona_lifecycle import create_request


SOURCE = """Chapter 1 Linear Equations
A linear equation in one variable has the form ax + b = c, where a is nonzero.
To solve it, subtract b from both sides, then divide both sides by a.
For example, 2x + 3 = 11 gives 2x = 8 and x = 4.
Check the answer by substitution: 2 times 4 plus 3 equals 11.
Dividing by zero is not allowed. If a is zero, examine b = c separately.
Subtracting the same number from both sides preserves equality.
Multiplying both sides by the same nonzero number preserves equality.
"""
CASES = {
    "three_bullets": "请用恰好三条 Markdown 无序列表讲解 2x+3=11 的求解和检验，每条一句。不要开场白、标题、结尾或出题。",
    "code_and_math": "请用中文说明 2x+3=11 的解，含一条 LaTeX 行内公式，再给一个 python 代码块用 assert 验证答案。不要生成图或题目。",
    "unknown_source": "教材是否说过这个方法是陈老师于1987年发明的？请核对教材，找不到就明确说教材未提供，别编造作者和年份。",
    "interactive_question": "请围绕本节出一道含四个选项的单选互动题。等我作答，暂时不要公布正确选项、答案或解析。",
}

SAFE_QUESTION_ERRORS = frozenset({
    "study_question_multiple_choice_options_required",
    "study_question_option_key_duplicate",
    "study_question_answer_key_required",
    "study_question_answer_key_unknown",
    "study_question_fill_blank_answers_required",
    "study_question_fill_blank_options_forbidden",
})


def safe_schema_errors(exc):
    records = []
    for error in exc.errors(include_input=False, include_url=False)[:20]:
        record = {"type": error["type"], "loc": error["loc"]}
        reason = str(error.get("ctx", {}).get("error", ""))
        if reason in SAFE_QUESTION_ERRORS:
            record["reason"] = reason
        records.append(record)
    return records


QUESTION_CONTRACT_CANDIDATE = (
    "\n互动题字段契约：multiple_choice 必须提供至少两个不同 key 的 options，"
    "并在 interactive_question.answer_key 中填写其中一个正确选项 key；"
    "fill_blank 必须提供非空 accepted_answers。answer_key、accepted_answers、explanation "
    "仅供服务器判分，会在向学习者展示前被移除。学习者要求暂不公布答案时，仍须完整填写这些私有字段；"
    "不要将答案或解析写入 text、rich_blocks、题干、选项说明或表演字段。"
)


def stable_system_prefix_candidate(system):
    dynamic = "{{PERSONA_RUNTIME_PROMPT}}\n{{SESSION_RUNTIME_CONTEXT}}"
    if not system.startswith(dynamic + "\n\n") or system.count(dynamic) != 1:
        raise ValueError("study_cache_candidate_template_changed")
    return system[len(dynamic) + 2:] + "\n\n" + dynamic


def run(root, repetitions, selected_case=None, question_contract_candidate=False, stable_prefix_candidate=False):
    root.mkdir(parents=True, exist_ok=False)
    settings = Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}",
        plan_provider="litellm", ocr_engine="disabled", openai_api_key=os.environ["K3_API_KEY"],
        openai_base_url="https://api.minimax.cn/v1", openai_plan_model="MiniMax-M3",
        openai_setting_model="MiniMax-M3", openai_chat_model="MiniMax-M3",
        openai_setting_web_search_enabled=False, openai_chat_max_tokens=4096, openai_timeout_seconds=90)
    calls = []
    original = ProviderRequestAdapter.request_chat_completion

    def observe(adapter, payload, *, request_kind, model):
        call = {"kind": request_kind, "model": model, "max_tokens": payload.get("max_tokens")}
        calls.append(call)
        started = time.perf_counter()
        try:
            raw, elapsed = original(adapter, payload, request_kind=request_kind, model=model)
            choices = raw.get("choices", [])
            call.update(usage=raw.get("usage"), finish_reason=choices[0].get("finish_reason") if choices else None)
            if choices and choices[0].get("finish_reason") != "tool_calls":
                content = choices[0].get("message", {}).get("content", "")
                try:
                    decoded = _decode_study_chat_reply_proposal(content)
                    call["production_decode"] = "structured" if decoded is not None else "plain_text"
                except RuntimeError:
                    call["production_decode"] = "rejected"
                try:
                    candidate = json.loads(content)
                    proposal = StudyChatReplyProposalV1.model_validate(candidate, strict=True)
                    call["proposal_text_empty"] = not proposal.text.strip()
                    call["public_grading_key_detected"] = any(
                        CHAT_PRIVATE_GRADING_KEY_RE.search(text) is not None
                        for text in _study_chat_public_proposal_texts(proposal)
                    )
                except (TypeError, ValueError) as exc:
                    # Keep server-only question answers and reasoning out of
                    # public reports. Field locations/types suffice to diagnose
                    # strict schema errors without persisting candidate values.
                    if isinstance(exc, ValidationError):
                        call["proposal_schema_errors"] = safe_schema_errors(exc)
                    else:
                        call["raw_json_object_valid"] = False
            return raw, elapsed
        except Exception as exc:
            call["error_class"] = type(exc).__name__
            raise
        finally:
            call["elapsed_ms"] = round((time.perf_counter()-started)*1000)

    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    app = create_app(settings=settings)
    sections = _chat_prompt_sections()
    if stable_prefix_candidate:
        sections = {**sections, "system": stable_system_prefix_candidate(sections["system"])}
    if question_contract_candidate:
        sections = {key: value + QUESTION_CONTRACT_CANDIDATE if key in {"system", "recovery"} else value
            for key, value in sections.items()}
    with patch("app.services.provider_study._chat_prompt_sections", return_value=sections), patch.object(ProviderRequestAdapter, "request_chat_completion", observe), TestClient(app) as client:
        persona = create_request("顾言").model_dump(mode="json")
        persona.update(summary="严谨、温和的数学老师，说话简洁，先核对证据再下结论。", relationship="数学老师与成年学习者", learner_address="小林")
        created = client.post("/personas", json=persona)
        created.raise_for_status()
        persona_id = created.json()["id"]
        with fitz.open() as pdf:
            page = pdf.new_page()
            assert page.insert_textbox((55, 55, 540, 750), SOURCE, fontsize=12) >= 0
            pdf_bytes = pdf.tobytes()
        uploaded = client.post("/documents", files={"file": ("linear-equations-quality.pdf", pdf_bytes, "application/pdf")})
        uploaded.raise_for_status()
        document_id = uploaded.json()["id"]
        processed = client.post(f"/documents/{document_id}/process", json={"force_ocr": False})
        processed.raise_for_status()
        document = processed.json()
        (root / "document.json").write_text(json.dumps(document, ensure_ascii=False, indent=2)+"\n")
        assert document["study_units"]
        runtime = HarnessRuntimeRepository(app.state.container.database)
        with (root / "report.jsonl").open("x", encoding="utf-8") as stream:
            for repetition in range(repetitions):
                for case_id, message in CASES.items():
                    if selected_case is not None and case_id != selected_case:
                        continue
                    calls.clear()
                    response = client.post("/study-sessions", json={"document_id": document_id,
                        "persona_id": persona_id, "study_unit_id": document["study_units"][0]["id"]})
                    response.raise_for_status()
                    initial = StudySessionResponse.model_validate(response.json())
                    request_id = f"quality-{case_id}-{repetition}"
                    started = time.perf_counter()
                    row = {"scope": "live_study_operation_receipt_readback", "fixture_version": "study-quality-v1",
                        "git_revision": revision, "case_id": case_id, "repetition": repetition,
                        "model": "MiniMax-M3", "message": message, "calls": calls}
                    row["prompt_variant"] = "question-contract-experiment-v1" if question_contract_candidate else "production"
                    if stable_prefix_candidate:
                        row["cache_variant"] = "study-static-system-prefix-experiment-v1"
                        row["cache_transform"] = "Move unchanged leading persona/session placeholders to end of system; keep all static instructions, tools, and message order unchanged."
                        row["trace_limitation"] = "Experimental system order; traces prove lifecycle only, not production prompt adoption."
                    if question_contract_candidate:
                        row["experimental_prompt_suffix"] = QUESTION_CONTRACT_CANDIDATE
                        row["trace_limitation"] = "Experimental prompt override; traces prove domain lifecycle only, not reviewed production prompt adoption."
                    try:
                        response = client.post(f"/study-sessions/{initial.id}/chat", json={
                            "client_request_id": request_id, "expected_session_revision": initial.revision, "message": message})
                        row["http_status"] = response.status_code
                        if response.status_code == 200:
                            receipt = StudyChatOperationReceiptResponse.model_validate(response.json())
                            row["receipt"] = receipt.model_dump(mode="json")
                            readback = client.get(f"/study-sessions/{initial.id}")
                            recovery = client.get(f"/study-sessions/{initial.id}/chat-operations/{request_id}")
                            row["readback_equal"] = bool(receipt.result) and readback.status_code == 200 and readback.json() == receipt.result.session.model_dump(mode="json")
                            row["receipt_equal"] = recovery.status_code == 200 and recovery.json() == response.json()
                            row["boundary_success"] = receipt.status == "committed" and row["readback_equal"] and row["receipt_equal"]
                            if receipt.result:
                                row["observations"] = {"list_items": len(re.findall(r"(?m)^[-*+] ", receipt.result.reply)),
                                    "python_fence": "```python\n" in receipt.result.reply,
                                    "code_rich_blocks": sum(b.get("kind") == "code" for b in receipt.result.rich_blocks),
                                    "citations": len(receipt.result.citations), "interactive_question": receipt.result.interactive_question is not None}
                            binding = app.state.container.study_chat_operation_repository.require_harness_operation(receipt.operation_id)
                            row["harness_operation_id"] = binding.harness_operation_id
                            executions = runtime.list_operation_traces(binding.harness_operation_id)
                            row["terminal_traces"] = [t.terminal_trace.model_dump(mode="json") for t in executions if t.terminal_trace]
                            row["runtime_executions"] = len(executions)
                            row["boundary_success"] = row["boundary_success"] and bool(row["terminal_traces"]) and all(
                                t["status"] in {"passed", "repaired"} and t["commit_evidence"]["status"] == "committed"
                                for t in row["terminal_traces"]
                            ) and len(row["terminal_traces"]) == len(executions)
                        else:
                            row["boundary_success"] = False
                    except Exception as exc:
                        row.update(boundary_success=False, error_class=type(exc).__name__)
                    row["elapsed_ms"] = round((time.perf_counter()-started)*1000)
                    stream.write(json.dumps(row, ensure_ascii=False)+"\n")
                    stream.flush()
                    print(json.dumps({k:row[k] for k in ("case_id", "repetition", "boundary_success", "elapsed_ms")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--question-contract-candidate", action="store_true")
    parser.add_argument("--stable-prefix-candidate", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("repetitions must be between 1 and 20")
    run(args.root.resolve(), args.repetitions, args.case, args.question_contract_candidate, args.stable_prefix_candidate)
