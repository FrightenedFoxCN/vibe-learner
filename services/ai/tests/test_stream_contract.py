from __future__ import annotations

import unittest

from pydantic import ValidationError

from app.models.harness import canonical_harness_digest
from app.models.stream import (
    DOCUMENT_STREAM_PROJECTION_CONTRACT,
    STREAM_EVENT_SCHEMA_VERSION,
    STREAM_REPORT_SCHEMA_VERSION,
    StreamReportRecord,
    StreamSubjectRefV1,
    StreamTerminalEvidenceV1,
)
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    StreamReportRecorder,
)


class _MemoryStore:
    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict[str, object]] = {}

    def save_item(self, category: str, item_id: str, item: object) -> None:
        self.items[(category, item_id)] = item.model_dump(mode="json")  # type: ignore[attr-defined]

    def load_item(self, category: str, item_id: str, model: type[object]):
        payload = self.items.get((category, item_id))
        return model.model_validate(payload) if payload is not None else None  # type: ignore[attr-defined]


def _document_projection(document_id: str) -> dict[str, object]:
    return {
        "id": document_id,
        "title": "Fixture",
    }


def _committed_evidence(document_id: str) -> StreamTerminalEvidenceV1:
    projection = _document_projection(document_id)
    return StreamTerminalEvidenceV1(
        commit_status="committed",
        domain_operation_id="document-process-op-fixture",
        domain_operation_status="committed",
        resource_type="document",
        resource_id=document_id,
        commit_contract_version="document-process-commit-v1",
        projection_contract_version=DOCUMENT_STREAM_PROJECTION_CONTRACT,
        projection_digest=canonical_harness_digest(projection),
    )


class StreamContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = _MemoryStore()
        self.subject = StreamSubjectRefV1(
            subject_type="document",
            subject_id="doc-fixture",
        )
        self.recorder = StreamReportRecorder(
            store=self.store,  # type: ignore[arg-type]
            category=DOCUMENT_PROCESS_STREAM_CATEGORY,
            document_id="doc-fixture",
            stream_kind="document_process",
            subject=self.subject,
            operation_id="stream-fixture",
            max_events=3,
        )

    def test_event_binds_version_operation_subject_sequence_and_payload_digest(self) -> None:
        event = self.recorder.emit(
            "document_processing_started",
            {"document_id": "doc-fixture", "force_ocr": False},
        )

        self.assertEqual(event.event_schema_version, STREAM_EVENT_SCHEMA_VERSION)
        self.assertEqual(event.operation_id, "stream-fixture")
        self.assertEqual(event.event_id, "stream-fixture:event:1")
        self.assertEqual(event.event_sequence, 1)
        self.assertEqual(event.subject, self.subject)
        self.assertEqual(
            event.payload_digest,
            canonical_harness_digest(event.payload),
        )

    def test_trimmed_replay_keeps_monotonic_resume_sequence_and_stable_event_identity(self) -> None:
        self.recorder.emit(
            "document_processing_started",
            {"document_id": "doc-fixture"},
        )
        self.recorder.emit("parser_started", {"page_count": 3})
        self.recorder.emit("page_parsed", {"page_number": 1, "page_count": 3})
        latest = self.recorder.emit(
            "page_parsed",
            {"page_number": 2, "page_count": 3},
        )

        replay = StreamReportRecorder.load(
            store=self.store,  # type: ignore[arg-type]
            category=DOCUMENT_PROCESS_STREAM_CATEGORY,
            document_id="doc-fixture",
            stream_kind="document_process",
        )

        self.assertEqual(replay.report_schema_version, STREAM_REPORT_SCHEMA_VERSION)
        self.assertEqual(replay.last_event_sequence, 4)
        self.assertEqual([event.event_sequence for event in replay.events], [2, 3, 4])
        self.assertEqual(replay.events[-1].event_id, latest.event_id)
        self.assertEqual(replay.events[-1].payload_digest, latest.payload_digest)

    def test_report_rejects_cross_operation_and_cross_subject_events(self) -> None:
        self.recorder.emit(
            "document_processing_started",
            {"document_id": "doc-fixture"},
        )
        payload = self.recorder.report.model_dump(mode="json")
        payload["events"][0]["operation_id"] = "stream-attacker"
        payload["events"][0]["event_id"] = "stream-attacker:event:1"
        with self.assertRaisesRegex(ValidationError, "stream_report_event_scope_mismatch"):
            StreamReportRecord.model_validate(payload)

        payload = self.recorder.report.model_dump(mode="json")
        payload["events"][0]["subject"] = {
            "subject_type": "document",
            "subject_id": "doc-attacker",
        }
        payload["events"][0]["payload"] = {"document_id": "doc-attacker"}
        payload["events"][0]["payload_digest"] = canonical_harness_digest(
            payload["events"][0]["payload"]
        )
        with self.assertRaisesRegex(ValidationError, "stream_report_event_scope_mismatch"):
            StreamReportRecord.model_validate(payload)

    def test_unknown_stage_and_payload_digest_tampering_fail_closed(self) -> None:
        event = self.recorder.emit(
            "document_processing_started",
            {"document_id": "doc-fixture"},
        )
        payload = event.model_dump(mode="json")
        payload["stage"] = "atomic_commit"
        with self.assertRaisesRegex(ValidationError, "stream_event_stage_unregistered"):
            type(event).model_validate(payload)

        payload = event.model_dump(mode="json")
        payload["payload"]["force_ocr"] = True
        with self.assertRaisesRegex(ValidationError, "stream_payload_digest_mismatch"):
            type(event).model_validate(payload)

    def test_committed_terminal_binds_projection_and_fences_later_events(self) -> None:
        self.recorder.emit(
            "document_processing_started",
            {"document_id": "doc-fixture"},
        )
        terminal = self.recorder.emit(
            "stream_completed",
            {"document_id": "doc-fixture", "status": "processed"},
            terminal_evidence=_committed_evidence("doc-fixture"),
            committed_projection=_document_projection("doc-fixture"),
        )

        self.assertEqual(terminal.terminal_evidence.commit_status, "committed")  # type: ignore[union-attr]
        self.assertEqual(self.recorder.report.status, "completed")
        with self.assertRaisesRegex(ValueError, "stream_event_after_terminal"):
            self.recorder.emit("page_parsed", {"page_number": 3})

        payload = terminal.model_dump(mode="json")
        payload["committed_projection"]["title"] = "Tampered"
        with self.assertRaisesRegex(ValidationError, "stream_projection_digest_mismatch"):
            type(terminal).model_validate(payload)

    def test_legacy_report_remains_explicitly_unversioned(self) -> None:
        legacy = StreamReportRecord.model_validate(
            {
                "document_id": "doc-legacy",
                "stream_kind": "document_process",
                "status": "completed",
                "created_at": "2026-08-01T00:00:00+00:00",
                "updated_at": "2026-08-01T00:01:00+00:00",
                "events": [
                    {
                        "stage": "stream_completed",
                        "payload": {"document_id": "doc-legacy"},
                        "created_at": "2026-08-01T00:01:00+00:00",
                    }
                ],
            }
        )

        self.assertIsNone(legacy.report_schema_version)
        self.assertIsNone(legacy.operation_id)
        self.assertIsNone(legacy.last_event_sequence)
        self.assertIsNone(legacy.events[0].event_schema_version)

        partial_upgrade = legacy.model_dump(mode="json")
        partial_upgrade["operation_id"] = "invented-operation"
        with self.assertRaisesRegex(ValidationError, "legacy_stream_report_has_v1_evidence"):
            StreamReportRecord.model_validate(partial_upgrade)


if __name__ == "__main__":
    unittest.main()
