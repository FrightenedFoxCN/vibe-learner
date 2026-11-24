from unittest import TestCase

from app.core.settings import Settings
from app.services.model_tool_config import ModelToolConfigService
from app.services.runtime_settings import RuntimeSettingsService


class FakeStore:
    def __init__(self):
        self.records = {}
        self.fail = False

    def load_item(self, category, item_id, record_type):
        return self.records.get((category, item_id))

    def load_runtime_settings_payload(self):
        record = self.records.get(("runtime_settings", "default"))
        return record.model_dump() if record is not None else None

    def save_item(self, category, item_id, record):
        if self.fail:
            raise OSError("synthetic write failure")
        self.records[category, item_id] = record


class RuntimeConfigPersistenceTest(TestCase):
    def test_runtime_settings_only_publish_after_save(self):
        store = FakeStore()
        base = Settings()
        settings = RuntimeSettingsService(store, base)
        previous = settings.describe()
        store.fail = True
        with self.assertRaises(OSError):
            settings.update({"openai_plan_model": "synthetic-model"})
        self.assertEqual(settings.describe(), previous)
        self.assertEqual(RuntimeSettingsService(store, base).describe(), previous)
        store.fail = False
        settings.update({"openai_plan_model": "synthetic-model"})
        self.assertEqual(
            settings.effective_settings().openai_plan_model, "synthetic-model"
        )

    def test_tool_config_only_publishes_after_save(self):
        store = FakeStore()
        config = ModelToolConfigService(store)
        before = config.describe()
        stage = "plan_generation"
        tool = config.list_stage_tools(stage)[0]
        updates = [{"stage_name": stage, "tool_name": tool, "enabled": False}]
        store.fail = True
        with self.assertRaises(OSError):
            config.update(updates)
        self.assertEqual(config.describe(), before)
        self.assertEqual(ModelToolConfigService(store).describe(), before)
        store.fail = False
        config.update(updates)
        self.assertIn(tool, config.disabled_tools_for_stage(stage))
