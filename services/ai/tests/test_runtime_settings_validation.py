import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_container
from app.api.routers.system import router
from app.core.model_runtime_limits import browser_model_runtime_config_snapshot
from app.core.runtime_settings_validation import NUMERIC_FIELDS
from app.core.settings import Settings
from app.models.api import RuntimeSettingsResponse, UpdateRuntimeSettingsRequest
from app.models.domain import RuntimeSettingsRecord
from app.persistence.migrate_local_data import migrate_from_legacy_store
from app.persistence.models import RuntimeSettingsRow
from app.services.local_store import LegacyLocalJsonStore, LocalJsonStore
from app.services.runtime_settings import RuntimeSettingsService
from app.services.token_usage import TokenUsageService


class RuntimeSettingsValidationTest(TestCase):
    def setUp(self):
        root = Path(self.enterContext(TemporaryDirectory()))
        self.store = LocalJsonStore(root / "db")
        self.addCleanup(self.store.close)
        self.legacy = LegacyLocalJsonStore(root / "old")

    def test_shared_numeric_contract_at_all_boundaries(self):
        specification = browser_model_runtime_config_snapshot()
        service = RuntimeSettingsService(self.store, Settings())
        valid_response = service.describe()
        with (
            patch("app.core.settings._load_dotenv"),
            patch.dict(os.environ, {}, clear=True),
        ):
            for field, (_, default) in NUMERIC_FIELDS.items():
                bounds = specification[field.removeprefix("openai_")]
                low, high = bounds["min"], bounds["max"]
                for accepted in (low, high, default):
                    with self.subTest(field=field, accepted=accepted):
                        os.environ[field.upper()] = str(accepted)
                        self.assertEqual(getattr(Settings.from_env(), field), accepted)
                        patch_model = UpdateRuntimeSettingsRequest.model_validate(
                            {field: accepted}
                        )
                        service.update(patch_model.model_dump(exclude_unset=True))
                        self.assertEqual(service.describe()[field], accepted)
                        self.assertEqual(
                            getattr(service.effective_settings(), field), accepted
                        )
                invalid = [
                    True,
                    str(default),
                    None,
                    low - 1,
                    high + 1,
                    float("nan"),
                    float("inf"),
                ]
                if type(default) is int:
                    invalid.extend([float(default), low + 0.5])
                for value in invalid:
                    with self.subTest(field=field, rejected=value):
                        for model, data in (
                            (UpdateRuntimeSettingsRequest, {field: value}),
                            (
                                RuntimeSettingsRecord,
                                {"updated_at": "synthetic", field: value},
                            ),
                            (RuntimeSettingsResponse, valid_response | {field: value}),
                        ):
                            with self.assertRaises(ValidationError):
                                model.model_validate(data)
                        with self.assertRaisesRegex(ValueError, f"invalid_{field}"):
                            service.update({field: value})
                for text in ("", "garbage", "nan", "Infinity", str(high + 1)):
                    os.environ[field.upper()] = text
                    with self.assertRaisesRegex(ValueError, field.upper()):
                        Settings.from_env()
                if type(default) is int:
                    os.environ[field.upper()] = f"{default}.0"
                    with self.assertRaisesRegex(ValueError, field.upper()):
                        Settings.from_env()
                del os.environ[field.upper()]
            self.assertEqual(
                Settings.from_env(),
                Settings(database_url=Settings.from_env().database_url),
            )

    def test_database_legacy_repair_resets_only_invalid_numbers(self):
        initial = RuntimeSettingsRecord(
            updated_at="old", openai_plan_model="custom"
        ).model_dump()
        initial.update(
            openai_chat_temperature=float("nan"),
            openai_chat_max_tokens="800",
            openai_chat_history_messages=True,
        )
        with self.store.database.session() as session:
            session.add(RuntimeSettingsRow(config_id="default", payload=initial))
        with self.assertLogs(
            "app.core.runtime_settings_validation", level="WARNING"
        ) as logs:
            service = RuntimeSettingsService(
                self.store, Settings(openai_chat_max_tokens=1111)
            )
        self.assertEqual(len(logs.output), 3)
        effective = service.effective_settings()
        self.assertEqual(effective.openai_plan_model, "custom")
        self.assertEqual(
            effective.openai_chat_max_tokens, Settings().openai_chat_max_tokens
        )
        self.assertEqual(
            effective.openai_chat_temperature, Settings().openai_chat_temperature
        )
        self.assertEqual(
            effective.openai_chat_history_messages,
            Settings().openai_chat_history_messages,
        )
        with self.store.database.session() as session:
            stored = session.get(RuntimeSettingsRow, "default").payload
        self.assertEqual(
            RuntimeSettingsRecord.model_validate(stored).openai_plan_model, "custom"
        )

    def test_legacy_json_import_resets_invalid_field_without_overwriting_existing_db(
        self,
    ):
        source = self.legacy.validate_item_path("runtime_settings", "default")
        source.parent.mkdir()
        source.write_text(
            '{"updated_at":"old","openai_timeout_seconds":1.5,"openai_chat_model":"legacy-model"}'
        )

        def migrate():
            migrate_from_legacy_store(
                self.legacy,
                self.store,
                TokenUsageService(self.store.database),
                self.legacy.root,
            )

        with self.assertLogs("app.core.runtime_settings_validation", level="WARNING"):
            migrate()
        service = RuntimeSettingsService(self.store, Settings())
        self.assertEqual(
            service.describe()["openai_timeout_seconds"],
            Settings().openai_timeout_seconds,
        )
        self.assertEqual(service.describe()["openai_chat_model"], "legacy-model")
        service.update({"openai_chat_model": "committed"})
        migrate()
        self.assertEqual(
            RuntimeSettingsService(self.store, Settings()).describe()[
                "openai_chat_model"
            ],
            "committed",
        )

    def test_runtime_patch_rejects_nonfinite_json_and_does_not_echo_raw_input(self):
        service = RuntimeSettingsService(self.store, Settings())

        class Fixture:
            runtime_settings_service = service
            update_runtime_settings = staticmethod(service.update)

        application = FastAPI()
        application.include_router(router)
        application.dependency_overrides[get_container] = Fixture
        client = self.enterContext(TestClient(application))
        before = client.get("/runtime-settings").json()
        for raw in (
            "NaN",
            "Infinity",
            "-Infinity",
            "1e900",
            "true",
            '"bad-value"',
            "null",
        ):
            with self.subTest(raw=raw):
                response = client.patch(
                    "/runtime-settings",
                    content='{"openai_chat_temperature": ' + raw + "}",
                    headers={"content-type": "application/json"},
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(
                    response.json()["detail"][0]["loc"],
                    ["body", "openai_chat_temperature"],
                )
                self.assertNotIn("input", response.json()["detail"][0])
        self.assertEqual(client.get("/runtime-settings").json(), before)
        accepted = client.patch(
            "/runtime-settings", json={"openai_chat_temperature": 1}
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["openai_chat_temperature"], 1)
