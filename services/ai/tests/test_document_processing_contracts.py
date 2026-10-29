"""DocumentProcessing DTO contracts: no application/container/provider setup."""

import unittest
from app.models import document_processing
from tests.support.harness_contracts import assert_domain_contracts


class DocumentProcessingContractTests(unittest.TestCase):
    def test_schema_and_contract_identity_match_pre_refactor_baseline(self):
        assert_domain_contracts(
            self,
            document_processing,
            added_models=("DocumentProcessInputManifestV2",),
            reviewed_contracts={
                "DOCUMENT_INPUT_CONTRACT": {
                    "name": "DocumentProcessInputManifest",
                    "version": "document-process-input-manifest-v2",
                },
                "DOCUMENT_SNAPSHOT_CONTRACT": {
                    "name": "DocumentProcessProtectedInput",
                    "version": "document-process-protected-input-v2",
                },
                "DOCUMENT_ADAPTER_CONTRACT": {
                    "name": "DocumentProcessWorkflowAdapter",
                    "version": "document-process-workflow-adapter-v2",
                },
            },
        )
