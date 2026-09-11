"""Deferred SDK loading preserves explicit injection and operation snapshots."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch
from app.services.model_provider import OpenAIModelProvider
from app.services.provider_sdk import ProviderSDK


class ProviderLazySDKTests(unittest.TestCase):
    def provider(self, **kwargs):
        return OpenAIModelProvider(api_key="synthetic", base_url="https://example.invalid/v1", plan_model="test", **kwargs)

    def test_configuration_does_not_import_remote_or_ocr_libraries(self):
        result = subprocess.run([sys.executable, "-c", '''
import sys
from app.services.model_provider import OpenAIModelProvider, MockModelProvider
provider = OpenAIModelProvider(api_key="synthetic", base_url="https://example.invalid/v1", plan_model="test")
provider.supports_page_image_tools()
provider.supports_chat_page_image_tools()
provider.plan_tools_runtime_enabled()
MockModelProvider()
assert not any(name == "litellm" or name.startswith("litellm.") or name == "onnxtr" or name.startswith("onnxtr.") for name in sys.modules)
'''], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_concurrent_first_access_loads_one_sdk_instance(self):
        gate = Barrier(4)
        sdk = ProviderSDK()
        with patch.object(ProviderSDK, "load", return_value=sdk) as load:
            provider = self.provider()
            load.assert_not_called()
            def first_access(_):
                gate.wait(timeout=5)
                return provider._sdk_adapter()
            with ThreadPoolExecutor(max_workers=4) as pool:
                adapters = list(pool.map(first_access, range(4)))
            load.assert_called_once_with()
            self.assertIs(provider.sdk, sdk)
            self.assertEqual(len(adapters), 4)

    def test_injected_sdk_never_loads_default_and_existing_adapter_keeps_callables(self):
        first, later = Mock(), Mock()
        with patch.object(ProviderSDK, "load", side_effect=AssertionError("unexpected default SDK")):
            provider = self.provider(sdk=ProviderSDK(completion=first))
            before = provider._sdk_adapter()
            provider.sdk = ProviderSDK(completion=later)
            after = provider._sdk_adapter()
            self.assertIs(before.completion, first)
            self.assertIs(after.completion, later)
