import json
import unittest
from app.models.diagnostic import DiagnosticEventV1
from app.models.diagnostic_index import DiagnosticHarnessIndexV1
from app.services.diagnostic_audit import build_diagnostic_audit


class DiagnosticAuditTests(unittest.TestCase):
    def event(self, identity, name, span, duration=None, *, model="model-a", tokens=None, recovered=False):
        child = name.startswith("provider_attempt")
        return DiagnosticEventV1.model_validate_json(json.dumps(dict(event_id=identity, source="server", name=name,
            timestamp="2026-09-10T00:00:00Z", span_id=span, parent_span_id="parent" if child else None,
            duration_ms=duration, request_id="request", provider_metric=dict(request_kind="plan", model=model, timeout_seconds=30,
                attempt_index=1 if child else None, attempts_used=2 if recovered else 1, recovered=recovered,
                input_tokens=tokens, output_tokens=tokens, total_tokens=tokens * 2 if tokens is not None else None,
                usage_source="provider_reported" if tokens is not None else "unavailable",
                usage_gap=None if tokens is not None else "not_returned" if child else "aggregate_not_additive"))))

    def test_retries_parent_duration_and_usage_are_not_added_twice(self):
        events = [self.event("s", "provider_started", "parent"),
            self.event("a1", "provider_attempt_started", "attempt1"), self.event("a2", "provider_attempt_failed", "attempt1", 20),
            self.event("b1", "provider_attempt_started", "attempt2"), self.event("b2", "provider_attempt_finished", "attempt2", 40, tokens=10),
            self.event("e", "provider_finished", "parent", 80, recovered=True)]
        report = build_diagnostic_audit(events + [events[-1]], [])
        self.assertEqual(report.duplicate_event_count, 1)
        groups = {item.key.kind: item for item in report.groups}
        self.assertEqual(groups["provider_call"].p95_ms, 80)
        self.assertEqual(groups["provider_call"].recovered_count, 1)
        self.assertIsNone(groups["provider_call"].total_tokens)
        self.assertEqual(groups["provider_attempt"].sample_count, 2)
        self.assertEqual(groups["provider_attempt"].failed_count, 1)
        self.assertEqual(groups["provider_attempt"].p50_ms, 20)
        self.assertEqual(groups["provider_attempt"].p95_ms, 40)
        self.assertEqual(groups["provider_attempt"].total_tokens, 20)
        self.assertEqual(groups["provider_attempt"].total_token_sample_count, 1)
        self.assertEqual(groups["provider_attempt"].recovered_count, 0)
        self.assertEqual(report.commit_claim, "none")

    def test_missing_conflicting_and_changed_model_samples_do_not_claim_success(self):
        events = [self.event("missing", "provider_started", "missing"),
            self.event("s", "provider_started", "changed", model="old"), self.event("e", "provider_finished", "changed", 100, model="new")]
        report = build_diagnostic_audit(events, [])
        self.assertTrue(all(item.outcome == "unknown" for item in report.observations))
        self.assertTrue(all(item.duration_ms is None for item in report.observations))
        conflict = next(item for item in report.observations if item.span_id == "changed")
        self.assertIn("conflicting_span_records", conflict.gaps)
        self.assertIsNone(conflict.group.model)
        self.assertIn("missing_terminal", next(item for item in report.observations if item.span_id == "missing").gaps)
        duplicate = events[0].model_copy(update={"duration_ms": 9.0})
        with self.assertRaisesRegex(ValueError, "identity_conflict"):
            build_diagnostic_audit([events[0], duplicate], [])

    def test_model_configuration_groups_and_nearest_rank_percentiles_are_deterministic(self):
        events = []
        for i in range(1, 21):
            events.extend([self.event(f"s{i}", "provider_attempt_started", f"span{i}"), self.event(f"e{i}", "provider_attempt_finished", f"span{i}", i, tokens=0)])
        events.append(self.event("other", "provider_attempt_finished", "other", 100, model="model-b"))
        report = build_diagnostic_audit(events, [])
        group = next(item for item in report.groups if item.key.model == "model-a")
        self.assertEqual((group.p50_ms, group.p95_ms), (10, 19))
        self.assertEqual(group.total_tokens, 0)
        self.assertEqual(group.total_token_sample_count, 20)
        self.assertEqual(len(report.groups), 2)
        self.assertEqual(report.model_dump(), build_diagnostic_audit(list(reversed(events)), []).model_dump())

    def test_harness_stage_and_attempts_remain_separate_and_source_gaps_stay_unknown(self):
        trace = DiagnosticHarnessIndexV1.model_validate_json(json.dumps(dict(trace_id="trace", operation_id="harness-operation-" + "a"*32,
            workflow="persona", stage="persona_generation", state="terminal", status="repaired", commit_status="committed", duration_ms=100,
            components=[dict(name="component", version="component-v1")], attempts=[dict(attempt_id="attempt", attempt_index=1, phase="generate", status="passed", duration_ms=70)])))
        report = build_diagnostic_audit([], [trace])
        self.assertEqual({item.group.kind: item.duration_ms for item in report.observations}, {"harness_stage": 100, "harness_attempt": 70})
        removed = trace.model_copy(update={"gap": "source_removed"})
        self.assertTrue(all(item.outcome == "unknown" and item.duration_ms is None for item in build_diagnostic_audit([], [removed]).observations))
        active = trace.model_copy(update={"gap": "terminal_trace_not_available", "state": "claimed"})
        observations = build_diagnostic_audit([], [active]).observations
        self.assertEqual(observations[0].outcome, "unknown")
        self.assertEqual(observations[1].outcome, "completed")

    def test_real_provider_observer_retry_events_feed_one_recovered_call(self):
        from app.core.diagnostic_provider import ProviderObservation
        from app.core.diagnostics import active_store
        captured = []
        class Sink:
            def emit(self, name, **fields):
                captured.append(DiagnosticEventV1(event_id=f"event{len(captured)}", name=name, source="server", timestamp="2026-09-10T00:00:00Z", **fields))
        token = active_store.set(Sink())
        try:
            observer = ProviderObservation("plan", "model-a", 30)
            observer.begin_attempt(1)
            observer.end_attempt(failed=True)
            observer.begin_attempt(2)
            observer.end_attempt(payload={"usage": {"prompt_tokens": 11, "completion_tokens": 4, "total_tokens": 15}})
            observer.finish()
        finally:
            active_store.reset(token)
        report = build_diagnostic_audit(captured, [])
        call = next(group for group in report.groups if group.key.kind == "provider_call")
        attempts = next(group for group in report.groups if group.key.kind == "provider_attempt")
        self.assertEqual(call.recovered_count, 1)
        self.assertEqual(call.sample_count, 1)
        self.assertEqual(attempts.sample_count, 2)
        self.assertEqual(attempts.total_tokens, 15)
        self.assertIsNone(call.total_tokens)
        self.assertTrue(any(gap.gap == "usage_not_returned" for gap in attempts.gaps))

    def test_tool_contract_versions_partition_samples_and_ignore_duplicate_http_timing(self):
        events = []
        for index, version in enumerate(("tool-v1", "tool-v2")):
            for suffix, name, duration in (("s", "tool_started", None), ("e", "tool_finished", 10 + index)):
                events.append(DiagnosticEventV1.model_validate_json(json.dumps(dict(event_id=f"{index}{suffix}", source="server", name=name,
                    timestamp="2026-09-10T00:00:00Z", span_id=f"tool{index}", duration_ms=duration,
                    tool_metric=dict(workflow="planning", offered_in_stage="plan_generation", canonical_name="read_section", input_contract_version=version, result_contract_version="result-v1")))))
        events.append(DiagnosticEventV1(event_id="http", source="server", name="request_finished", timestamp="2026-09-10T00:00:00Z", duration_ms=999.0))
        report = build_diagnostic_audit(events, [])
        self.assertEqual(len(report.observations), 2)
        self.assertEqual({group.key.input_contract for group in report.groups}, {"tool-v1", "tool-v2"})
        self.assertEqual({group.p95_ms for group in report.groups}, {10, 11})
