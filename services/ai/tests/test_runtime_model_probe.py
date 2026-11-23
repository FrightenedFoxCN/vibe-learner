from unittest import TestCase
from unittest.mock import patch

from app.services.runtime_model_probe import (
    parse_model_probe_payload,
    probe_openai_models,
)


class RuntimeProbeTest(TestCase):
    def test_invalid_directory_cannot_report_authentication_success(self):
        for payload in [None, {}, {"data": {}}, {"data": [{"id": 42}]}]:
            with self.subTest(payload=payload):
                result = parse_model_probe_payload(payload)
                self.assertFalse(result["available"])
                self.assertEqual(result["error"], "invalid_model_list_response")

    def test_empty_directory_is_valid_and_duplicate_model_ids_are_collapsed(self):
        self.assertTrue(parse_model_probe_payload({"data": []})["available"])
        result = parse_model_probe_payload({"data": [{"id": "synth"}, {"id": "synth"}]})
        self.assertEqual(result["models"], ["synth"])

    @patch("app.services.runtime_model_probe.urllib.request.urlopen")
    def test_invalid_encoding_and_then_valid_empty_directory(self, urlopen):
        reply = urlopen.return_value.__enter__.return_value
        reply.read.side_effect = [b"\xff", b'{"data": []}']
        args = {
            "api_key": "synthetic",
            "base_url": "https://example.invalid/v1",
            "timeout_seconds": 5,
        }
        self.assertFalse(probe_openai_models(**args)["available"])
        self.assertTrue(probe_openai_models(**args)["available"])
        self.assertEqual(urlopen.call_count, 2)
