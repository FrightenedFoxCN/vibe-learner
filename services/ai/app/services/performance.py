from __future__ import annotations

from app.models.domain import (
    CharacterStateEvent,
    ChatToolCallTraceRecord,
    PersonaProfile,
    persona_narrative_mode_label,
    persona_slot_content,
)


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
        narrative_mode = persona_narrative_mode_label(
            persona_slot_content(persona, "narrative_mode", "稳态导学")
        )
        return [
            CharacterStateEvent(
                emotion=mood,
                action=action,
                intensity=intensity,
                speech_style=speech_style,
                scene_hint=f"{persona.name}:{narrative_mode}",
                line_segment_id=line_segment_id,
                timing_hint="after_text",
            )
        ]

    def map_tool_calls_to_events(
        self,
        *,
        persona: PersonaProfile,
        tool_calls: list[ChatToolCallTraceRecord],
        line_segment_id: str,
    ) -> list[CharacterStateEvent]:
        if not tool_calls:
            return []
        speech_style = persona.default_speech_style
        events: list[CharacterStateEvent] = []
        for index, tool_call in enumerate(tool_calls[:4]):
            action = "point"
            if tool_call.tool_name in {"add_scene", "move_to_scene"}:
                action = "reflect"
            elif tool_call.tool_name in {"add_object", "update_object_description", "delete_object"}:
                action = "explain"
            events.append(
                CharacterStateEvent(
                    emotion="serious",
                    action=action,
                    intensity=0.42,
                    speech_style=speech_style,
                    scene_hint=f"scene_tool:{tool_call.tool_name}",
                    line_segment_id=f"{line_segment_id}:tool:{index}",
                    timing_hint="after_text",
                    tool_name=tool_call.tool_name,
                    tool_summary=tool_call.result_summary,
                )
            )
        return events
