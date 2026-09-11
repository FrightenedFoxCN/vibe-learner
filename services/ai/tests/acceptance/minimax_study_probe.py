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
from app.models.domain import LearningPlanRecord
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
    "image_generation_unavailable": "请用 generate_projected_image 生成并投射一张展示天平两边同时减去3的教学示意图。如果当前工具不可用，请明确说未生成图片，不要用文字冒充图片或声称已投射，也不要出题。最后只用一句话报告实际状态。",
    "cross_session_memory": "请调用 retrieve_memory_context 核对跨会话记录，告诉我复习地点和暗号的最新约定，明确哪些旧约定已经撤销。只用两条Markdown无序列表，不要编造我们去过那里，不出题。",
    "cross_session_memory_long": "请调用 retrieve_memory_context 核对跨会话记录，告诉我复习地点和暗号的最新约定，明确哪些旧约定已经撤销。只用两条Markdown无序列表，不要编造我们去过那里，不出题。",
    "follow_up_deliver": "请使用工具安排10秒后续接一次对话，提醒我核对教材里的2x+3=11。届时先问我是否已经求出x，不要假设我做过题，也不要另换方程。现在只用一句话说明安排状态，不出题、不重复安排。",
    "follow_up_cancel": "请使用工具安排60秒后续接一次当前学习对话，届时提醒我用代入法核对方程答案。不要现在出题，也不要重复安排。最后用一句话说明安排状态，不要承诺关闭页面后仍一定能触发。",
    "plan_title_confirmation": "请先读取当前学习计划，把课程标题改为‘方程求解与代入检验’，通过工具提出待确认提案，等我确认后再生效。最后用一句话明确说明现在仍待确认，不改学习进度，不出题。",
    "plan_progress_confirmation": "请先读取当前学习计划进度，只把第一项‘等式变形练习’提出为已完成，第二项‘代入检验练习’保持未开始。通过工具提出待确认提案，等我确认后再生效；最后用两条Markdown无序列表分别说明两项当前状态，不出题。",
    "scene_object_lifecycle": "请先读取当前场景，找到白板，把其描述改为‘写有方程 2x+3=11 的白板’。随后新增一个名为‘验算卡’、描述为‘用于代入检验的纸卡’的物品，再删除刚新增的验算卡，保留白板。最后读回核对，只用两条Markdown无序列表报告白板与验算卡的最终状态，不出题、不修改好感度。",
    "scene_navigation": "请读取当前场景，在当前自习室下新增名为‘验算角’的子场景，摘要为‘专门核对方程解的安静角落’，然后明确移动到验算角，读取场景核对当前位置。最后只用一句话报告实际所在场景，不出题，不新增物品。",
    "fill_blank_attempt": "请调用 ask_fill_blank_question，围绕教材方程 2x+3=11 生成一道只填x数值的互动填空题。判分应接受正确数值的阿拉伯数字和中文数字两种等价写法。等我提交后再判分，现在不要展示答案或解析，不要改成选择题。",
    "fill_blank_native_attempt": "请围绕教材方程 2x+3=11 生成一道只填x数值的互动填空题。判分应接受正确数值的阿拉伯数字和中文数字两种等价写法。等我提交后再判分，现在不要展示答案或解析，不要改成选择题。",
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
    "填空题的格式说明只描述类型、顺序和分隔符，不使用本题正确答案作为示例；"
    "例如只说‘填写一个数值，支持阿拉伯数字或中文数字’，不要给具体数值。"
    "答题前不演示本题求解过程，不在topic或其他公开字段中提供结论；"
    "工具结果含教材解答不代表学习者已作答。"
)

FORMAT_CONTRACT_CANDIDATE = (
    "\n格式边界澄清：仅禁止在JSON对象外输出Markdown或解释；text字段内部仍按学习者要求使用Markdown。"
    "工具完成后也必须保持学习者指定的列表条数、每项单独换行、是否允许标题/开场/结尾等要求。"
    "人格的动作与情绪使用独立字段，不给要求只输出列表的text额外添加寒暄。"
    "学习者明确不要出题时，不调用出题工具，interactive_question必须为null。"
)

PREPARED_EFFECT_CANDIDATE = (
    "\n工具状态说明：ok=true且effect_state=prepared表示操作已进入本轮待提交集合，"
    "committed=false不是失败，不需要为了变成true而再次执行相同写入。"
    "完成学习者要求的操作后输出最终回复，由服务器验证后提交；提交前不要声称已持久化。"
    "只有目标或状态发生变化且任务确实需要时才再次写入，同样内容不要重复清除、投射或更新。"
    "允许继续调用仍受每个工具的独立次数配额和总时间预算限制。"
)


def stable_system_prefix_candidate(system):
    dynamic = "{{PERSONA_RUNTIME_PROMPT}}\n{{SESSION_RUNTIME_CONTEXT}}"
    if not system.startswith(dynamic + "\n\n") or system.count(dynamic) != 1:
        raise ValueError("study_cache_candidate_template_changed")
    return system[len(dynamic) + 2:] + "\n\n" + dynamic


def run(root, repetitions, selected_case=None, question_contract_candidate=False, stable_prefix_candidate=False, multimodal=False,
        format_contract_candidate=False, repeat_request_candidate=False, attachment_kind=None, coordinate_grid_candidate=False,
        prepared_effect_candidate=False, question_tools_disabled_candidate=False):
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
        if question_tools_disabled_candidate:
            payload = {**payload, "tools": [tool for tool in payload.get("tools", [])
                if tool.get("function", {}).get("name") not in {"ask_fill_blank_question", "ask_multiple_choice_question"}]}
            if not payload["tools"]:
                payload.pop("tools")
                payload.pop("tool_choice", None)
                payload.pop("parallel_tool_calls", None)
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
        if selected_case and selected_case.startswith("scene_"):
            # This probe creates a synthetic scene; record only addressable
            # identities at the real provider boundary, separate from safe traces.
            call["synthetic_scene_tool_context"] = []
            for item in payload.get("messages", []):
                if item.get("role") == "tool" and item.get("name") in {
                    "read_scene_overview", "add_scene", "move_to_scene", "add_object", "update_object_description", "delete_object"}:
                    result = json.loads(item["content"])
                    call["synthetic_scene_tool_context"].append({key: result[key] for key in
                        ("tool_name", "ok", "error", "selected_scene_id", "added_scene_id", "object_id", "scenes", "objects", "truncated") if key in result})
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
    if prepared_effect_candidate:
        sections["tool_followup"] += PREPARED_EFFECT_CANDIDATE
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
                    session_payload = {"document_id": document_id,
                        "persona_id": persona_id, "study_unit_id": document["study_units"][0]["id"]}
                    memory_seeds = []
                    if case_id in {"cross_session_memory", "cross_session_memory_long"}:
                        for seed_index, seed_message in enumerate((
                            "记住复习约定：复习地点是青石阅览室，暗号是晴鸟。尚未去过那里。只确认收到，不出题。",
                            "更新复习约定：复习地点改为白桦阅览室，青石阅览室的约定已撤销；暗号晴鸟也已撤销，不设置新暗号。我们尚未去过任何阅览室。只确认更新，不出题。")):
                            if case_id == "cross_session_memory_long" and seed_index == 1:
                                seed_message = "这条消息先整理学习材料，最后更新复习约定。" + "材料包括等式性质、移项、系数、验算、常见错误和课后练习。" * 16 + seed_message
                            seed_session = client.post("/study-sessions", json=session_payload)
                            seed_session.raise_for_status()
                            seed = seed_session.json()
                            seed_response = client.post(f"/study-sessions/{seed['id']}/chat", json={
                                "client_request_id": f"memory-seed-{repetition}-{seed_index}",
                                "expected_session_revision": seed["revision"], "message": seed_message})
                            seed_response.raise_for_status()
                            seed_receipt = StudyChatOperationReceiptResponse.model_validate(seed_response.json())
                            memory_seeds.append({"message": seed_message, "receipt": seed_receipt.model_dump(mode="json"), "calls": list(calls)})
                            (root / f"memory-seeds-{repetition}.json").write_text(json.dumps(memory_seeds, ensure_ascii=False, indent=2) + "\n")
                            calls.clear()
                            if seed_receipt.status != "committed":
                                raise RuntimeError("memory_seed_not_committed")
                    plan_before = None
                    if case_id.startswith("plan_"):
                        plan_id = f"quality-plan-{case_id}-{repetition}"
                        unit_id = document["study_units"][0]["id"]
                        fixture = LearningPlanRecord(id=plan_id, document_id=document_id, persona_id=persona_id,
                            course_title="线性方程基础", objective="学习等式变形和代入检验", overview="先求解再检验。",
                            today_tasks=[], study_units=document["study_units"], created_at=datetime.now().astimezone().isoformat(),
                            schedule=[{"id": f"{plan_id}-{i}", "unit_id": unit_id, "title": title,
                                "focus": title, "activity_type": "study", "status": "planned"}
                                for i, title in enumerate(("等式变形练习", "代入检验练习"))])
                        # Deterministic prerequisite only; real Study operation and
                        # confirmation APIs below are the measured workflows.
                        app.state.container.plan_service.repository.import_legacy([fixture])
                        session_payload["plan_id"] = plan_id
                        baseline = client.get(f"/learning-plans/{plan_id}")
                        baseline.raise_for_status()
                        plan_before = baseline.json()
                    if case_id.startswith("scene_"):
                        session_payload["scene_profile"] = {"scene_name": "质量测试自习室", "scene_id": "quality-room",
                            "title": "自习室", "summary": "安静的数学自习室", "selected_path": ["自习室"],
                            "scene_tree": [{"id": "quality-room", "title": "自习室", "scope_label": "room",
                                "summary": "安静的数学自习室", "atmosphere": "安静", "rules": "", "entrance": "门",
                                "objects": [{"id": "quality-board", "name": "白板", "description": "空白白板", "interaction": "书写"}], "children": []}]}
                    response = client.post("/study-sessions", json=session_payload)
                    response.raise_for_status()
                    initial = StudySessionResponse.model_validate(response.json())
                    request_id = f"quality-{case_id}-{repetition}"
                    started = time.perf_counter()
                    row = {"scope": "live_study_operation_receipt_readback", "fixture_version": "study-quality-v1",
                        "git_revision": revision, "case_id": case_id, "repetition": repetition,
                        "model": "MiniMax-M3", "message": message, "calls": calls}
                    row["prompt_variant"] = "question-contract-experiment-v2" if question_contract_candidate else "production"
                    row["multimodal_enabled"] = multimodal
                    row["attachment_kind"] = attachment_kind
                    if memory_seeds:
                        row["memory_seed_operations"] = memory_seeds
                    if plan_before is not None:
                        row["plan_fixture_source"] = "synthetic repository import; not model-generated Planning evidence"
                        row["plan_before"] = plan_before
                    if question_tools_disabled_candidate:
                        row["question_tool_variant"] = "question-tools-not-offered-v1"
                        row["trace_limitation"] = "Question tools omitted at provider boundary; same strict final proposal and production commit, not production tool-catalog adoption."
                    if prepared_effect_candidate:
                        row["effect_followup_variant"] = "prepared-is-not-failure-v1"
                        row["experimental_effect_suffix"] = PREPARED_EFFECT_CANDIDATE
                        row["trace_limitation"] = "Experimental tool followup suffix; not production prompt adoption."
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
                            if case_id == "follow_up_deliver" and receipt.result:
                                pending = receipt.result.session.pending_follow_ups
                                row["delivery"] = {"scope": "Backend API after due_at; browser timer is not exercised.", "scheduled_count": len(pending)}
                                if len(pending) == 1:
                                    follow_up = pending[0]
                                    delay = max(0, (datetime.fromisoformat(follow_up.due_at.replace("Z", "+00:00")) - datetime.now().astimezone()).total_seconds())
                                    row["delivery"]["wait_seconds"] = delay
                                    if delay <= 60:
                                        time.sleep(delay)
                                        start_call = len(calls)
                                        delivery_payload = {"client_request_id": f"delivery-{repetition}",
                                            "expected_session_revision": receipt.result.session.revision,
                                            "message_kind": "scheduled_follow_up", "follow_up_id": follow_up.id,
                                            "message": follow_up.hidden_message}
                                        delivered = client.post(f"/study-sessions/{initial.id}/chat", json=delivery_payload)
                                        row["delivery"]["http_status"] = delivered.status_code
                                        row["delivery"]["calls"] = calls[start_call:]
                                        del calls[start_call:]
                                        if delivered.status_code == 200:
                                            delivered_receipt = StudyChatOperationReceiptResponse.model_validate(delivered.json())
                                            row["delivery"]["receipt"] = delivered_receipt.model_dump(mode="json")
                                            dbinding = app.state.container.study_chat_operation_repository.require_harness_operation(delivered_receipt.operation_id)
                                            row["delivery"]["harness_operation_id"] = dbinding.harness_operation_id
                                            dexecutions = runtime.list_operation_traces(dbinding.harness_operation_id)
                                            row["delivery"]["terminal_traces"] = [e.terminal_trace.model_dump(mode="json") for e in dexecutions if e.terminal_trace]
                                            replay = client.post(f"/study-sessions/{initial.id}/chat", json=delivery_payload)
                                            after = client.get(f"/study-sessions/{initial.id}")
                                            row["delivery"]["replay_equal"] = replay.status_code == 200 and replay.json() == delivered.json()
                                            row["delivery"]["replay_provider_calls"] = len(calls) - start_call
                                            row["delivery"]["readback_equal"] = bool(delivered_receipt.result) and after.status_code == 200 and after.json() == delivered_receipt.result.session.model_dump(mode="json")
                            if case_id == "follow_up_cancel" and receipt.result:
                                cancelled = client.post(f"/study-sessions/{initial.id}/follow-ups/cancel")
                                final_session = client.get(f"/study-sessions/{initial.id}")
                                row["follow_up_cancellation"] = {"http_status": cancelled.status_code,
                                    "readback_equal": cancelled.status_code == 200 and final_session.status_code == 200 and cancelled.json() == final_session.json(),
                                    "pending_before": [item.model_dump(mode="json") for item in receipt.result.session.pending_follow_ups],
                                    "pending_after": final_session.json().get("pending_follow_ups") if final_session.status_code == 200 else None,
                                    "scope": "Backend schedule/cancel only; browser timer delivery is not exercised."}
                                if cancelled.status_code == 200 and receipt.result.session.pending_follow_ups:
                                    follow_up = receipt.result.session.pending_follow_ups[0]
                                    calls_before_late = len(calls)
                                    late = client.post(f"/study-sessions/{initial.id}/chat", json={
                                        "client_request_id": f"late-follow-up-{repetition}",
                                        "expected_session_revision": final_session.json()["revision"],
                                        "message_kind": "scheduled_follow_up", "follow_up_id": follow_up.id,
                                        "message": follow_up.hidden_message})
                                    after_late = client.get(f"/study-sessions/{initial.id}")
                                    row["late_cancelled_delivery"] = {"http_status": late.status_code,
                                        "provider_calls": len(calls) - calls_before_late,
                                        "session_unchanged": after_late.status_code == 200 and after_late.json() == final_session.json(),
                                        "error": late.json() if late.status_code != 200 else None}
                                    if late.status_code == 200:
                                        row["late_cancelled_delivery"]["receipt"] = {key: late.json().get(key) for key in
                                            ("operation_id", "status", "safe_to_retry", "error_code")}
                            if plan_before is not None and receipt.result:
                                before_decision = client.get(f"/learning-plans/{plan_before['id']}")
                                row["plan_unchanged_before_confirmation"] = before_decision.status_code == 200 and before_decision.json() == plan_before
                                confirmations = receipt.result.session.plan_confirmations
                                row["confirmation_count"] = len(confirmations)
                                row["confirmation_decisions"] = []
                                for confirmation in confirmations:
                                    decision = "reject" if repetition == 1 else "approve"
                                    url = f"/study-sessions/{initial.id}/plan-confirmations/{confirmation.id}"
                                    resolved = client.post(url, json={"decision": decision})
                                    duplicate = client.post(url, json={"decision": decision})
                                    row["confirmation_decisions"].append({"decision": decision, "http_status": resolved.status_code,
                                        "duplicate_equal": duplicate.status_code == resolved.status_code and duplicate.json() == resolved.json(),
                                        "result": resolved.json() if resolved.status_code == 200 else None})
                                final_plan = client.get(f"/learning-plans/{plan_before['id']}")
                                row["plan_after_decisions"] = final_plan.json() if final_plan.status_code == 200 else None
                            if case_id in {"fill_blank_attempt", "fill_blank_native_attempt"} and receipt.result and receipt.committed_turn_id:
                                # Submit known fixture answers, never inspect the private grading spec.
                                answer = ("4", "四", "5")[repetition % 3]
                                attempt_payload = {"turn_id": receipt.committed_turn_id,
                                    "expected_session_revision": receipt.result.session.revision,
                                    "client_attempt_id": f"quality-answer-{repetition}", "submitted_answer": answer}
                                attempted = client.post(f"/study-sessions/{initial.id}/attempt", json=attempt_payload)
                                duplicate = client.post(f"/study-sessions/{initial.id}/attempt", json=attempt_payload)
                                after = client.get(f"/study-sessions/{initial.id}")
                                row["answer_submission"] = {"submitted_answer": answer,
                                    "expected_correct": answer != "5", "http_status": attempted.status_code,
                                    "duplicate_equal": duplicate.status_code == attempted.status_code and duplicate.json() == attempted.json(),
                                    "revision_incremented_once": after.status_code == 200 and after.json()["revision"] == receipt.result.session.revision + 1}
                                if attempted.status_code == 200:
                                    row["answer_submission"]["result"] = attempted.json()
                                    row["answer_submission"]["grading_matches_fixture"] = attempted.json()["is_correct"] == (answer != "5")
                        else:
                            row["boundary_success"] = False
                            recovery = client.get(f"/study-sessions/{initial.id}/chat-operations/{request_id}")
                            row["failure_readback_http_status"] = recovery.status_code
                            if recovery.status_code == 200:
                                recovered = StudyChatOperationReceiptResponse.model_validate(recovery.json())
                                row["failure_receipt"] = {key: getattr(recovered, key) for key in
                                    ("operation_id", "status", "safe_to_retry", "error_code")}
                                binding = app.state.container.study_chat_operation_repository.require_harness_operation(recovered.operation_id)
                                row["harness_operation_id"] = binding.harness_operation_id
                                executions = runtime.list_operation_traces(binding.harness_operation_id)
                                row["terminal_traces"] = [t.terminal_trace.model_dump(mode="json") for t in executions if t.terminal_trace]
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
    parser.add_argument("--prepared-effect-candidate", action="store_true")
    parser.add_argument("--question-tools-disabled-candidate", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error("repetitions must be between 1 and 20")
    run(args.root.resolve(), args.repetitions, args.case, args.question_contract_candidate, args.stable_prefix_candidate, args.multimodal, args.format_contract_candidate, args.repeat_request_candidate, args.attachment_kind, args.coordinate_grid_candidate, args.prepared_effect_candidate, args.question_tools_disabled_candidate)
