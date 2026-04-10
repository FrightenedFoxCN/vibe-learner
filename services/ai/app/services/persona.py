from __future__ import annotations

from fastapi import HTTPException

from app.models.api import CreatePersonaRequest, UpdatePersonaRequest
from app.models.domain import PersonaProfile


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
            background_story=payload.background_story,
            system_prompt=payload.system_prompt,
            teaching_style=payload.teaching_style,
            narrative_mode=payload.narrative_mode,
            encouragement_style=payload.encouragement_style,
            correction_style=payload.correction_style,
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
            background_story=payload.background_story,
            system_prompt=payload.system_prompt,
            teaching_style=payload.teaching_style,
            narrative_mode=payload.narrative_mode,
            encouragement_style=payload.encouragement_style,
            correction_style=payload.correction_style,
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
        background_story: str,
        teaching_style: list[str],
        narrative_mode: str,
        encouragement_style: str,
        correction_style: str,
    ) -> dict[str, str]:
        style_text = "、".join([item for item in teaching_style if item.strip()]) or "结构化讲解"
        narrative_text = "轻剧情" if narrative_mode == "light_story" else "稳态导学"
        identity_name = name.strip() or "这位教师"
        summary_text = summary.strip() or "擅长围绕章节核心概念组织学习路径"
        base_story = background_story.strip()
        if base_story:
            story = (
                f"{base_story}\n\n"
                f"补充设定：{identity_name} 在课堂中坚持{narrative_text}叙事，"
                f"以{style_text}推进讲解，鼓励策略偏向“{encouragement_style or '阶段性肯定'}”，"
                f"纠错策略采用“{correction_style or '温和纠偏'}”。"
            )
        else:
            story = (
                f"{identity_name} 的核心定位：{summary_text}。"
                f"其教学叙事采用{narrative_text}路线，常用{style_text}组织内容。"
                f"面对学习者挫折时，优先使用“{encouragement_style or '阶段性肯定'}”进行支持；"
                f"在纠错时坚持“{correction_style or '温和纠偏'}”，先指出可改进点，再给出可执行下一步。"
            )
        prompt = (
            "You are a chapter-grounded tutor persona. "
            f"Persona name: {identity_name}. "
            f"Narrative mode: {narrative_mode}. "
            f"Teaching style: {style_text}. "
            "Always keep explanations concise, grounded, and action-oriented."
        )
        return {
            "background_story": story,
            "system_prompt_suggestion": prompt,
        }

    def _builtin_personas(self) -> list[PersonaProfile]:
        return [
            PersonaProfile(
                id="mentor-aurora",
                name="Aurora",
                source="builtin",
                summary="温和而结构化的导学教师。",
                background_story="来自学院图书馆塔楼，擅长把复杂章节拆成可执行的小台阶。",
                system_prompt="Prioritize clarity, chapter grounding, and encouragement.",
                teaching_style=["structured", "guided"],
                narrative_mode="grounded",
                encouragement_style="small wins",
                correction_style="precise but warm",
                available_emotions=["calm", "encouraging", "serious"],
                available_actions=["idle", "explain", "point", "reflect"],
                default_speech_style="steady",
            ),
            PersonaProfile(
                id="mentor-lyra",
                name="Lyra",
                source="builtin",
                summary="带轻度剧情化陪伴感的活力教师。",
                background_story="前冒险队记录官，习惯把知识点编进轻剧情，保持学习节奏感。",
                system_prompt="Blend chapter teaching with playful narrative energy.",
                teaching_style=["story-led", "motivational"],
                narrative_mode="light_story",
                encouragement_style="hero journey",
                correction_style="redirect with energy",
                available_emotions=["playful", "encouraging", "excited", "concerned"],
                available_actions=["idle", "explain", "celebrate", "prompt"],
                default_speech_style="energetic",
            ),
        ]
