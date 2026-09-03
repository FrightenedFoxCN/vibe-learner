from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sqlalchemy import text

from app.persistence.database import Database
from app.persistence.tavern_invariant_scanner import (
    TavernReferenceIntegrityError,
    require_tavern_reference_integrity,
)


class TavernInvariantScannerTests(unittest.TestCase):
    def test_sqlite_fixture_blocks_dangling_run_and_step_edges(self) -> None:
        with TemporaryDirectory() as directory:
            database = Database(f"sqlite:///{Path(directory) / 'tavern.db'}")
            database.create_schema()
            try:
                with database.engine.begin() as connection:
                    connection.execute(text(
                        "INSERT INTO tavern_rooms (id, title, status, revision, last_sequence, "
                        "created_at, updated_at, creation_input_digest, harness_policy) "
                        "VALUES ('room-1', '', 'active', 0, 0, '', '', '', '{}')"
                    ))
                    connection.execute(text(
                        "INSERT INTO tavern_runs (id, room_id, idempotency_key, status, mode, "
                        "input_message_id, expected_room_revision, error_code, created_at, completed_at, payload) "
                        "VALUES ('run-1', 'room-1', 'key', 'pending', 'direct', 'missing-message', 0, '', '', '', '{}')"
                    ))
                    connection.execute(text(
                        "INSERT INTO tavern_run_steps (run_id, step_index, persona_id, participant_prompt_hash, status, "
                        "message_id, reply_to_message_id, error_code, started_at, completed_at, lease_owner, lease_expires_at, claim_count, payload) VALUES "
                        "('run-1', 0, 'persona-1', '', 'pending', 'missing-output', 'missing-anchor', '', '', '', '', '', 0, '{}')"
                    ))
                with self.assertRaises(TavernReferenceIntegrityError) as raised:
                    with database._session_factory() as session:
                        require_tavern_reference_integrity(session)
                kinds = {item.kind for item in raised.exception.violations}
                self.assertEqual(
                    kinds,
                    {"run_input_message", "step_message", "step_reply_anchor"},
                )
            finally:
                database.dispose()


if __name__ == "__main__":
    unittest.main()
