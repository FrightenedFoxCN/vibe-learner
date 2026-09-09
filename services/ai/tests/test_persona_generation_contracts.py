"""PersonaGeneration DTO contracts: no application/container/provider setup."""
import unittest
from app.models import persona_generation
from tests.support.harness_contracts import assert_domain_contracts


class PersonaGenerationContractTests(unittest.TestCase):
    def test_schema_and_contract_identity_match_pre_refactor_baseline(self):
        assert_domain_contracts(self, persona_generation)
