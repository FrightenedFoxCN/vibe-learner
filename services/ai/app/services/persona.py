from __future__ import annotations

from fastapi import HTTPException

from app.models.api import CreatePersonaRequest, UpdatePersonaRequest
from app.models.domain import PersonaProfile, PersonaSlot, persona_slot_content, persona_slot_list


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
        worldview = next((s.content for s in slots if s.kind == "worldview"), "")
        past_exp = next((s.content for s in slots if s.kind == "past_experiences"), "")
        teaching_method = next((s.content for s in slots if s.kind == "teaching_method"), "")
        narrative_mode = next((s.content for s in slots if s.kind == "narrative_mode"), "grounded")
        encouragement_style = next((s.content for s in slots if s.kind == "encouragement_style"), "")
        correction_style = next((s.content for s in slots if s.kind == "correction_style"), "")

        style_text = teaching_method.strip() or "结构化讲解"
        narrative_text = "轻剧情" if narrative_mode.strip() == "light_story" else "稳态导学"
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
        for slot in slots:
            if slot.kind in ("worldview", "past_experiences") and not narrative_inserted:
                updated_slots.append(
                    PersonaSlot(kind=slot.kind, label=slot.label, content=narrative_content)
                )
                narrative_inserted = True
            elif slot.kind in ("worldview", "past_experiences"):
                pass
            else:
                updated_slots.append(slot)
        if not narrative_inserted:
            updated_slots.append(
                PersonaSlot(kind="worldview", label="世界观起点", content=narrative_content)
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

    def _builtin_personas(self) -> list[PersonaProfile]:
        return [
            PersonaProfile(
                id="mentor-aurora",
                name="Aurora",
                source="builtin",
                summary="温和而结构化的导学教师。",
                system_prompt="Prioritize clarity, chapter grounding, and encouragement.",
                slots=[
                    PersonaSlot(kind="worldview", label="世界观起点", content="来自学院图书馆塔楼，擅长把复杂章节拆成可执行的小台阶。"),
                    PersonaSlot(kind="teaching_method", label="教学方法", content="structured, guided"),
                    PersonaSlot(kind="narrative_mode", label="叙事模式", content="grounded"),
                    PersonaSlot(kind="encouragement_style", label="鼓励策略", content="small wins"),
                    PersonaSlot(kind="correction_style", label="纠错策略", content="precise but warm"),
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
                system_prompt="Blend chapter teaching with playful narrative energy.",
                slots=[
                    PersonaSlot(kind="past_experiences", label="过往经历", content="前冒险队记录官，习惯把知识点编进轻剧情，保持学习节奏感。"),
                    PersonaSlot(kind="teaching_method", label="教学方法", content="story-led, motivational"),
                    PersonaSlot(kind="narrative_mode", label="叙事模式", content="light_story"),
                    PersonaSlot(kind="encouragement_style", label="鼓励策略", content="hero journey"),
                    PersonaSlot(kind="correction_style", label="纠错策略", content="redirect with energy"),
                ],
                available_emotions=["playful", "encouraging", "excited", "concerned"],
                available_actions=["idle", "explain", "celebrate", "prompt"],
                default_speech_style="energetic",
            ),
        ]
