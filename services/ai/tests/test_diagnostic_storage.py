from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.diagnostic_routes import router
from app.core.diagnostics import DiagnosticStore
from app.models.diagnostic_storage import DiagnosticStorageV1
from app.services.diagnostic_storage import observe_diagnostic_storage


class DiagnosticStorageTests(unittest.TestCase):
    def test_observation_is_read_only_and_absence_is_not_zero_usage_success(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "missing.db")
            result = observe_diagnostic_storage(store, None)
            self.assertEqual(result.databases[0].gap, "database_absent")
            self.assertEqual(result.databases[1].gap, "not_configured")
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertFalse(result.admission_guarantee)
            self.assertFalse(result.installation_disk_limit_certified)

    def test_budget_state_and_process_counts_do_not_claim_current_admission(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            store.start(); store.emit("lifecycle_started"); store.queue.join(); store.close()
            store.quota.rejected = 7
            store.disk_maintenance.busy = 3
            result = observe_diagnostic_storage(store, None)
            self.assertEqual(result.databases[0].status, "within_observed_limit")
            self.assertEqual(result.databases[0].counters.quota_refusals, 7)
            store.quota.max_bytes = 1
            result = observe_diagnostic_storage(store, None)
            self.assertEqual(result.databases[0].status, "over_observed_limit")
            self.assertEqual(result.databases[0].counters.maintenance_busy, 3)

    def test_filesystem_failure_is_explicit_and_never_echoes_paths(self):
        with TemporaryDirectory() as directory:
            store = DiagnosticStore(Path(directory) / "events.db")
            app = FastAPI(); app.state.diagnostics = store; app.include_router(router)
            with TestClient(app) as client, patch.object(store.quota, "sizes", side_effect=OSError("PRIVATE_PATH")):
                response = client.get("/diagnostics/storage")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.json()["databases"][0]["gap"], "filesystem_unavailable")
                self.assertNotIn("PRIVATE", response.text)
            with TestClient(app) as client, patch.object(store.quota, "sizes", return_value={"PRIVATE_FIELD": 1}):
                response = client.get("/diagnostics/storage")
                self.assertEqual(response.status_code, 503)
                self.assertNotIn("PRIVATE", response.text)

    def test_shared_schema_and_sample_match_backend(self):
        root = Path(__file__).parents[3] / "packages/shared/fixtures/diagnostics"
        self.assertEqual(json.loads((root / "storage-schema-v1.json").read_text()), DiagnosticStorageV1.model_json_schema())
        DiagnosticStorageV1.model_validate_json((root / "storage-sample-v1.json").read_text())
