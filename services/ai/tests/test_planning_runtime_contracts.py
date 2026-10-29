"""PlanningRuntime DTO contracts: no application/container/provider setup."""

import unittest
from app.models import planning_runtime
from tests.support.harness_contracts import assert_domain_contracts


class PlanningRuntimeContractTests(unittest.TestCase):
    def test_schema_and_contract_identity_match_pre_refactor_baseline(self):
        assert_domain_contracts(
            self,
            planning_runtime,
            added_models=("LearningPlanRuntimeOutputV2",),
            reviewed_contracts={
                "PLAN_PROMPT_CONTRACT": {
                    "name": "LearningPlanPrompt",
                    "version": "planning-prompt-v8",
                },
                "PLAN_ADAPTER_CONTRACT": {
                    "name": "LearningPlanWorkflowAdapter",
                    "version": "learning-plan-workflow-adapter-v2",
                },
                "PLAN_TRACE_CONTRACT": {
                    "name": "LearningPlanRuntimeOutput",
                    "version": "learning-plan-runtime-output-v2",
                },
            },
            reviewed_schema_digests={
                # Includes reviewed Document CAS and strict application language-tag
                # input constraints; model-owned output identity remains unchanged.
                "LearningPlanRuntimeOutputV1": "4fa27aee3a3d51fda1288c7d4d471d70110ca7f26f68512ff73b920655ad7e63",
            },
        )
