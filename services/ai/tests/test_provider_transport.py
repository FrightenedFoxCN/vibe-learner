"""Transport policy tests: fake SDK calls and clocks, no app/database setup."""
from types import SimpleNamespace
import subprocess
import sys
import unittest
from unittest.mock import Mock

from app.services.provider_transport import ModelRequestError, ProviderTransport, _normalize_completed_tool_indexes


class UpstreamFailure(Exception):
    def __init__(self, status, code="fixture"):
        super().__init__("upstream failure")
        self.status_code = status
        self.body = {"error": {"code": code, "message": "fixture error"}}


class ProviderTransportTests(unittest.TestCase):
    def test_complete_tool_indexes_are_metadata_without_mutating_sdk_payload(self):
        calls = [{"id": f"call-{i}", "index": 0, "type": "function",
            "function": {"name": "get_study_unit_detail", "arguments": '{"study_unit_id":"unit-1"}'}} for i in range(2)]
        payload = {"choices": [{"message": {"tool_calls": calls}}], "usage": {"total_tokens": 10}}
        result, _ = ProviderTransport(timeout_seconds=3).execute(request_kind="plan", model="test", invoke=lambda: payload)
        projected = result["choices"][0]["message"]["tool_calls"]
        self.assertEqual([c["id"] for c in projected], ["call-0", "call-1"])
        self.assertTrue(all("index" not in c for c in projected))
        self.assertEqual([c["index"] for c in calls], [0, 0])
        self.assertEqual(result["usage"], payload["usage"])
        from app.models.harness import HarnessStage, HarnessWorkflow
        from app.services.tool_provider_projection import decode_provider_tool_call
        decoded = decode_provider_tool_call(projected[0], workflow=HarnessWorkflow.PLANNING,
            offered_in_stage=HarnessStage.PLAN_GENERATION)
        self.assertEqual(decoded.transport_correlation_id, "call-0")

    def test_invalid_indexes_unknown_fields_and_partial_calls_are_not_repaired(self):
        base = {"id": "call-0", "index": 0, "type": "function",
            "function": {"name": "get_study_unit_detail", "arguments": "{}"}}
        variants = [{**base, "index": value} for value in (True, "0", None, -1, 2_147_483_648)]
        variants.extend([{**base, "operation_id": "forged"}, {**base, "id": ""},
            {**base, "function": {"arguments": "{}"}}])
        for call in variants:
            with self.subTest(call=call):
                payload = {"choices": [{"message": {"tool_calls": [call]}}]}
                self.assertEqual(_normalize_completed_tool_indexes(payload), payload)

    def test_success_after_transient_failures_has_two_retries_and_one_recovery(self):
        invoke = Mock(side_effect=[UpstreamFailure(503), UpstreamFailure(503), {"ok": True}])
        sleep, recovery = Mock(), Mock()
        transport = ProviderTransport(timeout_seconds=3, sleep=sleep, clock=Mock(side_effect=[10, 10.125]), record_recovery=recovery)
        with self.assertLogs("vibe_learner.provider_transport"):
            result, elapsed = transport.execute(request_kind="chat", model="test", invoke=invoke)
        self.assertEqual((result, elapsed), ({"ok": True}, 125))
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.4, 0.8])
        recovery.assert_called_once_with(category="transport_retry", reason="upstream_transient_error", strategy="retry_same_payload", attempts=3)

    def test_timeout_exhaustion_keeps_attempt_count_and_public_error_code(self):
        invoke, sleep = Mock(side_effect=TimeoutError("timed out")), Mock()
        transport = ProviderTransport(timeout_seconds=3, sleep=sleep)
        with self.assertLogs("vibe_learner.provider_transport"), self.assertRaises(ModelRequestError) as raised:
            transport.execute(request_kind="plan", model="test", invoke=invoke)
        self.assertEqual(str(raised.exception), "openai_plan_request_timeout")
        self.assertEqual(raised.exception.attempts, 3)
        self.assertEqual(invoke.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_nonretryable_errors_preserve_classification(self):
        cases = [
            (UpstreamFailure(429), "openai_setting_request_rate_limit"),
            (UpstreamFailure(401, "invalid_key"), "openai_setting_request_failed:401:invalid_key"),
            (ValueError("unsupported parameter temperature"), "openai_setting_request_unsupported_params"),
        ]
        for error, code in cases:
            with self.subTest(code=code):
                invoke, sleep = Mock(side_effect=error), Mock()
                with self.assertLogs("vibe_learner.provider_transport"), self.assertRaises(ModelRequestError) as raised:
                    ProviderTransport(timeout_seconds=3, sleep=sleep).execute(request_kind="setting", model="test", invoke=invoke)
                self.assertEqual(str(raised.exception), code)
                self.assertEqual(raised.exception.attempts, 1)
                invoke.assert_called_once()
                sleep.assert_not_called()

    def test_sdk_specific_error_type_is_classified_without_sdk_import(self):
        class QuotaFailure(Exception):
            pass
        transport = ProviderTransport(timeout_seconds=3, sdk=SimpleNamespace(RateLimitError=QuotaFailure), sleep=Mock())
        with self.assertLogs("vibe_learner.provider_transport"), self.assertRaisesRegex(ModelRequestError, "openai_chat_request_rate_limit"):
            transport.execute(request_kind="chat", model="test", invoke=Mock(side_effect=QuotaFailure("quota")))

    def test_sdk_payload_normalization_and_invalid_payload_do_not_retry(self):
        value = SimpleNamespace(model_dump_json=lambda: '{"result":"ok"}')
        result, _ = ProviderTransport(timeout_seconds=3).execute(request_kind="chat", model="test", invoke=lambda: value)
        self.assertEqual(result, {"result": "ok"})
        invoke, sleep = Mock(return_value=object()), Mock()
        with self.assertLogs("vibe_learner.provider_transport"), self.assertRaisesRegex(ModelRequestError, "openai_chat_request_failed:unknown:RuntimeError"):
            ProviderTransport(timeout_seconds=3, sleep=sleep).execute(request_kind="chat", model="test", invoke=invoke)
        invoke.assert_called_once()
        sleep.assert_not_called()

    def test_usage_accepts_responses_keys_and_recording_failure_does_not_escape(self):
        sink = Mock()
        transport = ProviderTransport(timeout_seconds=3, token_usage_service=sink)
        transport.record_usage({"usage": {"input_tokens": "7", "output_tokens": 2}}, feature="setting", model="test", prompt_key="input_tokens", completion_key="output_tokens")
        sink.record.assert_called_once_with(feature="setting", model="test", prompt_tokens=7, completion_tokens=2, total_tokens=9)
        sink.record.side_effect = RuntimeError("usage store unavailable")
        with self.assertLogs("vibe_learner.provider_transport"):
            transport.record_usage({"usage": {"prompt_tokens": 1}}, feature="chat", model="test")
        self.assertEqual(sink.record.call_count, 2)

    def test_transport_import_does_not_load_provider_or_litellm(self):
        result = subprocess.run([sys.executable, "-c", '''
import sys
from app.services.provider_transport import ProviderTransport
assert "app.services.model_provider" not in sys.modules
assert "litellm" not in sys.modules
'''], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
