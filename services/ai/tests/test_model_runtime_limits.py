import json
import unittest
from pathlib import Path

from app.core.model_runtime_limits import browser_model_runtime_config_snapshot


FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "packages"
    / "shared"
    / "fixtures"
    / "model-runtime-config-v1.json"
)


class ModelRuntimeLimitsTests(unittest.TestCase):
    def test_browser_visible_defaults_match_shared_golden(self) -> None:
        expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(browser_model_runtime_config_snapshot(), expected)


if __name__ == "__main__":
    unittest.main()
