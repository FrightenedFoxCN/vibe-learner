from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
    HarnessOperationResolutionStatus,
)
from app.persistence.database import Database
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
    HarnessOperationDomainAlreadyBound,
    HarnessOperationIdentityCollision,
    HarnessOperationLegacyUnbound,
    HarnessOperationParentKindInvalid,
)
from app.persistence.models import (
    DocumentProcessOperationRow,
    DocumentRow,
    HarnessOperationBindingRow,
    StudyChatOperationRow,
    StudySessionRow,
    TavernRoomRow,
    TavernRunRow,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "harness"
ADMITTED_AT = "2026-08-25T06:00:00+00:00"


class HarnessOperationIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{Path(self.temp.name) / 'identity.db'}")
        self.database.create_schema()
        self.repository = HarnessOperationBindingRepository(self.database)

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def test_strict_binding_fixtures_validate_and_reject_contract_drift(self) -> None:
        for name in ("operation_binding_v1.json", "operation_binding_child_v1.json"):
            with self.subTest(name=name):
                payload = json.loads((FIXTURE_ROOT / name).read_text())
                binding = HarnessOperationBindingV1.model_validate(payload)
                self.assertEqual(binding.model_dump(mode="json"), payload)

        invalid = json.loads((FIXTURE_ROOT / "operation_binding_v1.json").read_text())
        invalid["workflow"] = "planning"
        with self.assertRaisesRegex(ValidationError, "domain_route_mismatch"):
            HarnessOperationBindingV1.model_validate(invalid)
        invalid = json.loads((FIXTURE_ROOT / "operation_binding_v1.json").read_text())
        invalid["application_owned_identity"] = "must-not-enter-binding"
        with self.assertRaises(ValidationError):
            HarnessOperationBindingV1.model_validate(invalid)
        invalid = json.loads((FIXTURE_ROOT / "operation_binding_v1.json").read_text())
        invalid["parent_harness_operation_id"] = (
            "harness-operation-11111111111111111111111111111111"
        )
        with self.assertRaisesRegex(ValidationError, "parent_kind_invalid"):
            HarnessOperationBindingV1.model_validate(invalid)

    def test_domain_identity_is_one_to_one_and_absence_is_typed(self) -> None:
        binding = self._admit_document("document-process-op-0123456789abcdef")
        resolution = self.repository.resolve_domain(
            domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
            domain_operation_id="document-process-op-0123456789abcdef",
        )
        self.assertEqual(resolution.status, HarnessOperationResolutionStatus.RESOLVED)
        self.assertEqual(resolution.binding, binding)
        self.assertEqual(
            HarnessOperationBindingRepository(self.database).get(
                harness_operation_id=binding.harness_operation_id
            ),
            binding,
        )
        with self.database.session() as session:
            persisted = session.get(
                DocumentProcessOperationRow,
                "document-process-op-0123456789abcdef",
            )
            assert persisted is not None
            with self.assertRaises(HarnessOperationDomainAlreadyBound):
                self.repository._admit_domain_in_session(
                    session,
                    domain_row=persisted,
                    domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                    domain_operation_id=persisted.operation_id,
                    admitted_at=ADMITTED_AT,
                )

        missing = self.repository.resolve_domain(
            domain_operation_kind=HarnessDomainOperationKind.STUDY_CHAT,
            domain_operation_id="study-chat-op-missing000001",
        )
        self.assertEqual(missing.status, HarnessOperationResolutionStatus.NOT_FOUND)
        self._insert_legacy_study_operation("study-chat-op-legacy0000001")
        legacy = self.repository.resolve_domain(
            domain_operation_kind=HarnessDomainOperationKind.STUDY_CHAT,
            domain_operation_id="study-chat-op-legacy0000001",
        )
        self.assertEqual(
            legacy.status,
            HarnessOperationResolutionStatus.LEGACY_UNBOUND,
        )
        self.assertIsNone(legacy.binding)
        with self.assertRaises(HarnessOperationLegacyUnbound):
            self.repository.require_domain(
                domain_operation_kind=HarnessDomainOperationKind.STUDY_CHAT,
                domain_operation_id="study-chat-op-legacy0000001",
            )

    def test_child_binding_points_to_parent_and_cross_kind_parent_is_rejected(self) -> None:
        parent = self._admit_tavern_run("tavern-run-parent01")
        child = self._admit_tavern_run(
            "tavern-run-child01",
            parent_run_id="tavern-run-parent01",
            parent_harness_operation_id=parent.harness_operation_id,
        )
        self.assertEqual(
            child.parent_harness_operation_id,
            parent.harness_operation_id,
        )
        with self.assertRaisesRegex(HarnessOperationParentKindInvalid, "parent_kind"):
            with self.database.session() as session:
                study_row = self._study_operation_row(
                    "study-chat-op-parent-invalid",
                    session_id="study-session-parent-invalid",
                )
                session.add(self._study_session_row("study-session-parent-invalid"))
                session.add(study_row)
                self.repository._admit_domain_in_session(
                    session,
                    domain_row=study_row,
                    domain_operation_kind=HarnessDomainOperationKind.STUDY_CHAT,
                    domain_operation_id=study_row.operation_id,
                    admitted_at=ADMITTED_AT,
                    parent_harness_operation_id=parent.harness_operation_id,
                )

    def test_harness_identity_collision_rolls_back_second_domain_binding(self) -> None:
        forged_id = "harness-operation-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        fixed = HarnessOperationBindingRepository(
            self.database,
            operation_id_factory=lambda: forged_id,
        )
        self._admit_document(
            "document-process-op-collision0001",
            repository=fixed,
        )
        with self.assertRaises(HarnessOperationIdentityCollision):
            try:
                self._admit_document(
                    "document-process-op-collision0002",
                    repository=fixed,
                )
            except IntegrityError as exc:
                raise HarnessOperationIdentityCollision from exc
        unresolved = fixed.resolve_domain(
            domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
            domain_operation_id="document-process-op-collision0002",
        )
        self.assertEqual(
            unresolved.status,
            HarnessOperationResolutionStatus.NOT_FOUND,
        )

    def test_database_rejects_route_forgery(self) -> None:
        with self.assertRaises(IntegrityError):
            with self.database.session() as session:
                session.add(
                    HarnessOperationBindingRow(
                        harness_operation_id=(
                            "harness-operation-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
                        ),
                        schema_name="HarnessOperationBindingV1",
                        schema_version="harness-operation-binding-v1",
                        domain_operation_kind="document_process",
                        domain_operation_id="document-process-op-forged000001",
                        workflow="planning",
                        entry_stage="plan_generation",
                        parent_harness_operation_id=None,
                        admitted_at=ADMITTED_AT,
                    )
                )

    def test_binding_and_domain_identity_are_database_immutable(self) -> None:
        binding = self._admit_document("document-process-op-immutable01")
        with self.assertRaisesRegex(IntegrityError, "binding_update_forbidden"):
            with self.database.session() as session:
                session.execute(
                    update(HarnessOperationBindingRow)
                    .where(
                        HarnessOperationBindingRow.harness_operation_id
                        == binding.harness_operation_id
                    )
                    .values(admitted_at="2026-08-25T07:00:00+00:00")
                )
        with self.assertRaisesRegex(IntegrityError, "binding_delete_forbidden"):
            with self.database.session() as session:
                session.execute(
                    delete(HarnessOperationBindingRow).where(
                        HarnessOperationBindingRow.harness_operation_id
                        == binding.harness_operation_id
                    )
                )

        legacy_id = "study-chat-op-rebinding0001"
        self._insert_legacy_study_operation(legacy_id)
        with self.assertRaisesRegex(IntegrityError, "rebinding_forbidden"):
            with self.database.session() as session:
                session.execute(
                    update(StudyChatOperationRow)
                    .where(StudyChatOperationRow.operation_id == legacy_id)
                    .values(harness_operation_id=binding.harness_operation_id)
                )

    def test_database_rejects_cross_domain_binding_on_insert(self) -> None:
        binding = self._admit_document("document-process-op-crossbind01")
        session_id = "study-session-cross-binding"
        with self.assertRaisesRegex(IntegrityError, "domain_binding_mismatch"):
            with self.database.session() as session:
                session.add(self._study_session_row(session_id))
                session.flush()
                row = self._study_operation_row(
                    "study-chat-op-cross-binding",
                    session_id=session_id,
                )
                row.harness_operation_id = binding.harness_operation_id
                session.add(row)

    def test_binding_survives_domain_retention_purge_as_admission_tombstone(self) -> None:
        operation_id = "document-process-op-retained001"
        binding = self._admit_document(operation_id)
        with self.database.session() as session:
            session.execute(
                delete(DocumentProcessOperationRow).where(
                    DocumentProcessOperationRow.operation_id == operation_id
                )
            )

        resolution = self.repository.resolve_domain(
            domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
            domain_operation_id=operation_id,
        )
        self.assertEqual(resolution.status, HarnessOperationResolutionStatus.NOT_FOUND)
        self.assertEqual(
            self.repository.get(
                harness_operation_id=binding.harness_operation_id,
            ),
            binding,
        )

    def _admit_document(
        self,
        operation_id: str,
        *,
        repository: HarnessOperationBindingRepository | None = None,
    ) -> HarnessOperationBindingV1:
        repository = repository or self.repository
        document_id = f"doc-{operation_id[-16:]}"
        with self.database.session() as session:
            session.add(
                DocumentRow(
                    id=document_id,
                    title="fixture",
                    original_filename="fixture.pdf",
                    stored_path="/tmp/fixture.pdf",
                    status="uploaded",
                    ocr_status="pending",
                    created_at=ADMITTED_AT,
                    updated_at=ADMITTED_AT,
                    payload={},
                )
            )
            row = DocumentProcessOperationRow(
                operation_id=operation_id,
                harness_operation_id=None,
                document_id=document_id,
                request_schema_version="document-process-request-v1",
                fingerprint_contract_version="document-process-fingerprint-v1",
                request_fingerprint="a" * 64,
                request_payload={"document_id": document_id, "force_ocr": False},
                status="running",
                active_slot=1,
                projection_state="pending",
                base_document_payload={},
                document_digest="",
                debug_digest="",
                commit_contract_version="",
                error_code="",
                created_at=ADMITTED_AT,
                updated_at=ADMITTED_AT,
                completed_at="",
            )
            session.add(row)
            return repository._admit_domain_in_session(
                session,
                domain_row=row,
                domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                domain_operation_id=operation_id,
                admitted_at=ADMITTED_AT,
            )

    def _admit_tavern_run(
        self,
        run_id: str,
        *,
        parent_run_id: str | None = None,
        parent_harness_operation_id: str | None = None,
    ) -> HarnessOperationBindingV1:
        with self.database.session() as session:
            if session.get(TavernRoomRow, "room-operation-identity") is None:
                session.add(
                    TavernRoomRow(
                        id="room-operation-identity",
                        title="identity",
                        status="active",
                        harness_policy={},
                        revision=0,
                        last_sequence=0,
                        created_at=ADMITTED_AT,
                        updated_at=ADMITTED_AT,
                    )
                )
            row = TavernRunRow(
                id=run_id,
                harness_operation_id=None,
                room_id="room-operation-identity",
                idempotency_key=f"key-{run_id}",
                parent_run_id=parent_run_id,
                status="pending",
                mode="direct",
                input_message_id="",
                expected_room_revision=0,
                error_code="",
                created_at=ADMITTED_AT,
                completed_at="",
                payload={},
            )
            session.add(row)
            return self.repository._admit_domain_in_session(
                session,
                domain_row=row,
                domain_operation_kind=HarnessDomainOperationKind.TAVERN_RUN,
                domain_operation_id=run_id,
                admitted_at=ADMITTED_AT,
                parent_harness_operation_id=parent_harness_operation_id,
            )

    def _insert_legacy_study_operation(self, operation_id: str) -> None:
        session_id = f"session-{operation_id[-16:]}"
        with self.database.session() as session:
            session.add(self._study_session_row(session_id))
            session.flush()
            session.add(self._study_operation_row(operation_id, session_id=session_id))

    @staticmethod
    def _study_session_row(session_id: str) -> StudySessionRow:
        return StudySessionRow(
            id=session_id,
            document_id="",
            persona_id="",
            plan_id="",
            study_unit_id="unit-fixture",
            status="active",
            revision=0,
            last_turn_sequence=0,
            created_at=ADMITTED_AT,
            updated_at=ADMITTED_AT,
            payload={},
        )

    @staticmethod
    def _study_operation_row(
        operation_id: str,
        *,
        session_id: str,
    ) -> StudyChatOperationRow:
        return StudyChatOperationRow(
            operation_id=operation_id,
            harness_operation_id=None,
            session_id=session_id,
            client_request_id=f"request-{operation_id[-16:]}",
            request_schema_version="study-chat-operation-request-v2",
            fingerprint_contract_version="study-chat-fingerprint-v2",
            request_fingerprint="b" * 64,
            request_payload={},
            status="admitted",
            active_slot=1,
            admitted_session_revision=0,
            execution_token="",
            claim_count=0,
            execution_started_at="",
            provider_started_at="",
            execution_deadline_at="",
            heartbeat_at="",
            committed_session_revision=None,
            committed_turn_id=None,
            committed_turn_sequence=None,
            response_schema_version="",
            response_payload=None,
            response_digest="",
            error_code="",
            created_at=ADMITTED_AT,
            updated_at=ADMITTED_AT,
            completed_at="",
        )


if __name__ == "__main__":
    unittest.main()
