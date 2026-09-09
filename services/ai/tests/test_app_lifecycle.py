"""Production lifespan contracts, separate from route/domain fault tests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.persistence.database import Database


class AppLifecycleTests(unittest.TestCase):
    def settings(self, name="app"):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        return Settings(database_url=f"sqlite:///{root / (name + '.db')}", storage_root=str(root / "data"), ocr_engine="disabled")

    def test_import_and_app_factory_never_initialize_database(self):
        result = subprocess.run([sys.executable, "-c", '''
from unittest.mock import patch
from app.persistence.database import Database
with patch.object(Database, "__init__", side_effect=AssertionError("import opened database")):
    import app.core.bootstrap
    import app.api.routes
    import app.api.tavern_routes
    import app.main
    from app.app_factory import create_app
    first, second = create_app(), create_app()
    assert first is not second
'''], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_two_live_app_instances_have_independent_databases_and_settings(self):
        first = create_app(settings=self.settings("first"))
        second = create_app(settings=self.settings("second"))
        with TestClient(first) as a, TestClient(second) as b:
            ca, cb = first.state.container, second.state.container
            self.assertNotEqual(ca.database.url, cb.database.url)
            before = b.get("/runtime-settings").json()
            response = a.patch("/runtime-settings", json={"openai_chat_model": "first-only"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(a.get("/runtime-settings").json()["openai_chat_model"], "first-only")
            self.assertEqual(b.get("/runtime-settings").json(), before)
            stream = ca.stream_interrupt_registry.create(stream_kind="test", target_id="test")
            with patch.object(ca.database, "dispose", wraps=ca.database.dispose) as dispose:
                # Explicitly test idempotent resource release too.
                ca.close()
                ca.close()
                dispose.assert_called_once()
            self.assertTrue(stream.cancelled())
        self.assertIsNone(first.state.container)
        self.assertIsNone(second.state.container)
        self.assertTrue(cb._closed)

    def test_recovery_runs_only_at_explicit_start_once(self):
        with (
            patch("app.core.bootstrap.HarnessWorkflowOperationRepository.recover_abandoned_operations", return_value=0) as workflow,
            patch("app.core.bootstrap.DocumentService.recover_abandoned_operations") as document,
            patch("app.core.bootstrap.LearningPlanService.recover_abandoned_operations") as plan,
        ):
            container = Container(self.settings())
            self.addCleanup(container.close)
            workflow.assert_not_called()
            document.assert_not_called()
            plan.assert_not_called()
            container.start()
            container.start()
        workflow.assert_called_once()
        document.assert_called_once()
        plan.assert_called_once()

    def test_lifespan_orders_start_and_close_and_cleans_up_on_recovery_failure(self):
        calls = []
        container = Mock()
        container.start.side_effect = lambda: calls.append("start")
        container.close.side_effect = lambda: calls.append("close")
        app = create_app(settings=self.settings(), container_factory=lambda settings: container)
        self.assertEqual(calls, [])
        with TestClient(app):
            self.assertIs(app.state.container, container)
            self.assertEqual(calls, ["start"])
        self.assertEqual(calls, ["start", "close"])
        container.start.side_effect = RuntimeError("recovery failed")
        with self.assertRaisesRegex(RuntimeError, "recovery failed"):
            with TestClient(app):
                pass
        self.assertIsNone(app.state.container)
        self.assertEqual(container.close.call_count, 2)

    def test_logging_precedes_database_and_partial_initialization_disposes_it(self):
        calls = []
        original_init = Database.__init__
        def initialize(database, url):
            calls.append("database")
            original_init(database, url)
        with (
            patch("app.core.bootstrap.configure_logging", side_effect=lambda: calls.append("logging")),
            patch.object(Database, "__init__", initialize),
            patch.object(Database, "create_schema", side_effect=RuntimeError("schema failed")),
            patch.object(Database, "dispose", autospec=True) as dispose,
        ):
            with self.assertRaisesRegex(RuntimeError, "schema failed"):
                Container(self.settings())
        self.assertEqual(calls, ["logging", "database"])
        dispose.assert_called_once()
