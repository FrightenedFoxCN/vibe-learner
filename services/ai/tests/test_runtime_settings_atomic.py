from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier, Event
from unittest import TestCase
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import event

from app.core.settings import Settings
from app.persistence.database import Database
from app.persistence.models import RuntimeSettingsRow
from app.persistence.runtime_settings_repository import RuntimeSettingsRepository
from app.persistence.storage import StorageManager
from app.services.local_store import LocalJsonStore
from app.services.runtime_settings import RuntimeSettingsService


class RuntimeSettingsAtomicTest(TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        database_url = f"sqlite:///{root / 'settings.sqlite'}"
        a = Database(database_url)
        a.create_schema()
        b = Database(database_url)
        self.store_a = LocalJsonStore(a, StorageManager(root / "a"))
        self.store_b = LocalJsonStore(b, StorageManager(root / "b"))
        self.addCleanup(self.store_a.close)
        self.addCleanup(self.store_b.close)

    def test_existing_process_reads_fresh_and_parallel_sparse_patches_merge(self):
        one = RuntimeSettingsService(self.store_a, Settings())
        two = RuntimeSettingsService(self.store_b, Settings())
        first_version, first_settings = two.effective_snapshot()
        writer_one_read = Event()
        writer_two_attempted = Event()
        allow_first_commit = Event()

        candidate = RuntimeSettingsRepository._commit_candidate

        def hold_first_candidate(payload, *, revision):
            if (
                payload.get("openai_chat_model") == "writer-one"
                and revision == first_version.revision + 1
            ):
                writer_one_read.set()
                if not allow_first_commit.wait(timeout=4):
                    raise AssertionError("first writer was not released")
            return candidate(payload, revision=revision)

        def observe_second_write(
            conn, cursor, statement, parameters, context, executemany
        ):
            if statement.startswith("UPDATE runtime_settings"):
                writer_two_attempted.set()

        engine = self.store_b.database.engine
        event.listen(engine, "before_cursor_execute", observe_second_write)
        try:
            with (
                patch.object(
                    RuntimeSettingsRepository,
                    "_commit_candidate",
                    staticmethod(hold_first_candidate),
                ),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                first = pool.submit(one.update, {"openai_chat_model": "writer-one"})
                try:
                    self.assertTrue(writer_one_read.wait(timeout=4))
                    second = pool.submit(
                        two.update, {"openai_plan_model": "writer-two"}
                    )
                    self.assertTrue(writer_two_attempted.wait(timeout=4))
                finally:
                    allow_first_commit.set()
                self.assertEqual(
                    first.result(timeout=5).revision, first_version.revision + 1
                )
                self.assertEqual(
                    second.result(timeout=5).revision, first_version.revision + 2
                )
        finally:
            event.remove(engine, "before_cursor_execute", observe_second_write)
        first_view = one.effective_snapshot()
        self.assertEqual(first_view, two.effective_snapshot())
        version, settings = first_view
        self.assertEqual(version.revision, first_version.revision + 2)
        self.assertEqual(settings.openai_chat_model, "writer-one")
        self.assertEqual(settings.openai_plan_model, "writer-two")
        self.assertNotEqual(
            first_settings.openai_chat_model, settings.openai_chat_model
        )
        self.assertEqual(one.describe()["openai_plan_model"], "writer-two")
        self.assertEqual(two.update({}).revision, version.revision)

    def test_first_start_is_one_atomic_insert(self):
        start = Barrier(2, timeout=4)

        def initialize(store, model):
            start.wait()
            return RuntimeSettingsService(store, Settings(openai_plan_model=model))

        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(initialize, self.store_a, "first-default")
            b = pool.submit(initialize, self.store_b, "second-default")
            left = a.result(timeout=6).effective_snapshot()
            right = b.result(timeout=6).effective_snapshot()
        self.assertEqual(left, right)
        self.assertEqual(left[0].revision, 1)
        self.assertIn(left[1].openai_plan_model, {"first-default", "second-default"})
        self.assertEqual(self.store_a.count_bucket("runtime_settings"), 1)

    def test_desktop_secrets_have_a_distinct_local_generation(self):
        settings = Settings(desktop_mode=True)
        one = RuntimeSettingsService(self.store_a, settings)
        two = RuntimeSettingsService(self.store_b, settings)
        old_version, old_settings = one.effective_snapshot()
        one.apply_session_secrets({"openai_api_key": "synthetic-session-key"})
        new_version, new_settings = one.effective_snapshot()
        self.assertEqual(new_version.revision, old_version.revision)
        self.assertEqual(
            new_version.session_generation, old_version.session_generation + 1
        )
        self.assertEqual(new_settings.openai_chat_api_key, "synthetic-session-key")
        self.assertEqual(old_settings.openai_chat_api_key, "")
        self.assertEqual(two.effective_snapshot(), (old_version, old_settings))
        one.clear_session_secrets()
        self.assertEqual(one.effective_settings().openai_api_key, "")
        self.assertEqual(
            one.effective_snapshot()[0].session_generation,
            new_version.session_generation + 1,
        )

    def test_versioned_database_rows_are_strict_on_every_read(self):
        service = RuntimeSettingsService(self.store_a, Settings())
        service.update({"openai_plan_model": "unchanged"})
        with self.store_b.database.session() as session:
            row = session.get(RuntimeSettingsRow, "default")
            row.payload = row.payload | {"openai_timeout_seconds": "30"}
        with self.assertRaises(ValidationError):
            service.effective_snapshot()
        with self.assertRaises(ValidationError):
            service.describe()
        with self.assertRaises(ValidationError):
            RuntimeSettingsService(self.store_a, Settings())
