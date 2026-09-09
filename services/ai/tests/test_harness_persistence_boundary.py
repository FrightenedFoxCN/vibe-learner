"""Import-level guard for persistence's narrow transaction interface."""
import subprocess
import sys
import unittest


class HarnessPersistenceBoundaryTests(unittest.TestCase):
    def test_domain_repositories_import_without_application_runtime(self):
        result = subprocess.run([sys.executable, "-c", '''
import importlib.abc
import sys
class RejectApplicationRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"app.services.harness_runtime", "app.services.harness_broad_adoption"}:
            raise AssertionError("persistence imported application runtime: " + fullname)
sys.meta_path.insert(0, RejectApplicationRuntime())
from app.persistence.document_process_operation_repository import DocumentProcessOperationRepository
from app.persistence.learning_plan_operation_repository import LearningPlanOperationRepository
from app.models.harness_runtime_commit import HarnessTransactionFinalizer
'''], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
