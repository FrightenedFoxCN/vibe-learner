from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from app.models.domain import SessionSceneRecord
from app.persistence.models import SessionSceneRow
from app.services.local_store import LocalJsonStore


class SessionScenePersistenceTests(TestCase):
    def test_explicit_timestamp_and_empty_legacy_fallback_are_persisted(self):
        created = "2026-01-01T00:00:00Z"
        changed = "2026-01-01T00:01:00Z"
        with TemporaryDirectory() as tmp:
            store = LocalJsonStore(Path(tmp))
            self.addCleanup(store.close)
            for suffix, updated, expected in (
                ("current", changed, changed),
                ("legacy", "", created),
            ):
                with self.subTest(suffix=suffix):
                    record = SessionSceneRecord(
                        scene_instance_id=f"scene-{suffix}",
                        session_id="session-a",
                        document_id="document-a",
                        persona_id="persona-a",
                        created_at=created,
                        updated_at=updated,
                    )
                    store.save_item("session_scenes", record.scene_instance_id, record)
                    self.assertEqual(
                        store.load_item(
                            "session_scenes",
                            record.scene_instance_id,
                            SessionSceneRecord,
                        ),
                        record,
                    )
                    with store.database.session() as session:
                        row = session.get(SessionSceneRow, record.scene_instance_id)
                        self.assertEqual(row.updated_at, expected)
