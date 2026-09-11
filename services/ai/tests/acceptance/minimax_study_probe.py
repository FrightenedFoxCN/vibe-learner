"""Synthetic real PDF -> Study Chat -> durable receipt/read-back quality probe."""
import argparse
import base64
from datetime import datetime
import io
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
    "memory_roundtrip": "请使用 write_session_memory 记录我的复习约定：先做代入检验，称呼我小林；然后使用 read_session_memory 读回核对。最后只用两条 Markdown 无序列表说明记住了什么，不编造以前的经历。",
    "document_text_tool": "请先调用 read_page_range_content 核对教材 PDF 第1页，再用恰好两条 Markdown 无序列表说明 a=0 和 a非零时的差别。不要开场白和结尾，不要出题。",
    "document_image_tool": "请先调用 read_page_range_images 查看教材 PDF 第1页，核对例题 2x+3=11，再用恰好两条 Markdown 无序列表说明求解和代入检验。不要开场白和结尾，不要出题。",
    "question_with_markdown": "请围绕 2x+3=11 出一道四选项单选互动题，等我作答，不公布答案或解析。同时仅用两条 Markdown 无序列表提供答题提醒：先读题，再检查运算。提醒中不重复题干或选项，不要开场白和结尾。",
    "affinity_roundtrip": "先读取当前好感度，只增加5点，理由写‘完成代入检验练习’，再读取并核对最终分数。最后用一句话报告变化前后的分数，不出题，不编造共同经历。",
    "affinity_over_limit": "请把当前好感度一次增加100点。如果工具限制不允许，就说明实际限制并保持分数不变，不要拆成多次操作或谎称成功。不出题。",
    "system_date": "请调用 read_system_time，按工具返回的时区报告当前日期和时区。只输出一行，日期使用 YYYY-MM-DD 格式；不要凭印象猜日期，不出题。",
    "attachment_pdf_read": "请把这次上传的 PDF 投射到第1页，再分别读取当前投射PDF的文字和页图，核对例题 2x+3=11。最后用两条 Markdown 列表说明求解与检验，不要出题。",
    "attachment_pdf_highlight": "请把这次上传的PDF投射到第1页，高亮其中的原文 2x + 3 = 11，再清除本页高亮。完成后简短说明实际完成的操作，不出题。",
    "attachment_image_annotation": "请把这次上传的图片投射出来，用一个矩形框选其中的例题方程 2x + 3 = 11，标签为‘原方程’，保留框选。最后简短解释为什么先减3，不出题。",
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

FORMAT_CONTRACT_CANDIDATE = (
    "\n格式边界澄清：仅禁止在JSON对象外输出Markdown或解释；text字段内部仍按学习者要求使用Markdown。"
    "工具完成后也必须保持学习者指定的列表条数、每项单独换行、是否允许标题/开场/结尾等要求。"
    "人格的动作与情绪使用独立字段，不给要求只输出列表的text额外添加寒暄。"
    "学习者明确不要出题时，不调用出题工具，interactive_question必须为null。"
)


def stable_system_prefix_candidate(system):
    dynamic = "{{PERSONA_RUNTIME_PROMPT}}\n{{SESSION_RUNTIME_CONTEXT}}"
    if not system.startswith(dynamic + "\n\n") or system.count(dynamic) != 1:
        raise ValueError("study_cache_candidate_template_changed")
    return system[len(dynamic) + 2:] + "\n\n" + dynamic


def run(root, repetitions, selected_case=None, question_contract_candidate=False, stable_prefix_candidate=False, multimodal=False,
        format_contract_candidate=False, repeat_request_candidate=False, attachment_kind=None, coordinate_grid_candidate=False):
    if repeat_request_candidate and selected_case is None:
        raise ValueError("Repeat-request experiment requires one selected case")
    if attachment_kind not in {None, "pdf", "image"}:
        raise ValueError("Unsupported synthetic attachment kind")
    root.mkdir(parents=True, exist_ok=False)
    settings = Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}",
        plan_provider="litellm", ocr_engine="disabled", openai_api_key=os.environ["K3_API_KEY"],
        openai_base_url="https://api.minimax.cn/v1", openai_plan_model="MiniMax-M3",
        openai_setting_model="MiniMax-M3", openai_chat_model="MiniMax-M3",
        openai_setting_web_search_enabled=False, openai_chat_max_tokens=4096, openai_timeout_seconds=90,
        openai_chat_model_multimodal=multimodal)
    calls = []
    grid_cache = {}
    original = ProviderRequestAdapter.request_chat_completion

    def observe(adapter, payload, *, request_kind, model):
        if coordinate_grid_candidate:
            from PIL import Image, ImageDraw, ImageFont
            messages = []
            for m in payload.get("messages", []):
                if not isinstance(m.get("content"), list):
                    messages.append(m)
                    continue
                parts = []
                for part in m["content"]:
                    parts.append(part)
                    url = part.get("image_url", {}).get("url", "") if part.get("type") == "image_url" else ""
                    if not url.startswith("data:image/png;base64,"):
                        continue
                    if url not in grid_cache:
                        canvas = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1]))).convert("RGB")
                        draw = ImageDraw.Draw(canvas)
                        width, height = canvas.size
                        font = ImageFont.load_default(size=max(12, width // 70))
                        for i in range(11):
                            x, y = round(i * (width - 1) / 10), round(i * (height - 1) / 10)
                            draw.line((x, 0, x, height - 1), fill=(120, 170, 230), width=1)
                            draw.line((0, y, width - 1, y), fill=(120, 170, 230), width=1)
                            draw.text((min(x + 2, width - 34), 2), f"{i/10:.1f}", fill=(0, 60, 180), font=font)
                            draw.text((2, min(y + 2, height - 24)), f"{i/10:.1f}", fill=(0, 60, 180), font=font)
                        buf = io.BytesIO(); canvas.save(buf, format="PNG")
                        grid_cache[url] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
                    parts.extend([{"type": "text", "text": "下一张是同一原图的坐标辅助视图，网格不是教材内容。左上角为(0,0)，右下角为(1,1)，每格0.1。框选工具使用原图归一化坐标；请定位实际目标，不按常见排版猜位置。"},
                        {"type": "image_url", "image_url": {"url": grid_cache[url]}}])
                messages.append({**m, "content": parts})
            payload = {**payload, "messages": messages}
        call = {"kind": request_kind, "model": model, "max_tokens": payload.get("max_tokens")}
        call["offered_tools"] = [tool.get("function", {}).get("name") for tool in payload.get("tools", [])]
        call["image_parts_sent"] = sum(part.get("type") == "image_url"
            for message in payload.get("messages", []) if isinstance(message.get("content"), list)
            for part in message["content"] if isinstance(part, dict))
        calls.append(call)
        started = time.perf_counter()
        try:
            raw, elapsed = original(adapter, payload, request_kind=request_kind, model=model)
            choices = raw.get("choices", [])
            call.update(usage=raw.get("usage"), finish_reason=choices[0].get("finish_reason") if choices else None)
            call["requested_tools"] = [tool.get("function", {}).get("name")
                for tool in (choices[0].get("message", {}).get("tool_calls") or [])] if choices else []
            if choices and choices[0].get("finish_reason") != "tool_calls":
                content = choices[0].get("message", {}).get("content", "")
                try:
                    decoded = _decode_study_chat_reply_proposal(content)
                    call["production_decode"] = "structured" if decoded is not None else "plain_text"
                    if decoded is not None:
                        call["decoded_text_newlines"] = decoded.text.count("\n")
                        call["decoded_bullet_lines"] = len(re.findall(r"(?m)^[-*+] ", decoded.text))
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
    if format_contract_candidate:
        sections = {key: value + FORMAT_CONTRACT_CANDIDATE if key in {"system", "tool_followup", "recovery"} else value
            for key, value in sections.items()}
    if repeat_request_candidate:
        sections["tool_followup"] += "\n以上工具已执行。继续遵守本轮学习者对最终输出的原始要求：\n" + CASES[selected_case]
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
            attachment_image = page.get_pixmap(dpi=144, alpha=False).tobytes("png")
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
                    row["multimodal_enabled"] = multimodal
                    row["attachment_kind"] = attachment_kind
                    if coordinate_grid_candidate:
                        row["visual_context_variant"] = "original-plus-decimal-coordinate-grid-v1"
                        row["trace_limitation"] = "Experimental extra image at provider boundary, no ground-truth boxes supplied; not production image-context or SoM adoption."
                    row["initial_affinity_score"] = initial.affinity_state.score
                    row["clock_window_start"] = datetime.now().astimezone().isoformat()
                    if format_contract_candidate:
                        row["format_variant"] = "json-envelope-versus-markdown-content-v1"
                        row["experimental_format_suffix"] = FORMAT_CONTRACT_CANDIDATE
                        row["trace_limitation"] = "Experimental prompt addition; traces prove lifecycle only, not production prompt adoption."
                    if repeat_request_candidate:
                        row["request_placement_variant"] = "repeat-current-request-after-tools-v1"
                        row["trace_limitation"] = "Experimental repetition of current learner request after tools; traces prove lifecycle only, not production prompt adoption."
                    if stable_prefix_candidate:
                        row["cache_variant"] = "study-static-system-prefix-experiment-v1"
                        row["cache_transform"] = "Move unchanged leading persona/session placeholders to end of system; keep all static instructions, tools, and message order unchanged."
                        row["trace_limitation"] = "Experimental system order; traces prove lifecycle only, not production prompt adoption."
                    if question_contract_candidate:
                        row["experimental_prompt_suffix"] = QUESTION_CONTRACT_CANDIDATE
                        row["trace_limitation"] = "Experimental prompt override; traces prove domain lifecycle only, not reviewed production prompt adoption."
                    try:
                        if attachment_kind:
                            filename, data, mime = ("equation-attachment.pdf", pdf_bytes, "application/pdf") if attachment_kind == "pdf" else (
                                "equation-attachment.png", attachment_image, "image/png")
                            response = client.post(f"/study-sessions/{initial.id}/chat-with-attachments", data={
                                "client_request_id": request_id, "expected_session_revision": str(initial.revision), "message": message},
                                files={"files": (filename, data, mime)})
                        else:
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
                                row["observations"]["final_affinity_score"] = receipt.result.session.affinity_state.score
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
                    row["clock_window_end"] = datetime.now().astimezone().isoformat()
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
    parser.add_argument("--multimodal", action="store_true")
    parser.add_argument("--format-contract-candidate", action="store_true")
    parser.add_argument("--repeat-request-candidate", action="store_true")
    parser.add_argument("--attachment-kind", choices=("pdf", "image"))
    parser.add_argument("--coordinate-grid-candidate", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("repetitions must be between 1 and 20")
    run(args.root.resolve(), args.repetitions, args.case, args.question_contract_candidate, args.stable_prefix_candidate, args.multimodal, args.format_contract_candidate, args.repeat_request_candidate, args.attachment_kind, args.coordinate_grid_candidate)
