import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock

from app.core.diagnostics import DiagnosticStore, active_store, active_harness, correlation
from app.services.provider_transport import ProviderTransport, ModelRequestError
from tests.test_provider_transport import UpstreamFailure


class DiagnosticProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = DiagnosticStore(Path(self.temp.name) / "events.sqlite3")
        token = active_store.set(self.store)
        self.addCleanup(active_store.reset, token)
        token = correlation.set({"request_id": "request", "flow_id": "flow"})
        self.addCleanup(correlation.reset, token)

    def events(self):
        return [item.model_dump(mode="json") for item in list(self.store.queue.queue)]

    def test_retry_has_distinct_child_spans_and_reported_usage_only_on_attempt(self):
        raw = {"usage": {"input_tokens": 7, "output_tokens": 2, "total_tokens": 9}, "output": "SECRET_OUTPUT"}
        invoke = Mock(side_effect=[UpstreamFailure(503), raw])
        transport = ProviderTransport(timeout_seconds=3, sleep=Mock())
        result, _ = transport.execute(request_kind="setting", model="test-model", invoke=invoke)
        self.assertIs(result, raw)
        events = self.events()
        self.assertEqual([item["name"] for item in events], ["provider_started", "provider_attempt_started", "provider_attempt_failed", "provider_attempt_started", "provider_attempt_finished", "provider_finished"])
        parent = events[-1]
        self.assertTrue(parent["provider_metric"]["recovered"])
        self.assertEqual(parent["provider_metric"]["attempts_used"], 2)
        self.assertIsNone(parent["provider_metric"]["total_tokens"])
        self.assertEqual(parent["provider_metric"]["usage_gap"], "aggregate_not_additive")
        children = [item for item in events if item["parent_span_id"]]
        self.assertEqual({item["parent_span_id"] for item in children}, {parent["span_id"]})
        self.assertEqual(len({item["span_id"] for item in children}), 2)
        terminal = events[-2]
        self.assertEqual(terminal["provider_metric"]["total_tokens"], 9)
        self.assertEqual(terminal["provider_metric"]["usage_source"], "provider_reported")
        self.assertIsNone(terminal["provider_metric"]["usage_gap"])
        self.assertGreaterEqual(parent["duration_ms"], terminal["duration_ms"])
        self.assertNotIn("SECRET_OUTPUT", json.dumps(events))
        self.assertNotIn("fixture error", json.dumps(events))

    def test_missing_and_malformed_usage_never_become_zero_or_estimated(self):
        for raw, expected in [({}, "not_returned"), ({"usage": {"prompt_tokens": "7", "completion_tokens": -1, "total_tokens": 10**100}}, "partial_or_invalid")]:
            ProviderTransport(timeout_seconds=3).execute(request_kind="embedding", model="secret invalid label", invoke=lambda: raw)
            metric = self.events()[-2]["provider_metric"]
            self.assertIsNone(metric["input_tokens"])
            self.assertIsNone(metric["total_tokens"])
            self.assertEqual(metric["usage_source"], "unavailable")
            self.assertEqual(metric["usage_gap"], expected)
            self.assertIsNone(metric["model"])
            self.assertNotIn("secret invalid label", json.dumps(self.events()))

    def test_failure_and_sink_failure_preserve_transport_semantics(self):
        invoke = Mock(side_effect=TimeoutError("PRIVATE_PROVIDER_EXCEPTION"))
        with self.assertRaises(ModelRequestError) as raised:
            ProviderTransport(timeout_seconds=3, sleep=Mock()).execute(request_kind="chat", model="test", invoke=invoke)
        self.assertEqual(raised.exception.attempts, 3)
        self.assertEqual(self.events()[-1]["name"], "provider_failed")
        self.assertEqual(self.events()[-1]["provider_metric"]["attempts_used"], 3)
        self.assertNotIn("PRIVATE_PROVIDER_EXCEPTION", json.dumps(self.events()))
        token = active_store.set(Mock(emit=Mock(side_effect=OSError("disk unavailable"))))
        try:
            payload, _ = ProviderTransport(timeout_seconds=3).execute(request_kind="chat", model="test", invoke=lambda: {"ok": True})
            self.assertEqual(payload, {"ok": True})
        finally:
            active_store.reset(token)

    def test_runtime_binds_real_prepared_trace_and_restores_scope(self):
        from app.core.bootstrap import Container
        from app.core.settings import Settings
        from app.models.persona_generation import PersonaGenerationInputManifest, PersonaGenerationProposalV1, PersonaSlotContentProposalV1
        root = Path(self.temp.name)
        container = Container(Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}", ocr_engine="disabled"))
        self.addCleanup(container.close)
        def generate(_):
            ProviderTransport(timeout_seconds=3).execute(request_kind="setting", model="test", invoke=lambda: {"usage": {"prompt_tokens": 1}})
            return PersonaGenerationProposalV1(request_kind="slot_assist", slot=PersonaSlotContentProposalV1(kind="custom", label="Tone", content="Patient"))
        _, trace = container.harness_proposal_runtime.run_persona(
            manifest=PersonaGenerationInputManifest(request_kind="slot_assist", mode="assist", requested_count=1, input_char_count=8),
            protected_input={"input_text": "PRIVATE_PROMPT"}, generate=generate,
        )
        metrics = [item for item in self.events() if item["provider_metric"]]
        self.assertTrue(metrics)
        self.assertEqual({item["harness"]["operation_id"] for item in metrics}, {trace.operation_id})
        self.assertEqual({item["harness"]["trace_id"] for item in metrics}, {trace.trace_id})
        self.assertTrue(all(item["harness"]["attempt_id"] is None for item in metrics))
        self.assertIsNone(active_harness.get())
