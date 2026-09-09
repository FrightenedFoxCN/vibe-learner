"""Room/write-set selection contracts, independent of repository orchestration."""
import unittest

from sqlalchemy import event
from sqlalchemy.orm import Session

from tests.support.database import isolated_database
from app.persistence.models import TavernMessageRow, TavernRoomRow, TavernRunRow, TavernRunStepRow
from app.persistence.tavern_invariant_scanner import (
    TavernReferenceWriteSet,
    scan_tavern_reference_integrity,
)


class TavernReferenceScopeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = isolated_database(self)
        # Deliberately bypass application validation to exercise audit inputs.
        with self.database.engine.begin() as connection:
            connection.execute(TavernRoomRow.__table__.insert(), [
                {"id": "a", "title": "A"}, {"id": "b", "title": "B"},
            ])

    def scan(self, scope: TavernReferenceWriteSet | None):
        with Session(self.database.engine) as session:
            return scan_tavern_reference_integrity(session, write_set=scope)

    def test_empty_write_set_performs_no_queries(self) -> None:
        queries = []
        def capture(*args):
            queries.append(args[2])
        event.listen(self.database.engine, "before_cursor_execute", capture)
        self.addCleanup(event.remove, self.database.engine, "before_cursor_execute", capture)
        self.assertEqual(self.scan(TavernReferenceWriteSet()), ())
        self.assertEqual(queries, [])

    def test_unrelated_corruption_is_only_reported_by_full_audit(self) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(TavernRunRow.__table__.insert().values(
                id="bad", room_id="b", idempotency_key="bad", input_message_id="missing",
            ))
        self.assertEqual(self.scan(TavernReferenceWriteSet(room_ids=frozenset({"a"}))), ())
        self.assertEqual([v.kind for v in self.scan(None)], ["run_input_message"])

    def test_cross_room_incoming_and_outgoing_edges_are_both_checked(self) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(TavernMessageRow.__table__.insert().values(
                id="message-a", room_id="a", sequence=1, author_kind="user", content="A",
            ))
            connection.execute(TavernRunRow.__table__.insert().values(
                id="run-b", room_id="b", idempotency_key="run-b", input_message_id="message-a",
            ))
        for room in ("a", "b"):
            with self.subTest(room=room):
                violations = self.scan(TavernReferenceWriteSet(room_ids=frozenset({room})))
                self.assertEqual([v.kind for v in violations], ["run_input_message_room"])

    def test_deleted_message_identity_preserves_incoming_edge_validation(self) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(TavernRunRow.__table__.insert().values(
                id="run-b", room_id="b", idempotency_key="run-b", input_message_id="deleted",
            ))
            connection.execute(TavernRunStepRow.__table__.insert().values(
                run_id="run-b", step_index=0, persona_id="persona", reply_to_message_id="deleted",
            ))
        violations = self.scan(TavernReferenceWriteSet(message_ids=frozenset({"deleted"})))
        self.assertEqual({v.kind for v in violations}, {"run_input_message", "step_reply_anchor"})

    def test_deleted_run_identity_preserves_incoming_edge_validation(self) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(TavernMessageRow.__table__.insert().values(
                id="message-b", room_id="b", sequence=1, author_kind="persona", content="B", run_id="deleted",
            ))
        violations = self.scan(TavernReferenceWriteSet(run_ids=frozenset({"deleted"})))
        self.assertEqual([v.kind for v in violations], ["message_run"])

    def test_scoped_and_full_audit_agree_for_affected_room(self) -> None:
        with self.database.engine.begin() as connection:
            connection.execute(TavernRunRow.__table__.insert().values(
                id="run-a", room_id="a", idempotency_key="run-a", input_message_id="missing-input",
            ))
            connection.execute(TavernRunStepRow.__table__.insert().values(
                run_id="run-a", step_index=0, persona_id="persona", message_id="missing-output",
                reply_to_message_id="missing-anchor",
            ))
        self.assertEqual(self.scan(TavernReferenceWriteSet(room_ids=frozenset({"a"}))), self.scan(None))
