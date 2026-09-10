import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from app.core.diagnostics import DiagnosticStore, active_store, active_span
from app.core.diagnostic_tool import observe_tool_call
from app.models.harness import HarnessWorkflow, HarnessStage
from app.models.tool_manifest import TOOL_MANIFEST_ENTRIES
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.provider_study import _execute_chat_tool_call
from app.services.provider_transport import ProviderTransport
from app.services.study_session_chat_runtime import StudySessionChatToolRuntime


def call(name, arguments="{}"):
    return {"id": "provider-call-1", "type": "function", "function": {"name": name, "arguments": arguments}}


def study(tool_call, **extra):
    return _execute_chat_tool_call(tool_call, section_id="section", section_context="PRIVATE_CONTEXT", learner_message="PRIVATE_MESSAGE",
                                   memory_hits=[], debug_report=None, document_path=None, **extra)


class DiagnosticToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DiagnosticStore(Path(self.temp.name) / "events.db")
        token = active_store.set(self.store)
        self.addCleanup(active_store.reset, token)

    def events(self):
        return [item.model_dump(mode="json") for item in list(self.store.queue.queue)]

    def test_all_37_manifest_tools_have_metrics_even_when_arguments_are_rejected(self):
        plan = build_plan_tool_runtime()
        entries = list(TOOL_MANIFEST_ENTRIES.values())
        self.assertEqual(len(entries), 37)
        for entry in entries:
            tool_call = call(entry.canonical_name, "PRIVATE_INVALID_JSON")
            result = plan.execute_tool_call(tool_call) if entry.workflow == HarnessWorkflow.PLANNING else study(tool_call)
            events = self.events()[-2:]
            self.assertEqual([item["name"] for item in events], ["tool_started", "tool_failed"])
            metric = events[-1]["tool_metric"]
            self.assertEqual(metric["manifest_key"], entry.key)
            self.assertEqual(metric["timeout_ms"], entry.budget.timeout_ms)
            self.assertEqual(metric["input_contract_version"], entry.input_contract.version)
            self.assertEqual(metric["result_contract_version"], entry.result_contract.version)
            self.assertEqual(metric["provider_tool_call_id"], "provider-call-1")
            self.assertEqual(metric["effect_commit_claim"], "none")
            self.assertGreaterEqual(events[-1]["duration_ms"], 0)
        self.assertNotIn("PRIVATE", json.dumps(self.events()))
        self.assertIsNone(active_span.get())

    def test_actual_plan_and_study_success_and_budget_failure(self):
        plan = build_plan_tool_runtime()
        result = plan.execute_tool_call(call("estimate_plan_completion"))
        self.assertTrue(result.result["ok"])
        self.assertEqual(self.events()[-1]["name"], "tool_finished")
        runtime = StudySessionChatToolRuntime(session_service=Mock(), plan_service=Mock(), session_id="session")
        result = study(call("read_system_time"), session_tool_runtime=runtime, available_tool_names={"read_system_time"})
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(self.events()[-1]["name"], "tool_finished")
        from app.services.tool_provider_projection import ToolExecutionBudgetTracker
        budget = Mock(spec=ToolExecutionBudgetTracker)
        from app.services.tool_provider_projection import ToolContractViolation
        budget.admit.side_effect = ToolContractViolation("tool_operation_call_limit_exceeded", detail="PRIVATE_BUDGET_DETAIL")
        result = study(call("read_system_time"), session_tool_runtime=runtime, available_tool_names={"read_system_time"}, budget_tracker=budget)
        self.assertFalse(result["result"]["ok"])
        self.assertEqual(self.events()[-1]["name"], "tool_failed")
        self.assertNotIn("PRIVATE_BUDGET_DETAIL", json.dumps(self.events()))

    def test_nested_provider_parentage_unknown_names_and_sink_failure(self):
        @observe_tool_call(HarnessWorkflow.STUDY_CHAT, HarnessStage.STUDY_CHAT_REPLY)
        def nested(tool_call):
            ProviderTransport(timeout_seconds=3).execute(request_kind="chat", model="test", invoke=lambda: {"usage": {"prompt_tokens": 2}})
            return {"result": {"ok": True}}
        result = nested(call("read_system_time"))
        self.assertTrue(result["result"]["ok"])
        events = self.events()
        tool_span = events[0]["span_id"]
        provider = next(item for item in events if item["name"] == "provider_started")
        self.assertEqual(provider["parent_span_id"], tool_span)
        self.assertIsNone(active_span.get())
        study(call("PRIVATE_UNKNOWN_TOOL"))
        self.assertIsNone(self.events()[-1]["tool_metric"]["canonical_name"])
        self.assertEqual(self.events()[-1]["tool_metric"]["manifest_gap"], "unregistered_tool")
        self.assertNotIn("PRIVATE_UNKNOWN_TOOL", json.dumps(self.events()))
        token = active_store.set(Mock(emit=Mock(side_effect=OSError("PRIVATE_DISK_ERROR"))))
        try:
            self.assertTrue(nested(call("read_system_time"))["result"]["ok"])
        finally:
            active_store.reset(token)
