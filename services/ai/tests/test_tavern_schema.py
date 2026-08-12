from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models.domain import PersonaProfile
from app.models.harness import (
    HarnessCheckRecord,
    HarnessCheckStatus,
    HarnessStatus,
    HarnessTraceRecord,
)
from app.models.tavern import (
    CreateTavernRoomRequest,
    TavernActorReply,
    TavernAuthorKind,
    TavernHarnessPolicy,
    TavernInteractionMode,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRoomRecord,
    TavernRunRecord,
    TavernSpeakerStepRecord,
    TavernTurnRequest,
    UpdateTavernRoomRequest,
)
from app.persistence.database import Database
from app.persistence.models import TavernRoomRow, TavernRunRow
from app.persistence.tavern_repository import TavernRepository, TavernStepClaimConflict


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

    @staticmethod
    def _lease_failure_trace() -> HarnessTraceRecord:
        return HarnessTraceRecord(
            version="tavern-harness-v1/test",
            workflow="tavern",
            stage="lease_recovery",
            status=HarnessStatus.FAILED,
            schema_name="TavernSpeakerStepLease",
            checks=[
                HarnessCheckRecord(
                    name="bounded_step_claims",
                    status=HarnessCheckStatus.FAILED,
                    code="tavern_step_claims_exhausted",
                )
            ],
            recovery_strategy="lease_takeover_exhausted",
        )

    def test_schema_uses_normalized_tavern_tables(self) -> None:
        tables = set(inspect(self.database.engine).get_table_names())
        self.assertTrue(
            {
                "tavern_rooms",
                "tavern_participants",
                "tavern_messages",
                "tavern_runs",
                "tavern_run_steps",
            }
            <= tables
        )
        self.assertNotIn("tavern_sessions", tables)

    def test_facilitated_schema_has_run_lineage_steps_and_sqlite_foreign_keys(self) -> None:
        inspector = inspect(self.database.engine)
        run_columns = {item["name"] for item in inspector.get_columns("tavern_runs")}
        self.assertIn("parent_run_id", run_columns)
        step_columns = {
            item["name"] for item in inspector.get_columns("tavern_run_steps")
        }
        self.assertTrue(
            {"lease_owner", "lease_expires_at", "claim_count"} <= step_columns
        )

        step_primary_key = inspector.get_pk_constraint("tavern_run_steps")
        self.assertEqual(
            set(step_primary_key["constrained_columns"]),
            {"run_id", "step_index"},
        )
        step_foreign_keys = inspector.get_foreign_keys("tavern_run_steps")
        self.assertTrue(
            any(
                item["referred_table"] == "tavern_runs"
                and item["constrained_columns"] == ["run_id"]
                for item in step_foreign_keys
            )
        )
        with self.database.engine.connect() as connection:
            enabled = connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one()
        self.assertEqual(enabled, 1)

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

    def test_sqlite_existing_tavern_run_table_adds_retry_lineage_and_steps(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "tavern-schema-v3.db"
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
                connection.exec_driver_sql(
                    """
                    CREATE TABLE tavern_runs (
                        id VARCHAR(64) PRIMARY KEY,
                        room_id VARCHAR(64) NOT NULL,
                        idempotency_key VARCHAR(80) NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        mode VARCHAR(32) NOT NULL DEFAULT 'direct',
                        input_message_id VARCHAR(64) NOT NULL DEFAULT '',
                        expected_room_revision INTEGER NOT NULL DEFAULT 0,
                        error_code VARCHAR(128) NOT NULL DEFAULT '',
                        created_at VARCHAR(64) NOT NULL DEFAULT '',
                        completed_at VARCHAR(64) NOT NULL DEFAULT '',
                        payload JSON NOT NULL DEFAULT '{}'
                    )
                    """
                )
            legacy_database.create_schema()
            inspector = inspect(legacy_database.engine)
            run_columns = {
                item["name"] for item in inspector.get_columns("tavern_runs")
            }
            self.assertIn("parent_run_id", run_columns)
            self.assertIn("tavern_run_steps", inspector.get_table_names())
            unique_column_sets = {
                tuple(item["column_names"])
                for item in inspector.get_unique_constraints("tavern_runs")
            }
            self.assertIn(("parent_run_id",), unique_column_sets)
            foreign_keys = inspector.get_foreign_keys("tavern_runs")
            self.assertTrue(
                any(
                    item["referred_table"] == "tavern_runs"
                    and item["constrained_columns"] == ["parent_run_id"]
                    for item in foreign_keys
                )
            )
            with legacy_database.session() as session:
                session.add(TavernRoomRow(id="legacy-room", title="Legacy Room"))
            with self.assertRaises(IntegrityError):
                with legacy_database.session() as session:
                    session.add(
                        TavernRunRow(
                            id="invalid-child",
                            room_id="legacy-room",
                            idempotency_key="invalid-child-key",
                            parent_run_id="missing-parent",
                        )
                    )
        finally:
            legacy_database.dispose()

    def test_sqlite_partial_facilitated_upgrade_preserves_runs_and_steps(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "tavern-schema-partial-v4.db"
        legacy_database = Database(f"sqlite:///{legacy_path}")
        try:
            BaseRoom = TavernRoomRow.__table__
            with legacy_database.engine.begin() as connection:
                BaseRoom.create(connection)
                connection.exec_driver_sql(
                    """
                    CREATE TABLE tavern_runs (
                        id VARCHAR(64) PRIMARY KEY,
                        room_id VARCHAR(64) NOT NULL,
                        idempotency_key VARCHAR(80) NOT NULL,
                        parent_run_id VARCHAR(64),
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        mode VARCHAR(32) NOT NULL DEFAULT 'direct',
                        input_message_id VARCHAR(64) NOT NULL DEFAULT '',
                        expected_room_revision INTEGER NOT NULL DEFAULT 0,
                        error_code VARCHAR(128) NOT NULL DEFAULT '',
                        created_at VARCHAR(64) NOT NULL DEFAULT '',
                        completed_at VARCHAR(64) NOT NULL DEFAULT '',
                        payload JSON NOT NULL DEFAULT '{}',
                        UNIQUE (room_id, idempotency_key),
                        UNIQUE (parent_run_id)
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    CREATE TABLE tavern_run_steps (
                        run_id VARCHAR(64) NOT NULL,
                        step_index INTEGER NOT NULL,
                        persona_id VARCHAR(64) NOT NULL,
                        participant_prompt_hash VARCHAR(64) NOT NULL DEFAULT '',
                        status VARCHAR(32) NOT NULL DEFAULT 'pending',
                        message_id VARCHAR(64),
                        reply_to_message_id VARCHAR(64) NOT NULL DEFAULT '',
                        error_code VARCHAR(128) NOT NULL DEFAULT '',
                        started_at VARCHAR(64) NOT NULL DEFAULT '',
                        completed_at VARCHAR(64) NOT NULL DEFAULT '',
                        payload JSON NOT NULL DEFAULT '{}',
                        PRIMARY KEY (run_id, step_index),
                        UNIQUE (run_id, persona_id),
                        UNIQUE (message_id)
                    )
                    """
                )
                connection.execute(
                    BaseRoom.insert().values(id="partial-room", title="Partial Room")
                )
                run_payload = (
                    '{"trigger_kind":"retry","root_run_id":"root-run",'
                    '"anchor_message_id":"anchor-1",'
                    '"scheduled_participant_ids":["persona-b"],'
                    '"terminal_sequence":2}'
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO tavern_runs (
                        id, room_id, idempotency_key, parent_run_id, status, mode,
                        input_message_id, expected_room_revision, error_code,
                        created_at, completed_at, payload
                    ) VALUES (
                        'root-run', 'partial-room', 'root-request', NULL, 'partial',
                        'facilitated', 'input-1', 0, 'planned_failure',
                        '2026-08-12T00:00:00+00:00', '2026-08-12T00:00:01+00:00', '{}'
                    )
                    """
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO tavern_runs (
                        id, room_id, idempotency_key, parent_run_id, status, mode,
                        input_message_id, expected_room_revision, error_code,
                        created_at, completed_at, payload
                    ) VALUES (
                        'child-run', 'partial-room', 'child-request', 'root-run', 'completed',
                        'facilitated', 'input-1', 1, '',
                        '2026-08-12T00:00:02+00:00', '2026-08-12T00:00:03+00:00', ?
                    )
                    """,
                    (run_payload,),
                )
                connection.exec_driver_sql(
                    """
                    INSERT INTO tavern_run_steps (
                        run_id, step_index, persona_id, participant_prompt_hash,
                        status, message_id, reply_to_message_id, error_code,
                        started_at, completed_at, payload
                    ) VALUES (
                        'child-run', 0, 'persona-b', 'hash-b', 'completed',
                        'message-b', 'anchor-1', '',
                        '2026-08-12T00:00:02+00:00',
                        '2026-08-12T00:00:03+00:00', '{}'
                    )
                    """
                )

            legacy_database.create_schema()
            repository = TavernRepository(legacy_database)
            child = repository.get_run("child-run")
            self.assertIsNotNone(child)
            assert child is not None
            self.assertEqual(child.parent_run_id, "root-run")
            self.assertEqual(child.speaker_steps[0].persona_id, "persona-b")
            self.assertEqual(child.speaker_steps[0].message_id, "message-b")
            step_columns = {
                item["name"]
                for item in inspect(legacy_database.engine).get_columns(
                    "tavern_run_steps"
                )
            }
            self.assertTrue(
                {"lease_owner", "lease_expires_at", "claim_count"} <= step_columns
            )
            with legacy_database.engine.connect() as connection:
                self.assertEqual(
                    connection.exec_driver_sql("PRAGMA foreign_key_check").all(),
                    [],
                )
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

    def test_repository_refuses_to_finalize_before_all_speaker_steps_complete(self) -> None:
        room = TavernRoomRecord(
            id="tavern-early-finalize",
            title="Invariant Room",
            created_at=NOW,
            updated_at=NOW,
        )
        self.repository.create_room(room=room, participants=[])
        run = TavernRunRecord(
            id="run-early-finalize",
            room_id=room.id,
            idempotency_key="early-finalize-key",
            request_digest="early-finalize-digest",
            mode=TavernInteractionMode.FACILITATED,
            scheduled_participant_ids=["persona-a", "persona-b"],
            speaker_steps=[
                TavernSpeakerStepRecord(
                    run_id="run-early-finalize",
                    step_index=0,
                    persona_id="persona-a",
                ),
                TavernSpeakerStepRecord(
                    run_id="run-early-finalize",
                    step_index=1,
                    persona_id="persona-b",
                ),
            ],
            expected_room_revision=0,
            created_at=NOW,
        )
        user_message = TavernMessageRecord(
            id="message-early-finalize-user",
            room_id=room.id,
            sequence=1,
            author_kind=TavernAuthorKind.USER,
            content="请依次回应。",
            created_at=NOW,
        )
        self.repository.begin_run(run=run, user_message=user_message)
        with self.assertRaises(TavernStepClaimConflict):
            self.repository.claim_step(
                run_id=run.id,
                step_index=1,
                lease_owner="test-worker",
                lease_seconds=120,
                max_claims=3,
                exhaustion_trace=self._lease_failure_trace(),
            )
        first_claim = self.repository.claim_step(
            run_id=run.id,
            step_index=0,
            lease_owner="test-worker",
            lease_seconds=120,
            max_claims=3,
            exhaustion_trace=self._lease_failure_trace(),
        )
        generated = TavernMessageRecord(
            id="message-early-finalize-persona",
            room_id=room.id,
            sequence=1,
            author_kind=TavernAuthorKind.PERSONA,
            persona_id="persona-a",
            content="第一位回应。",
            created_at=NOW,
        )

        with self.assertRaisesRegex(RuntimeError, "tavern_run_steps_incomplete"):
            self.repository.complete_step(
                run_id=run.id,
                step_index=0,
                message=generated,
                completed_at=NOW,
                finalize_run=True,
                lease_owner="test-worker",
                claim_count=first_claim.claim_count,
            )

        persisted = self.repository.require_room(room.id)
        self.assertEqual(persisted.message_count, 1)
        self.assertEqual(persisted.room.last_sequence, 1)
        persisted_run = self.repository.get_run(run.id)
        assert persisted_run is not None
        self.assertEqual(persisted_run.status.value, "pending")
        self.assertEqual(
            [item.status.value for item in persisted_run.speaker_steps],
            ["generating", "pending"],
        )

        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                "UPDATE tavern_run_steps SET lease_expires_at = ? "
                "WHERE run_id = ? AND step_index = 0",
                ("2020-01-01T00:00:00.000000+00:00", run.id),
            )

        takeover = self.repository.claim_step(
            run_id=run.id,
            step_index=0,
            lease_owner="takeover-worker",
            lease_seconds=120,
            max_claims=3,
            exhaustion_trace=self._lease_failure_trace(),
        )
        self.assertEqual(takeover.status.value, "generating")
        with self.assertRaisesRegex(TavernStepClaimConflict, "lease_lost"):
            self.repository.complete_step(
                run_id=run.id,
                step_index=0,
                message=generated,
                completed_at="2026-08-12T00:04:00+00:00",
                finalize_run=False,
                lease_owner="test-worker",
                claim_count=first_claim.claim_count,
            )
        recovered = self.repository.complete_step(
            run_id=run.id,
            step_index=0,
            message=generated,
            completed_at="2026-08-12T00:04:00+00:00",
            finalize_run=False,
            lease_owner="takeover-worker",
            claim_count=takeover.claim_count,
        )
        self.assertEqual(recovered.speaker_steps[0].status.value, "completed")
        self.assertEqual(len(self.repository.list_run_messages(run.id)), 1)

    def test_step_lease_rejects_invalid_budgets_or_owner(self) -> None:
        with self.assertRaisesRegex(ValueError, "tavern_step_lease_owner_required"):
            self.repository.claim_step(
                run_id="missing-run",
                step_index=0,
                lease_owner="",
                lease_seconds=120,
                max_claims=3,
                exhaustion_trace=self._lease_failure_trace(),
            )
        with self.assertRaisesRegex(ValueError, "tavern_step_lease_seconds_invalid"):
            self.repository.claim_step(
                run_id="missing-run",
                step_index=0,
                lease_owner="test-worker",
                lease_seconds=0,
                max_claims=3,
                exhaustion_trace=self._lease_failure_trace(),
            )
        with self.assertRaisesRegex(ValueError, "tavern_step_max_claims_invalid"):
            self.repository.claim_step(
                run_id="missing-run",
                step_index=0,
                lease_owner="test-worker",
                lease_seconds=120,
                max_claims=6,
                exhaustion_trace=self._lease_failure_trace(),
            )

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
            input={"kind": "user_message", "content": "回应我。"},
            mode=TavernInteractionMode.DIRECT,
            target_persona_ids=["persona-a"],
            idempotency_key="request-12345678",
            expected_room_revision=0,
        )
        self.assertEqual(request.mode, TavernInteractionMode.DIRECT)

        continued = TavernTurnRequest(
            input={"kind": "continue", "anchor_message_id": "message-latest"},
            mode=TavernInteractionMode.DIRECT,
            target_persona_ids=["persona-a"],
            idempotency_key="request-continue",
            expected_room_revision=1,
        )
        self.assertEqual(continued.input.kind, "continue")

        with self.assertRaises(ValidationError):
            TavernTurnRequest(
                input={"kind": "user_message", "content": "请两位一起回应。"},
                mode=TavernInteractionMode.DIRECT,
                target_persona_ids=["persona-a", "persona-b"],
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
                input={"kind": "user_message", "content": "   "},
                mode=TavernInteractionMode.DIRECT,
                target_persona_ids=["persona-a"],
                idempotency_key="request-turn-key",
                expected_room_revision=0,
            )

        with self.assertRaises(ValidationError):
            TavernTurnRequest(
                input={"kind": "user_message", "content": "没有指定角色。"},
                mode=TavernInteractionMode.DIRECT,
                target_persona_ids=[],
                idempotency_key="request-no-target",
                expected_room_revision=0,
            )


if __name__ == "__main__":
    unittest.main()
