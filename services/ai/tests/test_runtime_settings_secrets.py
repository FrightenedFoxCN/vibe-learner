import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from app.core.settings import Settings
from app.persistence.models import RuntimeSettingsRow
from app.services.local_store import LocalJsonStore
from app.services.runtime_settings import SECRET_FIELDS, RuntimeSettingsService


class RuntimeSettingsInheritanceTest(TestCase):
    def setUp(self):
        self.store = LocalJsonStore(Path(self.enterContext(TemporaryDirectory())))
        self.addCleanup(self.store.close)

    def test_env_stores_blank_scoped_keys_and_rotation_updates_effective_only(self):
        with (
            patch("app.core.settings._load_dotenv"),
            patch.dict(
                os.environ,
                {"OPENAI_API_KEY": "synthetic-initial", "OPENAI_CHAT_API_KEY": "  "},
                clear=True,
            ),
        ):
            base = Settings.from_env()
        self.assertTrue(all(getattr(base, name) == "" for name in SECRET_FIELDS[1:]))
        service = RuntimeSettingsService(self.store, base)
        for name in SECRET_FIELDS[1:]:
            self.assertEqual(service.describe()[name], "")
            self.assertTrue(service.describe()[f"{name}_configured"])
            self.assertEqual(
                getattr(service.effective_settings(), name), "synthetic-initial"
            )

        saved = service.update({"openai_api_key": "synthetic-rotated"})
        for name in SECRET_FIELDS[1:]:
            self.assertEqual(getattr(saved, name), "")
            self.assertEqual(
                getattr(service.effective_settings(), name), "synthetic-rotated"
            )

        service.update({"openai_api_key": ""})
        for name in SECRET_FIELDS[1:]:
            self.assertFalse(service.describe()[f"{name}_configured"])

    def test_explicit_scoped_values_survive_legacy_upgrade_even_when_equal(self):
        with self.store.database.session() as session:
            session.add(
                RuntimeSettingsRow(
                    config_id="default",
                    payload={
                        "updated_at": "legacy",
                        "openai_api_key": "synthetic-same",
                        "openai_plan_api_key": "synthetic-same",
                        "openai_setting_api_key": "synthetic-other",
                        "openai_chat_api_key": "",
                    },
                )
            )
        service = RuntimeSettingsService(self.store, Settings())
        service.update({"openai_api_key": "synthetic-rotated"})
        self.assertEqual(
            service.effective_settings().openai_plan_api_key, "synthetic-same"
        )
        self.assertEqual(
            service.effective_settings().openai_setting_api_key, "synthetic-other"
        )
        self.assertEqual(
            service.effective_settings().openai_chat_api_key, "synthetic-rotated"
        )

        saved = service.update(
            {"openai_plan_api_key": "  ", "openai_chat_api_key": "synthetic-override"}
        )
        self.assertEqual(saved.openai_plan_api_key, "")
        self.assertEqual(saved.openai_chat_api_key, "synthetic-override")
        second = RuntimeSettingsService(self.store, Settings())
        self.assertEqual(second.describe()["openai_plan_api_key"], "")
        self.assertEqual(
            second.effective_settings().openai_plan_api_key, "synthetic-rotated"
        )
        self.assertEqual(
            second.effective_settings().openai_chat_api_key, "synthetic-override"
        )
