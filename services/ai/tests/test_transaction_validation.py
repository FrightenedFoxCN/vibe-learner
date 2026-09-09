"""Transaction entrance tests: no API container, model provider or business fixture."""
import unittest

from sqlalchemy import bindparam, literal_column, delete, event, insert, select, text, update

from tests.support.database import isolated_database
from app.persistence.models import RuntimeSettingsRow, TavernMessageRow, TavernRoomRow, TavernRunRow
from app.persistence.tavern_invariant_scanner import TavernReferenceIntegrityError


class TransactionValidationTests(unittest.TestCase):
    def setUp(self):
        self.database = isolated_database(self)
        with self.database.session() as session:
            session.add(TavernRoomRow(id="room", title="Room"))
        with self.database.session() as session:
            session.add(TavernRunRow(id="run", room_id="room", idempotency_key="key"))

    def assert_run_unchanged(self):
        with self.database.session() as session:
            self.assertEqual(session.get(TavernRunRow, "run").input_message_id, "")

    def test_orm_flush_cannot_bypass_commit_validation(self):
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                session.get(TavernRunRow, "run").input_message_id = "missing"
                session.flush()
        self.assert_run_unchanged()

    def test_explicit_commit_cannot_bypass_validation(self):
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                session.get(TavernRunRow, "run").input_message_id = "missing"
                session.commit()
        self.assert_run_unchanged()

    def test_core_update_and_connection_update_are_checked(self):
        for connection_api in (False, True):
            with self.subTest(connection_api=connection_api):
                with self.assertRaises(TavernReferenceIntegrityError):
                    with self.database.session() as session:
                        # Populate a stale ORM identity to ensure SQL read-back wins.
                        session.get(TavernRunRow, "run")
                        executor = session.connection() if connection_api else session
                        executor.execute(update(TavernRunRow).where(TavernRunRow.id == "run").values(input_message_id="missing"))
                self.assert_run_unchanged()

    def test_insert_executemany_is_checked(self):
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                session.execute(insert(TavernRunRow), [
                    {"id": "one", "room_id": "room", "idempotency_key": "one", "input_message_id": ""},
                    {"id": "two", "room_id": "room", "idempotency_key": "two", "input_message_id": "missing"},
                ])
        with self.database.session() as session:
            self.assertIsNone(session.get(TavernRunRow, "one"))

    def test_transient_dangling_reference_can_be_repaired_before_commit(self):
        with self.database.session() as session:
            session.get(TavernRunRow, "run").input_message_id = "message"
            session.flush()
            session.add(TavernMessageRow(id="message", room_id="room", sequence=1, author_kind="user", content="hello"))
        with self.database.session() as session:
            self.assertEqual(session.get(TavernRunRow, "run").input_message_id, "message")

    def test_delete_referenced_message_is_rolled_back(self):
        with self.database.session() as session:
            session.add(TavernMessageRow(id="message", room_id="room", sequence=1, author_kind="user", content="hello"))
            session.get(TavernRunRow, "run").input_message_id = "message"
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                session.execute(delete(TavernMessageRow).where(TavernMessageRow.id == "message"))

    def test_savepoint_defers_validation_until_outer_commit(self):
        with self.database.session() as session:
            with session.begin_nested():
                session.get(TavernRunRow, "run").input_message_id = "message"
            session.add(TavernMessageRow(id="message", room_id="room", sequence=1, author_kind="user", content="hello"))

    def test_rollback_clears_pooled_connection_write_set(self):
        with self.database.session() as session:
            session.get(TavernRunRow, "run").input_message_id = "missing"
            session.flush()
            session.rollback()
        queries = []
        def capture(conn, cursor, statement, *args):
            queries.append(statement)
        event.listen(self.database.engine, "before_cursor_execute", capture)
        try:
            with self.database.session() as session:
                session.execute(select(1))
        finally:
            event.remove(self.database.engine, "before_cursor_execute", capture)
        self.assertFalse(any("tavern_" in sql for sql in queries))

    def test_opaque_mutation_is_rejected_before_execution(self):
        with self.assertRaisesRegex(ValueError, "structured_dml"):
            with self.database.session() as session:
                session.execute(text("UPDATE tavern_runs SET input_message_id = 'missing'"))
        self.assert_run_unchanged()

    def test_unrelated_orm_and_sql_settings_writes_never_query_tavern(self):
        queries = []
        def capture(conn, cursor, statement, *args):
            queries.append(statement)
        event.listen(self.database.engine, "before_cursor_execute", capture)
        try:
            with self.database.session() as session:
                session.add(RuntimeSettingsRow(config_id="settings"))
            with self.database.session() as session:
                session.execute(update(RuntimeSettingsRow).values(plan_provider="litellm"))
        finally:
            event.remove(self.database.engine, "before_cursor_execute", capture)
        self.assertFalse(any("tavern_" in sql for sql in queries))

    def test_connection_commit_cannot_bypass_validation(self):
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                connection = session.connection()
                connection.execute(update(TavernRunRow).values(input_message_id="missing"))
                connection.commit()
        self.assert_run_unchanged()

    def test_expanding_sql_parameters_capture_only_affected_rows(self):
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                session.execute(update(TavernRunRow).where(TavernRunRow.id.in_(["run", "absent"])).values(input_message_id="missing"))
        self.assert_run_unchanged()

    def test_rejected_sql_scope_expression_cannot_bypass_validation(self):
        with self.assertRaisesRegex(ValueError, "scope_identity"):
            with self.database.session() as session:
                session.execute(update(TavernRunRow).values(id=TavernRunRow.id + "-new"))
        self.assert_run_unchanged()

    def test_named_insert_parameters_still_record_scope(self):
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                session.connection().execute(insert(TavernRunRow).values(
                    id=bindparam("new_id"), room_id=bindparam("new_room"),
                    idempotency_key="named", input_message_id="missing",
                ), {"new_id": "named", "new_room": "room"})

    def test_expression_insert_cannot_hide_its_scope(self):
        with self.assertRaisesRegex(ValueError, "scope_identity"):
            with self.database.session() as session:
                session.execute(insert(TavernRunRow).values(
                    id=literal_column("'hidden'"), room_id=literal_column("'room'"),
                    idempotency_key="hidden", input_message_id="missing",
                ))

    def test_savepoint_release_cannot_persist_before_failed_outer_commit(self):
        with self.assertRaises(TavernReferenceIntegrityError):
            with self.database.session() as session:
                with session.begin_nested():
                    session.get(TavernRunRow, "run").input_message_id = "missing"
        self.assert_run_unchanged()
