from __future__ import annotations

from dataclasses import dataclass

from app.models.domain import PersonaProfile


@dataclass
class ModelReply:
    text: str
    mood: str
    action: str


class ModelProvider:
    def generate_chat(
        self, *, persona: PersonaProfile, section_id: str, message: str
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


class MockModelProvider(ModelProvider):
    def generate_chat(
        self, *, persona: PersonaProfile, section_id: str, message: str
    ) -> ModelReply:
        style = persona.teaching_style[0] if persona.teaching_style else "structured"
        text = (
            f"{persona.name} 正在结合章节 {section_id} 讲解。"
            f" 当前提问是：{message}。"
            f" 我会用 {style} 的方式先解释核心概念，再给你一个复述任务。"
        )
        mood = "playful" if persona.narrative_mode == "light_story" else "calm"
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
