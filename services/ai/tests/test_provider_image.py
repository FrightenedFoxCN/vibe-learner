"""Image readiness, request, and decode boundaries without a model SDK."""
import unittest
from unittest.mock import Mock

from app.services.provider_image import RemoteImageProvider


class ImageProviderTests(unittest.TestCase):
    def test_unsupported_model_or_absent_responses_does_not_issue_request(self):
        for model, available in [("gpt-5", False), ("unsupported", True)]:
            with self.subTest(model=model, available=available):
                request = Mock()
                provider = RemoteImageProvider(model, available, request)
                self.assertFalse(provider.supports_chat_generated_image_tools())
                with self.assertRaisesRegex(RuntimeError, "chat_image_generation_unsupported"):
                    provider.generate_projected_image(prompt="draw")
                request.assert_not_called()

    def test_empty_prompt_is_rejected_before_request(self):
        request = Mock()
        with self.assertRaisesRegex(RuntimeError, "chat_image_generation_prompt_required"):
            RemoteImageProvider("gpt-5", True, request).generate_projected_image(prompt="  ")
        request.assert_not_called()

    def test_image_request_and_projection(self):
        for size, expected in [(" AUTO ", "auto"), ("invalid", "1024x1024")]:
            with self.subTest(size=size):
                request = Mock(return_value=({"output": [
                    {"type": "message"},
                    {"type": "image_generation_call", "result": ["", " abc "], "revised_prompt": " revised "},
                ]}, 1))
                result = RemoteImageProvider("gpt-5", True, request).generate_projected_image(prompt=" draw ", size=size)
                self.assertEqual(result, {"image_url": "data:image/png;base64,abc", "revised_prompt": "revised"})
                request.assert_called_once_with({"model": "gpt-5", "input": "draw", "tools": [
                    {"type": "image_generation", "size": expected},
                ]}, request_kind="chat", model="gpt-5")

    def test_empty_output_does_not_trigger_hidden_generation(self):
        request = Mock(return_value=({"output": []}, 1))
        with self.assertRaisesRegex(RuntimeError, "chat_image_generation_empty_response"):
            RemoteImageProvider("gpt-5", True, request).generate_projected_image(prompt="draw")
        self.assertEqual(request.call_count, 1)
