from types import SimpleNamespace
from unittest import TestCase

from app.api.routers.system import get_model_tool_config
from app.services.model_tool_config import ModelToolConfigService


class FakeStore:
    def load_item(self, *args):
        return None

    def save_item(self, *args):
        pass


class ToolAuditTest(TestCase):
    def test_each_stage_reports_only_its_own_multimodal_switch(self):
        config = ModelToolConfigService(FakeStore())
        for plan_enabled, chat_enabled in [(True, False), (False, True)]:
            container = SimpleNamespace(
                model_tool_config_service=config,
                capture_model_provider=lambda: SimpleNamespace(
                    supports_page_image_tools=lambda: plan_enabled,
                    supports_chat_page_image_tools=lambda: chat_enabled,
                ),
            )
            response = get_model_tool_config(container=container)
            for stage, prefix, enabled in [
                ("plan_generation", "plan", plan_enabled),
                ("study_chat", "chat", chat_enabled),
            ]:
                tools = next(
                    item.tools for item in response.stages if item.name == stage
                )
                tool = next(
                    item for item in tools if item.name == "read_page_range_images"
                )
                self.assertEqual(tool.available, enabled)
                self.assertEqual(
                    [basis for basis in tool.audit_basis if "multimodal=" in basis],
                    [f"{prefix}_multimodal={'on' if enabled else 'off'}"],
                )
