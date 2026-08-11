from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError
from sqlalchemy import inspect

from app.models.domain import PersonaProfile
from app.models.tavern import (
    CreateTavernRoomRequest,
    TavernActorReply,
    TavernAuthorKind,
    TavernHarnessPolicy,
    TavernInteractionMode,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomRecord,
    TavernTurnRequest,
    UpdateTavernRoomRequest,
)
from app.persistence.database import Database
from app.persistence.tavern_repository import TavernRepository


NOW = "2026-08-12T00:00:00+00:00"


def _persona(persona_id: str, name: str) -> PersonaProfile:
    return PersonaProfile(
        id=persona_id,
        name=name,
        source="user",
        summary=f"{name} 的角色摘要",
        relationship="同行者",
        learner_address="你",
        system_prompt="保持角色身份稳定。",
        reference_hints=[],
        slots=[],
        available_emotions=["calm", "playful"],
        available_actions=["nod", "pause"],
        default_speech_style="warm",
    )


class TavernSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "tavern-schema.db"
        self.database = Database(f"sqlite:///{database_path}")
        self.database.create_schema()
        self.repository = TavernRepository(self.database)

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp_dir.cleanup()

    def test_schema_uses_normalized_tavern_tables(self) -> None:
        tables = set(inspect(self.database.engine).get_table_names())
        self.assertTrue(
            {"tavern_rooms", "tavern_participants", "tavern_messages", "tavern_runs"}
            <= tables
        )
        self.assertNotIn("tavern_sessions", tables)

    def test_sqlite_existing_tavern_room_table_adds_creation_key(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "tavern-schema-v2.db"
        legacy_database = Database(f"sqlite:///{legacy_path}")
        try:
            with legacy_database.engine.begin() as connection:
                connection.exec_driver_sql(
                    """
                    CREATE TABLE tavern_rooms (
                        id VARCHAR(64) PRIMARY KEY,
                        title TEXT NOT NULL DEFAULT '',
                        status VARCHAR(32) NOT NULL DEFAULT 'active',
                        scene_profile JSON,
                        harness_policy JSON NOT NULL DEFAULT '{}',
                        revision INTEGER NOT NULL DEFAULT 0,
                        last_sequence INTEGER NOT NULL DEFAULT 0,
                        created_at VARCHAR(64) NOT NULL DEFAULT '',
                        updated_at VARCHAR(64) NOT NULL DEFAULT ''
                    )
                    """
                )
            legacy_database.create_schema()
            columns = {
                item["name"]
                for item in inspect(legacy_database.engine).get_columns("tavern_rooms")
            }
            self.assertIn("creation_key", columns)
            self.assertIn("creation_input_digest", columns)
        finally:
            legacy_database.dispose()

    def test_room_repository_roundtrip_and_summary(self) -> None:
        room = TavernRoomRecord(
            id="tavern-room-1",
            title="夜航酒馆",
            harness_policy=TavernHarnessPolicy(context_message_limit=12),
            last_sequence=1,
            created_at=NOW,
            updated_at=NOW,
        )
        participants = [
            TavernParticipantRecord(
                room_id=room.id,
                persona_id="persona-a",
                display_order=0,
                display_name="阿澜",
                persona_snapshot=_persona("persona-a", "阿澜"),
                prompt_hash="hash-a",
                joined_at=NOW,
            ),
            TavernParticipantRecord(
                room_id=room.id,
                persona_id="persona-b",
                display_order=1,
                display_name="柏舟",
                persona_snapshot=_persona("persona-b", "柏舟"),
                prompt_hash="hash-b",
                joined_at=NOW,
            ),
        ]
        opening = TavernMessageRecord(
            id="message-1",
            room_id=room.id,
            sequence=1,
            author_kind=TavernAuthorKind.DIRECTOR,
            content="今晚讨论选择与责任。",
            created_at=NOW,
        )

        created = self.repository.create_room(
            room=room,
            participants=participants,
            messages=[opening],
        )

        self.assertEqual(created.room.title, "夜航酒馆")
        self.assertEqual([item.persona_id for item in created.participants], ["persona-a", "persona-b"])
        self.assertEqual(created.messages[0].author_kind, TavernAuthorKind.DIRECTOR)
        self.assertEqual(created.room.harness_policy.context_message_limit, 12)

        summaries = self.repository.list_rooms()
        self.assertEqual(len(summaries), 1)
        self.assertEqual(summaries[0].participant_names, ["阿澜", "柏舟"])
        self.assertEqual(summaries[0].message_count, 1)
        self.assertEqual(self.repository.count_persona_references("persona-a"), 1)

        self.assertTrue(self.repository.delete_room(room.id, expected_revision=0))
        self.assertEqual(self.repository.list_rooms(), [])
        self.assertFalse(self.repository.delete_room(room.id, expected_revision=0))

    def test_tavern_model_owned_reply_is_strict(self) -> None:
        with self.assertRaises(ValidationError):
            TavernActorReply.model_validate(
                {
                    "text": "你好。",
                    "mood": "calm",
                    "action": "点头",
                    "speaker_persona_id": "model-must-not-own-speaker-id",
                }
            )

        schema = TavernActorReply.model_json_schema()
        self.assertEqual(set(schema["required"]), set(schema["properties"]))
        transport_schema = TavernActorReply.transport_json_schema()
        self.assertEqual(
            set(transport_schema["required"]),
            set(transport_schema["properties"]),
        )
        self.assertNotIn("minLength", str(transport_schema))
        self.assertNotIn("maxLength", str(transport_schema))

    def test_direct_turn_has_one_server_scheduled_character_message(self) -> None:
        request = TavernTurnRequest(
            message="回应我。",
            mode=TavernInteractionMode.DIRECT,
            target_persona_ids=["persona-a"],
            max_character_messages=1,
            idempotency_key="request-12345678",
            expected_room_revision=0,
        )
        self.assertEqual(request.mode, TavernInteractionMode.DIRECT)

        with self.assertRaises(ValidationError):
            TavernTurnRequest(
                message="请两位一起回应。",
                mode=TavernInteractionMode.DIRECT,
                target_persona_ids=["persona-a", "persona-b"],
                max_character_messages=2,
                idempotency_key="request-abcdefgh",
                expected_room_revision=0,
            )

    def test_request_text_is_normalized_before_bounds_validation(self) -> None:
        with self.assertRaises(ValidationError):
            CreateTavernRoomRequest(
                title="   ",
                persona_ids=["persona-a"],
                idempotency_key="request-room-key",
            )
        with self.assertRaises(ValidationError):
            UpdateTavernRoomRequest(title="\n\t", expected_revision=0)
        with self.assertRaises(ValidationError):
            TavernTurnRequest(
                message="   ",
                mode=TavernInteractionMode.DIRECT,
                target_persona_ids=["persona-a"],
                max_character_messages=1,
                idempotency_key="request-turn-key",
                expected_room_revision=0,
            )

        with self.assertRaises(ValidationError):
            TavernTurnRequest(
                message="没有指定角色。",
                mode=TavernInteractionMode.DIRECT,
                target_persona_ids=[],
                max_character_messages=1,
                idempotency_key="request-no-target",
                expected_room_revision=0,
            )


if __name__ == "__main__":
    unittest.main()
