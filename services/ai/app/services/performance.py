from __future__ import annotations

from app.models.domain import CharacterStateEvent, PersonaProfile


class PerformanceMapper:
    def map_text_to_events(
        self,
        *,
        persona: PersonaProfile,
        text: str,
        mood: str,
        action: str,
        line_segment_id: str,
    ) -> list[CharacterStateEvent]:
        speech_style = persona.default_speech_style
        intensity = 0.75 if mood in {"excited", "playful"} else 0.55
        return [
            CharacterStateEvent(
                emotion=mood,
                action=action,
                intensity=intensity,
                speech_style=speech_style,
                scene_hint=f"{persona.name}:{persona.narrative_mode}",
                line_segment_id=line_segment_id,
                timing_hint="after_text",
            )
        ]
