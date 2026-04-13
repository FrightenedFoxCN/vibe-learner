from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Callable
from typing import Any

from fastapi import HTTPException

from app.core.logging import get_logger
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
from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG
from app.services.model_recovery import record_model_recovery
from app.services.persona_runtime import render_persona_runtime_instruction
from app.services.token_usage import TokenUsageService
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
    '"scene_name": string, '
    '"scene_summary": string, '
    '"selected_layer_id": string, '
    '"scene_layers": [{"id"?: string, "title": string, "scope_label": string, "summary": string, '
    '"atmosphere": string, "rules": string, "entrance": string, "tags"?: string, "reuse_id"?: string, '
    '"reuse_hint"?: string, "objects"?: [{"id"?: string, "name": string, "description": string, '
    '"interaction": string, "tags"?: string, "reuse_id"?: string, "reuse_hint"?: string}], '
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
LITELLM_TRANSIENT_RETRY_COUNT = 2
LITELLM_TRANSIENT_RETRYABLE_STATUS_CODES = frozenset({"408", "409", "425", "500", "502", "503", "504"})


class ModelRequestError(RuntimeError):
    def __init__(
        self,
        code: str,
        *,
        attempts: int = 1,
        status_code: str = "",
        upstream_code: str = "",
        upstream_message: str = "",
    ) -> None:
        super().__init__(code)
        self.attempts = max(1, attempts)
        self.status_code = status_code
        self.upstream_code = upstream_code
        self.upstream_message = upstream_message


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


def _recover_legacy_chat_payload(content: str) -> dict[str, object] | None:
    text_key = '"text": "'
    text_start = content.find(text_key)
    if text_start == -1:
        return None
    raw_text_start = text_start + len(text_key)
    raw_text_end = content.find('",\n  "mood"', raw_text_start)
    if raw_text_end == -1:
        raw_text = content[raw_text_start:]
        raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        raw_text = re.sub(r'"\s*}\s*```?\s*$', "", raw_text).rstrip("`").rstrip()
    else:
        raw_text = content[raw_text_start:raw_text_end]
    repaired_source = (
        raw_text
        .replace(r"\"", "__ESCAPED_QUOTE__")
        .replace('"', r"\"")
        .replace("__ESCAPED_QUOTE__", r"\"")
        .replace("\r\n", r"\n")
        .replace("\n", r"\n")
    )
    try:
        recovered_text = json.loads(f'"{repaired_source}"')
    except json.JSONDecodeError:
        return None
    payload: dict[str, object] = {
        "text": recovered_text,
        "mood": str(re.search(r'"mood"\s*:\s*"([^"]+)"', content).group(1)) if re.search(r'"mood"\s*:\s*"([^"]+)"', content) else "calm",
        "action": str(re.search(r'"action"\s*:\s*"([^"]+)"', content).group(1)) if re.search(r'"action"\s*:\s*"([^"]+)"', content) else "point",
    }
    speech_style_match = re.search(r'"speech_style"\s*:\s*"([^"]+)"', content)
    delivery_cue_match = re.search(r'"delivery_cue"\s*:\s*"([^"]+)"', content)
    commentary_match = re.search(r'"state_commentary"\s*:\s*"([^"]+)"', content)
    if speech_style_match:
        payload["speech_style"] = speech_style_match.group(1)
    if delivery_cue_match:
        payload["delivery_cue"] = delivery_cue_match.group(1)
    if commentary_match:
        payload["state_commentary"] = commentary_match.group(1)
    return payload


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


@dataclass
class ModelReply:
    text: str
    mood: str
    action: str
    speech_style: str = ""
    delivery_cue: str = ""
    state_commentary: str = ""
    rich_blocks: list[RichTextBlockRecord] | None = None
    interactive_question: dict[str, Any] | None = None
    memory_trace: list[dict[str, Any]] | None = None
    tool_calls: list[ChatToolCallTraceRecord] | None = None
    scene_profile: SceneProfileRecord | None = None


@dataclass
class PlanScheduleItem:
    unit_id: str
    title: str
    focus: str
    activity_type: str


@dataclass
class PlanModelReply:
    course_title: str
    overview: str
    study_chapters: list[str]
    today_tasks: list[str]
    schedule: list[PlanScheduleItem]
    revised_study_units: list[StudyUnitRecord] | None = None
    planning_questions: list[PlanningQuestionRecord] | None = None
    debug_trace: PlanGenerationTraceRecord | None = None


class ModelProvider:
    def generate_chat(
        self,
        *,
        persona: PersonaProfile,
        section_id: str,
        message: str,
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
        raise NotImplementedError

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return []

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ModelReply:
        raise NotImplementedError

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> ModelReply:
        raise NotImplementedError

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
    ) -> PlanModelReply:
        raise NotImplementedError

    def supports_page_image_tools(self) -> bool:
        return False

    def supports_chat_page_image_tools(self) -> bool:
        return False

    def plan_tools_runtime_enabled(self) -> bool:
        return False

    def chat_tools_runtime_enabled(self) -> bool:
        return False

    def chat_memory_tool_runtime_enabled(self) -> bool:
        return False

    def assist_persona_setting(
        self,
        *,
        name: str,
        summary: str,
        slots: list[PersonaSlot],
        rewrite_strength: float,
    ) -> dict[str, object]:
        raise NotImplementedError

    def assist_persona_slot(
        self,
        *,
        name: str,
        summary: str,
        slot: PersonaSlot,
        rewrite_strength: float,
    ) -> dict[str, object]:
        raise NotImplementedError

    def generate_persona_cards_from_keywords(
        self,
        *,
        keywords: str,
        count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError

    def generate_persona_cards_from_text(
        self,
        *,
        text: str,
        count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError

    def generate_scene_tree_from_keywords(
        self,
        *,
        keywords: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError

    def generate_scene_tree_from_text(
        self,
        *,
        text: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        raise NotImplementedError


class MockModelProvider(ModelProvider):
    def generate_chat(
        self,
        *,
        persona: PersonaProfile,
        section_id: str,
        message: str,
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
        teaching_method = persona_slot_content(persona, "teaching_method")
        style = teaching_method.split(",")[0].strip() if teaching_method else "结构化讲解"
        history_hint = ""
        if conversation_history:
            history_hint = f" 我已读取最近 {len(conversation_history)} 条上下文。"
        section_hint = f" 章节上下文：{section_context[:80]}。" if section_context else ""
        memory_hint = f" 我还参考了历史互动记忆：{memory_context[:80]}。" if memory_context else ""
        attachment_hint = f" 学习者还上传了材料：{attachment_context[:80]}。" if attachment_context else ""
        scene_hint = f" 当前会话场景：{scene_context[:80]}。" if scene_context else ""
        session_state_hint = f" 当前会话动态状态：{session_state_context[:80]}。" if session_state_context else ""
        text = (
            f"{persona.name} 正在结合章节 {section_id} 讲解。"
            f" 当前提问是：{message}。"
            f"{section_hint}"
            f"{memory_hint}"
            f"{attachment_hint}"
            f"{scene_hint}"
            f"{session_state_hint}"
            f"{history_hint}"
            f"{' 会话约束：' + session_prompt[:80] if session_prompt else ''}"
            f" 我会用 {style} 的方式先解释核心概念，再给你一个复述任务。"
        )
        narrative_mode = persona_slot_content(persona, "narrative_mode", "稳态导学")
        mood = "playful" if normalize_persona_narrative_mode(narrative_mode) == "light_story" else "calm"
        return ModelReply(
            text=text,
            mood=mood,
            action="point",
            speech_style=persona.default_speech_style,
            delivery_cue="先稳住节奏，再把概念拆成两到三个抓手。",
            state_commentary=f"围绕 {section_id} 保持连续讲解，并根据当前提问延展重点。",
            rich_blocks=[],
            memory_trace=memory_trace_hits or [],
        )

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ModelReply:
        text = (
            f"围绕 {section_id} 的 {topic}，请你先用三句话概括概念，"
            "再举一个教材中的例子。"
        )
        return ModelReply(
            text=text,
            mood="encouraging",
            action="lean_in",
            speech_style=persona.default_speech_style,
            delivery_cue="提问时把语气往前推一点，给学习者明确的答题起点。",
            state_commentary=f"正在把 {topic} 转成可作答的小练习。",
            rich_blocks=[],
        )

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> ModelReply:
        quality = "完整" if len(answer.strip()) > 24 else "偏短"
        text = (
            f"针对练习 {exercise_id}，你的回答{quality}。"
            " 我会指出遗漏点，并给出下一步复习建议。"
        )
        mood = "excited" if quality == "完整" else "concerned"
        action = "smile" if quality == "完整" else "pause"
        return ModelReply(
            text=text,
            mood=mood,
            action=action,
            speech_style=persona.default_speech_style,
            delivery_cue="先给判断，再补原因，末尾留一个可执行的修正动作。",
            state_commentary="正在根据答题完整度切换鼓励或纠偏反馈。",
            rich_blocks=[],
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
    ) -> PlanModelReply:
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
            study_chapters=[unit.title for unit in plannable_units[:4]],
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
        raise RuntimeError("setting_keyword_generation_requires_openai")

    def generate_persona_cards_from_text(
        self,
        *,
        text: str,
        count: int | None,
    ) -> dict[str, object]:
        sentences = [segment.strip() for segment in re.split(r"[。！？\n]+", text) if segment.strip()]
        target_count = _resolve_persona_card_count_hint(count, default=6)
        seed = sentences[:target_count]
        if not seed:
            raise RuntimeError("setting_model_invalid_payload")
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
        selected_layer_id = _select_deepest_layer_id(layers)
        return {
            "scene_name": f"{seed_name} 场景树" if seed_name else "关键词场景树",
            "scene_summary": f"根据关键词 {theme} 生成的分层场景草稿，适合继续补充教学动线、规则与交互节点。",
            "selected_layer_id": selected_layer_id,
            "scene_layers": [layer.model_dump(mode="json") for layer in layers],
            "used_model": "mock",
            "used_web_search": False,
        }

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
        selected_layer_id = _select_deepest_layer_id(layers)
        scene_name_seed = fragments[0][:18].strip("：:- ")
        return {
            "scene_name": f"{scene_name_seed or '长文本'} 场景树",
            "scene_summary": f"从长文本中抽取出的分层场景结构，共 {len(layers)} 层，可继续作为教学或角色互动场景复用。",
            "selected_layer_id": selected_layer_id,
            "scene_layers": [layer.model_dump(mode="json") for layer in layers],
            "used_model": "mock",
            "used_web_search": False,
        }


class OpenAIModelProvider(MockModelProvider):
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

    def supports_page_image_tools(self) -> bool:
        return self.multimodal_enabled

    def supports_chat_page_image_tools(self) -> bool:
        return self.chat_multimodal_enabled

    def plan_tools_runtime_enabled(self) -> bool:
        return self.plan_tools_enabled

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
            "如需读取系统时间、读写临时记忆、调整好感度、安排稍后自动续接，或把会话中的 PDF/图片附件投到预览窗口并进行切页或标注，可调用 read_system_time、read_session_memory、write_session_memory、read_affinity_state、update_affinity_state、schedule_session_follow_up、project_uploaded_pdf、project_uploaded_image、read_projected_pdf_content、read_projected_pdf_images、focus_projected_pdf_page、highlight_projected_pdf_text、annotate_projected_pdf_region、clear_projected_pdf_overlays、annotate_projected_image_region、clear_projected_image_overlays。"
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
        tool_call_traces: list[ChatToolCallTraceRecord] = []
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
                    )
                    last_tool_results.append(execution["result"])
                    tool_call_traces.append(
                        ChatToolCallTraceRecord.model_validate(
                            serialize_chat_tool_trace_item(
                                tool_call_id=execution["tool_call_id"],
                                tool_name=execution["tool_name"],
                                arguments_json=execution["arguments_json"],
                                result=execution["result"],
                            )
                        )
                    )
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": execution["tool_call_id"],
                            "name": execution["tool_name"],
                            "content": json.dumps(execution["result"], ensure_ascii=False),
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
            recovery_messages = [
                *messages,
                {
                    "role": "user",
                    "content": _build_chat_recovery_instruction(
                        reason=recovery_reason,
                        prompt_sections=prompt_sections,
                    ).replace("{{CHAT_JSON_SCHEMA}}", CHAT_JSON_SCHEMA),
                },
            ]
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
                tool_results=[],
                fallback_memory_trace=memory_trace_hits or [],
                tool_traces=[],
            )
            record_model_recovery(
                category="semantic_retry",
                reason=recovery_reason,
                strategy="retry_without_tools",
                attempts=2,
            )
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
        returned_slots_raw = parsed.get("slots") or []
        system_prompt_suggestion = str(parsed.get("system_prompt_suggestion") or "").strip()
        if not system_prompt_suggestion:
            raise RuntimeError("setting_model_invalid_payload")
        returned_slots: list[PersonaSlot] = []
        for item in returned_slots_raw:
            if isinstance(item, dict) and item.get("kind") and item.get("content"):
                returned_slots.append(
                    PersonaSlot(
                        kind=str(item["kind"]),
                        label=str(item.get("label") or item["kind"]),
                        content=str(item["content"]),
                        weight=float(item.get("weight") or 1),
                        locked=bool(item.get("locked") or False),
                        sort_order=int(item.get("sort_order") or 0),
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
        )
        slot_raw = parsed.get("slot")
        if not isinstance(slot_raw, dict) or not slot_raw.get("kind") or not slot_raw.get("content"):
            raise RuntimeError("setting_model_invalid_payload")
        return {
            "slot": PersonaSlot(
                kind=str(slot_raw.get("kind")),
                label=str(slot_raw.get("label") or slot_raw.get("kind")),
                content=str(slot_raw.get("content")),
                weight=float(slot_raw.get("weight") or slot.weight),
                locked=bool(slot_raw.get("locked") if slot_raw.get("locked") is not None else slot.locked),
                sort_order=int(slot_raw.get("sort_order") if slot_raw.get("sort_order") is not None else slot.sort_order),
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
        return {
            "summary": str(parsed.get("summary") or "").strip(),
            "relationship": str(parsed.get("relationship") or "").strip(),
            "learner_address": str(parsed.get("learner_address") or "").strip(),
            "cards": _normalize_generated_persona_cards(parsed),
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
        return {
            "summary": str(parsed.get("summary") or "").strip(),
            "relationship": str(parsed.get("relationship") or "").strip(),
            "learner_address": str(parsed.get("learner_address") or "").strip(),
            "cards": _normalize_generated_persona_cards(parsed),
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
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，并确保 scene_name、scene_summary、selected_layer_id、scene_layers 字段完整。",
        )

    def _request_setting_json_chat(
        self,
        payload: dict[str, Any],
        *,
        retry_instruction: str,
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
            retry_instruction="上一次输出没有形成合法 JSON。请严格只输出一个 JSON 对象，并确保 scene_name、scene_summary、selected_layer_id、scene_layers 字段完整。",
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
        run_result = self._run_plan_model(
            model=self.plan_model,
            document_id=goal.document_id,
            messages=messages,
            tool_runtime=tool_runtime,
            progress_callback=progress_callback,
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
                allow_fallback=False,
            )
            if run_result is not None:
                active_tool_runtime = fallback_runtime
                _emit_progress(
                    progress_callback,
                    "model_fallback_succeeded",
                    {
                        "fallback_model": self.fallback_plan_model,
                    },
                )
        if run_result is None:
            raise RuntimeError("plan_model_empty_response")
        parsed = _extract_json_payload(run_result.content)
        schedule_items = [
            PlanScheduleItem(
                unit_id=str(item["unit_id"]),
                title=str(item["title"]),
                focus=str(item["focus"]),
                activity_type=str(item["activity_type"]),
            )
            for item in parsed.get("schedule", [])
        ]
        active_study_units = active_tool_runtime.current_study_units()
        planning_questions = active_tool_runtime.current_planning_questions()
        return PlanModelReply(
            course_title=str(
                parsed.get("course_title")
                or _build_course_title(
                    document_title=document_title,
                    plannable_units=study_units,
                )
            ),
            overview=str(parsed["overview"]),
            study_chapters=[
                str(item)
                for item in parsed.get("study_chapters", [])
            ],
            today_tasks=[str(item) for item in parsed.get("today_tasks", [])],
            schedule=schedule_items,
            revised_study_units=active_study_units if _study_units_changed(study_units, active_study_units) else None,
            planning_questions=planning_questions,
            debug_trace=run_result.trace,
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
            return build_plan_tool_runtime(planning_questions=planning_questions)
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
            )
        except RuntimeError as exc:
            if allow_fallback and str(exc) in {"plan_model_empty_response", "plan_model_tool_loop_exhausted"}:
                return None
            raise

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
        clean = [text.strip() for text in texts if text and text.strip()]
        if not clean:
            return []
        payload: dict[str, Any] = {
            "model": self.embedding_model,
            "input": clean,
        }
        raw_payload, _ = self._request_openai_embeddings(payload, model=self.embedding_model)
        data = raw_payload.get("data") or []
        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if isinstance(embedding, list):
                vectors.append([float(value) for value in embedding])
        return vectors

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
        if self.token_usage_service is None:
            return
        usage = raw_payload.get("usage") if isinstance(raw_payload, dict) else None
        if not isinstance(usage, dict):
            return
        prompt_tokens = _coerce_int(usage.get(prompt_key) or usage.get("prompt_tokens"), default=0)
        completion_tokens = _coerce_int(usage.get(completion_key) or usage.get("completion_tokens"), default=0)
        total_tokens = _coerce_int(usage.get("total_tokens"), default=prompt_tokens + completion_tokens)
        try:
            self.token_usage_service.record(
                feature=feature,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            )
        except Exception:
            logger.exception("token_usage.record failed feature=%s model=%s", feature, model)

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
        return resolved_payload

    def _map_litellm_request_error(self, exc: Exception, *, request_kind: str) -> RuntimeError:
        if _is_litellm_rate_limit_error(exc):
            logger.exception("model.%s.rate_limit provider=litellm", request_kind)
            return ModelRequestError(f"openai_{request_kind}_request_rate_limit")
        if _is_litellm_timeout_error(exc):
            logger.exception(
                "model.%s.timeout provider=litellm timeout_seconds=%s",
                request_kind,
                self.timeout_seconds,
            )
            return ModelRequestError(f"openai_{request_kind}_request_timeout")
        if _is_litellm_network_error(exc):
            logger.exception("model.%s.network_error provider=litellm", request_kind)
            return ModelRequestError(f"openai_{request_kind}_request_network_error")

        status_code, error_code, error_message = _extract_litellm_exception_details(exc)
        logger.exception(
            "model.%s.http_error provider=litellm status=%s upstream_code=%s upstream_message=%s",
            request_kind,
            status_code,
            error_code,
            error_message,
        )
        return ModelRequestError(
            f"openai_{request_kind}_request_failed:{status_code}:{error_code or 'unknown'}",
            status_code=status_code,
            upstream_code=error_code,
            upstream_message=error_message,
        )

    def _execute_litellm_request(
        self,
        *,
        request_kind: str,
        model: str,
        invoke: Callable[[], Any],
    ) -> tuple[dict[str, Any], int]:
        started_at = time.perf_counter()
        attempt = 0
        while True:
            attempt += 1
            try:
                raw_result = invoke()
                raw_payload = _normalize_litellm_payload(raw_result)
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                if attempt > 1:
                    record_model_recovery(
                        category="transport_retry",
                        reason="upstream_transient_error",
                        strategy="retry_same_payload",
                        attempts=attempt,
                    )
                    logger.info(
                        "model.%s.retry_recovered provider=litellm model=%s attempts=%s elapsed_ms=%s",
                        request_kind,
                        model,
                        attempt,
                        elapsed_ms,
                    )
                return raw_payload, elapsed_ms
            except Exception as exc:
                if _is_litellm_retryable_error(exc) and attempt <= LITELLM_TRANSIENT_RETRY_COUNT:
                    retry_delay_seconds = min(0.4 * attempt, 1.2)
                    status_code, error_code, error_message = _extract_litellm_exception_details(exc)
                    logger.warning(
                        "model.%s.retry provider=litellm model=%s attempt=%s max_retries=%s delay_ms=%s status=%s upstream_code=%s upstream_message=%s",
                        request_kind,
                        model,
                        attempt,
                        LITELLM_TRANSIENT_RETRY_COUNT,
                        int(retry_delay_seconds * 1000),
                        status_code or "unknown",
                        error_code or "unknown",
                        error_message,
                    )
                    time.sleep(retry_delay_seconds)
                    continue
                mapped_error = self._map_litellm_request_error(exc, request_kind=request_kind)
                if isinstance(mapped_error, ModelRequestError):
                    mapped_error.attempts = attempt
                raise mapped_error from exc


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

    disabled = disabled_tools or set()

    tools: list[dict[str, object]] = [
        {
            "type": "function",
            "function": {
                "name": "ask_multiple_choice_question",
                "description": TOOL_CATALOG[CHAT_STAGE]["ask_multiple_choice_question"]["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "可选。指定题目聚焦的概念、术语或练习主题。",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": "题目难度。",
                        },
                        "focus_mode": {
                            "type": "string",
                            "enum": ["detail", "deep_understanding"],
                            "description": "偏向细节核对，或偏向深层理解。",
                        },
                        "option_count": {
                            "type": "integer",
                            "minimum": 3,
                            "maximum": 5,
                            "description": "选项数量。",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "ask_fill_blank_question",
                "description": TOOL_CATALOG[CHAT_STAGE]["ask_fill_blank_question"]["description"],
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "可选。指定题目聚焦的概念、术语或练习主题。",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": "题目难度。",
                        },
                        "focus_mode": {
                            "type": "string",
                            "enum": ["detail", "deep_understanding"],
                            "description": "偏向细节核对，或偏向深层理解。",
                        },
                        "blank_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                            "description": "题干中需要填空的位置数量。",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
    ]

    if memory_tool_enabled and memory_hits:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "retrieve_memory_context",
                    "description": TOOL_CATALOG[CHAT_STAGE]["retrieve_memory_context"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "top_k": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 8,
                                "description": "返回的历史记忆条数。",
                            }
                        },
                        "additionalProperties": False,
                    },
                },
            }
        )

    if debug_report is not None:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "read_page_range_content",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_page_range_content"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_start": {"type": "integer", "description": "要读取的起始页码。"},
                            "page_end": {"type": "integer", "description": "要读取的结束页码。"},
                            "max_chars": {"type": "integer", "description": "返回文本的最大字符预算。"},
                        },
                        "required": ["page_start", "page_end"],
                        "additionalProperties": False,
                    },
                },
            }
        )

    if multimodal_enabled and debug_report is not None and document_path:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "read_page_range_images",
                    "description": TOOL_CATALOG[CHAT_STAGE]["read_page_range_images"]["description"],
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_start": {"type": "integer", "description": "要渲染图像的起始页码。"},
                            "page_end": {"type": "integer", "description": "要渲染图像的结束页码。"},
                            "max_images": {"type": "integer", "description": "最多返回的页图像数量。"},
                        },
                        "required": ["page_start", "page_end"],
                        "additionalProperties": False,
                    },
                },
            }
        )

    if plan_tool_runtime is not None:
        tools.extend(plan_tool_runtime.tool_specs())

    if session_tool_runtime is not None:
        tools.extend(session_tool_runtime.tool_specs())

    if scene_tool_runtime is not None:
        tools.extend(scene_tool_runtime.tool_specs())

    return [
        tool
        for tool in tools
        if str((tool.get("function") or {}).get("name") or "") not in disabled
    ]


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
) -> dict[str, Any]:
    function_payload = tool_call.get("function") or {}
    tool_name = str(function_payload.get("name") or "")
    tool_call_id = str(tool_call.get("id") or "")
    raw_arguments = str(function_payload.get("arguments") or "{}")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        arguments = {}

    if tool_name in (disabled_tools or set()):
        result = {
            "ok": False,
            "error": "tool_disabled",
            "tool_name": tool_name,
        }
        return {
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "arguments_json": raw_arguments,
            "result": result,
        }

    if tool_name == "ask_multiple_choice_question":
        result = _build_multiple_choice_question(
            section_id=section_id,
            section_context=section_context,
            learner_message=learner_message,
            arguments=arguments,
        )
    elif tool_name == "ask_fill_blank_question":
        result = _build_fill_blank_question(
            section_id=section_id,
            section_context=section_context,
            learner_message=learner_message,
            arguments=arguments,
        )
    elif tool_name == "read_page_range_content":
        page_start = _coerce_int(arguments.get("page_start"), default=1)
        page_end = _coerce_int(arguments.get("page_end"), default=page_start)
        max_chars = _coerce_int(arguments.get("max_chars"), default=4000)
        result = {
            "ok": True,
            "tool_name": tool_name,
            "section_id": section_id,
            **read_page_range_content(
                debug_report=debug_report,
                page_start=max(1, page_start),
                page_end=max(max(1, page_start), page_end),
                max_chars=max(800, min(max_chars, 8000)),
            ),
        }
    elif tool_name == "read_page_range_images":
        page_start = _coerce_int(arguments.get("page_start"), default=1)
        page_end = _coerce_int(arguments.get("page_end"), default=page_start)
        max_images = _coerce_int(arguments.get("max_images"), default=2)
        result = {
            "ok": True,
            "tool_name": tool_name,
            "section_id": section_id,
            **read_page_range_images(
                document_path=document_path,
                page_start=max(1, page_start),
                page_end=max(max(1, page_start), page_end),
                max_images=max(1, min(max_images, 4)),
            ),
        }
    elif tool_name == "retrieve_memory_context":
        top_k = _coerce_int(arguments.get("top_k"), default=4)
        top_k = max(1, min(top_k, 8))
        result = {
            "ok": True,
            "tool_name": tool_name,
            "section_id": section_id,
            "hit_count": min(len(memory_hits), top_k),
            "hits": memory_hits[:top_k],
        }
    elif session_tool_runtime is not None and bool(getattr(session_tool_runtime, "has_tool", lambda _name: False)(tool_name)):
        try:
            result = session_tool_runtime.execute_tool(tool_name, arguments)
        except HTTPException as exc:
            result = {
                "ok": False,
                "error": str(exc.detail),
                "tool_name": tool_name,
            }
    elif plan_tool_runtime is not None and bool(getattr(plan_tool_runtime, "has_tool", lambda _name: False)(tool_name)):
        try:
            result = plan_tool_runtime.execute_tool(tool_name, arguments)
        except HTTPException as exc:
            result = {
                "ok": False,
                "error": str(exc.detail),
                "tool_name": tool_name,
            }
    elif scene_tool_runtime is not None:
        try:
            result = scene_tool_runtime.execute_tool(tool_name, arguments)
        except HTTPException as exc:
            result = {
                "ok": False,
                "error": str(exc.detail),
                "tool_name": tool_name,
            }
    else:
        result = {
            "ok": False,
            "error": "unknown_tool",
            "tool_name": tool_name,
        }

    return {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "arguments_json": raw_arguments,
        "result": result,
    }


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
    context_title = _extract_section_title(section_context)
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


def _extract_section_title(section_context: str) -> str:
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


def _coerce_int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sanitize_reply_text_for_question(text: str, question: dict[str, Any] | None) -> str:
    if not question:
        return text
    cleaned = text
    prompt = str(question.get("prompt") or "").strip()
    if prompt and prompt in cleaned:
        cleaned = cleaned.replace(prompt, "")
    for option in question.get("options") or []:
        option_text = str((option or {}).get("text") or "").strip()
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
) -> dict[str, Any] | None:
    payload = parsed.get("interactive_question")
    if isinstance(payload, dict):
        normalized = _normalize_interactive_question(payload)
        if normalized is not None:
            return normalized

    for result in reversed(tool_results):
        normalized = _normalize_interactive_question(result)
        if normalized is not None:
            return normalized
    return None


def _normalize_interactive_question(payload: dict[str, Any]) -> dict[str, Any] | None:
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
            if isinstance(option, dict):
                key = str(option.get("key") or chr(ord("A") + index)).strip() or chr(ord("A") + index)
                text = str(option.get("text") or "").strip()
            else:
                key = chr(ord("A") + index)
                text = str(option).strip()
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

    return {
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


def _normalize_generated_persona_cards(parsed: dict[str, object]) -> list[dict[str, object]]:
    raw_cards = parsed.get("cards")
    if not isinstance(raw_cards, list):
        raise RuntimeError("setting_model_invalid_payload")
    cards: list[dict[str, object]] = []
    for item in raw_cards:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        kind = str(item.get("kind") or "").strip() or "custom"
        label = str(item.get("label") or kind).strip() or kind
        content = str(item.get("content") or "").strip()
        if not title or not content:
            continue
        tags_raw = item.get("tags")
        tags = [str(tag).strip() for tag in tags_raw] if isinstance(tags_raw, list) else []
        cards.append(
            {
                "title": title,
                "kind": kind,
                "label": label,
                "content": content,
                "tags": [tag for tag in tags if tag],
                "source_note": str(item.get("source_note") or "").strip(),
            }
        )
    if not cards:
        raise RuntimeError("setting_model_invalid_payload")
    return cards


def _stable_scene_token(seed: str, prefix: str) -> str:
    value = 0
    for char in seed:
        value = ((value * 131) + ord(char)) % 0xFFFFFFFF
    return f"{prefix}-{value:08x}"


def _normalize_generated_scene_object(
    raw_object: object,
    *,
    parent_title: str,
    index: int,
) -> SceneObjectStateRecord | None:
    if not isinstance(raw_object, dict):
        return None
    name = str(raw_object.get("name") or "").strip()
    description = str(raw_object.get("description") or "").strip()
    interaction = str(raw_object.get("interaction") or "").strip()
    if not name or not description or not interaction:
        return None
    seed = f"{parent_title}:{name}:{index}"
    return SceneObjectStateRecord(
        id=str(raw_object.get("id") or _stable_scene_token(seed, "scene-object")),
        name=name,
        description=description,
        interaction=interaction,
        tags=str(raw_object.get("tags") or "").strip(),
        reuse_id=str(raw_object.get("reuse_id") or _stable_scene_token(seed, "scene-object-reuse")),
        reuse_hint=str(raw_object.get("reuse_hint") or f"可复用为“{name}”这一类交互物体。").strip(),
    )


def _normalize_generated_scene_layer(
    raw_layer: object,
    *,
    trail: tuple[str, ...],
    index: int,
) -> SceneLayerStateRecord | None:
    if not isinstance(raw_layer, dict):
        return None
    title = str(raw_layer.get("title") or "").strip()
    scope_label = str(raw_layer.get("scope_label") or raw_layer.get("scopeLabel") or "").strip()
    summary = str(raw_layer.get("summary") or "").strip()
    atmosphere = str(raw_layer.get("atmosphere") or "").strip()
    rules = str(raw_layer.get("rules") or "").strip()
    entrance = str(raw_layer.get("entrance") or "").strip()
    if not title or not scope_label or not summary or not atmosphere or not rules or not entrance:
        return None
    current_trail = (*trail, title)
    seed = "/".join(current_trail) + f":{scope_label}:{index}"
    raw_objects = raw_layer.get("objects")
    raw_children = raw_layer.get("children")
    objects = [
        item
        for object_index, raw_object in enumerate(raw_objects if isinstance(raw_objects, list) else [])
        if (item := _normalize_generated_scene_object(raw_object, parent_title=title, index=object_index)) is not None
    ]
    children = [
        item
        for child_index, raw_child in enumerate(raw_children if isinstance(raw_children, list) else [])
        if (item := _normalize_generated_scene_layer(raw_child, trail=current_trail, index=child_index)) is not None
    ]
    return SceneLayerStateRecord(
        id=str(raw_layer.get("id") or _stable_scene_token(seed, "scene-layer")),
        title=title,
        scope_label=scope_label,
        summary=summary,
        atmosphere=atmosphere,
        rules=rules,
        entrance=entrance,
        tags=str(raw_layer.get("tags") or "").strip(),
        reuse_id=str(raw_layer.get("reuse_id") or _stable_scene_token(seed, "scene-layer-reuse")),
        reuse_hint=str(
            raw_layer.get("reuse_hint")
            or f"可复用为“{title}”这一层场景模板，保留其规则、氛围和进入方式。"
        ).strip(),
        objects=objects,
        children=children,
    )


def _select_deepest_layer_id(layers: list[SceneLayerStateRecord]) -> str:
    deepest_id = ""
    deepest_depth = -1
    for root in layers:
        for layer, depth in _iter_scene_layers_with_depth(root):
            if depth > deepest_depth:
                deepest_id = layer.id
                deepest_depth = depth
    return deepest_id


def _normalize_generated_scene_result(
    parsed: dict[str, object],
    *,
    used_model: str,
    used_web_search: bool,
) -> dict[str, object]:
    raw_layers = parsed.get("scene_layers")
    if not isinstance(raw_layers, list):
        raise RuntimeError("setting_model_invalid_payload")
    scene_layers = [
        item
        for index, raw_layer in enumerate(raw_layers)
        if (item := _normalize_generated_scene_layer(raw_layer, trail=(), index=index)) is not None
    ]
    if not scene_layers:
        raise RuntimeError("setting_model_invalid_payload")
    selected_layer_id = str(parsed.get("selected_layer_id") or "").strip()
    valid_ids = {
        layer.id
        for layer in scene_layers
        for layer in _iter_scene_layers(layer)
    }
    if selected_layer_id not in valid_ids:
        selected_layer_id = _select_deepest_layer_id(scene_layers)
    scene_name = str(parsed.get("scene_name") or "").strip() or "生成场景树"
    scene_summary = str(parsed.get("scene_summary") or "").strip()
    if not scene_summary:
        scene_summary = f"围绕 {scene_name} 生成的可复用场景树。"
    return {
        "scene_name": scene_name,
        "scene_summary": scene_summary,
        "selected_layer_id": selected_layer_id,
        "scene_layers": [layer.model_dump(mode="json") for layer in scene_layers],
        "used_model": used_model,
        "used_web_search": used_web_search,
    }


def _iter_scene_layers(layer: SceneLayerStateRecord):
    yield layer
    for child in layer.children:
        yield from _iter_scene_layers(child)


def _iter_scene_layers_with_depth(layer: SceneLayerStateRecord, depth: int = 0):
    yield layer, depth
    for child in layer.children:
        yield from _iter_scene_layers_with_depth(child, depth + 1)


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


def _parse_chat_model_reply(
    *,
    raw_payload: dict[str, Any],
    tool_results: list[dict[str, Any]],
    fallback_memory_trace: list[dict[str, Any]],
    tool_traces: list[ChatToolCallTraceRecord],
) -> ModelReply:
    content = ""
    try:
        content = _extract_choice_content(raw_payload)
    except RuntimeError:
        content = ""

    parsed: dict[str, object] = {}
    if content.strip():
        try:
            parsed = _extract_json_payload(
                content,
                invalid_json_code="chat_model_invalid_payload",
                invalid_payload_code="chat_model_invalid_payload",
            )
        except RuntimeError:
            legacy_payload = _recover_legacy_chat_payload(content)
            if legacy_payload is not None:
                parsed = legacy_payload
                logger.info("model.chat.parse_recovered legacy_text_payload")
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
    scene_profile = extract_scene_profile_from_tool_results(tool_results)
    rich_blocks = _extract_rich_blocks_payload(parsed)
    mood = str(parsed.get("mood") or "calm")
    action = str(parsed.get("action") or "point")
    speech_style = str(parsed.get("speech_style") or "").strip()
    delivery_cue = str(parsed.get("delivery_cue") or "").strip()
    state_commentary = str(parsed.get("state_commentary") or "").strip()
    text = str(parsed.get("text") or "").strip()

    if not text:
        if interactive_question is not None:
            text = "请先完成这道题，再告诉我你的思路，我会继续追问关键细节。"
        elif content.strip():
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


def _extract_upstream_error(body: str) -> tuple[str, str]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return "", body[:200]
    if not isinstance(payload, dict):
        return "", body[:200]
    error = payload.get("error")
    if not isinstance(error, dict):
        return "", body[:200]
    return str(error.get("code", "")), str(error.get("message", ""))


def _should_fallback_setting_web_search(exc: RuntimeError) -> bool:
    detail = str(exc).strip()
    return (
        detail.startswith("openai_setting_request_failed:400:")
        or detail.startswith("openai_setting_request_failed:422:")
        or detail.startswith("openai_setting_request_failed:500:")
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


def _normalize_litellm_payload(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result

    model_dump = getattr(result, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump(mode="json")
        if isinstance(dumped, dict):
            return dumped

    model_dump_json = getattr(result, "model_dump_json", None)
    if callable(model_dump_json):
        dumped_json = model_dump_json()
        if isinstance(dumped_json, str):
            parsed = _try_parse_json_dict(dumped_json)
            if parsed is not None:
                return parsed

    json_method = getattr(result, "json", None)
    if callable(json_method):
        raw_json = json_method()
        if isinstance(raw_json, str):
            parsed = _try_parse_json_dict(raw_json)
            if parsed is not None:
                return parsed

    raise RuntimeError("litellm_invalid_payload")


def _try_parse_json_dict(raw_value: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _extract_litellm_exception_details(exc: Exception) -> tuple[str, str, str]:
    status_code = _extract_litellm_status_code(exc)
    error_code = ""
    error_message = str(exc)

    body_candidates = [
        getattr(exc, "body", None),
        getattr(exc, "response_body", None),
    ]
    response = getattr(exc, "response", None)
    if response is not None:
        body_candidates.extend(
            [
                getattr(response, "text", None),
                getattr(response, "content", None),
                getattr(response, "body", None),
            ]
        )

    for candidate in body_candidates:
        error_code, error_message = _extract_litellm_error_from_body(candidate, fallback_message=error_message)
        if error_code:
            break

    if not error_code:
        error_code = str(
            getattr(exc, "code", "")
            or getattr(exc, "type", "")
            or type(exc).__name__
        ).strip()

    return status_code or "unknown", error_code or "unknown", error_message or str(exc)


def _extract_litellm_status_code(exc: Exception) -> str:
    for value in (
        getattr(exc, "status_code", None),
        getattr(exc, "status", None),
        getattr(getattr(exc, "response", None), "status_code", None),
        getattr(getattr(exc, "response", None), "status", None),
    ):
        if isinstance(value, int):
            return str(value)
        if isinstance(value, str) and value.isdigit():
            return value
    return ""


def _extract_litellm_error_from_body(
    body: Any,
    *,
    fallback_message: str,
) -> tuple[str, str]:
    if body is None:
        return "", fallback_message
    if isinstance(body, bytes):
        body = body.decode("utf-8", errors="ignore")
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            return (
                str(error.get("code") or error.get("type") or ""),
                str(error.get("message") or fallback_message),
            )
        return "", fallback_message
    if isinstance(body, str):
        error_code, error_message = _extract_upstream_error(body)
        return error_code, error_message or fallback_message
    return "", fallback_message


def _is_litellm_rate_limit_error(exc: Exception) -> bool:
    rate_limit_cls = getattr(litellm, "RateLimitError", None) if litellm is not None else None
    if rate_limit_cls is not None and isinstance(exc, rate_limit_cls):
        return True
    return _extract_litellm_status_code(exc) == "429" or "ratelimit" in type(exc).__name__.lower()


def _is_litellm_timeout_error(exc: Exception) -> bool:
    timeout_cls = getattr(litellm, "Timeout", None) if litellm is not None else None
    if timeout_cls is not None and isinstance(exc, timeout_cls):
        return True
    class_name = type(exc).__name__.lower()
    message = str(exc).lower()
    return isinstance(exc, TimeoutError) or "timeout" in class_name or "timed out" in message


def _is_litellm_network_error(exc: Exception) -> bool:
    connection_cls = getattr(litellm, "APIConnectionError", None) if litellm is not None else None
    if connection_cls is not None and isinstance(exc, connection_cls):
        return True
    class_name = type(exc).__name__.lower()
    message = str(exc).lower()
    return any(
        token in class_name or token in message
        for token in (
            "connection",
            "network",
            "dns",
            "refused",
        )
    )


def _is_litellm_retryable_error(exc: Exception) -> bool:
    if _is_litellm_timeout_error(exc) or _is_litellm_network_error(exc):
        return True
    status_code = _extract_litellm_status_code(exc)
    return status_code in LITELLM_TRANSIENT_RETRYABLE_STATUS_CODES


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
