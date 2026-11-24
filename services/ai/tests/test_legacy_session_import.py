from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.models.domain import StudySessionRecord
from app.persistence.study_session_repository import StudySessionRepository
from app.services.local_store import LocalJsonStore


class LegacySessionImportTests(TestCase):
    def test_old_section_id_can_be_imported(self):
        legacy = StudySessionRecord.model_validate(
            {
                "id": "session-legacy",
                "document_id": "doc-legacy",
                "persona_id": "persona-fixture",
                "section_id": "section-legacy",
                "status": "active",
                "turns": [],
                "created_at": "2025-01-01T00:00:00+00:00",
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        )
        root = Path(self.enterContext(TemporaryDirectory()))
        store = LocalJsonStore(root)
        self.addCleanup(store.close)
        store.save_list("sessions", [legacy])
        record = StudySessionRepository(store.database).require(legacy.id)
        self.assertEqual(record.study_unit_id, "section-legacy")
