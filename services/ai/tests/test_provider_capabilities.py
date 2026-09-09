"""Default capability behavior is independent of transport and model packages."""
import subprocess
import sys
import unittest

from app.services.provider_capabilities import EmbeddingModelCapability, ImageModelCapability, PlanningModelCapability, StudyModelCapability


class ProviderCapabilityContractTests(unittest.TestCase):
    def test_capabilities_import_without_provider_transport(self):
        result = subprocess.run([sys.executable, "-c", '''
import sys
from app.services.provider_capabilities import PlanningModelCapability, TavernModelCapability
assert "app.services.model_provider" not in sys.modules
assert "litellm" not in sys.modules
'''], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_optional_capabilities_preserve_unsupported_defaults(self):
        self.assertEqual(EmbeddingModelCapability().embed_texts(["example"]), [])
        self.assertFalse(PlanningModelCapability().supports_page_image_tools())
        self.assertFalse(StudyModelCapability().supports_chat_page_image_tools())
        self.assertFalse(ImageModelCapability().supports_chat_generated_image_tools())
        with self.assertRaisesRegex(RuntimeError, "chat_image_generation_unsupported"):
            ImageModelCapability().generate_projected_image(prompt="example")
