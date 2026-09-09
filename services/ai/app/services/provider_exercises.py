from app.models.domain import PersonaProfile
from app.services.provider_capabilities import ExerciseModelCapability, ModelReply


class LocalExerciseProvider(ExerciseModelCapability):
    """Existing deterministic exercise behavior, independent of mock/remote chat."""

    exercise_implementation = "local_heuristic"

    def generate_exercise(
        self, *, persona: PersonaProfile, section_id: str, topic: str
    ) -> ModelReply:
        text = (
            f"围绕 {section_id} 的 {topic}，请你先用三句话概括概念，"
            "再举一个教材中的例子。"
        )
        return ModelReply(
            text=text,
            mood="encouraging",
            action="lean_in",
            speech_style=persona.default_speech_style,
            delivery_cue="提问时把语气往前推一点，给学习者明确的答题起点。",
            state_commentary=f"正在把 {topic} 转成可作答的小练习。",
            rich_blocks=[],
        )

    def grade_submission(
        self, *, persona: PersonaProfile, exercise_id: str, answer: str
    ) -> ModelReply:
        quality = "完整" if len(answer.strip()) > 24 else "偏短"
        text = (
            f"针对练习 {exercise_id}，你的回答{quality}。"
            " 我会指出遗漏点，并给出下一步复习建议。"
        )
        mood = "excited" if quality == "完整" else "concerned"
        action = "smile" if quality == "完整" else "pause"
        return ModelReply(
            text=text,
            mood=mood,
            action=action,
            speech_style=persona.default_speech_style,
            delivery_cue="先给判断，再补原因，末尾留一个可执行的修正动作。",
            state_commentary="正在根据答题完整度切换鼓励或纠偏反馈。",
            rich_blocks=[],
        )
