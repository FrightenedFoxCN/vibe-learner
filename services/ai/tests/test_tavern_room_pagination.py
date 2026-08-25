from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import event, insert, select

from app.persistence.database import Database
from app.persistence.models import (
    TavernMessageRow,
    TavernParticipantRow,
    TavernRoomRow,
)
from app.persistence.tavern_repository import (
    TavernRepository,
    TavernRoomCursorInvalid,
    _encode_room_cursor,
)


FIXTURE_SEED = "vibe-learner-tavern-1000-v1"


class TavernRoomPaginationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = TemporaryDirectory()
        database_path = Path(cls.temp_dir.name) / "tavern-room-pagination.db"
        cls.database = Database(f"sqlite:///{database_path}")
        cls.database.create_schema()
        cls.repository = TavernRepository(cls.database)
        cls._seed_fixture()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.database.dispose()
        cls.temp_dir.cleanup()

    @classmethod
    def _seed_fixture(cls) -> None:
        base_time = datetime(2026, 8, 25, 8, 0, tzinfo=timezone.utc)
        room_records: list[dict[str, object]] = []
        participant_records: list[dict[str, object]] = []
        message_records: list[dict[str, object]] = []
        for room_index in range(1000):
            room_id = f"room-{room_index:019d}"
            timestamp = (base_time - timedelta(seconds=room_index // 7)).isoformat()
            # Equal-timestamp groups sort by descending Room ID, so the first
            # 50 rows reach through source index 55.
            participant_count = 6 if room_index < 56 else (room_index % 6) + 1
            message_count = (room_index % 6) + 1
            room_records.append(
                {
                    "id": room_id,
                    "creation_key": None,
                    "creation_input_digest": "",
                    "title": "房" * 64,
                    "status": "active",
                    "scene_profile": None,
                    "harness_policy": {},
                    "revision": 0,
                    "last_sequence": message_count,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                }
            )
            for participant_index in range(participant_count):
                participant_records.append(
                    {
                        "room_id": room_id,
                        "persona_id": f"persona-{participant_index:016d}",
                        "display_order": participant_index,
                        "display_name": "角" * 48,
                        "persona_snapshot": {},
                        "prompt_hash": f"hash-{participant_index}",
                        "joined_at": timestamp,
                    }
                )
            for sequence in range(1, message_count + 1):
                message_records.append(
                    {
                        "id": f"message-{room_index:019d}-{sequence}",
                        "room_id": room_id,
                        "sequence": sequence,
                        "run_id": "",
                        "author_kind": "user",
                        "persona_id": "",
                        "client_request_id": "",
                        "content": "fixture message body is intentionally not loaded",
                        "created_at": timestamp,
                        "payload": {},
                    }
                )
        with cls.database.session() as session:
            session.execute(insert(TavernRoomRow), room_records)
            session.execute(insert(TavernParticipantRow), participant_records)
            session.execute(insert(TavernMessageRow), message_records)

    def test_pages_cover_1000_rooms_with_equal_timestamp_tiebreaks(self) -> None:
        with self.database.session() as session:
            expected_ids = session.scalars(
                select(TavernRoomRow.id).order_by(
                    TavernRoomRow.updated_at.desc(),
                    TavernRoomRow.id.desc(),
                )
            ).all()

        actual_ids: list[str] = []
        cursor = None
        first_page = self.repository.list_rooms(limit=30)
        self.assertIsNotNone(first_page.next_cursor)
        second_page = self.repository.list_rooms(
            limit=30,
            cursor=first_page.next_cursor,
        )
        self.assertEqual(
            first_page.items[-1].updated_at,
            second_page.items[0].updated_at,
        )
        while True:
            page = self.repository.list_rooms(limit=30, cursor=cursor)
            actual_ids.extend(item.id for item in page.items)
            if page.next_cursor is None:
                break
            cursor = page.next_cursor

        self.assertEqual(actual_ids, expected_ids)
        self.assertEqual(len(actual_ids), 1000)
        self.assertEqual(len(set(actual_ids)), 1000)

    def test_default_and_max_pages_meet_query_payload_and_shape_gates(self) -> None:
        statement_count = 0

        def count_statement(*_args) -> None:
            nonlocal statement_count
            statement_count += 1

        event.listen(self.database.engine, "before_cursor_execute", count_statement)
        try:
            default_page = self.repository.list_rooms()
            default_query_count = statement_count
            statement_count = 0
            maximum_page = self.repository.list_rooms(limit=50)
            maximum_query_count = statement_count
            self.assertIsNotNone(maximum_page.next_cursor)
            statement_count = 0
            second_page = self.repository.list_rooms(
                limit=50,
                cursor=maximum_page.next_cursor,
            )
            cursor_query_count = statement_count
        finally:
            event.remove(self.database.engine, "before_cursor_execute", count_statement)

        self.assertEqual(len(default_page.items), 30)
        self.assertEqual(len(maximum_page.items), 50)
        self.assertIsNotNone(second_page.next_cursor)
        self.assertEqual(
            maximum_page.items[-1].updated_at,
            second_page.items[0].updated_at,
        )
        self.assertLessEqual(default_query_count, 4)
        self.assertLessEqual(maximum_query_count, 4)
        self.assertLessEqual(cursor_query_count, 4)
        self.assertTrue(all(len(item.participant_names) == 6 for item in maximum_page.items))
        default_payload = len(default_page.model_dump_json().encode("utf-8"))
        maximum_payload = len(maximum_page.model_dump_json().encode("utf-8"))
        self.assertLessEqual(default_payload, 192 * 1024)
        self.assertLessEqual(maximum_payload, 320 * 1024)

    def test_cursor_decode_is_closed_and_unknown_anchor_fails(self) -> None:
        page = self.repository.list_rooms(limit=30)
        cursor = page.next_cursor
        self.assertIsNotNone(cursor)
        assert cursor is not None
        replacement = "0" if cursor[-1] != "0" else "1"
        with self.assertRaisesRegex(TavernRoomCursorInvalid, "tampered"):
            self.repository.list_rooms(cursor=f"{cursor[:-1]}{replacement}")
        with self.assertRaisesRegex(TavernRoomCursorInvalid, "malformed"):
            self.repository.list_rooms(cursor="not-a-valid-cursor")
        unknown_cursor = _encode_room_cursor(
            "2026-08-25T07:59:00+00:00",
            "room-9999999999999999999",
        )
        with self.assertRaisesRegex(TavernRoomCursorInvalid, "unknown"):
            self.repository.list_rooms(cursor=unknown_cursor)

    def test_sqlite_query_plan_uses_descending_composite_index(self) -> None:
        with self.database.engine.connect() as connection:
            index_rows = connection.exec_driver_sql(
                "PRAGMA index_xinfo(ix_tavern_rooms_updated_at_id)"
            ).all()
            plan_rows = connection.exec_driver_sql(
                "EXPLAIN QUERY PLAN "
                "SELECT id FROM tavern_rooms "
                "ORDER BY updated_at DESC, id DESC LIMIT 31"
            ).all()
        indexed_fields = [(str(row[2]), int(row[3])) for row in index_rows if int(row[5]) == 1]
        self.assertEqual(indexed_fields, [("updated_at", 1), ("id", 1)])
        self.assertIn(
            "ix_tavern_rooms_updated_at_id",
            " ".join(str(row) for row in plan_rows),
        )


if __name__ == "__main__":
    unittest.main()
