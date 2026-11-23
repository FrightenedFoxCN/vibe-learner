from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.api import ContainerTestCase
from app.persistence.database import Database
from app.persistence.study_session_repository import StudySessionRepository
from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
from app.models.domain import StudySessionRecord


class StudyChatOperationTestCase(ContainerTestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        self.database.create_schema()
        self.sessions = StudySessionRepository(self.database)
        self.operations = StudyChatOperationRepository(self.database)
        self.sessions.create(
            StudySessionRecord(
                id="session-invalid-reply",
                document_id="doc",
                persona_id="persona-strict-chat",
                study_unit_id="unit-1",
                status="active",
                turns=[],
                revision=0,
                last_turn_sequence=0,
                created_at="2026-08-25T00:00:00+00:00",
                updated_at="2026-08-25T00:00:00+00:00",
            )
        )

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()
