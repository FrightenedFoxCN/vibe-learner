from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from app.models.harness import HarnessArtifactType, HarnessContractRef
from app.models.harness_artifact_access import (
    HarnessArtifactAccessAuditV1,
    HarnessArtifactAccessCasesV1,
    HarnessArtifactAccessGoldenV1,
    HarnessArtifactAccessOutcome,
    HarnessArtifactGrantScopeV1,
    HarnessArtifactGrantV1,
    HarnessArtifactPermission,
    HarnessArtifactPrincipalV1,
    authorize_harness_artifact_access,
    harness_artifact_access_contract_registry_snapshot,
)


FIXTURE = (
    Path(__file__).parents[3]
    / "packages"
    / "shared"
    / "fixtures"
    / "harness"
    / "artifact-access-contract-registry-v1.json"
)
CASE_FIXTURE = FIXTURE.with_name("artifact-access-cases-v1.json")
GOLDEN_FIXTURE = FIXTURE.with_name("artifact-access-golden-v1.json")
NOW = datetime(2026, 8, 25, 3, 0, tzinfo=timezone.utc)
CONTRACT = HarnessContractRef(
    name="TavernTranscriptSnapshot",
    version="tavern-transcript-snapshot-v1",
)
HARNESS_OPERATION_ID = f"harness-operation-{'b' * 32}"


def _principal(suffix: str = "0") -> HarnessArtifactPrincipalV1:
    return HarnessArtifactPrincipalV1(
        principal_id=f"local-installation-{suffix * 32}",
    )


def _scope(
    *,
    artifact_id: str = "transcript-1",
    permission: HarnessArtifactPermission = HarnessArtifactPermission.READ,
) -> HarnessArtifactGrantScopeV1:
    return HarnessArtifactGrantScopeV1(
        artifact_type=HarnessArtifactType.TAVERN_TRANSCRIPT,
        artifact_id=artifact_id,
        artifact_contract=CONTRACT,
        permission=permission,
    )


def _grant(**overrides: object) -> HarnessArtifactGrantV1:
    payload: dict[str, object] = {
        "grant_id": f"harness-artifact-grant-{'a' * 32}",
        "harness_operation_id": HARNESS_OPERATION_ID,
        "subject": _principal(),
        "scopes": (
            _scope(),
            _scope(permission=HarnessArtifactPermission.VERIFY_DIGEST),
        ),
        "issued_at": NOW - timedelta(minutes=5),
        "expires_at": NOW + timedelta(minutes=5),
        "revoked_at": None,
    }
    payload.update(overrides)
    return HarnessArtifactGrantV1.model_validate(payload)


def _authorize(
    *,
    principal: HarnessArtifactPrincipalV1 | None = None,
    grant: HarnessArtifactGrantV1 | None = None,
    evaluated_at: datetime = NOW,
    artifact_id: str = "transcript-1",
    contract: HarnessContractRef = CONTRACT,
    permission: HarnessArtifactPermission = HarnessArtifactPermission.READ,
    harness_operation_id: str = HARNESS_OPERATION_ID,
):
    return authorize_harness_artifact_access(
        principal=_principal() if principal is None else principal,
        grant=grant or _grant(),
        harness_operation_id=harness_operation_id,
        artifact_type=HarnessArtifactType.TAVERN_TRANSCRIPT,
        artifact_id=artifact_id,
        artifact_contract=contract,
        permission=permission,
        evaluated_at=evaluated_at,
    )


class HarnessArtifactAccessTests(unittest.TestCase):
    def test_python_and_shared_contract_registry_match(self) -> None:
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(harness_artifact_access_contract_registry_snapshot(), expected)

    def test_versioned_authorization_cases_prove_fail_closed_boundary(self) -> None:
        fixture = HarnessArtifactAccessCasesV1.model_validate_json(
            CASE_FIXTURE.read_text(encoding="utf-8")
        )

        for case in fixture.cases:
            with self.subTest(case_id=case.case_id):
                principal_id = case.presented_principal_id
                principal = (
                    HarnessArtifactPrincipalV1(principal_id=principal_id)
                    if principal_id is not None
                    else None
                )
                grant = _grant(
                    harness_operation_id=fixture.grant_harness_operation_id,
                    expires_at=case.grant_expires_at,
                    revoked_at=case.grant_revoked_at,
                )
                audit = authorize_harness_artifact_access(
                    principal=principal,
                    grant=grant,
                    harness_operation_id=case.harness_operation_id,
                    artifact_type=HarnessArtifactType.TAVERN_TRANSCRIPT,
                    artifact_id=case.artifact_id,
                    artifact_contract=CONTRACT,
                    permission=HarnessArtifactPermission.READ,
                    evaluated_at=case.evaluated_at,
                )
                self.assertEqual(audit.outcome, case.expected_outcome)

    def test_cross_language_golden_wire_decodes_strictly(self) -> None:
        golden = HarnessArtifactAccessGoldenV1.model_validate_json(
            GOLDEN_FIXTURE.read_text(encoding="utf-8")
        )
        self.assertEqual(golden.grant.scopes[0].artifact_id, "transcript-1")
        self.assertTrue(golden.allowed_audit.allowed)

        forged = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
        forged["grant"]["access_token"] = "secret"
        with self.assertRaises(ValidationError):
            HarnessArtifactAccessGoldenV1.model_validate(forged)

        offset_wire = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
        offset_wire["grant"]["issued_at"] = "2026-08-25T10:55:00+08:00"
        with self.assertRaisesRegex(ValidationError, "wire_must_be_utc_z"):
            HarnessArtifactAccessGoldenV1.model_validate(offset_wire)

        forged_allowed = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))[
            "allowed_audit"
        ]
        forged_allowed["grant_harness_operation_id"] = (
            f"harness-operation-{'c' * 32}"
        )
        with self.assertRaisesRegex(ValidationError, "allowed_identity_mismatch"):
            HarnessArtifactAccessAuditV1.model_validate_json(
                json.dumps(forged_allowed)
            )

    def test_same_local_installation_principal_is_allowed_for_exact_scope(self) -> None:
        audit = _authorize()

        self.assertEqual(audit.outcome, HarnessArtifactAccessOutcome.ALLOWED)
        self.assertTrue(audit.allowed)
        self.assertEqual(audit.presented_principal_id, _principal().principal_id)
        serialized = audit.model_dump(mode="json")
        self.assertNotIn("token", serialized)
        self.assertNotIn("secret", serialized)

    def test_missing_principal_fails_closed(self) -> None:
        audit = authorize_harness_artifact_access(
            principal=None,
            grant=_grant(),
            harness_operation_id=HARNESS_OPERATION_ID,
            artifact_type=HarnessArtifactType.TAVERN_TRANSCRIPT,
            artifact_id="transcript-1",
            artifact_contract=CONTRACT,
            permission=HarnessArtifactPermission.READ,
            evaluated_at=NOW,
        )

        self.assertEqual(
            audit.outcome,
            HarnessArtifactAccessOutcome.PRINCIPAL_REQUIRED,
        )
        self.assertFalse(audit.allowed)
        self.assertIsNone(audit.presented_principal_id)

    def test_cross_principal_and_scope_rebinding_are_forbidden(self) -> None:
        cross_principal = _authorize(principal=_principal("1"))
        wrong_artifact = _authorize(artifact_id="transcript-2")
        wrong_contract = _authorize(
            contract=HarnessContractRef(
                name=CONTRACT.name,
                version="tavern-transcript-snapshot-v2",
            )
        )
        wrong_operation = _authorize(
            harness_operation_id=f"harness-operation-{'c' * 32}"
        )

        self.assertEqual(cross_principal.outcome, HarnessArtifactAccessOutcome.FORBIDDEN)
        self.assertEqual(wrong_artifact.outcome, HarnessArtifactAccessOutcome.FORBIDDEN)
        self.assertEqual(wrong_contract.outcome, HarnessArtifactAccessOutcome.FORBIDDEN)
        self.assertEqual(wrong_operation.outcome, HarnessArtifactAccessOutcome.FORBIDDEN)

    def test_revoked_expired_and_not_yet_active_grants_are_distinct(self) -> None:
        revoked = _authorize(grant=_grant(revoked_at=NOW - timedelta(seconds=1)))
        expired = _authorize(grant=_grant(expires_at=NOW))
        not_active = _authorize(
            grant=_grant(
                issued_at=NOW + timedelta(minutes=1),
                expires_at=NOW + timedelta(minutes=2),
            )
        )

        self.assertEqual(revoked.outcome, HarnessArtifactAccessOutcome.REVOKED)
        self.assertEqual(expired.outcome, HarnessArtifactAccessOutcome.EXPIRED)
        self.assertEqual(not_active.outcome, HarnessArtifactAccessOutcome.GRANT_NOT_ACTIVE)

    def test_grant_requires_sorted_unique_exact_scopes_and_utc_lifecycle(self) -> None:
        reversed_scopes = (
            _scope(permission=HarnessArtifactPermission.VERIFY_DIGEST),
            _scope(),
        )
        with self.assertRaisesRegex(
            ValidationError,
            "harness_artifact_grant_scopes_not_sorted",
        ):
            _grant(scopes=reversed_scopes)

        with self.assertRaisesRegex(
            ValidationError,
            "harness_artifact_grant_scope_duplicate",
        ):
            _grant(scopes=(_scope(), _scope()))

        with self.assertRaisesRegex(
            ValidationError,
            "harness_artifact_grant_timestamp_must_be_utc",
        ):
            _grant(
                issued_at=NOW.astimezone(timezone(timedelta(hours=8))),
            )

        with self.assertRaisesRegex(
            ValidationError,
            "harness_artifact_grant_expiry_invalid",
        ):
            _grant(expires_at=NOW - timedelta(minutes=6))

    def test_contracts_reject_bearer_material_and_unknown_fields(self) -> None:
        grant = _grant()
        with self.assertRaises(ValidationError):
            grant.expires_at = NOW + timedelta(hours=1)  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            grant.scopes.append(_scope(artifact_id="transcript-2"))  # type: ignore[attr-defined]

        payload = _grant().model_dump(mode="json")
        forged = deepcopy(payload)
        forged["access_token"] = "secret"
        with self.assertRaises(ValidationError):
            HarnessArtifactGrantV1.model_validate(forged)

        principal = _principal().model_dump(mode="json")
        principal["api_key"] = "secret"
        with self.assertRaises(ValidationError):
            HarnessArtifactPrincipalV1.model_validate(principal)

        with self.assertRaisesRegex(
            ValidationError,
            "harness_contract_version_not_adopted",
        ):
            HarnessArtifactGrantScopeV1(
                artifact_type=HarnessArtifactType.TAVERN_TRANSCRIPT,
                artifact_id="transcript-1",
                artifact_contract=HarnessContractRef(
                    name="TavernTranscriptSnapshot",
                    version="pending-v1",
                ),
                permission=HarnessArtifactPermission.READ,
            )


if __name__ == "__main__":
    unittest.main()
