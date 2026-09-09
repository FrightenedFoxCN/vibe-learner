"""PlanningRuntime DTO contracts: no application/container/provider setup."""
import unittest
from app.models import planning_runtime
from tests.support.harness_contracts import assert_domain_contracts


class PlanningRuntimeContractTests(unittest.TestCase):
    def test_schema_and_contract_identity_match_pre_refactor_baseline(self):
        assert_domain_contracts(self, planning_runtime)
