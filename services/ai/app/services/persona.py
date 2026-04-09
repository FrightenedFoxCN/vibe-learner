from __future__ import annotations

from fastapi import HTTPException

from app.models.api import CreatePersonaRequest
from app.models.domain import PersonaProfile


class PersonaEngine:
    def __init__(self) -> None:
        self._personas: dict[str, PersonaProfile] = {}
        for persona in self._builtin_personas():
            self._personas[persona.id] = persona

    def list_personas(self) -> list[PersonaProfile]:
        return list(self._personas.values())

    def require_persona(self, persona_id: str) -> PersonaProfile:
        persona = self._personas.get(persona_id)
        if persona is None:
            raise HTTPException(status_code=404, detail="persona_not_found")
        return persona

    def create_persona(self, payload: CreatePersonaRequest) -> PersonaProfile:
        persona_id = payload.name.strip().lower().replace(" ", "-")
        persona = PersonaProfile(
            id=persona_id,
            name=payload.name,
            source="user",
            summary=payload.summary,
            system_prompt=payload.system_prompt,
            teaching_style=payload.teaching_style,
            narrative_mode=payload.narrative_mode,
            encouragement_style=payload.encouragement_style,
            correction_style=payload.correction_style,
            available_emotions=["calm", "encouraging", "playful", "serious"],
            available_actions=["idle", "explain", "point", "celebrate", "reflect", "prompt"],
            default_speech_style="warm",
        )
        self._personas[persona.id] = persona
        return persona

    def _builtin_personas(self) -> list[PersonaProfile]:
        return [
            PersonaProfile(
                id="mentor-aurora",
                name="Aurora",
                source="builtin",
                summary="温和而结构化的导学教师。",
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
