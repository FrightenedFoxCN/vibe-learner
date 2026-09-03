from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from app.models.harness import HarnessArtifactType, HarnessContractRef
from app.models.harness_artifact_access import (
    HarnessArtifactGrantScopeV1,
    HarnessArtifactPermission,
    HarnessArtifactResolutionStatus,
    HarnessArtifactResolveRequestV1,
)
from app.models.harness_eval import (
    HarnessEvalCaseV1,
    canonical_harness_eval_case_digest,
)
from app.models.harness_operation import HarnessOperationBindingV1
from app.persistence.database import Database
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.models import (
    HarnessArtifactPrincipalRow,
    HarnessArtifactGrantRow,
    HarnessArtifactRow,
    HarnessOperationBindingRow,
)
from app.services.harness_eval_runner import (
    HarnessArtifactEvalResolver,
    HarnessEvalRunnerError,
)


NOW = datetime(2026, 8, 31, 4, 0, tzinfo=timezone.utc)
OPERATION_ID = f"harness-operation-{'1' * 32}"
CONTRACT = HarnessContractRef(name="TavernTranscriptSnapshot", version="tavern-transcript-snapshot-v1")


class HarnessArtifactResolverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.database = Database(f"sqlite:///{self._tmp.name}/resolver.sqlite3")
        self.database.create_schema()
        self.repository = HarnessArtifactRepository(self.database)
        with self.database.session() as session:
            session.add(
                HarnessOperationBindingRow(
                    harness_operation_id=OPERATION_ID,
                    schema_name="HarnessOperationBindingV1",
                    schema_version="harness-operation-binding-v1",
                    domain_operation_kind="tavern_run",
                    domain_operation_id="run-artifact-test",
                    workflow="tavern",
                    entry_stage="actor_reply",
                    parent_harness_operation_id=None,
                    admitted_at="2026-08-31T04:00:00Z",
                )
            )

    def tearDown(self) -> None:
        self.database.dispose()
        self._tmp.cleanup()

    def _artifact_and_grant(
        self,
        *,
        expires_at: datetime | None = None,
        permission: HarnessArtifactPermission = HarnessArtifactPermission.READ,
    ):
        artifact = self.repository.register_artifact(
            artifact_type=HarnessArtifactType.TAVERN_TRANSCRIPT,
            artifact_contract=CONTRACT,
            content=b"protected transcript",
            expires_at=expires_at,
            now=NOW,
        )
        scope = HarnessArtifactGrantScopeV1(
            artifact_type=artifact.artifact_type,
            artifact_id=artifact.artifact_id,
            artifact_contract=CONTRACT,
            permission=permission,
        )
        grant = self.repository.issue_grant(
            harness_operation_id=OPERATION_ID,
            scopes=(scope,),
            expires_at=expires_at or NOW + timedelta(hours=1),
            now=NOW,
        )
        request = HarnessArtifactResolveRequestV1(
            grant_id=grant.grant_id,
            harness_operation_id=OPERATION_ID,
            artifact_id=artifact.artifact_id,
            artifact_type=artifact.artifact_type,
            artifact_contract=CONTRACT,
            permission=permission,
        )
        return artifact, grant, request

    def test_resolves_opaque_immutable_content_and_replays_after_restart(self) -> None:
        artifact, _, request = self._artifact_and_grant()
        self.assertRegex(artifact.artifact_id, r"^harness-artifact-[0-9a-f]{32}$")
        with self.assertRaises(IntegrityError):
            with self.database.session() as session:
                session.execute(
                    update(HarnessArtifactRow)
                    .where(HarnessArtifactRow.artifact_id == artifact.artifact_id)
                    .values(artifact_id=f"harness-artifact-{'0' * 32}")
                )
        resolved = self.repository.resolve(request, now=NOW)
        self.assertEqual(resolved.status, HarnessArtifactResolutionStatus.RESOLVED)
        self.assertEqual(resolved.content, b"protected transcript")

        restarted = HarnessArtifactRepository(self.database)
        replayed = restarted.resolve(request, now=NOW + timedelta(minutes=1))
        self.assertEqual(replayed.status, HarnessArtifactResolutionStatus.RESOLVED)
        self.assertEqual(replayed.payload_digest, resolved.payload_digest)
        audit = restarted.list_resolution_audits()[-1]
        self.assertEqual(audit.authorization_outcome.value, "allowed")
        self.assertEqual(audit.resolution_status.value, "resolved")
        self.assertNotIn("protected transcript", audit.model_dump_json())

    def test_digest_verification_never_returns_protected_content(self) -> None:
        artifact, _, request = self._artifact_and_grant(
            permission=HarnessArtifactPermission.VERIFY_DIGEST,
        )
        resolved = self.repository.resolve(request, now=NOW)
        self.assertEqual(resolved.status, HarnessArtifactResolutionStatus.RESOLVED)
        self.assertEqual(resolved.payload_digest, artifact.payload_digest)
        self.assertIsNone(resolved.content)

    def test_deleted_corrupt_and_expired_artifacts_have_typed_results(self) -> None:
        artifact, _, request = self._artifact_and_grant()
        self.assertTrue(self.repository.delete_artifact(artifact_id=artifact.artifact_id, now=NOW))
        self.assertEqual(self.repository.resolve(request, now=NOW).status, HarnessArtifactResolutionStatus.NOT_FOUND)

        artifact, _, request = self._artifact_and_grant()
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER trg_harness_artifacts_immutable_update")
            connection.exec_driver_sql(
                "UPDATE harness_artifacts SET payload = ? WHERE artifact_id = ?",
                (b"corrupt", artifact.artifact_id),
            )
        self.assertEqual(self.repository.resolve(request, now=NOW).status, HarnessArtifactResolutionStatus.DIGEST_MISMATCH)

        _, _, request = self._artifact_and_grant(expires_at=NOW + timedelta(seconds=1))
        self.assertEqual(self.repository.resolve(request, now=NOW + timedelta(seconds=1)).status, HarnessArtifactResolutionStatus.EXPIRED)

    def test_cross_principal_revocation_expiry_and_partial_batch_fail_closed(self) -> None:
        _, grant, request = self._artifact_and_grant()
        with self.database.session() as session:
            session.add(HarnessArtifactPrincipalRow(
                installation_slot="other-installation",
                principal_id=f"local-installation-{'2' * 32}",
                schema_name="HarnessArtifactPrincipal",
                schema_version="harness-artifact-principal-v1",
                created_at="2026-08-31T04:00:00Z",
            ))
            session.flush()
        with self.assertRaises(IntegrityError):
            with self.database.session() as session:
                session.execute(
                    update(HarnessArtifactGrantRow)
                    .where(HarnessArtifactGrantRow.grant_id == grant.grant_id)
                    .values(principal_id=f"local-installation-{'2' * 32}")
                )
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql(
                "DROP TRIGGER trg_harness_artifact_grants_revocation_only"
            )
            connection.exec_driver_sql(
                "UPDATE harness_artifact_grants SET principal_id = ? WHERE grant_id = ?",
                (f"local-installation-{'2' * 32}", grant.grant_id),
            )
        self.assertEqual(self.repository.resolve(request, now=NOW).status, HarnessArtifactResolutionStatus.FORBIDDEN)

        # Restore the server-resolved principal to prove revocation separately.
        with self.database.session() as session:
            session.execute(update(HarnessArtifactGrantRow).where(HarnessArtifactGrantRow.grant_id == grant.grant_id).values(principal_id=grant.subject.principal_id))
        self.assertTrue(self.repository.revoke_grant(grant_id=grant.grant_id, now=NOW))
        self.assertEqual(self.repository.resolve(request, now=NOW + timedelta(seconds=1)).status, HarnessArtifactResolutionStatus.FORBIDDEN)

        artifact, grant, request = self._artifact_and_grant()
        missing = request.model_copy(update={"artifact_id": f"harness-artifact-{'f' * 32}"})
        results = self.repository.resolve_batch((request, missing), now=NOW)
        self.assertEqual([item.status for item in results.results], [HarnessArtifactResolutionStatus.RESOLVED, HarnessArtifactResolutionStatus.FORBIDDEN])
        with self.assertRaisesRegex(ValueError, "batch_size_invalid"):
            self.repository.resolve_batch((), now=NOW)
        with self.assertRaisesRegex(ValueError, "batch_size_invalid"):
            self.repository.resolve_batch((request,) * 65, now=NOW)

        short_grant = self.repository.issue_grant(
            harness_operation_id=OPERATION_ID,
            scopes=(HarnessArtifactGrantScopeV1(artifact_type=artifact.artifact_type, artifact_id=artifact.artifact_id, artifact_contract=CONTRACT, permission=HarnessArtifactPermission.READ),),
            expires_at=NOW + timedelta(seconds=1),
            now=NOW,
        )
        expired_request = request.model_copy(update={"grant_id": short_grant.grant_id})
        self.assertEqual(self.repository.resolve(expired_request, now=NOW + timedelta(seconds=1)).status, HarnessArtifactResolutionStatus.EXPIRED)

    def test_removable_debug_cache_cannot_register_as_replay_artifact(self) -> None:
        with self.assertRaisesRegex(ValueError, "removable_cache_unsupported"):
            self.repository.register_artifact(
                artifact_type=HarnessArtifactType.DOCUMENT_DEBUG,
                artifact_contract=CONTRACT,
                content=b"cache",
                now=NOW,
            )

    def test_corrupt_registered_schema_is_schema_unsupported(self) -> None:
        artifact, _, request = self._artifact_and_grant()
        with self.database.engine.begin() as connection:
            connection.exec_driver_sql("DROP TRIGGER trg_harness_artifacts_immutable_update")
            connection.exec_driver_sql(
                "UPDATE harness_artifacts SET artifact_type = ? WHERE artifact_id = ?",
                ("unsupported_artifact_type", artifact.artifact_id),
            )
        self.assertEqual(
            self.repository.resolve(request, now=NOW).status,
            HarnessArtifactResolutionStatus.SCHEMA_UNSUPPORTED,
        )

    def test_eval_replay_bridge_requires_authorized_resolution(self) -> None:
        artifact, grant, _ = self._artifact_and_grant(
            expires_at=NOW + timedelta(days=7)
        )
        fixture = json.loads(
            (
                Path(__file__).parents[3]
                / "packages/shared/fixtures/harness/eval-contract-golden-v1.json"
            ).read_text(encoding="utf-8")
        )
        case_payload = fixture["case"]
        case_payload["source"] = {
            "source_mode": "protected_artifact",
            "artifact_type": artifact.artifact_type.value,
            "artifact_id": artifact.artifact_id,
            "artifact_contract": CONTRACT.model_dump(mode="json"),
            "payload_digest": artifact.payload_digest,
        }
        case_payload["provenance"] = {
            "source_kind": "production_derived",
            "review_status": "unreviewed",
            "review_contract": None,
            "attestation_digest": None,
        }
        case_payload["sensitivity"] = "protected"
        case_payload["split"] = "development"
        case_payload["case_digest"] = canonical_harness_eval_case_digest(case_payload)
        case = HarnessEvalCaseV1.model_validate(case_payload)
        binding = HarnessOperationBindingV1(
            harness_operation_id=OPERATION_ID,
            domain_operation_kind="tavern_run",
            domain_operation_id="run-artifact-test",
            workflow="tavern",
            entry_stage="actor_reply",
            parent_harness_operation_id=None,
            admitted_at=NOW,
        )
        resolver = HarnessArtifactEvalResolver(
            self.repository,
            lambda _case, _binding: grant.grant_id,
        )

        replay = resolver.resolve(case, binding)
        self.assertEqual(replay.resolution_status, "resolved", replay)
        replay.validate_for(case, binding)
        self.assertEqual(replay.payload, b"protected transcript")

        self.repository.revoke_grant(grant_id=grant.grant_id, now=NOW)
        forbidden = resolver.resolve(case, binding)
        with self.assertRaisesRegex(HarnessEvalRunnerError, "protected_artifact_forbidden"):
            forbidden.validate_for(case, binding)


if __name__ == "__main__":
    unittest.main()
