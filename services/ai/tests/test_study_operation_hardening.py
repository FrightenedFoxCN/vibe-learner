import unittest
from contextlib import contextmanager
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.schema import CreateTable

from app.persistence.database import Database
from app.persistence.database_clock import database_utc_now, database_utc_wire
from app.persistence.models import Base, HarnessEffectJournalRow
from app.services.harness_effect_scanner import scan_harness_effect_journal
from app.services.study_v3 import StudyV3ReplyAdapter


class StudyOperationHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database = Database("sqlite:///:memory:")
        self.database.create_schema()

    def tearDown(self) -> None:
        self.database.dispose()

    def test_database_clock_is_utc_and_wire_parseable(self) -> None:
        with self.database.session() as session:
            current = database_utc_now(session)
            wire = database_utc_wire(session)
        self.assertIsNotNone(current.tzinfo)
        self.assertEqual(current.utcoffset().total_seconds(), 0)
        self.assertTrue(wire.endswith("+00:00"))

    def test_empty_journal_is_healthy(self) -> None:
        result = scan_harness_effect_journal(self.database)
        self.assertTrue(result.healthy)
        self.assertEqual(result.findings, ())

    def test_journal_ddl_compiles_for_sqlite_and_postgresql(self) -> None:
        table = HarnessEffectJournalRow.__table__
        sqlite_ddl = str(CreateTable(table).compile(dialect=sqlite.dialect()))
        postgres_ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))
        for ddl in (sqlite_ddl, postgres_ddl):
            self.assertIn("harness_effect_journal", ddl)
            self.assertIn("schema_version", ddl)
            self.assertIn("claim_count", ddl)
            self.assertIn("terminal_evidence", ddl)
        self.assertEqual(
            {column.name for column in table.columns},
            {column.name for column in Base.metadata.tables["harness_effect_journal"].columns},
        )

    def test_scanner_reports_unknown_version_and_corrupt_terminal(self) -> None:
        rows = [
            SimpleNamespace(
                effect_id="harness-effect-unknown",
                schema_name="HarnessEffectJournalEntryV1",
                schema_version="harness-effect-journal-entry-v99",
                state="prepared",
                claim_count=0,
                claim_owner="",
                lease_expires_at="",
            ),
            SimpleNamespace(
                effect_id="harness-effect-corrupt",
                schema_name="HarnessEffectJournalEntryV1",
                schema_version="harness-effect-journal-entry-v1",
                state="terminal",
                claim_count=1,
                claim_owner="worker",
                lease_expires_at="",
                terminal_evidence={"schema_name": "invalid"},
                proposal_digest="0" * 64,
                terminal_outcome="committed",
            ),
        ]

        class FakeDatabase:
            @contextmanager
            def session(self):
                class FakeSession:
                    def scalars(self, _query):
                        return SimpleNamespace(all=lambda: rows)

                yield FakeSession()

        result = scan_harness_effect_journal(FakeDatabase())
        self.assertFalse(result.healthy)
        self.assertEqual(
            [finding.reason_code for finding in result.findings],
            ["journal_schema_unsupported", "terminal_evidence_invalid"],
        )

    def test_study_reply_adapter_rejects_malformed_nested_tool(self) -> None:
        with self.assertRaises(ValueError):
            StudyV3ReplyAdapter().decode({"reply": "ok", "citations": [], "character_events": [], "tool_calls": [{"tool_call_id": "", "tool_name": "x", "arguments_json": "{}", "result_json": "{}"}]})


if __name__ == "__main__":
    unittest.main()
