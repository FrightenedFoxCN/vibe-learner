from __future__ import annotations

from fastapi import HTTPException

from app.models.api import CreatePersonaRequest, UpdatePersonaRequest
from app.models.domain import (
    PersonaProfile,
    PersonaSlot,
    persona_narrative_mode_label,
    persona_slot_content,
    persona_slot_list,
    persona_sorted_slots,
)


class PersonaEngine:
    def __init__(self) -> None:
        self._personas: dict[str, PersonaProfile] = {}
        for persona in self._builtin_personas():
            self._personas[persona.id] = persona

    @staticmethod
    def _default_available_emotions() -> list[str]:
        return ["calm", "encouraging", "playful", "serious"]

    @staticmethod
    def _default_available_actions() -> list[str]:
        return ["idle", "explain", "point", "celebrate", "reflect", "prompt"]

    def list_personas(self) -> list[PersonaProfile]:
        return list(self._personas.values())

    def require_persona(self, persona_id: str) -> PersonaProfile:
        persona = self._personas.get(persona_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="persona_not_found")
        return persona

    def create_persona(self, payload: CreatePersonaRequest) -> PersonaProfile:
        persona_id = payload.name.strip().lower().replace(" ", "-")
        available_emotions = [
            emotion.strip()
            for emotion in (payload.available_emotions or self._default_available_emotions())
            if emotion.strip()
        ]
        available_actions = [
            action.strip()
            for action in (payload.available_actions or self._default_available_actions())
            if action.strip()
        ]
        persona = PersonaProfile(
            id=persona_id,
            name=payload.name,
            source="user",
            summary=payload.summary,
            system_prompt=payload.system_prompt,
            slots=payload.slots,
            available_emotions=available_emotions or self._default_available_emotions(),
            available_actions=available_actions or self._default_available_actions(),
            default_speech_style=(payload.default_speech_style or "warm").strip() or "warm",
        )
        self._personas[persona.id] = persona
        return persona

    def update_persona(self, persona_id: str, payload: UpdatePersonaRequest) -> PersonaProfile:
        current = self.require_persona(persona_id)
        if current.source == "builtin":
            raise HTTPException(status_code=403, detail="persona_readonly_builtin")
        available_emotions = [
            emotion.strip()
            for emotion in (payload.available_emotions or current.available_emotions)
            if emotion.strip()
        ]
        available_actions = [
            action.strip()
            for action in (payload.available_actions or current.available_actions)
            if action.strip()
        ]
        updated = PersonaProfile(
            id=current.id,
            source=current.source,
            name=payload.name,
            summary=payload.summary,
            system_prompt=payload.system_prompt,
            slots=payload.slots,
            available_emotions=available_emotions or self._default_available_emotions(),
            available_actions=available_actions or self._default_available_actions(),
            default_speech_style=(payload.default_speech_style or current.default_speech_style).strip()
            or current.default_speech_style,
        )
        self._personas[current.id] = updated
        return updated

    def assist_setting(
        self,
        *,
        name: str,
        summary: str,
        slots: list[PersonaSlot],
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

        base_narrative = (worldview or past_exp).strip()
        enc_style = encouragement_style or "阶段性肯定"
        cor_style = correction_style or "温和纠偏"
        if base_narrative:
            narrative_content = (
                base_narrative
                + "\n\n"
                + f"补充设定：{identity_name} 在课堂中坚持{narrative_text}叙事，"
                + f"以{style_text}推进讲解，鼓励策略偏向“{enc_style}”，"
                + f"纠错策略采用“{cor_style}”。"
            )
        else:
            narrative_content = (
                f"{identity_name} 的核心定位：{summary_text}。"
                + f"其教学叙事采用{narrative_text}路线，常用{style_text}组织内容。"
                + f"面对学习者挫折时，优先使用“{enc_style}”进行支持；"
                + f"在纠错时坚持“{cor_style}”，先指出可改进点，再给出可执行下一步。"
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

    def assist_slot(
        self,
        *,
        name: str,
        summary: str,
        slot: PersonaSlot,
        rewrite_strength: float,
    ) -> PersonaSlot:
        identity_name = name.strip() or "这位教师"
        summary_text = summary.strip() or "围绕章节核心概念组织学习路径"
        base = slot.content.strip()
        strength = max(0.0, min(1.0, rewrite_strength))

        if slot.kind == "worldview":
            rewritten = (
                f"{identity_name} 相信学习应该先建立可验证的概念支点，再推进抽象推理与迁移。"
                f"在教学中始终围绕教材章节结构，避免脱离文本的空泛发挥。"
            )
        elif slot.kind == "past_experiences":
            rewritten = (
                f"{identity_name} 曾长期负责章节导学与错题复盘，形成了“先稳核心定义、再攻难点变体”的节奏。"
                f"这段经历让其在复杂主题中更擅长拆解路径。"
            )
        elif slot.kind == "thinking_style":
            rewritten = "先澄清前提，再给出推理链，最后用反例或边界条件做自检。"
        elif slot.kind == "teaching_method":
            rewritten = "按“概念-例子-反例-迁移”四步推进，每轮只解决一个关键难点。"
        elif slot.kind == "correction_style":
            rewritten = "纠错先指出可执行改进点，再给下一步练习，不使用否定人格的措辞。"
        elif slot.kind == "encouragement_style":
            rewritten = "鼓励聚焦具体进步与可复现方法，避免空泛夸奖。"
        elif slot.kind == "narrative_mode":
            rewritten = "稳态导学"
        else:
            rewritten = f"{identity_name}：{summary_text}。{base or '请补充该插槽内容。'}"

        if base and strength < 0.45:
            content = f"{base}\n\n润色补充：{rewritten}"
        else:
            content = rewritten
        return PersonaSlot(
            kind=slot.kind,
            label=slot.label,
            content=content,
            weight=slot.weight,
            locked=slot.locked,
            sort_order=slot.sort_order,
        )

    def _builtin_personas(self) -> list[PersonaProfile]:
        return [
            PersonaProfile(
                id="mentor-aurora",
                name="Aurora",
                source="builtin",
                summary="温和而结构化的导学教师。",
                system_prompt="优先保持讲解清晰、贴合章节，并通过温和反馈推动学习者继续前进。",
                slots=[
                    PersonaSlot(kind="worldview", label="世界观起点", content="来自学院图书馆塔楼，擅长把复杂章节拆成可执行的小台阶。"),
                    PersonaSlot(kind="teaching_method", label="教学方法", content="结构化、引导式推进"),
                    PersonaSlot(kind="narrative_mode", label="叙事模式", content="稳态导学"),
                    PersonaSlot(kind="encouragement_style", label="鼓励策略", content="强调小步成功与可见进展"),
                    PersonaSlot(kind="correction_style", label="纠错策略", content="准确指出问题，同时保持温和语气"),
                ],
                available_emotions=["calm", "encouraging", "serious"],
                available_actions=["idle", "explain", "point", "reflect"],
                default_speech_style="steady",
            ),
            PersonaProfile(
                id="mentor-lyra",
                name="Lyra",
                source="builtin",
                summary="\u5e26\u8f7b\u5ea6\u5267\u60c5\u5316\u966a\u4f34\u611f\u7684\u6d3b\u529b\u6559\u5e08\u3002",
                system_prompt="把章节讲解和轻剧情陪伴结合起来，保持活力、节奏感和明确推进。",
                slots=[
                    PersonaSlot(kind="past_experiences", label="过往经历", content="前冒险队记录官，习惯把知识点编进轻剧情，保持学习节奏感。"),
                    PersonaSlot(kind="teaching_method", label="教学方法", content="剧情引导、激励式推进"),
                    PersonaSlot(kind="narrative_mode", label="叙事模式", content="轻剧情陪伴"),
                    PersonaSlot(kind="encouragement_style", label="鼓励策略", content="把学习进展包装成阶段闯关"),
                    PersonaSlot(kind="correction_style", label="纠错策略", content="用有节奏的转向提示带回正确路径"),
                ],
                available_emotions=["playful", "encouraging", "excited", "concerned"],
                available_actions=["idle", "explain", "celebrate", "prompt"],
                default_speech_style="energetic",
            ),
        ]
