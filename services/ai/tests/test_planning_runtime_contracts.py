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
                    "version": "planning-prompt-v7",
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
                # Document CAS adds optional revision to the nested Document schema;
                # revision zero still serializes exactly as the historical payload.
                "LearningPlanRuntimeOutputV1": "ea126d324a408395b4c2b587718cf0ac6b9f7822bd7915d5b1ebb4a235fa7768",
            },
        )
