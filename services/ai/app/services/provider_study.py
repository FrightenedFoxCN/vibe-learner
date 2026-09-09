"""Study model generation, strict decoding, and bounded tool execution."""
from __future__ import annotations

from dataclasses import dataclass
from app.services.provider_capabilities import StudyModelCapability
from app.services.provider_transport import _coerce_int
from app.services.provider_capabilities import ModelReply
from app.services.provider_payload import _extract_choice_content
import json
import re
from typing import Callable
from typing import Any
from fastapi import HTTPException
from pydantic import ValidationError
from app.core.logging import get_logger
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.domain import ChatToolCallTraceRecord, DocumentDebugRecord, PersonaProfile, RichTextBlockRecord
from app.models.study_chat_reply import StudyChatReplyProposalV1
from app.models.study_chat_operation import StudyChatMessageKind
from app.models.study_question import StudyQuestionProposalV1
from app.models.tool_manifest import resolve_tool_manifest_entry
from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG
from app.services.model_recovery import record_model_recovery
from app.services.persona_runtime import render_persona_runtime_instruction
from app.services.tool_provider_projection import ProviderToolCallDecodeError, ToolContractViolation, ToolExecutionBudgetTracker, adapt_tool_runtime_result, build_versioned_tool_error, decode_provider_tool_call, project_tool_arguments_for_observability, project_validated_tool_result, provider_function_for_entry
from app.services.plan_prompt import read_page_range_content, read_page_range_images
from app.services.prompt_loader import load_prompt_template
from app.services.session_scene import SCENE_TOOL_NAMES, extract_scene_profile_from_tool_results, serialize_chat_tool_trace_item


@dataclass(frozen=True)
class RemoteStudyProvider(StudyModelCapability):
    chat_model: str
    chat_temperature: float
    chat_max_tokens: int
    chat_history_messages: int
    chat_tool_max_rounds: int
    chat_tools_enabled: bool
    chat_memory_tool_enabled: bool
    chat_multimodal_enabled: bool
    disabled_tools: frozenset[str]
    request: Callable[..., tuple[dict[str, Any], int]]

    def supports_chat_page_image_tools(self) -> bool:
        return self.chat_multimodal_enabled

    def chat_tools_runtime_enabled(self) -> bool:
        return self.chat_tools_enabled

    def chat_memory_tool_runtime_enabled(self) -> bool:
        return self.chat_memory_tool_enabled

    def generate_chat(
        self,
        *,
        persona: PersonaProfile,
        section_id: str,
        message: str,
        message_kind: StudyChatMessageKind = "learner",
        session_prompt: str = "",
        section_context: str = "",
        memory_context: str = "",
        attachment_context: str = "",
        learner_multimodal_parts: list[dict[str, Any]] | None = None,
        scene_context: str = "",
        active_plan_context: str = "",
        session_state_context: str = "",
        session_tool_runtime: Any | None = None,
        scene_tool_runtime: Any | None = None,
        plan_tool_runtime: Any | None = None,
        memory_trace_hits: list[dict[str, Any]] | None = None,
        conversation_history: list[dict[str, str]] | None = None,
        debug_report: DocumentDebugRecord | None = None,
        document_path: str | None = None,
    ) -> ModelReply:
        history = conversation_history or []
        persona_runtime_prompt = render_persona_runtime_instruction(persona)
        plan_tool_instruction = (
            "如需读取当前学习计划完成度，可调用 read_learning_plan_progress；如需提出计划结构修改或完成度更新建议，可调用 update_learning_plan、update_learning_plan_progress，但这些提案都必须等待用户确认后才会真正应用。"
            if plan_tool_runtime is not None
            else "当前会话没有绑定可操作的学习计划进度。"
        )
        session_tool_instruction = (
            "如需读取系统时间、读写临时记忆、调整好感度、安排稍后自动续接，或把会话中的 PDF/图片附件投到预览窗口并进行切页或标注，也可在当前模型支持时直接生成并投射一张图片；可调用 read_system_time、read_session_memory、write_session_memory、read_affinity_state、update_affinity_state、schedule_session_follow_up、project_uploaded_pdf、project_uploaded_image、generate_projected_image、read_projected_pdf_content、read_projected_pdf_images、focus_projected_pdf_page、highlight_projected_pdf_text、annotate_projected_pdf_region、clear_projected_pdf_overlays、annotate_projected_image_region、clear_projected_image_overlays。"
            if session_tool_runtime is not None
            else "当前会话没有启用额外的会话状态工具。"
        )
        scene_tool_instruction = (
            "如需读取或修改当前会话绑定场景，可调用 read_scene_overview、add_scene、move_to_scene、add_object、update_object_description、delete_object；所有场景修改都必须限制在当前会话绑定场景内。"
            if scene_tool_runtime is not None
            else "当前对话没有绑定可操作的会话场景。"
        )
        prompt_sections = _chat_prompt_sections()
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": prompt_sections["system"]
                .replace("{{PERSONA_RUNTIME_PROMPT}}", persona_runtime_prompt)
                .replace("{{SESSION_RUNTIME_CONTEXT}}", session_prompt.strip())
                .replace("{{CHAT_JSON_SCHEMA}}", CHAT_JSON_SCHEMA)
                .replace("{{PERSONA_EVENT_GUIDANCE}}", _build_persona_event_guidance(persona))
                .replace("{{PLAN_TOOL_INSTRUCTION}}", plan_tool_instruction)
                .replace("{{SESSION_TOOL_INSTRUCTION}}", session_tool_instruction)
                .replace("{{SCENE_TOOL_INSTRUCTION}}", scene_tool_instruction),
            }
        ]
        messages.extend(history[-self.chat_history_messages:])
        user_text = (
            prompt_sections["user"]
            .replace("{{SECTION_ID}}", section_id)
            .replace("{{SECTION_CONTEXT}}", section_context or "无")
            .replace("{{MEMORY_CONTEXT}}", memory_context or "无")
            .replace("{{ATTACHMENT_CONTEXT}}", attachment_context or "无")
            .replace("{{PLAN_CONTEXT}}", active_plan_context or "无")
            .replace("{{SESSION_STATE_CONTEXT}}", session_state_context or "无")
            .replace("{{SCENE_CONTEXT}}", scene_context or "无")
            .replace("{{LEARNER_MESSAGE}}", message)
            .replace("{{CHAT_JSON_SCHEMA}}", CHAT_JSON_SCHEMA)
        )
        user_content: Any = user_text
        if learner_multimodal_parts:
            user_content = [
                {"type": "text", "text": user_text},
                *learner_multimodal_parts,
            ]
        messages.append(
            {
                "role": "user",
                "content": user_content,
            }
        )

        current_messages = list(messages)
        raw_payload: dict[str, Any] | None = None
        last_tool_results: list[dict[str, Any]] = []
        last_application_tool_results: list[dict[str, Any]] = []
        tool_call_traces: list[ChatToolCallTraceRecord] = []
        tool_budget_tracker = ToolExecutionBudgetTracker()
        limited_rounds_used = 0
        total_rounds = 0
        max_total_rounds = max(
            self.chat_tool_max_rounds + CHAT_EXEMPT_TOOL_EXTRA_ROUNDS,
            self.chat_tool_max_rounds * 3,
        )
        while total_rounds < max_total_rounds:
            total_rounds += 1
            round_disabled_tools = _chat_tools_disabled_for_round(
                disabled_tools=set(self.disabled_tools),
                limited_rounds_used=limited_rounds_used,
                limited_rounds_max=self.chat_tool_max_rounds,
            )
            payload: dict[str, Any] = {
                "model": self.chat_model,
                "temperature": self.chat_temperature,
                "max_tokens": self.chat_max_tokens,
                "messages": current_messages,
            }
            tool_specs = _chat_tools(
                tools_enabled=self.chat_tools_enabled,
                memory_tool_enabled=self.chat_memory_tool_enabled,
                memory_hits=memory_trace_hits or [],
                multimodal_enabled=self.chat_multimodal_enabled,
                debug_report=debug_report,
                document_path=document_path,
                plan_tool_runtime=plan_tool_runtime,
                session_tool_runtime=session_tool_runtime,
                scene_tool_runtime=scene_tool_runtime,
                disabled_tools=round_disabled_tools,
            )
            if tool_specs:
                payload["tools"] = tool_specs
                payload["tool_choice"] = "auto"
                payload["parallel_tool_calls"] = False
            else:
                payload["response_format"] = {"type": "json_object"}

            raw_payload, _ = self.request(
                payload,
                request_kind="chat",
                model=self.chat_model,
            )
            choice = raw_payload["choices"][0]
            message_payload = choice["message"]
            tool_calls = message_payload.get("tool_calls") or []
            if tool_calls:
                tool_budget_tracker.begin_round()
                available_tool_names = {
                    str((tool.get("function") or {}).get("name") or "")
                    for tool in tool_specs
                }
                current_messages.append(
                    {
                        "role": "assistant",
                        "content": message_payload.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                )
                for tool_call in tool_calls:
                    execution = _execute_chat_tool_call(
                        tool_call,
                        section_id=section_id,
                        section_context=section_context,
                        learner_message=message,
                        memory_hits=memory_trace_hits or [],
                        debug_report=debug_report,
                        document_path=document_path,
                        plan_tool_runtime=plan_tool_runtime,
                        session_tool_runtime=session_tool_runtime,
                        scene_tool_runtime=scene_tool_runtime,
                        disabled_tools=round_disabled_tools,
                        available_tool_names=available_tool_names,
                        budget_tracker=tool_budget_tracker,
                    )
                    last_tool_results.append(execution["result"])
                    last_application_tool_results.append(
                        execution["application_result"]
                    )
                    tool_call_traces.append(
                        ChatToolCallTraceRecord.model_validate(
                            serialize_chat_tool_trace_item(
                                tool_call_id=execution["tool_call_id"],
                                tool_name=execution["tool_name"],
                                arguments_json=execution["arguments_json"],
                                result=execution["public_result"],
                                argument_contract_version=execution[
                                    "argument_contract_version"
                                ],
                                result_contract_version=execution[
                                    "result_contract_version"
                                ],
                            )
                        )
                    )
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": execution["tool_call_id"],
                            "name": execution["tool_name"],
                            "content": json.dumps(
                                execution["provider_result"],
                                ensure_ascii=False,
                            ),
                        }
                    )
                exempt_only_round = _round_uses_only_exempt_chat_tools(tool_calls)
                if not exempt_only_round:
                    limited_rounds_used += 1
                current_messages.append(
                    {
                        "role": "user",
                        "content": prompt_sections["tool_followup"]
                        .replace("{{CHAT_JSON_SCHEMA}}", CHAT_JSON_SCHEMA)
                        .replace("{{TOOL_FOLLOWUP_RULES}}", _chat_tool_followup_rules(exempt_only_round=exempt_only_round)),
                    }
                )
                continue
            break

        if raw_payload is None:
            raise RuntimeError("chat_model_invalid_payload")

        try:
            finish_reason, _, _ = _extract_choice_diagnostics(raw_payload)
            if finish_reason == "content_filter":
                raise RuntimeError("chat_model_content_filter")
            return _parse_chat_model_reply(
                raw_payload=raw_payload,
                tool_results=last_tool_results,
                application_tool_results=last_application_tool_results,
                fallback_memory_trace=memory_trace_hits or [],
                tool_traces=tool_call_traces,
            )
        except RuntimeError as exc:
            recovery_reason = str(exc)
            if recovery_reason not in {
                "chat_model_invalid_payload",
                "chat_model_content_filter",
            }:
                raise
            logger.warning("model.chat.recovery retry_without_tools reason=%s", recovery_reason)
            recovery_messages = list(current_messages)
            try:
                invalid_content = _extract_choice_content(raw_payload).strip()
            except RuntimeError:
                invalid_content = ""
            if invalid_content:
                recovery_messages.append(
                    {"role": "assistant", "content": invalid_content}
                )
            recovery_messages.append(
                {
                    "role": "user",
                    "content": _build_chat_recovery_instruction(
                        reason=recovery_reason,
                        prompt_sections=prompt_sections,
                    ).replace("{{CHAT_JSON_SCHEMA}}", CHAT_JSON_SCHEMA),
                }
            )
            recovery_payload: dict[str, Any] = {
                "model": self.chat_model,
                "temperature": min(self.chat_temperature, 0.2),
                "max_tokens": max(self.chat_max_tokens, 1600),
                "messages": recovery_messages,
                "response_format": {"type": "json_object"},
            }
            recovery_raw_payload, _ = self.request(
                recovery_payload,
                request_kind="chat",
                model=self.chat_model,
            )
            recovered = _parse_chat_model_reply(
                raw_payload=recovery_raw_payload,
                tool_results=last_tool_results,
                application_tool_results=last_application_tool_results,
                fallback_memory_trace=memory_trace_hits or [],
                tool_traces=tool_call_traces,
            )
            record_model_recovery(
                category="semantic_retry",
                reason=recovery_reason,
                strategy="retry_without_tools",
                attempts=2,
            )
            return recovered



logger = get_logger("vibe_learner.model_provider")



MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\s*\n(.*?)```|```\s*\nmermaid\s*\n(.*?)```",
    re.IGNORECASE | re.DOTALL,
)



CHAT_JSON_FENCE_RE = re.compile(
    r"\A```(?P<language>[A-Za-z0-9_-]*)[ \t]*\r?\n"
    r"(?P<body>.*?)\r?\n?```[ \t]*\Z",
    re.DOTALL,
)



CHAT_JSON_KEY_RE = re.compile(
    r'''(?ix)
    (?:
        ["'](?:
            text|mood|action|speech_style|delivery_cue|state_commentary|
            rich_blocks|interactive_question|question_type|prompt|difficulty|
            topic|options|call_back|answer_key|accepted_answers|grading_spec|
            correct_option_key|normalization_policy|submitted_answer|
            normalized_answer|explanation|is_correct|feedback|feedback_text
        )["']
        |
        \b(?:
            answer_key|accepted_answers|grading_spec|correct_option_key|
            normalization_policy|submitted_answer|normalized_answer|is_correct|
            feedback_text
        )\b
    )\s*:
    ''',
)



CHAT_PRIVATE_GRADING_KEY_RE = re.compile(
    r'''(?ix)
    (?:
        ["'](?:
            answer_key|accepted_answers|grading_spec|correct_option_key|
            normalization_policy|submitted_answer|normalized_answer|is_correct|
            explanation|feedback|feedback_text
        )["']
        |
        \b(?:
            answer_key|accepted_answers|grading_spec|correct_option_key|
            normalization_policy|submitted_answer|normalized_answer|is_correct|
            feedback_text
        )\b
    )\s*:
    ''',
)



CHAT_BARE_REPLY_KEY_RE = re.compile(
    r"(?ix)\b(?P<key>text|mood|action)\b\s*(?::|=)"
)



CHAT_JSON_SCHEMA = (
    '{'
    '"text": string, '
    '"mood": string, '
    '"action": string, '
    '"speech_style"?: string, '
    '"delivery_cue"?: string, '
    '"state_commentary"?: string, '
    '"rich_blocks"?: [{"kind": string, "content": string}], '
    '"interactive_question"?: {'
    '"question_type": "multiple_choice" | "fill_blank", '
    '"prompt": string, '
    '"difficulty"?: "easy" | "medium" | "hard", '
    '"topic"?: string, '
    '"options"?: [{"key": string, "text": string}], '
    '"call_back"?: boolean, '
    '"answer_key"?: string, '
    '"accepted_answers"?: [string], '
    '"explanation"?: string'
    '}'
    '}'
)



CHAT_EXEMPT_TOOL_NAMES = frozenset(
    (
        "read_page_range_content",
        "read_page_range_images",
        "project_uploaded_pdf",
        "project_uploaded_image",
        "read_projected_pdf_content",
        "read_projected_pdf_images",
        "focus_projected_pdf_page",
        "highlight_projected_pdf_text",
        "annotate_projected_pdf_region",
        "clear_projected_pdf_overlays",
        "annotate_projected_image_region",
        "clear_projected_image_overlays",
        *SCENE_TOOL_NAMES,
    )
)



CHAT_EXEMPT_TOOL_EXTRA_ROUNDS = 12



def _chat_prompt_sections() -> dict[str, str]:
    template = load_prompt_template("openai_chat_prompt.txt")
    return {
        "system": template.require("system"),
        "user": template.require("user"),
        "tool_followup": template.require("tool_followup"),
        "recovery": template.require("recovery"),
    }



def _build_chat_recovery_instruction(*, reason: str, prompt_sections: dict[str, str]) -> str:
    base = prompt_sections["recovery"]
    if reason == "chat_model_content_filter":
        return (
            "上一次输出被内容过滤截断。请改为更克制、更教学化的表达，不要生成多余铺陈，只输出一个合法 JSON 对象。\n\n"
            + base
        )
    return base



def _chat_tool_name(tool_call: dict[str, Any]) -> str:
    function_payload = tool_call.get("function") or {}
    return str(function_payload.get("name") or "").strip()



def _round_uses_only_exempt_chat_tools(tool_calls: list[dict[str, Any]]) -> bool:
    tool_names = [_chat_tool_name(tool_call) for tool_call in tool_calls]
    valid_tool_names = [tool_name for tool_name in tool_names if tool_name]
    return bool(valid_tool_names) and all(tool_name in CHAT_EXEMPT_TOOL_NAMES for tool_name in valid_tool_names)



def _chat_tools_disabled_for_round(
    *,
    disabled_tools: set[str],
    limited_rounds_used: int,
    limited_rounds_max: int,
) -> set[str]:
    if limited_rounds_used < limited_rounds_max:
        return disabled_tools
    return disabled_tools | {
        tool_name
        for tool_name in TOOL_CATALOG[CHAT_STAGE]
        if tool_name not in CHAT_EXEMPT_TOOL_NAMES
    }



def _chat_tool_followup_rules(*, exempt_only_round: bool) -> str:
    if exempt_only_round:
        return (
            "- 如果还需要与场景继续互动，或继续翻看课本页、图表、公式，可以继续调用对应工具；这类轮次不计入常规工具调用限制，也允许重复调用。\n"
            "- 除非确实需要记忆检索或出题，否则优先继续用场景互动和课本页面读取把讲解补足。"
        )
    return (
        "- 如果信息已经足够，直接输出最终结果；除非确有必要，不要继续调用记忆检索或出题等常规工具。\n"
        "- 与场景互动和读取课本页面相关的工具不受这条抑制：它们仍可继续调用，且允许重复调用。"
    )



def _dedupe_rich_blocks(blocks: list[RichTextBlockRecord]) -> list[RichTextBlockRecord]:
    result: list[RichTextBlockRecord] = []
    seen: set[tuple[str, str]] = set()
    for block in blocks:
        key = (block.kind.strip().lower(), block.content.strip())
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(
            RichTextBlockRecord(
                kind=block.kind.strip(),
                content=block.content.strip(),
            )
        )
    return result



def _extract_rich_blocks_payload(parsed: dict[str, object]) -> list[RichTextBlockRecord]:
    raw_blocks = parsed.get("rich_blocks")
    if not isinstance(raw_blocks, list):
        return []
    result: list[RichTextBlockRecord] = []
    for item in raw_blocks:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        content = str(item.get("content") or "").strip()
        if not kind or not content:
            continue
        result.append(RichTextBlockRecord(kind=kind, content=content))
    return _dedupe_rich_blocks(result)



def _extract_mermaid_blocks_from_text(text: str) -> tuple[str, list[RichTextBlockRecord]]:
    blocks: list[RichTextBlockRecord] = []

    def replace(match: re.Match[str]) -> str:
        content = (match.group(1) or match.group(2) or "").strip()
        if content:
            blocks.append(RichTextBlockRecord(kind="mermaid", content=content))
        return "\n\n"

    cleaned = MERMAID_BLOCK_RE.sub(replace, text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned, _dedupe_rich_blocks(blocks)



def _normalize_reply_text_and_blocks(
    *,
    text: str,
    rich_blocks: list[RichTextBlockRecord],
) -> tuple[str, list[RichTextBlockRecord]]:
    cleaned_text, inline_blocks = _extract_mermaid_blocks_from_text(text)
    merged = _dedupe_rich_blocks([*rich_blocks, *inline_blocks])
    return cleaned_text, merged



def _build_persona_event_guidance(persona: PersonaProfile) -> str:
    available_emotions = ", ".join(persona.available_emotions) or "calm, encouraging, serious"
    available_actions = ", ".join(persona.available_actions) or "nod, point, lean_in"
    default_speech_style = persona.default_speech_style or "steady"
    return (
        f"- 优先从这些情绪词中挑选最贴合当前回答的一项，必要时也可自定义更细的情绪：{available_emotions}。\n"
        f"- 可参考这些常见动作示例，但不要被它们限制：{available_actions}。\n"
        "- `action` 请写成一条简短中文动作短句，像舞台说明，例如“微微前倾，抬手点向黑板右侧”“停笔片刻，像是在等你补全下一步”。\n"
        "- `action` 必须描述可视化的肢体动作、手势、姿态、视线或节奏停顿；不要只写“讲解”“追问”“纠错”“鼓励”这类抽象话语功能词。\n"
        "- 如果正在与场景互动，或正在翻看课本页、图表、公式，鼓励把讲解焦点压缩进 `action`，例如“翻到第 12 页，指着图 2-3 的箭头逐项对照”“伸手扶住实验台边缘，示意物块受力方向”。\n"
        f"- `speech_style` 默认参考 `{default_speech_style}`，但可按当前互动切换成更具体的语气标签。\n"
        "- `delivery_cue` 用一句中文短语描述语气、节奏或停顿方式，例如“先压低语速，再逐步抬高强调”。\n"
        "- `state_commentary` 用一句中文短句解释本轮状态变化、场景操作结果或当前陪伴策略。"
    )



def _chat_tools(
    *,
    tools_enabled: bool,
    memory_tool_enabled: bool,
    memory_hits: list[dict[str, Any]],
    multimodal_enabled: bool,
    debug_report: DocumentDebugRecord | None,
    document_path: str | None,
    plan_tool_runtime: Any | None = None,
    session_tool_runtime: Any | None = None,
    scene_tool_runtime: Any | None = None,
    disabled_tools: set[str] | None = None,
) -> list[dict[str, object]]:
    if not tools_enabled:
        return []
    names = ["ask_multiple_choice_question", "ask_fill_blank_question"]
    if memory_tool_enabled and memory_hits:
        names.append("retrieve_memory_context")
    if debug_report is not None:
        names.append("read_page_range_content")
    if multimodal_enabled and debug_report is not None and document_path:
        names.append("read_page_range_images")
    for runtime in (plan_tool_runtime, session_tool_runtime, scene_tool_runtime):
        if runtime is None:
            continue
        available_names = getattr(runtime, "available_tool_names", None)
        if not callable(available_names):
            raise RuntimeError("study_tool_runtime_availability_contract_missing")
        names.extend(str(name) for name in available_names())
    disabled = disabled_tools or set()
    projected: list[dict[str, object]] = []
    seen: set[str] = set()
    for name in names:
        if name in disabled or name in seen:
            continue
        entry = resolve_tool_manifest_entry(
            workflow=HarnessWorkflow.STUDY_CHAT,
            offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
            transport_name=name,
        )
        catalog_description = TOOL_CATALOG[CHAT_STAGE][entry.canonical_name]["description"]
        if catalog_description != entry.display.provider_description:
            raise RuntimeError("study_tool_description_manifest_mismatch")
        projected.append(provider_function_for_entry(entry).model_dump(mode="json"))
        seen.add(entry.canonical_name)
    return projected



def _execute_chat_tool_call(
    tool_call: dict[str, Any],
    *,
    section_id: str,
    section_context: str,
    learner_message: str,
    memory_hits: list[dict[str, Any]],
    debug_report: DocumentDebugRecord | None,
    document_path: str | None,
    plan_tool_runtime: Any | None = None,
    session_tool_runtime: Any | None = None,
    scene_tool_runtime: Any | None = None,
    disabled_tools: set[str] | None = None,
    available_tool_names: set[str] | None = None,
    budget_tracker: ToolExecutionBudgetTracker | None = None,
) -> dict[str, Any]:
    transport_id = tool_call.get("id") if isinstance(tool_call.get("id"), str) else ""
    function_payload = tool_call.get("function")
    raw_name = (
        function_payload.get("name")
        if isinstance(function_payload, dict)
        and isinstance(function_payload.get("name"), str)
        else ""
    )
    try:
        decoded = decode_provider_tool_call(
            tool_call,
            workflow=HarnessWorkflow.STUDY_CHAT,
            offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
        )
    except ProviderToolCallDecodeError as error:
        return _chat_tool_error_execution(
            tool_call_id=transport_id,
            tool_name=raw_name,
            error=_study_decode_error_code(error.code),
            path=list(error.path),
            detail=error.detail,
        )
    entry = resolve_tool_manifest_entry(
        workflow=HarnessWorkflow.STUDY_CHAT,
        offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
        transport_name=decoded.canonical_name,
    )
    tool_name = entry.canonical_name
    if available_tool_names is None:
        available_tool_names = _runtime_available_chat_tool_names(
            memory_hits=memory_hits,
            debug_report=debug_report,
            document_path=document_path,
            plan_tool_runtime=plan_tool_runtime,
            session_tool_runtime=session_tool_runtime,
            scene_tool_runtime=scene_tool_runtime,
        )
    if tool_name in (disabled_tools or set()) or tool_name not in available_tool_names:
        return _chat_tool_error_execution(
            tool_call_id=decoded.transport_correlation_id,
            tool_name=tool_name,
            error="tool_unavailable",
            path=["function", "name"],
            detail="tool is not available in this Study Chat context",
            entry=entry,
            arguments=decoded.arguments,
        )
    tracker = budget_tracker or ToolExecutionBudgetTracker()
    try:
        tracker.admit(entry)
    except ToolContractViolation as error:
        return _chat_tool_error_execution(
            tool_call_id=decoded.transport_correlation_id,
            tool_name=tool_name,
            error=error.code,
            path=[],
            detail=error.detail,
            entry=entry,
            arguments=decoded.arguments,
        )
    arguments = decoded.arguments.model_dump(mode="python")
    if tool_name == "ask_multiple_choice_question":
        raw_result = _build_multiple_choice_question(
            section_id=section_id,
            section_context=section_context,
            learner_message=learner_message,
            arguments=arguments,
        )
    elif tool_name == "ask_fill_blank_question":
        raw_result = _build_fill_blank_question(
            section_id=section_id,
            section_context=section_context,
            learner_message=learner_message,
            arguments=arguments,
        )
    elif tool_name == "read_page_range_content":
        raw_result = {
            "ok": True,
            "tool_name": tool_name,
            "section_id": section_id,
            **read_page_range_content(
                debug_report=debug_report,
                page_start=arguments["page_start"],
                page_end=arguments["page_end"],
                max_chars=arguments["max_chars"],
            ),
        }
    elif tool_name == "read_page_range_images":
        raw_result = {
            "ok": True,
            "tool_name": tool_name,
            "section_id": section_id,
            **read_page_range_images(
                document_path=document_path,
                page_start=arguments["page_start"],
                page_end=arguments["page_end"],
                max_images=arguments["max_images"],
            ),
        }
    elif tool_name == "retrieve_memory_context":
        top_k = arguments["top_k"]
        raw_result = {
            "ok": True,
            "tool_name": tool_name,
            "section_id": section_id,
            "hit_count": min(len(memory_hits), top_k),
            "hits": memory_hits[:top_k],
        }
    else:
        runtime = _runtime_for_study_tool(
            tool_name,
            plan_tool_runtime=plan_tool_runtime,
            session_tool_runtime=session_tool_runtime,
            scene_tool_runtime=scene_tool_runtime,
        )
        try:
            raw_result = runtime.execute_tool(tool_name, arguments)
        except HTTPException as error:
            raw_result = {
                "ok": False,
                "error": str(error.detail),
                "tool_name": tool_name,
            }
    validated = adapt_tool_runtime_result(entry, raw_result)
    canonical = validated.model_dump(mode="json")
    return {
        "tool_call_id": decoded.transport_correlation_id,
        "tool_name": tool_name,
        "arguments_json": project_tool_arguments_for_observability(
            entry,
            decoded.arguments,
        ),
        "argument_contract_version": entry.input_contract.version,
        "result_contract_version": entry.result_contract.version,
        "result": canonical,
        "application_result": dict(raw_result),
        "provider_result": project_validated_tool_result(
            entry,
            validated,
            audience="provider",
        ),
        "trace_result": project_validated_tool_result(
            entry,
            validated,
            audience="trace",
        ),
        "public_result": project_validated_tool_result(
            entry,
            validated,
            audience="public",
        ),
    }



def _runtime_available_chat_tool_names(
    *,
    memory_hits: list[dict[str, Any]],
    debug_report: DocumentDebugRecord | None,
    document_path: str | None,
    plan_tool_runtime: Any | None,
    session_tool_runtime: Any | None,
    scene_tool_runtime: Any | None,
) -> set[str]:
    names = {"ask_multiple_choice_question", "ask_fill_blank_question"}
    if memory_hits:
        names.add("retrieve_memory_context")
    if debug_report is not None:
        names.add("read_page_range_content")
    if debug_report is not None and document_path:
        names.add("read_page_range_images")
    for runtime in (plan_tool_runtime, session_tool_runtime, scene_tool_runtime):
        if runtime is None:
            continue
        available_names = getattr(runtime, "available_tool_names", None)
        if callable(available_names):
            names.update(str(name) for name in available_names())
    return names



def _runtime_for_study_tool(
    tool_name: str,
    *,
    plan_tool_runtime: Any | None,
    session_tool_runtime: Any | None,
    scene_tool_runtime: Any | None,
) -> Any:
    for runtime in (session_tool_runtime, plan_tool_runtime, scene_tool_runtime):
        if runtime is not None and tool_name in set(runtime.available_tool_names()):
            return runtime
    raise RuntimeError("study_tool_runtime_missing")



def _chat_tool_error_execution(
    *,
    tool_call_id: str,
    tool_name: str,
    error: str,
    path: list[str | int],
    detail: str,
    entry: Any | None = None,
    arguments: Any | None = None,
) -> dict[str, Any]:
    result = build_versioned_tool_error(
        workflow=HarnessWorkflow.STUDY_CHAT,
        tool_name=tool_name,
        error=error,
        path=path,
        detail=detail,
    )
    canonical = result.model_dump(mode="json")
    if entry is not None:
        provider_result = project_validated_tool_result(
            entry,
            result,
            audience="provider",
        )
        trace_result = project_validated_tool_result(
            entry,
            result,
            audience="trace",
        )
        public_result = project_validated_tool_result(
            entry,
            result,
            audience="public",
        )
        arguments_json = (
            project_tool_arguments_for_observability(entry, arguments)
            if arguments is not None
            else json.dumps(
                {"contract_version": entry.input_contract.version, "redacted": True},
                separators=(",", ":"),
            )
        )
        argument_version = entry.input_contract.version
        result_version = entry.result_contract.version
        canonical_name = entry.canonical_name
    else:
        safe_error = {
            "schema_version": canonical["schema_version"],
            "ok": False,
            "tool_name": canonical["tool_name"],
            "error": canonical["error"],
        }
        provider_result = safe_error
        trace_result = safe_error
        public_result = safe_error
        arguments_json = (
            '{"contract_version":"study-chat-tool-arguments-v1","redacted":true}'
        )
        argument_version = "study-chat-tool-arguments-v1"
        result_version = "study-chat-tool-result-v1"
        canonical_name = tool_name or "unknown_tool"
    return {
        "tool_call_id": tool_call_id,
        "tool_name": canonical_name,
        "arguments_json": arguments_json,
        "argument_contract_version": argument_version,
        "result_contract_version": result_version,
        "result": canonical,
        "application_result": canonical,
        "provider_result": provider_result,
        "trace_result": trace_result,
        "public_result": public_result,
    }



def _study_decode_error_code(code: str) -> str:
    if code == "tool_arguments_json_invalid":
        return "tool_argument_invalid_json"
    if code in {
        "provider_function_call_shape_invalid",
        "tool_arguments_object_required",
        "tool_arguments_json_string_required",
        "tool_arguments_contract_invalid",
        "tool_arguments_duplicate_key",
        "tool_arguments_nonfinite",
    }:
        return "tool_argument_schema_invalid"
    if code == "tool_arguments_budget_exceeded":
        return "tool_argument_budget_exceeded"
    if code == "tool_manifest_tool_unknown":
        return "unknown_tool"
    return code



def _build_multiple_choice_question(
    *,
    section_id: str,
    section_context: str,
    learner_message: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    topic = _tool_topic(arguments, section_context, learner_message, default=section_id)
    difficulty = str(arguments.get("difficulty") or "medium")
    focus_mode = str(arguments.get("focus_mode") or "deep_understanding")
    option_count = int(arguments.get("option_count") or 4)
    option_count = max(3, min(option_count, 5))
    correct_option = "A"
    options = [
        {
            "key": chr(ord("A") + index),
            "text": _mcq_option_text(topic, section_context, index, correct_option == chr(ord("A") + index)),
        }
        for index in range(option_count)
    ]
    return {
        "ok": True,
        "question_type": "multiple_choice",
        "difficulty": difficulty,
        "topic": topic,
        "question": f"围绕 {topic}，以下哪项最能体现{_focus_label(focus_mode)}？",
        "options": options,
        "call_back": True,
        "answer_key": correct_option,
        "explanation": f"本题关注{_focus_label(focus_mode)}。结合当前章节上下文，{topic} 的正确表述应与教材中的关键条件和因果关系保持一致。",
        "source_context": _summarize_section_context(section_context),
    }



def _build_fill_blank_question(
    *,
    section_id: str,
    section_context: str,
    learner_message: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    topic = _tool_topic(arguments, section_context, learner_message, default=section_id)
    difficulty = str(arguments.get("difficulty") or "medium")
    focus_mode = str(arguments.get("focus_mode") or "deep_understanding")
    blank_count = int(arguments.get("blank_count") or 1)
    blank_count = max(1, min(blank_count, 3))
    blanks = " ".join("______" for _ in range(blank_count))
    return {
        "ok": True,
        "question_type": "fill_blank",
        "difficulty": difficulty,
        "topic": topic,
        "question": f"请补全：围绕 {topic} 的{_focus_label(focus_mode)}表述是 {blanks}。",
        "call_back": True,
        "answer": f"{topic} 的核心概念应根据教材上下文补全。",
        "explanation": f"本题关注{_focus_label(focus_mode)}。回到当前章节，围绕 {topic} 的关键条件、限定语或推理关系进行补写。",
        "source_context": _summarize_section_context(section_context),
    }



def _tool_topic(
    arguments: dict[str, Any],
    section_context: str,
    learner_message: str,
    *,
    default: str,
) -> str:
    candidate = str(arguments.get("topic") or "").strip()
    if candidate:
        return candidate
    context_title = _extract_scope_title(section_context)
    if context_title:
        return context_title
    message_title = _extract_topic_hint(learner_message)
    if message_title:
        return message_title
    return default



def _mcq_option_text(topic: str, section_context: str, index: int, is_correct: bool) -> str:
    if is_correct:
        return f"关于 {topic} 的表述与教材定义一致。"
    distractors = [
        f"{topic} 是一个与当前章节无关的概念。",
        f"{topic} 与教材中的定义方向相反。",
        f"{topic} 只适用于例题，不适用于概念理解。",
        f"{topic} 可以被任意替换而不影响结论。",
    ]
    return distractors[index % len(distractors)]



def _summarize_section_context(section_context: str) -> str:
    lines = [line.strip() for line in section_context.splitlines() if line.strip()]
    if not lines:
        return section_context
    return lines[0]



def _extract_scope_title(section_context: str) -> str:
    match = re.search(r"^(?:章节|Section)[:：]\s*(.+?)\s*\(", section_context, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""



def _extract_topic_hint(learner_message: str) -> str:
    trimmed = learner_message.strip()
    if not trimmed:
        return ""
    if len(trimmed) <= 18:
        return trimmed
    return trimmed[:18].rstrip("，。！？,. ")



def _focus_label(focus_mode: str) -> str:
    if focus_mode == "detail":
        return "细节辨析"
    return "深度理解"



def _sanitize_reply_text_for_question(
    text: str,
    question: StudyQuestionProposalV1 | None,
) -> str:
    if not question:
        return text
    cleaned = text
    prompt = question.prompt
    if prompt and prompt in cleaned:
        cleaned = cleaned.replace(prompt, "")
    for option in question.options:
        option_text = option.text
        if option_text and option_text in cleaned:
            cleaned = cleaned.replace(option_text, "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return "请先完成题目，再告诉我你的解题思路，我会继续追问关键细节。"
    return cleaned



def _extract_interactive_question_payload(
    *,
    parsed: dict[str, object],
    tool_results: list[dict[str, Any]],
) -> StudyQuestionProposalV1 | None:
    payload = parsed.get("interactive_question")
    if isinstance(payload, dict):
        normalized = _normalize_interactive_question(payload)
        if normalized is None:
            raise RuntimeError("chat_model_invalid_interactive_question")
        return normalized

    for result in reversed(tool_results):
        if "question_type" not in result:
            continue
        normalized = _normalize_interactive_question(result)
        if normalized is None:
            raise RuntimeError("chat_model_invalid_interactive_question")
        return normalized
    return None



def _normalize_interactive_question(
    payload: dict[str, Any],
) -> StudyQuestionProposalV1 | None:
    question_type = str(payload.get("question_type") or "").strip().lower()
    prompt = str(payload.get("prompt") or payload.get("question") or "").strip()
    if question_type not in {"multiple_choice", "fill_blank"} or not prompt:
        return None

    topic = str(payload.get("topic") or "").strip()
    difficulty = str(payload.get("difficulty") or "medium").strip() or "medium"
    explanation = str(payload.get("explanation") or "").strip()
    call_back = bool(payload.get("call_back"))

    options: list[dict[str, str]] = []
    raw_options = payload.get("options")
    if isinstance(raw_options, list):
        for index, option in enumerate(raw_options):
            if not isinstance(option, dict):
                return None
            key = str(option.get("key") or chr(ord("A") + index)).strip() or chr(ord("A") + index)
            text = str(option.get("text") or "").strip()
            if text:
                options.append({"key": key, "text": text})

    answer_key_raw = str(payload.get("answer_key") or "").strip()
    answer_key = answer_key_raw if answer_key_raw else None

    accepted_answers: list[str] = []
    raw_answer = payload.get("answer")
    if isinstance(raw_answer, str) and raw_answer.strip():
        accepted_answers.append(raw_answer.strip())
    raw_accepted = payload.get("accepted_answers")
    if isinstance(raw_accepted, list):
        for item in raw_accepted:
            if isinstance(item, str) and item.strip():
                accepted_answers.append(item.strip())

    if question_type == "multiple_choice" and not options:
        return None
    if question_type == "fill_blank" and not accepted_answers:
        fallback_answer = str(payload.get("answer_key") or "").strip()
        if fallback_answer:
            accepted_answers.append(fallback_answer)

    try:
        return StudyQuestionProposalV1.model_validate(
            {
                "question_type": question_type,
                "prompt": prompt,
                "difficulty": difficulty,
                "topic": topic,
                "options": options,
                "call_back": call_back,
                "answer_key": answer_key,
                "accepted_answers": accepted_answers,
                "explanation": explanation,
            }
        )
    except ValueError:
        return None



def _decode_study_chat_reply_proposal(
    content: str,
) -> StudyChatReplyProposalV1 | None:
    """Decode a complete structured reply or authorize genuine plain text."""

    stripped = content.strip()
    if not stripped:
        return None

    candidate = stripped
    fence_match = CHAT_JSON_FENCE_RE.fullmatch(stripped)
    fence_language = ""
    if fence_match is not None:
        fence_language = (fence_match.group("language") or "").lower()
        if fence_language in {"", "json"}:
            candidate = (fence_match.group("body") or "").strip()

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError as exc:
        if _looks_like_study_chat_json(
            original=stripped,
            candidate=candidate,
            fence_language=fence_language,
        ):
            raise RuntimeError("chat_model_invalid_payload") from exc
        return None

    if not isinstance(payload, dict):
        raise RuntimeError("chat_model_invalid_payload")
    try:
        proposal = StudyChatReplyProposalV1.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError("chat_model_invalid_payload") from exc
    if any(
        CHAT_PRIVATE_GRADING_KEY_RE.search(text)
        for text in _study_chat_public_proposal_texts(proposal)
    ):
        raise RuntimeError("chat_model_invalid_payload")
    return proposal



def _study_chat_public_proposal_texts(
    proposal: StudyChatReplyProposalV1,
) -> list[str]:
    texts = [
        proposal.text,
        proposal.mood,
        proposal.action,
        proposal.speech_style,
        proposal.delivery_cue,
        proposal.state_commentary,
        *(block.kind for block in proposal.rich_blocks),
        *(block.content for block in proposal.rich_blocks),
    ]
    if proposal.interactive_question is not None:
        texts.extend(
            [
                proposal.interactive_question.prompt,
                proposal.interactive_question.topic,
                *(option.key for option in proposal.interactive_question.options),
                *(option.text for option in proposal.interactive_question.options),
            ]
        )
    return texts



def _looks_like_study_chat_json(
    *,
    original: str,
    candidate: str,
    fence_language: str,
) -> bool:
    if fence_language == "json":
        return True
    left_stripped = candidate.lstrip()
    if left_stripped.startswith("{"):
        return True
    if re.match(
        r"\A\[\s*(?:\Z|[\[{\"\d-]|true\b|false\b|null\b)",
        left_stripped,
        re.IGNORECASE,
    ):
        return True
    bare_reply_keys = {
        match.group("key").lower()
        for match in CHAT_BARE_REPLY_KEY_RE.finditer(original)
    }
    if len(bare_reply_keys) >= 2:
        return True
    return CHAT_JSON_KEY_RE.search(original) is not None



def _parse_chat_model_reply(
    *,
    raw_payload: dict[str, Any],
    tool_results: list[dict[str, Any]],
    fallback_memory_trace: list[dict[str, Any]],
    tool_traces: list[ChatToolCallTraceRecord],
    application_tool_results: list[dict[str, Any]] | None = None,
) -> ModelReply:
    content = ""
    try:
        content = _extract_choice_content(raw_payload)
    except RuntimeError:
        content = ""

    parsed: dict[str, object] = {}
    if content.strip():
        proposal = _decode_study_chat_reply_proposal(content)
        if proposal is not None:
            parsed = proposal.model_dump(mode="json", exclude_none=True)
        else:
            finish_reason, reasoning_tokens, completion_tokens = _extract_choice_diagnostics(raw_payload)
            logger.info(
                "model.chat.parse_fallback using_plain_text finish_reason=%s reasoning_tokens=%s completion_tokens=%s content_preview=%s",
                finish_reason,
                reasoning_tokens,
                completion_tokens,
                content[:120],
            )

    interactive_question = _extract_interactive_question_payload(
        parsed=parsed,
        tool_results=tool_results,
    )
    memory_trace = _extract_memory_trace_payload(tool_results, fallback_memory_trace)
    scene_profile = extract_scene_profile_from_tool_results(
        application_tool_results or tool_results
    )
    rich_blocks = _extract_rich_blocks_payload(parsed)
    mood = str(parsed.get("mood") or "calm")
    action = str(parsed.get("action") or "point")
    speech_style = str(parsed.get("speech_style") or "").strip()
    delivery_cue = str(parsed.get("delivery_cue") or "").strip()
    state_commentary = str(parsed.get("state_commentary") or "").strip()
    text = str(parsed.get("text") or "").strip()

    if not text:
        if content.strip() and not parsed:
            text = content.strip()
        else:
            finish_reason, reasoning_tokens, completion_tokens = _extract_choice_diagnostics(raw_payload)
            logger.warning(
                "model.chat.invalid_payload empty_text finish_reason=%s reasoning_tokens=%s completion_tokens=%s",
                finish_reason,
                reasoning_tokens,
                completion_tokens,
            )
            raise RuntimeError("chat_model_invalid_payload")

    text = _sanitize_reply_text_for_question(text, interactive_question)
    text, rich_blocks = _normalize_reply_text_and_blocks(
        text=text,
        rich_blocks=rich_blocks,
    )
    return ModelReply(
        text=text.strip(),
        mood=mood,
        action=action,
        speech_style=speech_style,
        delivery_cue=delivery_cue,
        state_commentary=state_commentary,
        rich_blocks=rich_blocks,
        interactive_question=interactive_question,
        memory_trace=memory_trace,
        tool_calls=tool_traces,
        scene_profile=scene_profile,
    )



def _extract_memory_trace_payload(
    tool_results: list[dict[str, Any]],
    fallback_memory_trace: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    for result in reversed(tool_results):
        if str(result.get("tool_name") or "") != "retrieve_memory_context":
            continue
        hits = result.get("hits")
        if isinstance(hits, list):
            normalized: list[dict[str, Any]] = []
            for item in hits:
                if not isinstance(item, dict):
                    continue
                normalized.append({
                    **item,
                    "source": "tool_call",
                })
            return normalized
    return [{**item, "source": str(item.get("source") or "retriever")} for item in fallback_memory_trace]



def _extract_choice_diagnostics(payload: dict[str, Any]) -> tuple[str, int, int]:
    choices = payload.get("choices")
    finish_reason = ""
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        finish_reason = str(choices[0].get("finish_reason") or "")

    usage = payload.get("usage") if isinstance(payload, dict) else None
    completion_tokens = 0
    reasoning_tokens = 0
    if isinstance(usage, dict):
        completion_tokens = _coerce_int(usage.get("completion_tokens"), default=0)
        details = usage.get("completion_tokens_details")
        if isinstance(details, dict):
            reasoning_tokens = _coerce_int(details.get("reasoning_tokens"), default=0)
    return finish_reason, reasoning_tokens, completion_tokens

