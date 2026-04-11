from __future__ import annotations

import json
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable
from typing import Any

from app.core.logging import get_logger
from app.models.domain import (
    DocumentDebugRecord,
    LearningGoalInput,
    PlanGenerationTraceRecord,
    PersonaProfile,
    PersonaSlot,
    StudyUnitRecord,
    persona_slot_content,
        persona_sorted_slots,
)
from app.services.openai_plan_runner import OpenAIPlanRunner
from app.services.plan_prompt import (
    build_learning_plan_context,
    build_learning_plan_messages,
    read_page_range_content,
    read_page_range_images,
)
from app.services.plan_tool_runtime import build_plan_tool_runtime

logger = get_logger("vibe_learner.model_provider")


@dataclass
class ModelReply:
    text: str
    mood: str
    action: str
    interactive_question: dict[str, Any] | None = None


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
    weekly_focus: list[str]
    today_tasks: list[str]
    schedule: list[PlanScheduleItem]
    revised_study_units: list[StudyUnitRecord] | None = None
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
        conversation_history: list[dict[str, str]] | None = None,
        debug_report: DocumentDebugRecord | None = None,
        document_path: str | None = None,
    ) -> ModelReply:
        raise NotImplementedError

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
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> PlanModelReply:
        raise NotImplementedError

    def supports_page_image_tools(self) -> bool:
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


class MockModelProvider(ModelProvider):
    def generate_chat(
        self,
        *,
        persona: PersonaProfile,
        section_id: str,
        message: str,
        session_prompt: str = "",
        section_context: str = "",
        conversation_history: list[dict[str, str]] | None = None,
        debug_report: DocumentDebugRecord | None = None,
        document_path: str | None = None,
    ) -> ModelReply:
        teaching_method = persona_slot_content(persona, "teaching_method")
        style = teaching_method.split(",")[0].strip() if teaching_method else "structured"
        history_hint = ""
        if conversation_history:
            history_hint = f" 我已读取最近 {len(conversation_history)} 条上下文。"
        section_hint = f" 章节上下文：{section_context[:80]}。" if section_context else ""
        text = (
            f"{persona.name} 正在结合章节 {section_id} 讲解。"
            f" 当前提问是：{message}。"
            f"{section_hint}"
            f"{history_hint}"
            f"{' 会话约束：' + session_prompt[:80] if session_prompt else ''}"
            f" 我会用 {style} 的方式先解释核心概念，再给你一个复述任务。"
        )
        narrative_mode = persona_slot_content(persona, "narrative_mode", "grounded")
        mood = "playful" if narrative_mode == "light_story" else "calm"
        return ModelReply(text=text, mood=mood, action="explain")

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ModelReply:
        text = (
            f"围绕 {section_id} 的 {topic}，请你先用三句话概括概念，"
            "再举一个教材中的例子。"
        )
        return ModelReply(text=text, mood="encouraging", action="prompt")

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> ModelReply:
        quality = "完整" if len(answer.strip()) > 24 else "偏短"
        text = (
            f"针对练习 {exercise_id}，你的回答{quality}。"
            " 我会指出遗漏点，并给出下一步复习建议。"
        )
        mood = "excited" if quality == "完整" else "concerned"
        action = "celebrate" if quality == "完整" else "reflect"
        return ModelReply(text=text, mood=mood, action=action)

    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> PlanModelReply:
        plannable_units = [unit for unit in study_units if unit.include_in_plan] or study_units
        today_tasks = [
            f"阅读 {unit.title}，提取 2 条定义或结论。"
            for unit in plannable_units[:2]
        ]
        if not today_tasks:
            today_tasks = [f"阅读 {document_title}，确认主线主题与细分要点。"]
        schedule: list[PlanScheduleItem] = []
        for unit in plannable_units[:4]:
            schedule.append(
                PlanScheduleItem(
                    unit_id=unit.id,
                    title=f"{unit.title} 精读",
                    focus=f"在 {unit.title} 中整理概念、例题与疑问。",
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
            ),
            weekly_focus=[unit.title for unit in plannable_units[:4]],
            today_tasks=today_tasks,
            schedule=schedule,
        )
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
        narrative_mode = next((s.content for s in ordered_slots if s.kind == "narrative_mode"), "grounded")
        encouragement_style = next((s.content for s in ordered_slots if s.kind == "encouragement_style"), "")
        correction_style = next((s.content for s in ordered_slots if s.kind == "correction_style"), "")

        style_text = teaching_method.strip() or "结构化讲解"
        narrative_text = "轻剧情" if narrative_mode.strip() == "light_story" else "稳态导学"
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
            "You are a chapter-grounded tutor persona. "
            f"Persona name: {identity_name}. "
            f"Narrative mode: {narrative_mode.strip() or 'grounded'}. "
            f"Teaching style: {style_text}. "
            "Always keep explanations concise, grounded, and action-oriented."
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


class OpenAIModelProvider(MockModelProvider):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        plan_model: str,
        setting_model: str | None = None,
        chat_model: str | None = None,
        chat_temperature: float = 0.35,
        setting_temperature: float = 0.4,
        setting_max_tokens: int = 900,
        chat_max_tokens: int = 800,
        chat_history_messages: int = 8,
        chat_tool_max_rounds: int = 4,
        chat_tools_enabled: bool = True,
        chat_multimodal_enabled: bool = False,
        timeout_seconds: int = 30,
        multimodal_enabled: bool = False,
        plan_tools_enabled: bool = True,
        fallback_plan_model: str = "",
        fallback_disable_tools: bool = True,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.plan_model = plan_model
        self.setting_model = setting_model or chat_model or plan_model
        self.chat_model = chat_model or plan_model
        self.chat_temperature = chat_temperature
        self.setting_temperature = setting_temperature
        self.setting_max_tokens = setting_max_tokens
        self.chat_max_tokens = chat_max_tokens
        self.chat_history_messages = max(1, chat_history_messages)
        self.chat_tool_max_rounds = max(1, chat_tool_max_rounds)
        self.chat_tools_enabled = chat_tools_enabled
        self.chat_multimodal_enabled = chat_multimodal_enabled
        self.timeout_seconds = timeout_seconds
        self.multimodal_enabled = multimodal_enabled
        self.plan_tools_enabled = plan_tools_enabled
        self.fallback_plan_model = fallback_plan_model.strip()
        self.fallback_disable_tools = fallback_disable_tools

    def supports_page_image_tools(self) -> bool:
        return self.multimodal_enabled

    def generate_chat(
        self,
        *,
        persona: PersonaProfile,
        section_id: str,
        message: str,
        session_prompt: str = "",
        section_context: str = "",
        conversation_history: list[dict[str, str]] | None = None,
        debug_report: DocumentDebugRecord | None = None,
        document_path: str | None = None,
    ) -> ModelReply:
        history = conversation_history or []
        persona_slots_text = "\n".join(
            f"- [{slot.kind}] {slot.label}: {slot.content}"
            for slot in persona_sorted_slots(persona.slots)
            if slot.content.strip()
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    f"{persona.system_prompt}\n"
                    f"{session_prompt.strip()}\n"
                    f"Persona slot assembly (ordered):\n{persona_slots_text or 'N/A'}\n"
                    "You are a tutor for a chapter-focused learning chat. "
                    "Output strict JSON with keys: text, mood, action. "
                    "mood must be one of calm, encouraging, playful, serious, excited, concerned. "
                    "action must be one of explain, point, prompt, reflect, celebrate, idle. "
                    "If the learner asks for practice, a check-up, a quiz, or a question drill, "
                    "you may call ask_multiple_choice_question or ask_fill_blank_question. "
                    "If you need deeper grounding from the textbook, call read_page_range_content. "
                    "If diagrams/formulas/layout matter and image tool is available, call read_page_range_images. "
                    "Use the tool result directly in your final JSON reply. "
                    "When an interactive question is present, do NOT repeat the question stem/options/answer in text; "
                    "text should only provide short guidance or encouragement. "
                    "Prioritize detail-level reasoning and deep understanding over shallow recall."
                ),
            }
        ]
        messages.extend(history[-self.chat_history_messages:])
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Section ID: {section_id}\n"
                    f"Section Context:\n{section_context or 'N/A'}\n\n"
                    f"Learner message: {message}\n"
                    "Answer in Chinese and keep explanations grounded in the section context when possible. "
                    "If you generate a question, focus on subtle distinctions, boundary conditions, causal links, "
                    "or application-level understanding from this section."
                ),
            }
        )

        current_messages = list(messages)
        raw_payload: dict[str, Any] | None = None
        last_tool_results: list[dict[str, Any]] = []
        for _ in range(self.chat_tool_max_rounds):
            payload: dict[str, Any] = {
                "model": self.chat_model,
                "temperature": self.chat_temperature,
                "max_tokens": self.chat_max_tokens,
                "messages": current_messages,
            }
            tool_specs = _chat_tools(
                tools_enabled=self.chat_tools_enabled,
                multimodal_enabled=self.chat_multimodal_enabled,
                debug_report=debug_report,
                document_path=document_path,
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
                        debug_report=debug_report,
                        document_path=document_path,
                    )
                    last_tool_results.append(execution["result"])
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": execution["tool_call_id"],
                            "name": execution["tool_name"],
                            "content": json.dumps(execution["result"], ensure_ascii=False),
                        }
                    )
                continue
            break

        if raw_payload is None:
            raise RuntimeError("chat_model_invalid_payload")

        try:
            return _parse_chat_model_reply(
                raw_payload=raw_payload,
                tool_results=last_tool_results,
            )
        except RuntimeError as exc:
            if str(exc) != "chat_model_invalid_payload":
                raise
            logger.warning("model.chat.recovery invalid_payload retry_without_tools")
            recovery_messages = [
                *messages,
                {
                    "role": "user",
                    "content": (
                        "Your previous output was invalid. Return strict JSON now with keys: text, mood, action. "
                        "Do not call tools in this retry. Do not include markdown."
                    ),
                },
            ]
            recovery_payload: dict[str, Any] = {
                "model": self.chat_model,
                "temperature": min(self.chat_temperature, 0.2),
                "max_tokens": self.chat_max_tokens,
                "messages": recovery_messages,
                "response_format": {"type": "json_object"},
            }
            recovery_raw_payload, _ = self._request_openai_chat_completion(
                recovery_payload,
                request_kind="chat",
                model=self.chat_model,
            )
            return _parse_chat_model_reply(
                raw_payload=recovery_raw_payload,
                tool_results=[],
            )

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
        payload: dict[str, Any] = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": self.setting_max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a persona writing assistant for a tutoring system. "
                        "Return strict JSON only with a key 'slots' (array of objects with kind, label, content) "
                        "and 'system_prompt_suggestion'. "
                        "Improve the narrative slots (worldview, past_experiences, thinking_style) while "
                        "preserving the functional slots (teaching_method, narrative_mode, etc.) unless clearly wrong. "
                        "Use concise but vivid Chinese, keeping the persona educational and chapter-grounded."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请根据以下输入完善人格插槽设定。\n"
                        f"name: {name}\n"
                        f"summary: {summary}\n"
                        f"slots:\n{slots_text}\n"
                        f"rewrite_strength: {max(0.0, min(1.0, rewrite_strength))}\n"
                        "rewrite_strength 语义：0=尽量保留原文，仅增量润色；1=可重写为全新但同人设版本。\n"
                        "输出仅为 JSON，不要 markdown。slots 数组结构：[{{kind, label, content}}, ...]"
                    ),
                },
            ],
        }
        raw_payload, _ = self._request_openai_chat_completion(
            payload,
            request_kind="setting",
            model=self.setting_model,
        )
        raw_content = _extract_choice_content(raw_payload)
        parsed = _extract_json_payload(
            raw_content,
            invalid_json_code="setting_model_invalid_json",
            invalid_payload_code="setting_model_invalid_payload",
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
        payload: dict[str, Any] = {
            "model": self.setting_model,
            "temperature": self.setting_temperature,
            "max_tokens": self.setting_max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是人格卡片润色助手。只返回严格 JSON，格式："
                        "{\"slot\": {\"kind\": string, \"label\": string, \"content\": string}}。"
                        "内容必须是中文，保持教师人格与章节导学场景一致。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请重写这张人格卡片。\n"
                        f"name: {name}\n"
                        f"summary: {summary}\n"
                        f"slot.kind: {slot.kind}\n"
                        f"slot.label: {slot.label}\n"
                        f"slot.content: {slot.content}\n"
                        f"rewrite_strength: {max(0.0, min(1.0, rewrite_strength))}\n"
                        "rewrite_strength 语义：0=尽量保留原文并增量润色；1=可重写为同人设新版本。"
                    ),
                },
            ],
        }
        raw_payload, _ = self._request_openai_chat_completion(
            payload,
            request_kind="setting",
            model=self.setting_model,
        )
        raw_content = _extract_choice_content(raw_payload)
        parsed = _extract_json_payload(
            raw_content,
            invalid_json_code="setting_model_invalid_json",
            invalid_payload_code="setting_model_invalid_payload",
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



    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
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
        )
        tool_runtime = self._build_plan_tool_runtime(
            study_units=study_units,
            detail_map=planning_context["detail_map"],
            debug_report=debug_report,
            document_path=document_path,
            tools_enabled=self.plan_tools_enabled,
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
        return PlanModelReply(
            course_title=str(
                parsed.get("course_title")
                or _build_course_title(
                    document_title=document_title,
                    plannable_units=study_units,
                )
            ),
            overview=str(parsed["overview"]),
            weekly_focus=[str(item) for item in parsed.get("weekly_focus", [])],
            today_tasks=[str(item) for item in parsed.get("today_tasks", [])],
            schedule=schedule_items,
            revised_study_units=active_study_units if _study_units_changed(study_units, active_study_units) else None,
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
    ):
        if not tools_enabled:
            return build_plan_tool_runtime()
        return build_plan_tool_runtime(
            study_units=study_units,
            detail_map=detail_map,
            debug_report=debug_report,
            document_path=document_path,
            multimodal_enabled=self.multimodal_enabled,
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
        tools_enabled = "tools" in payload
        tool_round = len([message for message in payload.get("messages", []) if message.get("role") == "tool"])
        logger.info(
            "model.%s.request provider=openai model=%s tool_round=%s tools_enabled=%s",
            request_kind,
            model,
            tool_round,
            tools_enabled,
        )
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started_at = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_payload = json.loads(response.read().decode("utf-8"))
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            return raw_payload, elapsed_ms
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            error_code, error_message = _extract_upstream_error(body)
            logger.exception(
                "model.%s.http_error status=%s upstream_code=%s upstream_message=%s body=%s",
                request_kind,
                exc.code,
                error_code,
                error_message,
                body,
            )
            if error_code == "rate_limit":
                raise RuntimeError(f"openai_{request_kind}_request_rate_limit") from exc
            raise RuntimeError(
                f"openai_{request_kind}_request_failed:{exc.code}:{error_code or 'unknown'}"
            ) from exc
        except urllib.error.URLError as exc:
            logger.exception("model.%s.network_error reason=%s", request_kind, exc.reason)
            raise RuntimeError(f"openai_{request_kind}_request_network_error") from exc
        except (TimeoutError, socket.timeout) as exc:
            logger.exception(
                "model.%s.timeout timeout_seconds=%s",
                request_kind,
                self.timeout_seconds,
            )
            raise RuntimeError(f"openai_{request_kind}_request_timeout") from exc


def _chat_tools(
    *,
    tools_enabled: bool,
    multimodal_enabled: bool,
    debug_report: DocumentDebugRecord | None,
    document_path: str | None,
) -> list[dict[str, object]]:
    if not tools_enabled:
        return []

    tools: list[dict[str, object]] = [
        {
            "type": "function",
            "function": {
                "name": "ask_multiple_choice_question",
                "description": (
                    "Generate a multiple-choice practice question grounded in the current section context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Optional practice topic or concept focus.",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": "Difficulty level for the question.",
                        },
                        "focus_mode": {
                            "type": "string",
                            "enum": ["detail", "deep_understanding"],
                            "description": "Prefer detail checking or deep conceptual understanding.",
                        },
                        "option_count": {
                            "type": "integer",
                            "minimum": 3,
                            "maximum": 5,
                            "description": "Number of answer choices to include.",
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
                "description": (
                    "Generate a fill-in-the-blank practice question grounded in the current section context."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {
                            "type": "string",
                            "description": "Optional practice topic or concept focus.",
                        },
                        "difficulty": {
                            "type": "string",
                            "enum": ["easy", "medium", "hard"],
                            "description": "Difficulty level for the question.",
                        },
                        "focus_mode": {
                            "type": "string",
                            "enum": ["detail", "deep_understanding"],
                            "description": "Prefer detail checking or deep conceptual understanding.",
                        },
                        "blank_count": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 3,
                            "description": "Number of blanks to include in the prompt.",
                        },
                    },
                    "additionalProperties": False,
                },
            },
        },
    ]

    if debug_report is not None:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "read_page_range_content",
                    "description": (
                        "Read textbook text content from a page range for chapter-grounded tutoring."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_start": {"type": "integer"},
                            "page_end": {"type": "integer"},
                            "max_chars": {"type": "integer"},
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
                    "description": (
                        "Render textbook pages as images for formulas, diagrams, tables, and layout cues."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_start": {"type": "integer"},
                            "page_end": {"type": "integer"},
                            "max_images": {"type": "integer"},
                        },
                        "required": ["page_start", "page_end"],
                        "additionalProperties": False,
                    },
                },
            }
        )

    return tools


def _execute_chat_tool_call(
    tool_call: dict[str, Any],
    *,
    section_id: str,
    section_context: str,
    learner_message: str,
    debug_report: DocumentDebugRecord | None,
    document_path: str | None,
) -> dict[str, Any]:
    function_payload = tool_call.get("function") or {}
    tool_name = str(function_payload.get("name") or "")
    tool_call_id = str(tool_call.get("id") or "")
    raw_arguments = str(function_payload.get("arguments") or "{}")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        arguments = {}

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
    match = re.search(r"^Section:\s*(.+?)\s*\(", section_context, re.MULTILINE)
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


def _parse_chat_model_reply(
    *,
    raw_payload: dict[str, Any],
    tool_results: list[dict[str, Any]],
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
            logger.warning("model.chat.parse_fallback invalid_payload content_preview=%s", content[:120])

    interactive_question = _extract_interactive_question_payload(
        parsed=parsed,
        tool_results=tool_results,
    )
    mood = str(parsed.get("mood") or "calm")
    action = str(parsed.get("action") or "explain")
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
    return ModelReply(
        text=text.strip(),
        mood=mood,
        action=action,
        interactive_question=interactive_question,
    )


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
