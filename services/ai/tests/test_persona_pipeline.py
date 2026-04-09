from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.models.api import CreatePersonaRequest
from app.models.domain import LearningGoalInput
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.pedagogy import PedagogyOrchestrator
from app.services.performance import PerformanceMapper
from app.services.plans import LearningPlanService
from app.services.persona import PersonaEngine
from app.services.study_sessions import StudySessionService


class PersonaPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        store = LocalJsonStore(Path(self.temp_dir.name))
        self.persona_engine = PersonaEngine()
        self.document_service = DocumentService(store)
        self.plan_service = LearningPlanService(store)
        self.study_session_service = StudySessionService(store)
        self.orchestrator = PedagogyOrchestrator(
            model_provider=MockModelProvider(),
            performance_mapper=PerformanceMapper(),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

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

    def test_plan_and_session_can_be_persisted(self) -> None:
        from fastapi import UploadFile

        upload = UploadFile(
            filename="physics-notes.pdf",
            file=open(__file__, "rb"),
        )
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        processed = self.document_service.process_document(document.id)
        persona = self.persona_engine.require_persona("mentor-aurora")
        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=processed.id,
                persona_id=persona.id,
                objective="掌握第一章",
                deadline="2026-05-01",
                study_days_per_week=4,
                session_minutes=35,
            ),
            document=processed,
            persona_name=persona.name,
        )
        session = self.study_session_service.create_session(
            document_id=processed.id,
            persona_id=persona.id,
            section_id=processed.sections[0].id,
        )

        reply = self.orchestrator.generate_chat_reply(
            session_id=session.id,
            persona=persona,
            message="解释本章核心定义",
            section_id=processed.sections[0].id,
        )
        updated_session = self.study_session_service.append_turn(
            session_id=session.id,
            learner_message="解释本章核心定义",
            result=reply,
        )

        self.assertTrue(plan.overview)
        self.assertEqual(updated_session.turns[0].assistant_reply, reply.reply)
        self.assertEqual(updated_session.section_id, processed.sections[0].id)


if __name__ == "__main__":
    unittest.main()
