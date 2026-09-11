"""Persona/Scene proposals, web-search fallback, and bounded structured response repair."""
from __future__ import annotations

from dataclasses import dataclass
from app.services.provider_capabilities import PersonaModelCapability, SceneModelCapability
from app.services.provider_payload import _extract_choice_diagnostics
from app.services.provider_payload import _extract_choice_content, _extract_json_payload
from typing import Callable
from typing import Any
from pydantic import ValidationError
from app.core.logging import get_logger
from app.models.domain import PersonaSlot, persona_sorted_slots
from app.models.scene import decode_scene_tree_proposal, project_scene_tree_proposal
from app.services.model_recovery import record_model_recovery
from app.models.persona_generation import PersonaCardBatchContentProposalV1, PersonaSlotContentProposalV1
from app.services.prompt_loader import load_prompt_template


@dataclass(frozen=True)
class RemoteSettingsProvider(PersonaModelCapability, SceneModelCapability):
    """Persona/Scene content generation with one captured setting-model configuration."""

    setting_model: str
    setting_temperature: float
    setting_max_tokens: int
    setting_web_search_enabled: bool
    request_chat: Callable[..., tuple[dict[str, Any], int]]
    request_response: Callable[..., tuple[dict[str, Any], int]]

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
                    retry_instruction=PERSONA_CARD_RETRY_INSTRUCTION,
                    validate_payload=_validate_persona_card_batch_payload,
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
            retry_instruction=PERSONA_CARD_RETRY_INSTRUCTION,
            validate_payload=_validate_persona_card_batch_payload,
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
            retry_instruction=PERSONA_CARD_RETRY_INSTRUCTION,
            validate_payload=_validate_persona_card_batch_payload,
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
        raw_payload, _ = self.request_chat(
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
            retry_raw_payload, _ = self.request_chat(
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
        validate_payload: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        raw_payload, _ = self.request_response(
            payload,
            request_kind="setting",
            model=self.setting_model,
        )
        try:
            content = _extract_response_output_text(raw_payload).strip()
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
            raw_retry_payload, _ = self.request_response(
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
            if validate_payload is not None:
                validate_payload(parsed)
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



logger = get_logger("vibe_learner.model_provider")



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

PERSONA_CARD_RETRY_INSTRUCTION = (
    "上一次输出未通过人格卡片严格校验。请只输出一个符合 schema 的 JSON 对象；"
    "包含 summary、relationship、learner_address、cards；"
    "cards 中每张卡片都必须包含 title、kind、label、content 四个字符串字段。"
    "kind 是插槽类型，例如 thinking_style；不能省略，也不能用 label 替代。"
    "不得新增 schema 外字段；如包含 tags，它必须是无重复非空字符串的数组。"
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



def _validate_setting_slot_payload(payload: dict[str, Any]) -> None:
    try:
        PersonaSlotContentProposalV1.model_validate(payload.get("slot"), strict=True)
    except ValidationError as exc:
        raise RuntimeError("setting_model_invalid_payload") from exc



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



def _decode_persona_card_batch(parsed: dict[str, object]) -> dict[str, Any]:
    try:
        proposal = PersonaCardBatchContentProposalV1.model_validate(parsed, strict=True)
    except ValidationError as exc:
        raise RuntimeError("setting_model_invalid_payload") from exc
    batch = proposal.model_dump(mode="python")
    for field in ("summary", "relationship", "learner_address"):
        batch[field] = batch[field].strip()
    return batch


def _validate_persona_card_batch_payload(payload: dict[str, Any]) -> None:
    _decode_persona_card_batch(payload)



def _enforce_exact_persona_card_count(
    cards: list[dict[str, object]],
    *,
    count: int | None,
) -> None:
    if count is None or count < 1:
        return
    if len(cards) != count:
        raise RuntimeError("setting_persona_card_count_mismatch")



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



def _render_persona_card_count_hint(count: int | None) -> str:
    if count is None or count < 1:
        return "未指定"
    return str(count)



def _render_scene_layer_count_hint(layer_count: int | None) -> str:
    if layer_count is None or layer_count < 1:
        return "未指定"
    return str(layer_count)



def _should_fallback_setting_web_search(exc: RuntimeError) -> bool:
    detail = str(exc).strip()
    return (
        detail.startswith("openai_setting_request_failed:400:")
        or detail.startswith("openai_setting_request_failed:422:")
        or detail.startswith("openai_setting_request_failed:500:")
    )
