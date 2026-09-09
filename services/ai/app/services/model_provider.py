from __future__ import annotations

from app.services.provider_transport import ProviderTransport, ModelRequestError, _coerce_int

from app.services.provider_capabilities import ModelProvider, ModelReply, PlanModelReply, PlanScheduleItem
from app.services.provider_exercises import LocalExerciseProvider
from app.services.provider_embedding import RemoteEmbeddingProvider
from app.services.provider_image import RemoteImageProvider

import json
import re
from typing import Callable
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.domain import (
    ChatToolCallTraceRecord,
    DocumentDebugRecord,
    LearningGoalInput,
    LearningPlanRecord,
    PlanGenerationTraceRecord,
    PlanningQuestionRecord,
    PersonaProfile,
    PersonaSlot,
    RichTextBlockRecord,
    SceneLayerStateRecord,
    SceneObjectStateRecord,
    SceneProfileRecord,
    StudyUnitRecord,
    normalize_persona_narrative_mode,
    persona_narrative_mode_label,
    persona_slot_content,
    persona_sorted_slots,
)
from app.models.planning import (
    LearningPlanProposalV1,
    PlanContentSliceProposalV1,
    PlanScheduleChapterProposalV1,
)
from app.models.scene import (
    decode_scene_tree_proposal,
    project_scene_tree_proposal,
)
from app.models.study_chat_reply import StudyChatReplyProposalV1
from app.models.study_chat_operation import StudyChatMessageKind
from app.models.tavern import (
    TavernActorReply,
    TavernMessageRecord,
    TavernParticipantRecord,
)
from app.models.study_question import (
    STUDY_QUESTION_TOOL_TRACE_PRIVATE_FIELDS,
    StudyQuestionProposalV1,
)
from app.models.tool_manifest import resolve_tool_manifest_entry
from app.services.model_tool_config import CHAT_STAGE, PLAN_STAGE, TOOL_CATALOG
from app.services.model_recovery import record_model_recovery
from app.models.persona_generation import (
    PersonaCardBatchContentProposalV1,
    PersonaSlotContentProposalV1,
)
from app.services.persona_runtime import render_persona_runtime_instruction
from app.services.token_usage import TokenUsageService
from app.services.tool_provider_projection import (
    ProviderToolCallDecodeError,
    ToolContractViolation,
    ToolExecutionBudgetTracker,
    adapt_tool_runtime_result,
    build_versioned_tool_error,
    decode_provider_tool_call,
    project_tool_arguments_for_observability,
    project_validated_tool_result,
    provider_function_for_entry,
)
from app.services.tavern_prompt import (
    build_tavern_actor_messages,
    build_tavern_actor_recovery_message,
)
from app.services.openai_plan_runner import OpenAIPlanRunner
from app.services.plan_prompt import (
    build_learning_plan_context,
    build_learning_plan_messages,
    read_page_range_content,
    read_page_range_images,
)
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.prompt_loader import load_prompt_template
from app.services.session_scene import (
    SCENE_TOOL_NAMES,
    extract_scene_profile_from_tool_results,
    serialize_chat_tool_trace_item,
)

try:
    import litellm
    from litellm import completion as litellm_completion
    from litellm import embedding as litellm_embedding
    from litellm import responses as litellm_responses
except ImportError:
    litellm = None
    litellm_completion = None
    litellm_embedding = None
    litellm_responses = None

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

SETTING_ASSIST_SCHEMA = (
    '{'
    '"slots": [{"kind": string, "label": string, "content": string, "weight"?: number, "locked"?: boolean, "sort_order"?: number}], '
    '"system_prompt_suggestion": string'
    '}'
)

SETTING_SLOT_SCHEMA = (
    '{'
    '"slot": {"kind": string, "label": string, "content": string, "weight"?: number, "locked"?: boolean, "sort_order"?: number}'
    '}'
)

PERSONA_CARD_GENERATION_SCHEMA = (
    '{'
    '"summary": string, '
    '"relationship": string, '
    '"learner_address": string, '
    '"cards": [{"title": string, "kind": string, "label": string, "content": string, "tags"?: [string], "source_note"?: string}]'
    '}'
)

PERSONA_CARD_GENERATION_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "relationship": {"type": "string"},
        "learner_address": {"type": "string"},
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "title": {"type": "string"},
                    "kind": {"type": "string"},
                    "label": {"type": "string"},
                    "content": {"type": "string"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "source_note": {"type": "string"},
                },
                "required": ["title", "kind", "label", "content"],
            },
        }
    },
    "required": ["summary", "relationship", "learner_address", "cards"],
}

SCENE_TREE_GENERATION_SCHEMA = (
    "{"
    '"schema_name": "scene-tree-proposal", '
    '"schema_version": "scene-tree-proposal-v1", '
    '"scene_name": string, '
    '"scene_summary": string, '
    '"selected_path": [integer, ...], '
    '"scene_layers": [{"title": string, "scope_label": string, "summary": string, '
    '"atmosphere": string, "rules": string, "entrance": string, "tags"?: [string], '
    '"reuse_hint"?: string, "objects"?: [{"name": string, "description": string, '
    '"interaction": string, "tags"?: [string], "reuse_hint"?: string}], '
    '"children"?: [SceneLayer]}]'
    "}"
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
REASONING_CHAT_MODEL_RE = re.compile(
    r"^(?:gpt-5(?:[.-]|$)|o[134](?:[.-]|$))",
    re.IGNORECASE,
)


def adapt_openai_compatible_payload(
    payload: dict[str, Any],
    *,
    model: str,
) -> tuple[dict[str, Any], list[str]]:
    """Apply explicit model-family request rules without global parameter dropping."""
    adapted = dict(payload)
    adjustments: list[str] = []
    model_id = _bare_model_id(model)
    if REASONING_CHAT_MODEL_RE.match(model_id):
        if "temperature" in adapted:
            adapted.pop("temperature", None)
            adjustments.append("temperature_omitted")
        if "max_tokens" in adapted and "max_completion_tokens" not in adapted:
            adapted["max_completion_tokens"] = adapted.pop("max_tokens")
            adjustments.append("max_tokens_to_max_completion_tokens")
    return adapted, adjustments


def _bare_model_id(model: str) -> str:
    normalized = model.strip()
    if "/" in normalized:
        normalized = normalized.rsplit("/", 1)[-1]
    return normalized


def _feature_probe_tools_payload(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0.2,
        "max_tokens": 32,
        "messages": [
            {"role": "system", "content": "Return a brief acknowledgement."},
            {"role": "user", "content": "Compatibility probe."},
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "read_probe_context",
                    "description": "Read a minimal compatibility probe context.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                },
            }
        ],
        "tool_choice": "auto",
    }


def _feature_probe_json_payload(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0.4,
        "max_tokens": 48,
        "messages": [
            {"role": "system", "content": "Return only a JSON object."},
            {"role": "user", "content": 'Return {"ok":true}.'},
        ],
        "response_format": {"type": "json_object"},
    }


def _feature_probe_tavern_payload(model: str) -> dict[str, Any]:
    return {
        "model": model,
        "temperature": 0.35,
        "max_tokens": 48,
        "messages": [
            {"role": "system", "content": "Return the requested JSON object."},
            {"role": "user", "content": "Return a short compatibility acknowledgement."},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "tavern_probe",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
            },
        },
    }


def _feature_probe_failure_note(code: str) -> str:
    if code.endswith("_request_unsupported_params"):
        return "当前模型拒绝该功能的代表请求参数，请更换模型或调整显式兼容策略。"
    if code.endswith("_request_rate_limit"):
        return "鉴权已到达上游，但代表请求受到额度或频率限制。"
    if code.endswith("_request_timeout"):
        return "代表请求超时；模型列表成功不代表当前功能可用。"
    if code.endswith("_request_network_error"):
        return "代表请求发生网络错误；请检查 endpoint 连通性。"
    return "代表请求失败；模型可列出不代表当前功能可调用。"


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


def _build_setting_retry_instruction(*, reason: str, retry_instruction: str) -> str:
    if reason == "setting_model_content_filter":
        return (
            "上一次输出被内容过滤截断。请改为更中性、更克制的结构化表达，只输出符合要求的 JSON 对象。\n\n"
            + retry_instruction
        )
    if reason == "setting_model_empty_response":
        return (
            "上一次没有返回可用内容。请补全结果，并且只输出一个合法 JSON 对象。\n\n"
            + retry_instruction
        )
    return retry_instruction


def _setting_prompt_sections() -> dict[str, str]:
    template = load_prompt_template("openai_setting_prompt.txt")
    return {
        "assist_setting_system": template.require("assist_setting_system"),
        "assist_setting_user": template.require("assist_setting_user"),
        "assist_slot_system": template.require("assist_slot_system"),
        "assist_slot_user": template.require("assist_slot_user"),
        "generate_keywords_system": template.require("generate_keywords_system"),
        "generate_keywords_user": template.require("generate_keywords_user"),
        "generate_long_text_system": template.require("generate_long_text_system"),
        "generate_long_text_user": template.require("generate_long_text_user"),
        "generate_scene_keywords_system": template.require("generate_scene_keywords_system"),
        "generate_scene_keywords_user": template.require("generate_scene_keywords_user"),
        "generate_scene_long_text_system": template.require("generate_scene_long_text_system"),
        "generate_scene_long_text_user": template.require("generate_scene_long_text_user"),
    }


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


class MockModelProvider(LocalExerciseProvider, ModelProvider):
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
        if message_kind == "session_prelude":
            text = (
                "我们先把这一轮学习的落脚点安顿好。"
                "接下来我会先给出一条清晰主线，再用一个小问题帮你确认抓手。"
                "准备好后，我们就从最核心的概念开始。"
            )
            state_commentary = "已准备好自然进入本轮学习的引导节奏。"
        else:
            text = (
                "我们先把这个问题拆成一个清晰的学习抓手。"
                "先确认核心概念和成立条件，再用一个具体例子检查理解。"
                "请你试着用自己的话复述关键点，我会继续补齐边界与易错处。"
            )
            state_commentary = "保持连续讲解，并根据当前互动推进重点。"
        narrative_mode = persona_slot_content(persona, "narrative_mode", "稳态导学")
        mood = "playful" if normalize_persona_narrative_mode(narrative_mode) == "light_story" else "calm"
        return ModelReply(
            text=text,
            mood=mood,
            action="point",
            speech_style=persona.default_speech_style,
            delivery_cue="先稳住节奏，再把概念拆成两到三个抓手。",
            state_commentary=state_commentary,
            rich_blocks=[],
            memory_trace=memory_trace_hits or [],
        )


    def generate_tavern_actor_reply(
        self,
        *,
        persona: PersonaProfile,
        participants: list[TavernParticipantRecord],
        scene_profile: SceneProfileRecord | None,
        recent_messages: list[TavernMessageRecord],
        user_message: str,
        guidance: str,
        allowed_target_ids: list[str],
        turn_kind: str = "user_message",
        required_target_id: str = "",
        should_continue: Callable[[], bool] | None = None,
    ) -> TavernActorReply:
        if should_continue is not None and not should_continue():
            raise RuntimeError("tavern_actor_generation_canceled")
        relationship = persona.relationship.strip().rstrip("。！？!?，,；;：:") or "同行者"
        scene_hint = (
            f"在{scene_profile.scene_name or scene_profile.title}里，"
            if scene_profile is not None
            else ""
        )
        guidance_hint = "我会顺着当前互动方向回应。" if guidance.strip() else ""
        heard_text = (
            f"我听见你说“{user_message.strip()}”。"
            if user_message.strip()
            else "我会接着刚才的对话往下说。"
        )
        return TavernActorReply(
            text=(
                f"{scene_hint}{heard_text}"
                f"作为你的{relationship}，我想先接住这句话，再和你一起把它聊开。"
                f"{guidance_hint}"
            ),
            mood="calm",
            action="微微前倾，把注意力放回眼前的对话",
            speech_style=persona.default_speech_style,
            delivery_cue="自然停顿后再回应，不抢替对方下结论。",
            state_commentary="保持当前角色身份并直接回应用户。",
            addressed_participant_ids=[required_target_id] if required_target_id else [],
        )


    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
        planning_questions: list[PlanningQuestionRecord] | None = None,
        existing_plan: LearningPlanRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
    ) -> PlanModelReply:
        _call_interrupt(interrupt_check)
        plannable_units = [unit for unit in study_units if unit.include_in_plan] or study_units
        objective_hint = self._compact_objective(goal.objective)
        answered_questions = [
            item for item in (planning_questions or [])
            if item.status == "answered" and item.answer.strip()
        ]
        today_tasks = [
            f"阅读 {unit.title}，提取 2 条定义或结论。"
            for unit in plannable_units[:2]
        ]
        if not today_tasks:
            today_tasks = [f"阅读 {document_title}，确认学习章节顺序与关键知识点。"]
        if objective_hint:
            today_tasks.insert(0, f"先对照学习目标：{objective_hint}。")
        if answered_questions:
            latest_answer = answered_questions[-1]
            today_tasks.insert(
                1 if objective_hint else 0,
                f"按学习者新增偏好修订：{latest_answer.answer.strip()}。",
            )
        schedule: list[PlanScheduleItem] = []
        for unit in plannable_units[:4]:
            schedule.append(
                PlanScheduleItem(
                    unit_id=unit.id,
                    title=f"{unit.title} 精读",
                    focus=(
                        f"围绕 {unit.title} 推进学习目标，并整理概念、例题与疑问。"
                        if goal.objective.strip()
                        else f"在 {unit.title} 中整理概念、例题与疑问。"
                    ),
                    activity_type="learn",
                    schedule_chapters=_fallback_schedule_chapters_for_unit(unit),
                )
            )
        # course_title is the generated textbook-grounded title; objective remains learner-authored goal text.
        return PlanModelReply(
            course_title=_build_course_title(
                document_title=document_title,
                plannable_units=plannable_units,
            ),
            overview=(
                f"{persona.name} 将围绕 {document_title} 生成首轮学习计划，"
                f"覆盖 {len(plannable_units)} 个学习单元。"
                f"{' 目标优先：' + objective_hint + '。' if objective_hint else ''}"
                f"{' 已吸收最新规划回答。' if answered_questions else ''}"
            ),
            today_tasks=today_tasks,
            schedule=schedule,
            planning_questions=list(planning_questions or []),
        )

    def _compact_objective(self, objective: str) -> str:
        cleaned = re.sub(r"\s+", " ", objective or "").strip(" 。.!！?？;；：:")
        if not cleaned:
            return ""
        if len(cleaned) <= 20:
            return cleaned
        return f"{cleaned[:20].rstrip()}…"
    def assist_persona_setting(
        self,
        *,
        name: str,
        summary: str,
        slots: list[PersonaSlot],
        rewrite_strength: float,
    ) -> dict[str, object]:
        ordered_slots = persona_sorted_slots(slots)
        worldview = next((s.content for s in ordered_slots if s.kind == "worldview"), "")
        past_exp = next((s.content for s in ordered_slots if s.kind == "past_experiences"), "")
        teaching_method = next((s.content for s in ordered_slots if s.kind == "teaching_method"), "")
        narrative_mode = next((s.content for s in ordered_slots if s.kind == "narrative_mode"), "稳态导学")
        encouragement_style = next((s.content for s in ordered_slots if s.kind == "encouragement_style"), "")
        correction_style = next((s.content for s in ordered_slots if s.kind == "correction_style"), "")

        style_text = teaching_method.strip() or "结构化讲解"
        narrative_text = persona_narrative_mode_label(narrative_mode)
        identity_name = name.strip() or "这位教师"
        summary_text = summary.strip() or "擅长围绕章节核心概念组织学习路径"
        normalized_strength = max(0.0, min(1.0, rewrite_strength))
        base_narrative = (worldview or past_exp).strip()
        if base_narrative and normalized_strength < 0.45:
            narrative_content = (
                f"{base_narrative}\n\n"
                f"补充设定：{identity_name} 采用{narrative_text}叙事，"
                f"以{style_text}推进讲解，鼓励策略偏向\"{encouragement_style or '阶段性肯定'}\"，"
                f"纠错策略采用\"{correction_style or '温和纠偏'}\"。"
            )
        else:
            narrative_content = (
                f"{identity_name} 的核心定位：{summary_text}。"
                f"其教学叙事采用{narrative_text}路线，常用{style_text}组织内容。"
                f"面对学习者挫折时，优先使用\"{encouragement_style or '阶段性肯定'}\"进行支持；"
                f"在纠错时坚持\"{correction_style or '温和纠偏'}\"，先指出可改进点，再给出可执行下一步。"
            )
        updated_slots: list[PersonaSlot] = []
        narrative_inserted = False
        for slot in ordered_slots:
            if slot.kind in ("worldview", "past_experiences") and not narrative_inserted:
                updated_slots.append(
                    PersonaSlot(
                        kind=slot.kind,
                        label=slot.label,
                        content=narrative_content,
                        weight=slot.weight,
                        locked=slot.locked,
                        sort_order=slot.sort_order,
                    )
                )
                narrative_inserted = True
            elif slot.kind in ("worldview", "past_experiences"):
                pass
            else:
                updated_slots.append(slot)
        if not narrative_inserted:
            updated_slots.append(
                PersonaSlot(kind="worldview", label="世界观起点", content=narrative_content, sort_order=10)
            )
        prompt = (
            "你是一位严格贴合教材章节的教学人格。"
            f"人格名称：{identity_name}。"
            f"叙事模式：{narrative_text}。"
            f"教学风格：{style_text}。"
            "回答必须简洁、贴合章节、可执行，并优先帮助学习者推进下一步。"
        )
        return {
            "slots": [s.model_dump() for s in updated_slots],
            "system_prompt_suggestion": prompt,
        }

    def assist_persona_slot(
        self,
        *,
        name: str,
        summary: str,
        slot: PersonaSlot,
        rewrite_strength: float,
    ) -> dict[str, object]:
        identity_name = name.strip() or "这位教师"
        strength = max(0.0, min(1.0, rewrite_strength))
        base = slot.content.strip()
        if slot.kind == "worldview":
            rewritten = f"{identity_name} 坚持先建立概念锚点，再推进抽象推理，并始终回到章节证据。"
        elif slot.kind == "past_experiences":
            rewritten = "曾长期负责章节导学与错题复盘，习惯把复杂主题拆解成可执行步骤。"
        elif slot.kind == "thinking_style":
            rewritten = "先澄清前提，再给推理链，最后做边界与反例检查。"
        elif slot.kind == "teaching_method":
            rewritten = "按“概念-例子-反例-迁移”组织讲解，每次聚焦一个关键难点。"
        elif slot.kind == "encouragement_style":
            rewritten = "鼓励聚焦具体进步与可复现方法，避免空泛夸奖。"
        elif slot.kind == "correction_style":
            rewritten = "纠错先指出可执行改进点，再给下一步练习，保持语气温和但明确。"
        else:
            rewritten = f"{identity_name}：{summary or '围绕章节核心概念组织学习路径'}。"
        content = f"{base}\n\n润色补充：{rewritten}" if base and strength < 0.45 else rewritten
        return {
            "slot": PersonaSlot(
                kind=slot.kind,
                label=slot.label,
                content=content,
                weight=slot.weight,
                locked=slot.locked,
                sort_order=slot.sort_order,
            ).model_dump()
        }

    def generate_persona_cards_from_keywords(
        self,
        *,
        keywords: str,
        count: int | None,
    ) -> dict[str, object]:
        keyword_parts = [
            part.strip()
            for part in re.split(r"[，,、；;|\n]+", keywords)
            if part.strip()
        ]
        if not keyword_parts:
            raise RuntimeError("setting_model_invalid_payload")
        target_count = _resolve_persona_card_count_hint(count, default=6)
        slot_cycle = [
            ("worldview", "世界观起点"),
            ("past_experiences", "过往经历"),
            ("thinking_style", "思维风格"),
            ("teaching_method", "教学方法"),
            ("encouragement_style", "鼓励策略"),
            ("correction_style", "纠错策略"),
            ("narrative_mode", "叙事模式"),
        ]
        cards: list[dict[str, object]] = []
        for index in range(target_count):
            keyword = keyword_parts[index % len(keyword_parts)]
            kind, label = slot_cycle[index % len(slot_cycle)]
            cards.append(
                {
                    "title": f"{label}卡片 {index + 1}",
                    "kind": kind,
                    "label": label,
                    "content": f"围绕“{keyword}”形成稳定、可执行的{label}。",
                    "tags": ["关键词生成", keyword],
                    "source_note": "由关键词在本地模拟模式下确定性生成。",
                }
            )
        _enforce_exact_persona_card_count(cards, count=count)
        return {
            "summary": f"围绕{'、'.join(keyword_parts[:3])}构建的导学型教师人格。",
            "relationship": "陪伴式导师",
            "learner_address": "同学",
            "cards": cards,
            "used_model": "mock",
            "used_web_search": False,
        }

    def generate_persona_cards_from_text(
        self,
        *,
        text: str,
        count: int | None,
    ) -> dict[str, object]:
        sentences = [segment.strip() for segment in re.split(r"[。！？\n]+", text) if segment.strip()]
        target_count = _resolve_persona_card_count_hint(count, default=6)
        if not sentences:
            raise RuntimeError("setting_model_invalid_payload")
        if count is not None and count >= 1:
            seed = [sentences[index % len(sentences)] for index in range(target_count)]
        else:
            seed = sentences[:target_count]
        cards: list[dict[str, object]] = []
        slot_cycle = [
            ("worldview", "世界观起点"),
            ("past_experiences", "过往经历"),
            ("thinking_style", "思维风格"),
            ("teaching_method", "教学方法"),
            ("encouragement_style", "鼓励策略"),
            ("correction_style", "纠错策略"),
            ("narrative_mode", "叙事模式"),
        ]
        for index, fragment in enumerate(seed):
            kind, label = slot_cycle[index % len(slot_cycle)]
            cards.append(
                {
                    "title": f"{label}卡片 {index + 1}",
                    "kind": kind,
                    "label": label,
                    "content": fragment,
                    "tags": ["长文本提取"],
                    "source_note": "由输入长文本抽取的设定片段。",
                }
            )
        _enforce_exact_persona_card_count(cards, count=count)
        return {
            "summary": "从长文本中提取出的导学型教师人格，强调稳定叙事与可执行反馈。",
            "relationship": "陪伴式导师",
            "learner_address": "同学",
            "cards": cards,
            "used_model": "mock",
            "used_web_search": False,
        }

    def generate_scene_tree_from_keywords(
        self,
        *,
        keywords: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        keyword_parts = [
            part.strip()
            for part in re.split(r"[，,、；;|\n]+", keywords)
            if part.strip()
        ]
        if not keyword_parts:
            raise RuntimeError("setting_model_invalid_payload")
        seed_name = " / ".join(keyword_parts[:2])
        theme = "、".join(keyword_parts[:4])
        layers = _build_mock_scene_layers(
            layer_count=_resolve_scene_layer_count_hint(layer_count, default=5),
            anchors=keyword_parts,
            fragments=[
                f"围绕 {theme} 展开教学场景，强调从宏观规则一路收束到局部互动。",
                f"关键词驱动：{theme}。",
            ],
        )
        return _normalize_generated_scene_result(
            _scene_proposal_payload_from_layers(
                scene_name=f"{seed_name} 场景树" if seed_name else "关键词场景树",
                scene_summary=(
                    f"根据关键词 {theme} 生成的分层场景草稿，适合继续补充教学动线、"
                    "规则与交互节点。"
                ),
                layers=layers,
            ),
            used_model="mock",
            used_web_search=False,
        )

    def generate_scene_tree_from_text(
        self,
        *,
        text: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        fragments = [
            segment.strip()
            for segment in re.split(r"[。！？\n]+", text)
            if segment.strip()
        ]
        if not fragments:
            raise RuntimeError("setting_model_invalid_payload")
        anchors = _extract_scene_anchors_from_text(text)
        layers = _build_mock_scene_layers(
            layer_count=_resolve_scene_layer_count_hint(layer_count, default=5),
            anchors=anchors,
            fragments=fragments,
        )
        scene_name_seed = fragments[0][:18].strip("：:- ")
        return _normalize_generated_scene_result(
            _scene_proposal_payload_from_layers(
                scene_name=f"{scene_name_seed or '长文本'} 场景树",
                scene_summary=(
                    f"从长文本中抽取出的分层场景结构，共 {len(layers)} 层，"
                    "可继续作为教学或角色互动场景复用。"
                ),
                layers=layers,
            ),
            used_model="mock",
            used_web_search=False,
        )


class OpenAIModelProvider(ModelProvider):
    # Implementation identity, distinct from credential/model readiness probes.
    exercise_implementation = LocalExerciseProvider.exercise_implementation

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        plan_api_key: str = "",
        plan_base_url: str = "",
        plan_model: str,
        setting_api_key: str = "",
        setting_base_url: str = "",
        setting_model: str | None = None,
        setting_web_search_enabled: bool = True,
        chat_api_key: str = "",
        chat_base_url: str = "",
        chat_model: str | None = None,
        chat_temperature: float = 0.35,
        setting_temperature: float = 0.4,
        setting_max_tokens: int = 900,
        chat_max_tokens: int = 800,
        chat_history_messages: int = 8,
        chat_tool_max_rounds: int = 4,
        chat_tools_enabled: bool = True,
        chat_memory_tool_enabled: bool = True,
        chat_multimodal_enabled: bool = False,
        embedding_model: str = "text-embedding-3-small",
        timeout_seconds: int = 30,
        multimodal_enabled: bool = False,
        plan_tools_enabled: bool = True,
        fallback_plan_model: str = "",
        fallback_disable_tools: bool = True,
        plan_disabled_tools_provider: Callable[[], set[str]] | None = None,
        chat_disabled_tools_provider: Callable[[], set[str]] | None = None,
        token_usage_service: TokenUsageService | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.plan_api_key = (plan_api_key or api_key).strip()
        self.plan_base_url = (plan_base_url or base_url).rstrip("/")
        self.setting_api_key = (setting_api_key or api_key).strip()
        self.setting_base_url = (setting_base_url or base_url).rstrip("/")
        self.chat_api_key = (chat_api_key or api_key).strip()
        self.chat_base_url = (chat_base_url or base_url).rstrip("/")
        self.plan_model = plan_model
        self.setting_model = setting_model or chat_model or plan_model
        self.setting_web_search_enabled = setting_web_search_enabled
        self.chat_model = chat_model or plan_model
        self.chat_temperature = chat_temperature
        self.setting_temperature = setting_temperature
        self.setting_max_tokens = setting_max_tokens
        self.chat_max_tokens = chat_max_tokens
        self.chat_history_messages = max(1, chat_history_messages)
        self.chat_tool_max_rounds = max(1, chat_tool_max_rounds)
        self.chat_tools_enabled = chat_tools_enabled
        self.chat_memory_tool_enabled = chat_memory_tool_enabled
        self.chat_multimodal_enabled = chat_multimodal_enabled
        self.embedding_model = embedding_model
        self.timeout_seconds = timeout_seconds
        self.multimodal_enabled = multimodal_enabled
        self.plan_tools_enabled = plan_tools_enabled
        self.fallback_plan_model = fallback_plan_model.strip()
        self.fallback_disable_tools = fallback_disable_tools
        self.plan_disabled_tools_provider = plan_disabled_tools_provider
        self.chat_disabled_tools_provider = chat_disabled_tools_provider
        self.token_usage_service = token_usage_service
        self._local_exercises = LocalExerciseProvider()

    def generate_exercise(self, *, persona: PersonaProfile, section_id: str, topic: str) -> ModelReply:
        return self._local_exercises.generate_exercise(persona=persona, section_id=section_id, topic=topic)

    def grade_submission(self, *, persona: PersonaProfile, exercise_id: str, answer: str) -> ModelReply:
        return self._local_exercises.grade_submission(persona=persona, exercise_id=exercise_id, answer=answer)

    def supports_page_image_tools(self) -> bool:
        return self.multimodal_enabled

    def supports_chat_page_image_tools(self) -> bool:
        return self.chat_multimodal_enabled

    def supports_chat_generated_image_tools(self) -> bool:
        return self._image_provider().supports_chat_generated_image_tools()

    def plan_tools_runtime_enabled(self) -> bool:
        return self.plan_tools_enabled

    def chat_tools_runtime_enabled(self) -> bool:
        return self.chat_tools_enabled

    def chat_memory_tool_runtime_enabled(self) -> bool:
        return self.chat_memory_tool_enabled

    def probe_feature_readiness(self, features: list[str]) -> dict[str, dict[str, object]]:
        requested = list(dict.fromkeys(features))
        results: dict[str, dict[str, object]] = {}
        transports: list[tuple[list[str], dict[str, Any], str]] = []
        if "plan" in requested:
            transports.append((["plan"], _feature_probe_tools_payload(self.plan_model), "plan"))
        if "study" in requested:
            transports.append((["study"], _feature_probe_tools_payload(self.chat_model), "chat"))
        setting_features = [feature for feature in ("persona", "scene") if feature in requested]
        if setting_features:
            transports.append((setting_features, _feature_probe_json_payload(self.setting_model), "setting"))
        if "tavern" in requested:
            transports.append((["tavern"], _feature_probe_tavern_payload(self.chat_model), "chat"))

        for transport_features, payload, request_kind in transports:
            _, adjustments = adapt_openai_compatible_payload(
                payload,
                model=str(payload.get("model") or ""),
            )
            failure: RuntimeError | None = None
            readiness_note = "最小代表请求已沿当前 LiteLLM 调用路径成功返回。"
            try:
                self._request_openai_chat_completion(
                    payload,
                    request_kind=request_kind,
                    model=str(payload.get("model") or ""),
                )
            except RuntimeError as exc:
                if (
                    transport_features == ["tavern"]
                    and isinstance(exc, ModelRequestError)
                    and _should_fallback_tavern_schema_transport(exc)
                ):
                    fallback_payload = dict(payload)
                    fallback_payload["response_format"] = {"type": "json_object"}
                    try:
                        self._request_openai_chat_completion(
                            fallback_payload,
                            request_kind=request_kind,
                            model=str(payload.get("model") or ""),
                        )
                    except RuntimeError as fallback_exc:
                        failure = fallback_exc
                    else:
                        adjustments = [*adjustments, "json_schema_to_json_object"]
                        readiness_note = "严格 JSON Schema 被拒绝，但当前功能的 JSON Object 回退路径可调用。"
                else:
                    failure = exc

            if failure is None:
                readiness = {
                    "model": str(payload.get("model") or ""),
                    "status": "ready",
                    "code": "",
                    "note": readiness_note,
                    "parameter_adjustments": adjustments,
                }
            else:
                code = str(failure).split(":", 1)[0]
                readiness = {
                    "model": str(payload.get("model") or ""),
                    "status": (
                        "unsupported"
                        if code.endswith("_request_unsupported_params")
                        else "failed"
                    ),
                    "code": code,
                    "note": _feature_probe_failure_note(code),
                    "parameter_adjustments": adjustments,
                }
            for feature in transport_features:
                results[feature] = dict(readiness)
        return results

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
                disabled_tools=(self.chat_disabled_tools_provider() if self.chat_disabled_tools_provider else set()),
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

            raw_payload, _ = self._request_openai_chat_completion(
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
            recovery_raw_payload, _ = self._request_openai_chat_completion(
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

    def generate_tavern_actor_reply(
        self,
        *,
        persona: PersonaProfile,
        participants: list[TavernParticipantRecord],
        scene_profile: SceneProfileRecord | None,
        recent_messages: list[TavernMessageRecord],
        user_message: str,
        guidance: str,
        allowed_target_ids: list[str],
        turn_kind: str = "user_message",
        required_target_id: str = "",
        should_continue: Callable[[], bool] | None = None,
    ) -> TavernActorReply:
        if should_continue is not None and not should_continue():
            raise RuntimeError("tavern_actor_generation_canceled")
        actor_schema = TavernActorReply.transport_json_schema()
        actor_schema_text = json.dumps(actor_schema, ensure_ascii=False, sort_keys=True)
        messages = build_tavern_actor_messages(
            persona=persona,
            participants=participants,
            scene_profile=scene_profile,
            recent_messages=recent_messages,
            user_message=user_message,
            guidance=guidance,
            allowed_target_ids=allowed_target_ids,
            actor_reply_schema=actor_schema_text,
            turn_kind=turn_kind,
            required_target_id=required_target_id,
        )
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "tavern_actor_reply",
                "strict": True,
                "schema": actor_schema,
            },
        }
        payload: dict[str, Any] = {
            "model": self.chat_model,
            "temperature": self.chat_temperature,
            "max_tokens": self.chat_max_tokens,
            "messages": messages,
            "response_format": response_format,
        }
        active_response_format = response_format
        try:
            raw_payload, _ = self._request_openai_chat_completion(
                payload,
                request_kind="chat",
                model=self.chat_model,
            )
        except ModelRequestError as exc:
            if not _should_fallback_tavern_schema_transport(exc):
                raise
            if should_continue is not None and not should_continue():
                raise RuntimeError("tavern_actor_generation_canceled") from exc
            logger.warning(
                "model.tavern.schema_transport_fallback status=%s upstream_code=%s",
                exc.status_code,
                exc.upstream_code,
            )
            record_model_recovery(
                category="transport_compatibility",
                reason="tavern_json_schema_unsupported",
                strategy="retry_json_object",
                attempts=2,
            )
            active_response_format = {"type": "json_object"}
            fallback_payload = {**payload, "response_format": active_response_format}
            raw_payload, _ = self._request_openai_chat_completion(
                fallback_payload,
                request_kind="chat",
                model=self.chat_model,
            )

        try:
            return _parse_tavern_actor_reply(raw_payload)
        except RuntimeError as exc:
            recovery_reason = str(exc)
            if should_continue is not None and not should_continue():
                raise RuntimeError("tavern_actor_generation_canceled") from exc
            logger.warning("model.tavern.recovery reason=%s", recovery_reason)
            record_model_recovery(
                category="semantic_retry",
                reason=recovery_reason,
                strategy="retry_strict_actor_reply",
                attempts=2,
            )
            recovery_payload: dict[str, Any] = {
                "model": self.chat_model,
                "temperature": min(self.chat_temperature, 0.2),
                "max_tokens": max(self.chat_max_tokens, 900),
                "messages": [
                    *messages,
                    {
                        "role": "user",
                        "content": build_tavern_actor_recovery_message(actor_schema_text),
                    },
                ],
                "response_format": active_response_format,
            }
            recovery_raw_payload, _ = self._request_openai_chat_completion(
                recovery_payload,
                request_kind="chat",
                model=self.chat_model,
            )
            recovered = _parse_tavern_actor_reply(recovery_raw_payload)
            return recovered

    def assist_persona_setting(
        self,
        *,
        name: str,
        summary: str,
        slots: list[PersonaSlot],
        rewrite_strength: float,
    ) -> dict[str, object]:
        ordered_slots = persona_sorted_slots(slots)
        slots_text = "\n".join(
            f"{s.kind} ({s.label}) [sort_order={s.sort_order}, weight={s.weight}]: {s.content}"
            for s in ordered_slots
            if s.content.strip()
        )
        prompt_sections = _setting_prompt_sections()
        payload: dict[str, Any] = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": self.setting_max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": prompt_sections["assist_setting_system"].replace(
                        "{{SETTING_ASSIST_SCHEMA}}",
                        SETTING_ASSIST_SCHEMA,
                    ),
                },
                {
                    "role": "user",
                    "content": prompt_sections["assist_setting_user"]
                    .replace("{{NAME}}", name)
                    .replace("{{SUMMARY}}", summary)
                    .replace("{{SLOTS_TEXT}}", slots_text or "无")
                    .replace("{{REWRITE_STRENGTH}}", str(max(0.0, min(1.0, rewrite_strength))))
                    .replace("{{SETTING_ASSIST_SCHEMA}}", SETTING_ASSIST_SCHEMA),
                },
            ],
        }
        parsed = self._request_setting_json_chat(
            payload,
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，不要附加解释、代码块、注释或省略号。",
        )
        returned_slots_raw = parsed.get("slots")
        system_prompt_raw = parsed.get("system_prompt_suggestion")
        if not isinstance(returned_slots_raw, list) or not isinstance(system_prompt_raw, str):
            raise RuntimeError("setting_model_invalid_payload")
        system_prompt_suggestion = system_prompt_raw.strip()
        if not system_prompt_suggestion:
            raise RuntimeError("setting_model_invalid_payload")
        returned_slots: list[PersonaSlot] = []
        for item in returned_slots_raw:
            if not isinstance(item, dict):
                raise RuntimeError("setting_model_invalid_payload")
            try:
                proposal = PersonaSlotContentProposalV1.model_validate(
                    item,
                    strict=True,
                )
            except ValidationError as exc:
                raise RuntimeError("setting_model_invalid_payload") from exc
            returned_slots.append(
                PersonaSlot(
                    kind=proposal.kind,
                    label=proposal.label,
                    content=proposal.content,
                    weight=proposal.weight,
                    locked=proposal.locked,
                    sort_order=proposal.sort_order,
                )
            )
        if not returned_slots:
            raise RuntimeError("setting_model_invalid_payload")
        return {
            "slots": [s.model_dump() for s in returned_slots],
            "system_prompt_suggestion": system_prompt_suggestion,
        }

    def assist_persona_slot(
        self,
        *,
        name: str,
        summary: str,
        slot: PersonaSlot,
        rewrite_strength: float,
    ) -> dict[str, object]:
        prompt_sections = _setting_prompt_sections()
        payload: dict[str, Any] = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": self.setting_max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": prompt_sections["assist_slot_system"].replace(
                        "{{SETTING_SLOT_SCHEMA}}",
                        SETTING_SLOT_SCHEMA,
                    ),
                },
                {
                    "role": "user",
                    "content": prompt_sections["assist_slot_user"]
                    .replace("{{NAME}}", name)
                    .replace("{{SUMMARY}}", summary)
                    .replace("{{SLOT_KIND}}", slot.kind)
                    .replace("{{SLOT_LABEL}}", slot.label)
                    .replace("{{SLOT_CONTENT}}", slot.content)
                    .replace("{{REWRITE_STRENGTH}}", str(max(0.0, min(1.0, rewrite_strength))))
                    .replace("{{SETTING_SLOT_SCHEMA}}", SETTING_SLOT_SCHEMA),
                },
            ],
        }
        parsed = self._request_setting_json_chat(
            payload,
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，字段保持与 schema 一致，不要添加额外说明。",
            validate_payload=_validate_setting_slot_payload,
        )
        slot_raw = parsed.get("slot")
        if not isinstance(slot_raw, dict):
            raise RuntimeError("setting_model_invalid_payload")
        try:
            proposal = PersonaSlotContentProposalV1.model_validate(slot_raw, strict=True)
        except ValidationError as exc:
            raise RuntimeError("setting_model_invalid_payload") from exc
        return {
            "slot": PersonaSlot(
                kind=slot.kind,
                label=proposal.label,
                content=proposal.content,
                weight=slot.weight,
                locked=slot.locked,
                sort_order=slot.sort_order,
            ).model_dump()
        }

    def generate_persona_cards_from_keywords(
        self,
        *,
        keywords: str,
        count: int | None,
    ) -> dict[str, object]:
        prompt_sections = _setting_prompt_sections()
        card_count_hint = _render_persona_card_count_hint(count)
        used_web_search = False
        if self.setting_web_search_enabled:
            payload: dict[str, Any] = {
                "model": self.setting_model,
                "temperature": self.setting_temperature,
                "max_output_tokens": max(self.setting_max_tokens, 1200),
                "instructions": prompt_sections["generate_keywords_system"]
                .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA)
                .replace("{{CARD_COUNT}}", card_count_hint),
                "input": prompt_sections["generate_keywords_user"]
                .replace("{{KEYWORDS}}", keywords.strip())
                .replace("{{CARD_COUNT}}", card_count_hint)
                .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA),
                "tools": [{"type": "web_search"}],
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "persona_card_batch",
                        "schema": PERSONA_CARD_GENERATION_JSON_SCHEMA,
                    }
                },
            }
            try:
                parsed = self._request_setting_json_response(
                    payload,
                    retry_instruction="上一次输出没有形成完整 JSON。请保持结果简洁、中性、严格，只输出一个符合 schema 的 JSON 对象。",
                )
                used_web_search = True
            except RuntimeError as exc:
                if not _should_fallback_setting_web_search(exc):
                    raise
                logger.warning(
                    "model.setting.web_search_fallback feature=persona_cards_from_keywords model=%s error=%s",
                    self.setting_model,
                    exc,
                )
                parsed = self._generate_persona_cards_from_keywords_without_web_search(
                    prompt_sections=prompt_sections,
                    keywords=keywords,
                    card_count_hint=card_count_hint,
                )
                record_model_recovery(
                    category="feature_fallback",
                    reason=str(exc),
                    strategy="disable_web_search",
                    attempts=1,
                )
        else:
            parsed = self._generate_persona_cards_from_keywords_without_web_search(
                prompt_sections=prompt_sections,
                keywords=keywords,
                card_count_hint=card_count_hint,
            )
        batch = _decode_persona_card_batch(parsed)
        cards = batch.pop("cards")
        _enforce_exact_persona_card_count(cards, count=count)
        return {
            **batch,
            "cards": cards,
            "used_model": self.setting_model,
            "used_web_search": used_web_search,
        }

    def generate_persona_cards_from_text(
        self,
        *,
        text: str,
        count: int | None,
    ) -> dict[str, object]:
        prompt_sections = _setting_prompt_sections()
        card_count_hint = _render_persona_card_count_hint(count)
        payload: dict[str, Any] = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": max(self.setting_max_tokens, 1200),
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": prompt_sections["generate_long_text_system"]
                    .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA)
                    .replace("{{CARD_COUNT}}", card_count_hint),
                },
                {
                    "role": "user",
                    "content": prompt_sections["generate_long_text_user"]
                    .replace("{{SOURCE_TEXT}}", text.strip())
                    .replace("{{CARD_COUNT}}", card_count_hint)
                    .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA),
                },
            ],
        }
        parsed = self._request_setting_json_chat(
            payload,
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，并确保 summary、relationship、learner_address、cards 字段完整。",
        )
        batch = _decode_persona_card_batch(parsed)
        cards = batch.pop("cards")
        _enforce_exact_persona_card_count(cards, count=count)
        return {
            **batch,
            "cards": cards,
            "used_model": self.setting_model,
            "used_web_search": False,
        }

    def generate_scene_tree_from_keywords(
        self,
        *,
        keywords: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        prompt_sections = _setting_prompt_sections()
        layer_count_hint = _render_scene_layer_count_hint(layer_count)
        used_web_search = False
        if self.setting_web_search_enabled:
            payload: dict[str, Any] = {
                "model": self.setting_model,
                "temperature": self.setting_temperature,
                "max_output_tokens": max(self.setting_max_tokens, 1400),
                "instructions": prompt_sections["generate_scene_keywords_system"]
                .replace("{{SCENE_TREE_SCHEMA}}", SCENE_TREE_GENERATION_SCHEMA)
                .replace("{{LAYER_COUNT}}", layer_count_hint),
                "input": prompt_sections["generate_scene_keywords_user"]
                .replace("{{KEYWORDS}}", keywords.strip())
                .replace("{{LAYER_COUNT}}", layer_count_hint)
                .replace("{{SCENE_TREE_SCHEMA}}", SCENE_TREE_GENERATION_SCHEMA),
                "tools": [{"type": "web_search"}],
            }
            try:
                parsed = self._request_setting_json_response(
                    payload,
                    retry_instruction="上一次输出没有形成完整 JSON。请保持结果简洁、中性、严格，只输出一个符合场景树 schema 的 JSON 对象。",
                )
                used_web_search = True
            except RuntimeError as exc:
                if not _should_fallback_setting_web_search(exc):
                    raise
                logger.warning(
                    "model.setting.web_search_fallback feature=scene_tree_from_keywords model=%s error=%s",
                    self.setting_model,
                    exc,
                )
                parsed = self._generate_scene_tree_from_keywords_without_web_search(
                    prompt_sections=prompt_sections,
                    keywords=keywords,
                    layer_count_hint=layer_count_hint,
                )
                record_model_recovery(
                    category="feature_fallback",
                    reason=str(exc),
                    strategy="disable_web_search",
                    attempts=1,
                )
        else:
            parsed = self._generate_scene_tree_from_keywords_without_web_search(
                prompt_sections=prompt_sections,
                keywords=keywords,
                layer_count_hint=layer_count_hint,
            )
        return _normalize_generated_scene_result(
            parsed,
            used_model=self.setting_model,
            used_web_search=used_web_search,
        )

    def _generate_persona_cards_from_keywords_without_web_search(
        self,
        *,
        prompt_sections: dict[str, str],
        keywords: str,
        card_count_hint: str,
    ) -> dict[str, Any]:
        payload = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": max(self.setting_max_tokens, 1200),
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": prompt_sections["generate_keywords_system"]
                    .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA)
                    .replace("{{CARD_COUNT}}", card_count_hint),
                },
                {
                    "role": "user",
                    "content": (
                        prompt_sections["generate_keywords_user"]
                        .replace("{{KEYWORDS}}", keywords.strip())
                        .replace("{{CARD_COUNT}}", card_count_hint)
                        .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA)
                        + "\n\n补充限制：当前不允许访问网络资源，请仅根据关键词本身生成。"
                    ),
                },
            ],
        }
        return self._request_setting_json_chat(
            payload,
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，并确保 summary、relationship、learner_address、cards 字段完整。",
        )

    def _generate_scene_tree_from_keywords_without_web_search(
        self,
        *,
        prompt_sections: dict[str, str],
        keywords: str,
        layer_count_hint: str,
    ) -> dict[str, Any]:
        payload = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": max(self.setting_max_tokens, 1400),
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": prompt_sections["generate_scene_keywords_system"]
                    .replace("{{SCENE_TREE_SCHEMA}}", SCENE_TREE_GENERATION_SCHEMA)
                    .replace("{{LAYER_COUNT}}", layer_count_hint),
                },
                {
                    "role": "user",
                    "content": (
                        prompt_sections["generate_scene_keywords_user"]
                        .replace("{{KEYWORDS}}", keywords.strip())
                        .replace("{{LAYER_COUNT}}", layer_count_hint)
                        .replace("{{SCENE_TREE_SCHEMA}}", SCENE_TREE_GENERATION_SCHEMA)
                        + "\n\n补充限制：当前不允许访问网络资源，请仅根据关键词本身生成。"
                    ),
                },
            ],
        }
        return self._request_setting_json_chat(
            payload,
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，并确保 schema_name、schema_version、scene_name、scene_summary、selected_path、scene_layers 字段完整。",
        )

    def _request_setting_json_chat(
        self,
        payload: dict[str, Any],
        *,
        retry_instruction: str,
        validate_payload: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        raw_payload, _ = self._request_openai_chat_completion(
            payload,
            request_kind="setting",
            model=self.setting_model,
        )
        try:
            finish_reason, _, _ = _extract_choice_diagnostics(raw_payload)
            if finish_reason == "content_filter":
                raise RuntimeError("setting_model_content_filter")
            content = _extract_choice_content(raw_payload).strip()
            if not content:
                raise RuntimeError("setting_model_empty_response")
            parsed = _extract_json_payload(
                content,
                invalid_json_code="setting_model_invalid_json",
                invalid_payload_code="setting_model_invalid_payload",
            )
            if validate_payload is not None:
                validate_payload(parsed)
            return parsed
        except RuntimeError as exc:
            recovery_reason = str(exc)
            if recovery_reason not in {
                "setting_model_invalid_json",
                "setting_model_invalid_payload",
                "setting_model_content_filter",
                "setting_model_empty_response",
            }:
                raise
            logger.warning(
                "model.setting.json_retry model=%s reason=%s",
                self.setting_model,
                exc,
            )
            retry_payload = dict(payload)
            retry_messages = list(payload.get("messages") or [])
            retry_messages.append(
                {
                    "role": "user",
                    "content": _build_setting_retry_instruction(
                        reason=recovery_reason,
                        retry_instruction=retry_instruction,
                    ),
                }
            )
            retry_payload["messages"] = retry_messages
            retry_payload["temperature"] = min(float(payload.get("temperature") or self.setting_temperature), 0.2)
            existing_max_tokens = int(payload.get("max_tokens") or self.setting_max_tokens)
            retry_payload["max_tokens"] = min(
                max(existing_max_tokens + 800, int(existing_max_tokens * 1.5)),
                6400,
            )
            retry_raw_payload, _ = self._request_openai_chat_completion(
                retry_payload,
                request_kind="setting",
                model=self.setting_model,
            )
            retry_finish_reason, _, _ = _extract_choice_diagnostics(retry_raw_payload)
            if retry_finish_reason == "content_filter":
                raise RuntimeError("setting_model_content_filter")
            retry_content = _extract_choice_content(retry_raw_payload).strip()
            if not retry_content:
                raise RuntimeError("setting_model_empty_response")
            parsed = _extract_json_payload(
                retry_content,
                invalid_json_code="setting_model_invalid_json",
                invalid_payload_code="setting_model_invalid_payload",
            )
            if validate_payload is not None:
                validate_payload(parsed)
            record_model_recovery(
                category="semantic_retry",
                reason=recovery_reason,
                strategy="retry_structured_json",
                attempts=2,
            )
            return parsed

    def _request_setting_json_response(
        self,
        payload: dict[str, Any],
        *,
        retry_instruction: str,
    ) -> dict[str, Any]:
        raw_payload, _ = self._request_openai_response(
            payload,
            request_kind="setting",
            model=self.setting_model,
        )
        try:
            content = _extract_response_output_text(raw_payload).strip()
            if not content:
                raise RuntimeError("setting_model_empty_response")
            return _extract_json_payload(
                content,
                invalid_json_code="setting_model_invalid_json",
                invalid_payload_code="setting_model_invalid_payload",
            )
        except RuntimeError as exc:
            recovery_reason = str(exc)
            if recovery_reason not in {
                "setting_model_invalid_json",
                "setting_model_invalid_payload",
                "setting_model_empty_response",
            }:
                raise
            retry_payload = dict(payload)
            retry_payload["temperature"] = min(float(payload.get("temperature") or self.setting_temperature), 0.2)
            existing_instructions = str(payload.get("instructions") or "").strip()
            retry_payload["instructions"] = "\n\n".join(
                part
                for part in [
                    existing_instructions,
                    _build_setting_retry_instruction(
                        reason=recovery_reason,
                        retry_instruction=retry_instruction,
                    ),
                ]
                if part
            )
            raw_retry_payload, _ = self._request_openai_response(
                retry_payload,
                request_kind="setting",
                model=self.setting_model,
            )
            retry_content = _extract_response_output_text(raw_retry_payload).strip()
            if not retry_content:
                raise RuntimeError("setting_model_empty_response")
            parsed = _extract_json_payload(
                retry_content,
                invalid_json_code="setting_model_invalid_json",
                invalid_payload_code="setting_model_invalid_payload",
            )
            record_model_recovery(
                category="semantic_retry",
                reason=recovery_reason,
                strategy="retry_structured_response",
                attempts=2,
            )
            return parsed

    def generate_scene_tree_from_text(
        self,
        *,
        text: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        prompt_sections = _setting_prompt_sections()
        layer_count_hint = _render_scene_layer_count_hint(layer_count)
        payload: dict[str, Any] = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": max(self.setting_max_tokens, 1400),
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": prompt_sections["generate_scene_long_text_system"]
                    .replace("{{SCENE_TREE_SCHEMA}}", SCENE_TREE_GENERATION_SCHEMA)
                    .replace("{{LAYER_COUNT}}", layer_count_hint),
                },
                {
                    "role": "user",
                    "content": prompt_sections["generate_scene_long_text_user"]
                    .replace("{{SOURCE_TEXT}}", text.strip())
                    .replace("{{LAYER_COUNT}}", layer_count_hint)
                    .replace("{{SCENE_TREE_SCHEMA}}", SCENE_TREE_GENERATION_SCHEMA),
                },
            ],
        }
        parsed = self._request_setting_json_chat(
            payload,
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，并确保 schema_name、schema_version、scene_name、scene_summary、selected_path、scene_layers 字段完整。",
        )
        return _normalize_generated_scene_result(
            parsed,
            used_model=self.setting_model,
            used_web_search=False,
        )


    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
        planning_questions: list[PlanningQuestionRecord] | None = None,
        existing_plan: LearningPlanRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
    ) -> PlanModelReply:
        planning_context = build_learning_plan_context(
            study_units=study_units,
            debug_report=debug_report,
        )
        messages = build_learning_plan_messages(
            persona=persona,
            document_title=document_title,
            goal=goal,
            study_units=study_units,
            debug_report=debug_report,
            planning_questions=planning_questions,
            existing_plan=existing_plan,
        )
        tool_runtime = self._build_plan_tool_runtime(
            study_units=study_units,
            detail_map=planning_context["detail_map"],
            debug_report=debug_report,
            document_path=document_path,
            tools_enabled=self.plan_tools_enabled,
            planning_questions=planning_questions,
            progress_callback=progress_callback,
        )
        active_tool_runtime = tool_runtime
        active_model = self.plan_model
        run_result = self._run_plan_model(
            model=self.plan_model,
            document_id=goal.document_id,
            messages=messages,
            tool_runtime=tool_runtime,
            progress_callback=progress_callback,
            interrupt_check=interrupt_check,
        )
        if (
            self.fallback_plan_model
            and self.fallback_plan_model != self.plan_model
            and run_result is None
        ):
            fallback_tools_enabled = self.plan_tools_enabled and not self.fallback_disable_tools
            fallback_runtime = self._build_plan_tool_runtime(
                study_units=study_units,
                detail_map=planning_context["detail_map"],
                debug_report=debug_report,
                document_path=document_path,
                tools_enabled=fallback_tools_enabled,
                planning_questions=planning_questions,
                progress_callback=progress_callback,
            )
            logger.warning(
                "model.plan.fallback start primary=%s fallback=%s tools_enabled=%s",
                self.plan_model,
                self.fallback_plan_model,
                fallback_tools_enabled,
            )
            _emit_progress(
                progress_callback,
                "model_fallback_started",
                {
                    "primary_model": self.plan_model,
                    "fallback_model": self.fallback_plan_model,
                    "fallback_tools_enabled": fallback_tools_enabled,
                },
            )
            run_result = self._run_plan_model(
                model=self.fallback_plan_model,
                document_id=goal.document_id,
                messages=messages,
                tool_runtime=fallback_runtime,
                progress_callback=progress_callback,
                interrupt_check=interrupt_check,
                allow_fallback=False,
            )
            if run_result is not None:
                active_tool_runtime = fallback_runtime
                active_model = self.fallback_plan_model
                _emit_progress(
                    progress_callback,
                    "model_fallback_succeeded",
                    {
                        "fallback_model": self.fallback_plan_model,
                    },
                )
        if run_result is None:
            raise RuntimeError("plan_model_empty_response")
        _call_interrupt(interrupt_check)
        final_trace = run_result.trace
        try:
            proposal = _decode_learning_plan_proposal(run_result.content)
            _validate_learning_plan_proposal_refs(proposal, active_tool_runtime.current_study_units() or study_units)
        except PlanningProposalDecodeError as first_error:
            recovery = record_model_recovery(
                category="schema_retry",
                reason="plan_proposal_schema_invalid",
                strategy="strict_contract_repair",
                attempts=2,
                note=first_error.path,
            )
            _emit_progress(
                progress_callback,
                "model_recovery_attempt",
                {
                    "attempt": 1,
                    "reason": "plan_proposal_schema_invalid",
                    "strategy": "strict_contract_repair",
                    "path": first_error.path,
                },
            )
            repair_units = active_tool_runtime.current_study_units() or study_units
            repair_messages = [
                *build_learning_plan_messages(
                    persona=persona, document_title=document_title, goal=goal,
                    study_units=repair_units, debug_report=debug_report,
                    planning_questions=active_tool_runtime.current_planning_questions(),
                    existing_plan=existing_plan,
                ),
                {"role": "assistant", "content": run_result.content},
                {
                    "role": "user",
                    "content": (
                        "上一次最终计划未通过 learning-plan-proposal-v1 严格校验，"
                        f"首个错误路径为 {first_error.path or '$'}，错误类型为 {first_error.reason}。请只重新输出完整 JSON；"
                        "不得输出 plan/schedule/chapter ID、revision、状态或时间，不得遗漏或丢弃章节。"
                    ),
                },
            ]
            repaired_result = self._run_plan_model(
                model=active_model,
                document_id=goal.document_id,
                messages=repair_messages,
                tool_runtime=self._build_plan_tool_runtime(
                    study_units=repair_units,
                    detail_map=build_learning_plan_context(study_units=repair_units, debug_report=debug_report)["detail_map"],
                    debug_report=debug_report, document_path=document_path, tools_enabled=False,
                    planning_questions=active_tool_runtime.current_planning_questions(),
                    progress_callback=progress_callback,
                ),
                progress_callback=progress_callback,
                interrupt_check=interrupt_check,
                allow_fallback=False,
            )
            if repaired_result is None:
                raise RuntimeError("plan_proposal_repair_empty_response") from first_error
            try:
                proposal = _decode_learning_plan_proposal(repaired_result.content)
                _validate_learning_plan_proposal_refs(proposal, repair_units)
            except PlanningProposalDecodeError as repair_error:
                raise RuntimeError(
                    f"plan_proposal_schema_invalid:{repair_error.path or '$'}:{repair_error.reason}"
                ) from repair_error
            if repaired_result.trace.rounds:
                repaired_result.trace.rounds[0].recoveries.insert(0, recovery)
            final_trace = _merge_plan_generation_traces(
                first=run_result.trace,
                second=repaired_result.trace,
            )
        schedule_items = [
            PlanScheduleItem(
                unit_id=item.unit_id,
                title=item.title,
                focus=item.focus,
                activity_type=item.activity_type,
                schedule_chapters=list(item.schedule_chapters),
            )
            for item in proposal.schedule
        ]
        active_study_units = active_tool_runtime.current_study_units() or study_units
        planning_questions = active_tool_runtime.current_planning_questions()
        return PlanModelReply(
            course_title=proposal.course_title,
            overview=proposal.overview,
            today_tasks=list(proposal.today_tasks),
            schedule=schedule_items,
            revised_study_units=active_study_units if _study_units_changed(study_units, active_study_units) else None,
            planning_questions=planning_questions,
            debug_trace=final_trace,
        )

    def _build_plan_tool_runtime(
        self,
        *,
        study_units: list[StudyUnitRecord],
        detail_map: dict[str, object],
        debug_report: DocumentDebugRecord | None,
        document_path: str | None,
        tools_enabled: bool,
        planning_questions: list[PlanningQuestionRecord] | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ):
        if not tools_enabled:
            return build_plan_tool_runtime(
                study_units=study_units, detail_map=detail_map,
                planning_questions=planning_questions,
                disabled_tools=set(TOOL_CATALOG[PLAN_STAGE]),
            )
        return build_plan_tool_runtime(
            study_units=study_units,
            detail_map=detail_map,
            debug_report=debug_report,
            document_path=document_path,
            multimodal_enabled=self.multimodal_enabled,
            planning_questions=planning_questions,
            progress_callback=progress_callback,
            disabled_tools=(self.plan_disabled_tools_provider() if self.plan_disabled_tools_provider else set()),
        )

    def _run_plan_model(
        self,
        *,
        model: str,
        document_id: str,
        messages: list[dict[str, object]],
        tool_runtime,
        progress_callback: Callable[[str, dict[str, object]], None] | None,
        interrupt_check: Callable[[], None] | None = None,
        allow_fallback: bool = True,
    ):
        runner = OpenAIPlanRunner(
            model=model,
            timeout_seconds=self.timeout_seconds,
            request_chat_completion=(
                lambda payload: self._request_openai_chat_completion(
                    payload,
                    request_kind="plan",
                    model=model,
                )
            ),
        )
        try:
            return runner.run(
                document_id=document_id,
                messages=messages,
                tool_runtime=tool_runtime,
                progress_callback=progress_callback,
                interrupt_check=interrupt_check,
            )
        except RuntimeError as exc:
            if allow_fallback and str(exc) in {"plan_model_empty_response", "plan_model_tool_loop_exhausted"}:
                return None
            raise

    def generate_projected_image(self, *, prompt: str, size: str = "1024x1024") -> dict[str, str]:
        return self._image_provider().generate_projected_image(prompt=prompt, size=size)

    def _image_provider(self) -> RemoteImageProvider:
        return RemoteImageProvider(
            chat_model=self.chat_model,
            responses_available=bool(litellm_responses),
            request=self._request_openai_response,
        )

    def _request_openai_chat_completion(
        self,
        payload: dict[str, Any],
        *,
        request_kind: str,
        model: str,
    ) -> tuple[dict[str, Any], int]:
        request_base_url, request_api_key = self._resolve_request_endpoint(request_kind)
        resolved_payload = self._normalize_litellm_payload_model(
            payload,
            api_base=request_base_url,
        )
        tools_enabled = "tools" in payload
        tool_round = len(
            [message for message in resolved_payload.get("messages", []) if message.get("role") == "tool"]
        )
        logger.info(
            "model.%s.request provider=litellm model=%s tool_round=%s tools_enabled=%s",
            request_kind,
            str(resolved_payload.get("model") or model),
            tool_round,
            tools_enabled,
        )
        self._require_litellm_sdk(litellm_completion, feature="completion")
        raw_payload, elapsed_ms = self._execute_litellm_request(
            request_kind=request_kind,
            model=model,
            invoke=lambda: litellm_completion(
                **resolved_payload,
                **self._build_litellm_request_kwargs(
                    api_base=request_base_url,
                    api_key=request_api_key,
                    model=str(resolved_payload.get("model") or model),
                ),
            ),
        )
        self._record_token_usage(raw_payload, feature=request_kind, model=model)
        return raw_payload, elapsed_ms

    def _request_openai_response(
        self,
        payload: dict[str, Any],
        *,
        request_kind: str,
        model: str,
    ) -> tuple[dict[str, Any], int]:
        request_base_url, request_api_key = self._resolve_request_endpoint(request_kind)
        resolved_payload = self._normalize_litellm_payload_model(
            payload,
            api_base=request_base_url,
        )
        if "input" not in resolved_payload and "messages" in resolved_payload:
            resolved_payload["input"] = resolved_payload.pop("messages")
        logger.info(
            "model.%s.responses.request provider=litellm model=%s tools_enabled=%s",
            request_kind,
            str(resolved_payload.get("model") or model),
            bool(resolved_payload.get("tools")),
        )
        self._require_litellm_sdk(litellm_responses, feature="responses")
        raw_payload, elapsed_ms = self._execute_litellm_request(
            request_kind=request_kind,
            model=model,
            invoke=lambda: litellm_responses(
                **resolved_payload,
                **self._build_litellm_request_kwargs(
                    api_base=request_base_url,
                    api_key=request_api_key,
                    model=str(resolved_payload.get("model") or model),
                ),
            ),
        )
        self._record_token_usage_responses(raw_payload, feature=request_kind, model=model)
        return raw_payload, elapsed_ms

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return RemoteEmbeddingProvider(
            embedding_model=self.embedding_model,
            request=self._request_openai_embeddings,
        ).embed_texts(texts)

    def _request_openai_embeddings(
        self,
        payload: dict[str, Any],
        *,
        model: str,
    ) -> tuple[dict[str, Any], int]:
        request_base_url, request_api_key = self._resolve_request_endpoint("chat")
        resolved_payload = self._normalize_litellm_payload_model(
            payload,
            api_base=request_base_url,
        )
        self._require_litellm_sdk(litellm_embedding, feature="embedding")
        raw_payload, elapsed_ms = self._execute_litellm_request(
            request_kind="embedding",
            model=model,
            invoke=lambda: litellm_embedding(
                **resolved_payload,
                **self._build_litellm_request_kwargs(
                    api_base=request_base_url,
                    api_key=request_api_key,
                    model=str(resolved_payload.get("model") or model),
                ),
            ),
        )
        logger.info("model.embedding.request provider=litellm model=%s elapsed_ms=%s", model, elapsed_ms)
        self._record_token_usage(raw_payload, feature="embedding", model=model)
        return raw_payload, elapsed_ms

    def _record_token_usage(
        self,
        raw_payload: dict[str, Any],
        *,
        feature: str,
        model: str,
        prompt_key: str = "prompt_tokens",
        completion_key: str = "completion_tokens",
    ) -> None:
        return self._transport().record_usage(raw_payload, feature=feature, model=model, prompt_key=prompt_key, completion_key=completion_key)

    def _record_token_usage_responses(self, raw_payload: dict[str, Any], *, feature: str, model: str) -> None:
        self._record_token_usage(
            raw_payload,
            feature=feature,
            model=model,
            prompt_key="input_tokens",
            completion_key="output_tokens",
        )

    def _resolve_request_endpoint(self, request_kind: str) -> tuple[str, str]:
        if request_kind == "plan":
            return self.plan_base_url, self.plan_api_key
        if request_kind == "setting":
            return self.setting_base_url, self.setting_api_key
        if request_kind == "chat":
            return self.chat_base_url, self.chat_api_key
        return self.base_url, self.api_key

    def _require_litellm_sdk(self, client: Any, *, feature: str) -> None:
        if client is None:
            raise RuntimeError(f"litellm_sdk_not_installed:{feature}")

    def _build_litellm_request_kwargs(
        self,
        *,
        api_base: str,
        api_key: str,
        model: str,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "timeout": self.timeout_seconds,
        }
        if api_base:
            kwargs["api_base"] = api_base
        if api_key:
            kwargs["api_key"] = api_key
        forced_provider = _infer_openai_compatible_provider(model=model, api_base=api_base)
        if forced_provider:
            kwargs["custom_llm_provider"] = forced_provider
        return kwargs

    def _normalize_litellm_payload_model(
        self,
        payload: dict[str, Any],
        *,
        api_base: str,
    ) -> dict[str, Any]:
        resolved_payload = dict(payload)
        raw_model = str(resolved_payload.get("model") or "").strip()
        resolved_payload["model"] = _normalize_litellm_model_name(
            model=raw_model,
            api_base=api_base,
        )
        adapted_payload, adjustments = adapt_openai_compatible_payload(
            resolved_payload,
            model=str(resolved_payload["model"]),
        )
        if adjustments:
            logger.info(
                "model.request.compatibility model=%s adjustments=%s",
                raw_model,
                ",".join(adjustments),
            )
        return adapted_payload

    def _map_litellm_request_error(self, exc: Exception, *, request_kind: str) -> RuntimeError:
        return self._transport().map_error(exc, request_kind=request_kind)

    def _transport(self) -> ProviderTransport:
        return ProviderTransport(
            timeout_seconds=self.timeout_seconds,
            sdk=litellm,
            token_usage_service=self.token_usage_service,
        )

    def _execute_litellm_request(
        self,
        *,
        request_kind: str,
        model: str,
        invoke: Callable[[], Any],
    ) -> tuple[dict[str, Any], int]:
        return self._transport().execute(request_kind=request_kind, model=model, invoke=invoke)


def _validate_setting_slot_payload(payload: dict[str, Any]) -> None:
    try:
        PersonaSlotContentProposalV1.model_validate(payload.get("slot"), strict=True)
    except ValidationError as exc:
        raise RuntimeError("setting_model_invalid_payload") from exc


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


def _reject_nonstandard_json_constant(value: str) -> None:
    raise json.JSONDecodeError("non-standard JSON constant", value, 0)


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


def _extract_json_payload(
    content: str,
    *,
    invalid_json_code: str = "plan_model_invalid_json",
    invalid_payload_code: str = "plan_model_invalid_payload",
) -> dict[str, object]:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:].strip()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        # Some upstream models emit invalid string escapes like "\("; normalize and retry once.
        sanitized = _escape_invalid_backslashes_in_json_strings(content)
        if sanitized != content:
            try:
                payload = json.loads(sanitized)
            except json.JSONDecodeError:
                payload = None
        else:
            payload = None
        if payload is not None:
            if not isinstance(payload, dict):
                raise RuntimeError(invalid_payload_code)
            return payload
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError(invalid_json_code)
        sliced = content[start : end + 1]
        try:
            payload = json.loads(sliced)
        except json.JSONDecodeError:
            sanitized_sliced = _escape_invalid_backslashes_in_json_strings(sliced)
            try:
                payload = json.loads(sanitized_sliced)
            except json.JSONDecodeError as exc:
                raise RuntimeError(invalid_json_code) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(invalid_payload_code)
    return payload


class PlanningProposalDecodeError(RuntimeError):
    def __init__(self, *, path: str, reason: str) -> None:
        super().__init__(f"plan_proposal_schema_invalid:{path or '$'}:{reason}")
        self.path = path
        self.reason = reason


def _validate_learning_plan_proposal_refs(
    proposal: LearningPlanProposalV1, study_units: list[StudyUnitRecord],
) -> None:
    """Validate against the post-tool snapshot before the one repair allowance."""
    units = {unit.id: unit for unit in study_units}
    for index, item in enumerate(proposal.schedule):
        path = f"schedule.{index}"
        unit = units.get(item.unit_id)
        if unit is None:
            raise PlanningProposalDecodeError(path=f"{path}.unit_id", reason="unknown_ref")
        allowed = set(unit.source_section_ids)
        for chapter_index, chapter in enumerate(item.schedule_chapters):
            chapter_path = f"{path}.schedule_chapters.{chapter_index}"
            if not set(chapter.source_section_ids).issubset(allowed):
                raise PlanningProposalDecodeError(path=f"{chapter_path}.source_section_ids", reason="unknown_ref")
            for slice_index, content_slice in enumerate(chapter.content_slices):
                if not set(content_slice.source_section_ids).issubset(allowed):
                    raise PlanningProposalDecodeError(
                        path=f"{chapter_path}.content_slices.{slice_index}.source_section_ids",
                        reason="unknown_ref",
                    )


def _decode_learning_plan_proposal(content: str) -> LearningPlanProposalV1:
    try:
        payload = _extract_json_payload(content)
    except RuntimeError as exc:
        raise PlanningProposalDecodeError(path="$", reason=str(exc)) from exc
    try:
        return LearningPlanProposalV1.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        path = ".".join(str(item) for item in first_error.get("loc", ())) or "$"
        reason = str(first_error.get("type") or "validation_error")
        invariant = str(first_error.get("ctx", {}).get("error", ""))
        if invariant in {
            "duplicate_schedule_unit_ref", "duplicate_source_section_id",
            "page_end_before_page_start", "anchor_page_end_before_start",
        }:
            reason = invariant
        raise PlanningProposalDecodeError(path=path, reason=reason) from exc


def _merge_plan_generation_traces(
    *,
    first: PlanGenerationTraceRecord,
    second: PlanGenerationTraceRecord,
) -> PlanGenerationTraceRecord:
    offset = len(first.rounds)
    repaired_rounds = [
        item.model_copy(update={"round_index": offset + index})
        for index, item in enumerate(second.rounds)
    ]
    return first.model_copy(update={"rounds": [*first.rounds, *repaired_rounds]})


def _extract_response_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    output = payload.get("output")
    if not isinstance(output, list):
        raise RuntimeError("setting_model_invalid_payload")
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "output_text":
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
    merged = "\n".join(parts).strip()
    if not merged:
        raise RuntimeError("setting_model_invalid_payload")
    return merged








def _call_interrupt(callback: Callable[[], None] | None) -> None:
    if callback is None:
        return
    callback()


def _decode_persona_card_batch(parsed: dict[str, object]) -> dict[str, Any]:
    try:
        proposal = PersonaCardBatchContentProposalV1.model_validate(parsed, strict=True)
    except ValidationError as exc:
        raise RuntimeError("setting_model_invalid_payload") from exc
    batch = proposal.model_dump(mode="python")
    for field in ("summary", "relationship", "learner_address"):
        batch[field] = batch[field].strip()
    return batch


def _enforce_exact_persona_card_count(
    cards: list[dict[str, object]],
    *,
    count: int | None,
) -> None:
    if count is None or count < 1:
        return
    if len(cards) != count:
        raise RuntimeError("setting_persona_card_count_mismatch")


def _stable_scene_token(seed: str, prefix: str) -> str:
    value = 0
    for char in seed:
        value = ((value * 131) + ord(char)) % 0xFFFFFFFF
    return f"{prefix}-{value:08x}"


def _normalize_generated_scene_result(
    parsed: dict[str, object],
    *,
    used_model: str,
    used_web_search: bool,
) -> dict[str, object]:
    proposal = decode_scene_tree_proposal(parsed)
    try:
        projection = project_scene_tree_proposal(proposal)
    except ValueError as exc:
        reason = str(exc).strip().replace(" ", "_") or "projection_invalid"
        raise RuntimeError(
            f"setting_scene_proposal_invalid:$:{reason}"
        ) from exc
    return {
        "proposal": proposal.model_dump(mode="json", exclude_none=False),
        "scene_name": projection.scene_name,
        "scene_summary": projection.scene_summary,
        "selected_layer_id": projection.selected_layer_id,
        "scene_layers": [
            layer.model_dump(mode="json") for layer in projection.scene_layers
        ],
        "used_model": used_model,
        "used_web_search": used_web_search,
    }


def _scene_proposal_payload_from_layers(
    *,
    scene_name: str,
    scene_summary: str,
    layers: list[SceneLayerStateRecord],
) -> dict[str, object]:
    def split_tags(value: str) -> list[str]:
        return [
            item.strip()
            for item in value.replace("，", ",").split(",")
            if item.strip()
        ]

    def object_payload(item: SceneObjectStateRecord) -> dict[str, object]:
        return {
            "name": item.name,
            "description": item.description,
            "interaction": item.interaction,
            "tags": split_tags(item.tags),
            "reuse_hint": item.reuse_hint,
        }

    def layer_payload(item: SceneLayerStateRecord) -> dict[str, object]:
        return {
            "title": item.title,
            "scope_label": item.scope_label,
            "summary": item.summary,
            "atmosphere": item.atmosphere,
            "rules": item.rules,
            "entrance": item.entrance,
            "tags": split_tags(item.tags),
            "reuse_hint": item.reuse_hint,
            "objects": [object_payload(obj) for obj in item.objects],
            "children": [layer_payload(child) for child in item.children],
        }

    return {
        "schema_name": "scene-tree-proposal",
        "schema_version": "scene-tree-proposal-v1",
        "scene_name": scene_name,
        "scene_summary": scene_summary,
        "selected_path": _deepest_scene_layer_path(layers),
        "scene_layers": [layer_payload(layer) for layer in layers],
    }


def _deepest_scene_layer_path(layers: list[SceneLayerStateRecord]) -> list[int]:
    deepest_path: list[int] = []

    def visit(layer: SceneLayerStateRecord, path: list[int]) -> None:
        nonlocal deepest_path
        if len(path) > len(deepest_path):
            deepest_path = path
        for index, child in enumerate(layer.children):
            visit(child, [*path, index])

    for index, layer in enumerate(layers):
        visit(layer, [index])
    return deepest_path


def _render_persona_card_count_hint(count: int | None) -> str:
    if count is None or count < 1:
        return "未指定"
    return str(count)


def _resolve_persona_card_count_hint(count: int | None, *, default: int) -> int:
    if count is None or count < 1:
        return default
    return count


def _render_scene_layer_count_hint(layer_count: int | None) -> str:
    if layer_count is None or layer_count < 1:
        return "未指定"
    return str(layer_count)


def _resolve_scene_layer_count_hint(layer_count: int | None, *, default: int) -> int:
    if layer_count is None or layer_count < 1:
        return default
    return layer_count


def _extract_scene_anchors_from_text(text: str) -> list[str]:
    tokens = [
        token.strip()
        for token in re.split(r"[，,、；;：:\s]+", text)
        if token.strip()
    ]
    anchors: list[str] = []
    for token in tokens:
        if len(token) < 2:
            continue
        anchors.append(token)
        if len(anchors) >= 6:
            break
    return anchors or ["教材", "课堂", "实验台"]


def _build_mock_scene_layers(
    *,
    layer_count: int,
    anchors: list[str],
    fragments: list[str],
) -> list[SceneLayerStateRecord]:
    layer_templates = [
        ("世界整体", "宏观世界"),
        ("区域 / 城市群", "区域层"),
        ("街区 / 校园周边", "城市层"),
        ("校园 / 教学楼", "建筑层"),
        ("教室 / 实验区", "微观教室"),
        ("讲台 / 操作台", "互动层"),
        ("桌面 / 设备焦点", "近景层"),
        ("局部道具", "对象层"),
    ]

    def build_layer(depth: int) -> SceneLayerStateRecord:
        title, scope_label = layer_templates[min(depth, len(layer_templates) - 1)]
        anchor = anchors[depth % len(anchors)] if anchors else "学习"
        fragment = fragments[depth % len(fragments)] if fragments else "围绕学习任务组织空间。"
        layer_title = f"{anchor}{title}" if depth else f"{anchor}{title}"
        object_name = f"{anchor}装置"
        seed = f"{depth}:{layer_title}:{scope_label}"
        child_layers = [build_layer(depth + 1)] if depth + 1 < layer_count else []
        return SceneLayerStateRecord(
            id=_stable_scene_token(seed, "scene-layer"),
            title=layer_title,
            scope_label=scope_label,
            summary=f"{fragment[:64]} 这一层负责把“{anchor}”主题收束到当前空间尺度。",
            atmosphere=f"空间基调围绕“{anchor}”展开，信息密度和视觉焦点随层级逐步集中。",
            rules=f"当前层级保留与“{anchor}”相关的核心规则，并为下级节点提供更具体的互动边界。",
            entrance=f"从上一层进入时，先感知“{anchor}”相关线索，再把注意力推进到当前尺度的关键设施。",
            tags=",".join(dict.fromkeys([anchor, scope_label, "可复用节点"])),
            reuse_id=_stable_scene_token(seed, "scene-layer-reuse"),
            reuse_hint=f"适合作为“{anchor}”主题下的 {scope_label} 模板节点，后续可替换物体和规则后直接复用。",
            objects=[
                SceneObjectStateRecord(
                    id=_stable_scene_token(seed + ":object", "scene-object"),
                    name=object_name,
                    description=f"承载“{anchor}”主题线索的核心物体，用于帮助学习者快速识别当前层级的功能。",
                    interaction=f"可读取、操作或指向该物体，以推进与“{anchor}”相关的讲解或任务。",
                    tags=",".join(dict.fromkeys([anchor, "交互", scope_label])),
                    reuse_id=_stable_scene_token(seed + ":object", "scene-object-reuse"),
                    reuse_hint=f"可复用为“{object_name}”这一类核心交互物体。",
                )
            ],
            children=child_layers,
        )

    return [build_layer(0)]


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


def _public_chat_tool_trace_result(result: dict[str, Any]) -> dict[str, Any]:
    """Remove server-only question grading material from public tool traces."""

    if str(result.get("question_type") or "") not in {
        "multiple_choice",
        "fill_blank",
    }:
        return result
    return {
        key: value
        for key, value in result.items()
        if key not in STUDY_QUESTION_TOOL_TRACE_PRIVATE_FIELDS
    }


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


def _parse_tavern_actor_reply(raw_payload: dict[str, Any]) -> TavernActorReply:
    try:
        content = _extract_choice_content(raw_payload)
        parsed = _extract_json_payload(
            content,
            invalid_json_code="tavern_actor_invalid_payload",
            invalid_payload_code="tavern_actor_invalid_payload",
        )
        return TavernActorReply.model_validate(parsed)
    except Exception as exc:
        if isinstance(exc, ModelRequestError):
            raise
        raise RuntimeError("tavern_actor_invalid_payload") from exc


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


def _escape_invalid_backslashes_in_json_strings(raw: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    i = 0
    valid_escape = {'"', "\\", "/", "b", "f", "n", "r", "t", "u"}

    while i < len(raw):
        ch = raw[i]
        if not in_string:
            result.append(ch)
            if ch == '"':
                in_string = True
            i += 1
            continue

        if escaped:
            result.append(ch)
            escaped = False
            i += 1
            continue

        if ch == "\\":
            next_char = raw[i + 1] if i + 1 < len(raw) else ""
            if next_char and next_char in valid_escape:
                result.append(ch)
            else:
                # Double invalid backslashes so the payload remains literal text.
                result.append("\\\\")
            escaped = True
            i += 1
            continue

        result.append(ch)
        if ch == '"':
            in_string = False
        i += 1

    return "".join(result)


def _emit_progress(
    callback: Callable[[str, dict[str, object]], None] | None,
    stage: str,
    payload: dict[str, object],
) -> None:
    if callback is None:
        return
    callback(stage, payload)


def _build_course_title(
    *,
    document_title: str,
    plannable_units: list[StudyUnitRecord],
) -> str:
    lead_titles = [unit.title.strip() for unit in plannable_units[:2] if unit.title.strip()]
    if lead_titles:
        return " / ".join(lead_titles)
    return document_title.strip()


def _fallback_schedule_chapters_for_unit(
    unit: StudyUnitRecord,
) -> list[PlanScheduleChapterProposalV1]:
    normalized_sources = [str(item).strip() for item in unit.source_section_ids if str(item).strip()]
    return [
        PlanScheduleChapterProposalV1(
            title=unit.title,
            anchor_page_start=unit.page_start,
            anchor_page_end=unit.page_end,
            source_section_ids=normalized_sources,
            content_slices=[
                PlanContentSliceProposalV1(
                    page_start=unit.page_start,
                    page_end=unit.page_end,
                    source_section_ids=normalized_sources,
                )
            ],
        )
    ]


def _study_units_changed(
    original_units: list[StudyUnitRecord],
    current_units: list[StudyUnitRecord],
) -> bool:
    if len(original_units) != len(current_units):
        return True
    for original, current in zip(original_units, current_units):
        if (
            original.id != current.id
            or original.title != current.title
            or original.page_start != current.page_start
            or original.page_end != current.page_end
            or original.include_in_plan != current.include_in_plan
        ):
            return True
    return False


def _should_fallback_setting_web_search(exc: RuntimeError) -> bool:
    detail = str(exc).strip()
    return (
        detail.startswith("openai_setting_request_failed:400:")
        or detail.startswith("openai_setting_request_failed:422:")
        or detail.startswith("openai_setting_request_failed:500:")
    )


def _should_fallback_tavern_schema_transport(exc: ModelRequestError) -> bool:
    return (
        exc.status_code in {"400", "422"}
        or exc.upstream_code == "unsupported_params"
        or str(exc) == "openai_chat_request_unsupported_params"
    )


def _normalize_litellm_model_name(*, model: str, api_base: str) -> str:
    normalized = model.strip()
    if not normalized:
        return normalized
    if _litellm_model_has_provider_prefix(normalized):
        return normalized
    if _infer_openai_compatible_provider(model=normalized, api_base=api_base):
        return f"openai/{normalized}"
    return normalized


def _infer_openai_compatible_provider(*, model: str, api_base: str) -> str | None:
    if not model.strip():
        return None
    if _litellm_model_has_provider_prefix(model):
        return None
    normalized_base = api_base.rstrip("/")
    if not normalized_base:
        return None
    if normalized_base == "https://api.openai.com/v1":
        return None
    return "openai"


def _litellm_model_has_provider_prefix(model: str) -> bool:
    if "/" not in model:
        return False
    provider = model.split("/", 1)[0].strip().lower()
    if not provider:
        return False
    return provider in _known_litellm_providers()


def _known_litellm_providers() -> set[str]:
    if litellm is not None:
        providers = getattr(litellm, "provider_list", None)
        if providers:
            normalized = {
                str(getattr(provider, "value", provider)).strip().lower()
                for provider in providers
            }
            return {provider for provider in normalized if provider}
    return {
        "openai",
        "azure",
        "anthropic",
        "gemini",
        "vertex_ai",
        "vertex_ai_beta",
        "openrouter",
        "ollama",
        "huggingface",
        "bedrock",
        "xai",
        "custom_openai",
        "openai_like",
        "text-completion-openai",
    }


def _extract_choice_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("chat_model_invalid_payload")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise RuntimeError("chat_model_invalid_payload")

    # Some OpenAI-compatible providers return assistant text in non-standard shapes.
    # Keep extraction tolerant before treating the payload as invalid.
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        for key in ("text", "value", "content"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, dict):
                nested = value.get("value")
                if isinstance(nested, str) and nested.strip():
                    return nested
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type not in {"text", "output_text", "message"}:
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                texts.append(text_value)
                continue
            if isinstance(text_value, dict):
                nested_value = text_value.get("value")
                if isinstance(nested_value, str) and nested_value.strip():
                    texts.append(nested_value)
                    continue
            value_field = item.get("value")
            if isinstance(value_field, str) and value_field.strip():
                texts.append(value_field)
        merged = "".join(texts).strip()
        if merged:
            return merged

    alt_text = choices[0].get("text") if isinstance(choices[0], dict) else None
    if isinstance(alt_text, str) and alt_text.strip():
        return alt_text

    reasoning_content = message.get("reasoning_content")
    if isinstance(reasoning_content, str) and reasoning_content.strip():
        logger.warning("model.chat.extract_content fallback=reasoning_content")
        return reasoning_content

    logger.warning(
        "model.chat.extract_content failed message_keys=%s content_type=%s",
        sorted(message.keys()),
        type(content).__name__,
    )
    raise RuntimeError("chat_model_invalid_payload")


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
