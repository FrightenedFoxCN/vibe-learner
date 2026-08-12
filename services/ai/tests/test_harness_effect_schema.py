from __future__ import annotations

import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from app.models.harness import HarnessResourceType
from app.models.harness_effect import (
    HarnessEffectAdapterRefV1,
    HarnessEffectBoundaryKind,
    HarnessEffectCommitPolicy,
    HarnessEffectCompensationPolicy,
    HarnessEffectPreparePolicy,
    HarnessEffectReadBackPolicy,
    HarnessEffectTargetRefV1,
    HarnessPreparedEffectBatchV1,
    HarnessPreparedEffectV1,
    harness_effect_adapter_policy_registry_snapshot,
)
from app.models.study_chat_effect import (
    STUDY_PLAN_CONFIRMATION_ADAPTER,
    STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
)


class HarnessEffectSchemaTests(unittest.TestCase):
    def test_adapter_registry_matches_shared_golden(self) -> None:
        fixture = json.loads(
            (
                Path(__file__).parents[3]
                / "packages/shared/fixtures/harness/effect-adapter-policies-v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(harness_effect_adapter_policy_registry_snapshot(), fixture)

    def test_domain_proposal_rejects_application_owned_fields(self) -> None:
        with self.assertRaises(ValidationError):
            StudyPlanConfirmationEffectProposalV1.model_validate(
                {
                    "action": "update_plan",
                    "course_title": "New",
                    "plan_id": "model-owned-plan-id",
                }
            )

    def test_prepared_effect_rejects_pure_read_and_noncontiguous_batch(self) -> None:
        proposal = StudyPlanConfirmationEffectProposalV1(
            action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
            course_title="New",
        )
        pure_read = STUDY_PLAN_CONFIRMATION_ADAPTER.model_copy(
            update={"boundary_kind": HarnessEffectBoundaryKind.PURE_READ}
        )
        with self.assertRaisesRegex(ValidationError, "pure_read_forbidden"):
            HarnessPreparedEffectV1[StudyPlanConfirmationEffectProposalV1](
                operation_id="operation-1",
                effect_batch_id="batch-1",
                effect_id="effect-1",
                slot=0,
                adapter=pure_read,
                proposal_contract=STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
                target_refs=[
                    HarnessEffectTargetRefV1(
                        resource_type=HarnessResourceType.STUDY_SESSION,
                        resource_id="session-1",
                    )
                ],
                proposal=proposal,
            )
        effect = HarnessPreparedEffectV1[StudyPlanConfirmationEffectProposalV1](
            operation_id="operation-1",
            effect_batch_id="batch-1",
            effect_id="effect-1",
            slot=1,
            adapter=STUDY_PLAN_CONFIRMATION_ADAPTER,
            proposal_contract=STUDY_PLAN_CONFIRMATION_PROPOSAL_CONTRACT,
            target_refs=[
                HarnessEffectTargetRefV1(
                    resource_type=HarnessResourceType.STUDY_SESSION,
                    resource_id="session-1",
                )
            ],
            proposal=proposal,
        )
        with self.assertRaisesRegex(ValidationError, "slots_not_contiguous"):
            HarnessPreparedEffectBatchV1[StudyPlanConfirmationEffectProposalV1](
                operation_id="operation-1",
                effect_batch_id="batch-1",
                effects=[effect],
            )


if __name__ == "__main__":
    unittest.main()
