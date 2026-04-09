import unittest

from app.models.api import CreatePersonaRequest
from app.services.model_provider import MockModelProvider
from app.services.pedagogy import PedagogyOrchestrator
from app.services.performance import PerformanceMapper
from app.services.persona import PersonaEngine


class PersonaPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.persona_engine = PersonaEngine()
        self.orchestrator = PedagogyOrchestrator(
            model_provider=MockModelProvider(),
            performance_mapper=PerformanceMapper(),
        )

    def test_builtin_personas_are_available(self) -> None:
        personas = self.persona_engine.list_personas()
        self.assertGreaterEqual(len(personas), 2)
        self.assertEqual(personas[0].source, "builtin")

    def test_user_persona_creation_preserves_contract_shape(self) -> None:
        persona = self.persona_engine.create_persona(
            CreatePersonaRequest(
                name="Sora Guide",
                summary="A sharp but kind mentor.",
                system_prompt="Stay grounded in the document.",
                teaching_style=["socratic", "precise"],
                narrative_mode="light_story",
                encouragement_style="celebrate effort",
                correction_style="direct but supportive",
            )
        )
        self.assertEqual(persona.id, "sora-guide")
        self.assertEqual(persona.source, "user")
        self.assertIn("playful", persona.available_emotions)

    def test_chat_reply_returns_character_events(self) -> None:
        persona = self.persona_engine.require_persona("mentor-lyra")
        result = self.orchestrator.generate_chat_reply(
            session_id="session-1",
            persona=persona,
            message="解释牛顿第一定律",
            section_id="chapter-1",
        )
        self.assertTrue(result.reply)
        self.assertEqual(result.citations[0].section_id, "chapter-1")
        self.assertEqual(result.character_events[0].line_segment_id, "session-1:chat:0")

    def test_grading_changes_based_on_answer_length(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        short = self.orchestrator.grade_submission(
            persona=persona, exercise_id="exercise-1", answer="太短了"
        )
        long = self.orchestrator.grade_submission(
            persona=persona,
            exercise_id="exercise-1",
            answer="这是一个相对完整的回答，包含概念解释、教材例子以及一点自己的复述。",
        )
        self.assertLess(short.score, long.score)
        self.assertEqual(long.character_events[0].action, "celebrate")


if __name__ == "__main__":
    unittest.main()
