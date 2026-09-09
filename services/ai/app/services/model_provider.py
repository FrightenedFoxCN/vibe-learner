from __future__ import annotations

from app.services.provider_transport import ProviderTransport, ModelRequestError, _coerce_int

from app.services.provider_capabilities import ModelProvider, ModelReply, PlanModelReply, PlanScheduleItem
from app.services.provider_exercises import LocalExerciseProvider
from app.services.provider_embedding import RemoteEmbeddingProvider
from app.services.provider_image import RemoteImageProvider
from app.services.provider_settings import (
    RemoteSettingsProvider,
    _enforce_exact_persona_card_count,
    _normalize_generated_scene_result,
)
from app.services.provider_study import (
    RemoteStudyProvider, CHAT_JSON_SCHEMA,
    _chat_tools,
    _chat_tools_disabled_for_round,
    _decode_study_chat_reply_proposal,
    _execute_chat_tool_call,
    _extract_choice_diagnostics,
    _parse_chat_model_reply,
)
from app.services.provider_callbacks import _call_interrupt, _emit_progress
from app.services.provider_planning import (
    RemotePlanningProvider, PlanningProposalDecodeError, _decode_learning_plan_proposal,
    _study_units_changed, _validate_learning_plan_proposal_refs,
)
from app.services.provider_payload import (
    _extract_choice_content, _extract_json_payload, _escape_invalid_backslashes_in_json_strings,
)
from app.services.provider_tavern import RemoteTavernProvider, _should_fallback_tavern_schema_transport

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
from app.services.plan_prompt import (
    build_learning_plan_context,
    build_learning_plan_messages,
    read_page_range_content,
    read_page_range_images,
)
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
        return RemoteStudyProvider(
            chat_model=self.chat_model, chat_temperature=self.chat_temperature,
            chat_max_tokens=self.chat_max_tokens, chat_history_messages=self.chat_history_messages,
            chat_tool_max_rounds=self.chat_tool_max_rounds, chat_tools_enabled=self.chat_tools_enabled,
            chat_memory_tool_enabled=self.chat_memory_tool_enabled,
            chat_multimodal_enabled=self.chat_multimodal_enabled,
            disabled_tools=frozenset(self.chat_disabled_tools_provider() if self.chat_disabled_tools_provider else ()),
            request=self._request_openai_chat_completion,
        ).generate_chat(
            persona=persona,
            section_id=section_id,
            message=message,
            message_kind=message_kind,
            session_prompt=session_prompt,
            section_context=section_context,
            memory_context=memory_context,
            attachment_context=attachment_context,
            learner_multimodal_parts=learner_multimodal_parts,
            scene_context=scene_context,
            active_plan_context=active_plan_context,
            session_state_context=session_state_context,
            session_tool_runtime=session_tool_runtime,
            scene_tool_runtime=scene_tool_runtime,
            plan_tool_runtime=plan_tool_runtime,
            memory_trace_hits=memory_trace_hits,
            conversation_history=conversation_history,
            debug_report=debug_report,
            document_path=document_path,
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
        return RemoteTavernProvider(
            chat_model=self.chat_model,
            chat_temperature=self.chat_temperature,
            chat_max_tokens=self.chat_max_tokens,
            request=self._request_openai_chat_completion,
        ).generate_tavern_actor_reply(
            persona=persona, participants=participants, scene_profile=scene_profile,
            recent_messages=recent_messages, user_message=user_message, guidance=guidance,
            allowed_target_ids=allowed_target_ids, turn_kind=turn_kind,
            required_target_id=required_target_id, should_continue=should_continue,
        )

    def assist_persona_setting(
        self,
        *,
        name: str,
        summary: str,
        slots: list[PersonaSlot],
        rewrite_strength: float,
    ) -> dict[str, object]:
        return self._settings_provider().assist_persona_setting(
            name=name,
            summary=summary,
            slots=slots,
            rewrite_strength=rewrite_strength,
        )

    def assist_persona_slot(
        self,
        *,
        name: str,
        summary: str,
        slot: PersonaSlot,
        rewrite_strength: float,
    ) -> dict[str, object]:
        return self._settings_provider().assist_persona_slot(
            name=name,
            summary=summary,
            slot=slot,
            rewrite_strength=rewrite_strength,
        )

    def generate_persona_cards_from_keywords(
        self,
        *,
        keywords: str,
        count: int | None,
    ) -> dict[str, object]:
        return self._settings_provider().generate_persona_cards_from_keywords(
            keywords=keywords,
            count=count,
        )

    def generate_persona_cards_from_text(
        self,
        *,
        text: str,
        count: int | None,
    ) -> dict[str, object]:
        return self._settings_provider().generate_persona_cards_from_text(
            text=text,
            count=count,
        )

    def generate_scene_tree_from_keywords(
        self,
        *,
        keywords: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        return self._settings_provider().generate_scene_tree_from_keywords(
            keywords=keywords,
            layer_count=layer_count,
        )


    def generate_scene_tree_from_text(
        self,
        *,
        text: str,
        layer_count: int | None,
    ) -> dict[str, object]:
        return self._settings_provider().generate_scene_tree_from_text(
            text=text,
            layer_count=layer_count,
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
        return RemotePlanningProvider(
            plan_model=self.plan_model, plan_tools_enabled=self.plan_tools_enabled,
            fallback_plan_model=self.fallback_plan_model,
            fallback_disable_tools=self.fallback_disable_tools,
            multimodal_enabled=self.multimodal_enabled, timeout_seconds=self.timeout_seconds,
            disabled_tools=frozenset(self.plan_disabled_tools_provider() if self.plan_disabled_tools_provider else ()),
            request=self._request_openai_chat_completion,
        ).generate_learning_plan(
            persona=persona, document_title=document_title, goal=goal, study_units=study_units,
            document_path=document_path, debug_report=debug_report, planning_questions=planning_questions,
            existing_plan=existing_plan, progress_callback=progress_callback, interrupt_check=interrupt_check,
        )


    def generate_projected_image(self, *, prompt: str, size: str = "1024x1024") -> dict[str, str]:
        return self._image_provider().generate_projected_image(prompt=prompt, size=size)

    def _settings_provider(self) -> RemoteSettingsProvider:
        return RemoteSettingsProvider(
            setting_model=self.setting_model, setting_temperature=self.setting_temperature,
            setting_max_tokens=self.setting_max_tokens,
            setting_web_search_enabled=self.setting_web_search_enabled,
            request_chat=self._request_openai_chat_completion,
            request_response=self._request_openai_response,
        )

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


def _reject_nonstandard_json_constant(value: str) -> None:
    raise json.JSONDecodeError("non-standard JSON constant", value, 0)


def _stable_scene_token(seed: str, prefix: str) -> str:
    value = 0
    for char in seed:
        value = ((value * 131) + ord(char)) % 0xFFFFFFFF
    return f"{prefix}-{value:08x}"


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


def _resolve_persona_card_count_hint(count: int | None, *, default: int) -> int:
    if count is None or count < 1:
        return default
    return count


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
