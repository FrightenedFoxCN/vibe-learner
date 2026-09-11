import unittest

from app.core.execution_budget import check_execution_budget, execution_budget_scope
from app.services.provider_transport import ProviderTransport


class ExecutionBudgetTests(unittest.TestCase):
    def test_nested_scope_cannot_replace_parent_budget_and_resets_on_error(self):
        calls = []
        def expired():
            calls.append("parent")
            raise RuntimeError("expired")
        with self.assertRaisesRegex(RuntimeError, "expired"):
            with execution_budget_scope(expired), execution_budget_scope(lambda: calls.append("child")):
                check_execution_budget()
        self.assertEqual(calls, ["parent"])
        check_execution_budget()

    def test_transport_retry_checks_budget_before_issuing_sdk_call(self):
        from unittest.mock import patch
        expired = [False]
        calls = []
        def check():
            if expired[0]:
                raise RuntimeError("expired")
        def invoke():
            calls.append(True)
            raise RuntimeError("transient")
        transport = ProviderTransport(timeout_seconds=1, sleep=lambda _: expired.__setitem__(0, True))
        with execution_budget_scope(check), patch("app.services.provider_transport._is_litellm_retryable_error", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "expired"):
                transport.execute(request_kind="plan", model="fixture", invoke=invoke)
        self.assertEqual(len(calls), 1)
