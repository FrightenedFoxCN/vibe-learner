import unittest

from app.services.runtime_model_probe import describe_model_capabilities, parse_model_probe_payload


class RuntimeModelProbeTests(unittest.TestCase):
    def test_parse_payload_preserves_capability_metadata(self) -> None:
        payload = {
            "data": [
                {
                    "id": "gpt-4.1-mini",
                    "input_modalities": ["text", "image"],
                    "output_modalities": ["text"],
                    "supported_tools": [{"type": "web_search_preview"}],
                }
            ]
        }

        result = parse_model_probe_payload(payload)

        self.assertTrue(result["available"])
        self.assertEqual(result["models"], ["gpt-4.1-mini"])
        capability = result["capabilities"]["gpt-4.1-mini"]
        self.assertEqual(capability["input_modalities"], ["text", "image"])
        self.assertEqual(capability["multimodal"]["status"], "supported")
        self.assertEqual(capability["multimodal"]["source"], "metadata")
        self.assertEqual(capability["web_search"]["status"], "supported")
        self.assertEqual(capability["web_search"]["source"], "metadata")

    def test_explicit_false_flags_are_treated_as_unsupported(self) -> None:
        capability = describe_model_capabilities(
            {
                "id": "strict-text-model",
                "capabilities": {
                    "multimodal": False,
                    "web_search": False,
                },
            }
        )

        self.assertEqual(capability["multimodal"]["status"], "unsupported")
        self.assertEqual(capability["web_search"]["status"], "unsupported")

    def test_model_name_hint_marks_multimodal_as_inferred(self) -> None:
        capability = describe_model_capabilities({"id": "gpt-4o-mini"})

        self.assertEqual(capability["multimodal"]["status"], "supported")
        self.assertEqual(capability["multimodal"]["source"], "model_name")
        self.assertEqual(capability["web_search"]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
