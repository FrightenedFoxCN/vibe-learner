from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.models import harness_performance as budget
from app.models.harness import HarnessContextEnvelopeV3, HarnessSnapshotRefV3, canonical_harness_context_digest
from app.services.harness_runtime import HarnessOperationRuntime, HarnessRuntimeResolvedArtifact
from tests.support.harness_runtime import HarnessRuntimeFixture


class HarnessPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = HarnessRuntimeFixture()
        self.addCleanup(self.fixture.close)

    def test_canonical_measurement_matches_utf8_not_character_count(self):
        payload = {"字": ["中文", None, 3], "a": True}
        expected = len(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())
        self.assertEqual(budget.canonical_byte_count(payload), expected)
        budget.enforce_budget("context_bytes", expected, expected)
        with self.assertRaises(budget.HarnessBudgetExceeded):
            budget.enforce_budget("context_bytes", expected, expected - 1)

    def _snapshot_request(self):
        draft = self.fixture.context.model_dump(mode="json")
        draft["snapshot_refs"] = [HarnessSnapshotRefV3.model_validate({"artifact_type": "tavern_transcript", "artifact_id": "performance-fixture",
            "contract": {"name": "TavernTranscriptSnapshot", "version": "tavern-transcript-snapshot-v1"},
            "payload_digest": "a" * 64}).model_dump(mode="json", exclude_none=False)]
        draft["context_digest"] = canonical_harness_context_digest(draft)
        return replace(self.fixture.request, context=HarnessContextEnvelopeV3.model_validate(draft))

    def test_oversized_context_fails_before_resolver_and_worker_with_redacted_evidence(self):
        calls = {}
        resolver = SimpleNamespace(resolve=lambda **_: self.fail("resolver must not run"))
        runtime = HarnessOperationRuntime(repository=self.fixture.repository, artifact_resolver=resolver)
        with patch.object(budget, "CONTEXT_MAX_BYTES", 1):
            result = runtime.execute(request=self.fixture.request, adapter=self.fixture.adapter(calls), claim_owner="test")
        self.assertEqual(calls, {})
        self.assertEqual(result.terminal_trace.error_code, "harness_budget_context_bytes_exceeded")
        evidence = json.loads(result.terminal_trace.checks[0].message)
        self.assertEqual(evidence["limit"], 1)
        self.assertEqual(set(evidence), {"budget_version", "dimension", "actual", "limit"})

    def test_reference_budget_precedes_resolver(self):
        calls = {}
        request = self._snapshot_request()
        runtime = HarnessOperationRuntime(repository=self.fixture.repository)
        with patch.object(budget, "CONTEXT_MAX_REFERENCES", 0):
            result = runtime.execute(request=request, adapter=self.fixture.adapter(calls), claim_owner="test")
        self.assertEqual(calls, {})
        self.assertEqual(result.terminal_trace.error_code, "harness_budget_reference_count_exceeded")

    def test_oversized_resolved_snapshot_never_reaches_worker(self):
        calls = {}
        request = self._snapshot_request()
        resolver = SimpleNamespace(resolve=lambda **_: (HarnessRuntimeResolvedArtifact(
            "performance-fixture", "a" * 64, b"secret snapshot content"),))
        runtime = HarnessOperationRuntime(repository=self.fixture.repository, artifact_resolver=resolver)
        with patch.object(budget, "SNAPSHOT_MAX_BYTES", 1):
            result = runtime.execute(request=request, adapter=self.fixture.adapter(calls), claim_owner="test")
        self.assertEqual(calls, {})
        self.assertEqual(result.terminal_trace.error_code, "harness_budget_snapshot_bytes_exceeded")
        self.assertNotIn("secret snapshot content", result.terminal_trace.model_dump_json())

    def test_resolved_total_limit_is_independent_from_per_snapshot_limit(self):
        request = self._snapshot_request()
        resolver = SimpleNamespace(resolve=lambda **_: (HarnessRuntimeResolvedArtifact("performance-fixture", "a" * 64, b"abc"),))
        runtime = HarnessOperationRuntime(repository=self.fixture.repository, artifact_resolver=resolver)
        with patch.object(budget, "RESOLVED_MAX_BYTES", 2):
            with self.assertRaisesRegex(budget.HarnessBudgetExceeded, "resolved_bytes"):
                runtime._resolve_artifacts(request)

    def test_real_snapshot_64mib_and_total_128mib_boundaries(self):
        request = self._snapshot_request()
        draft = request.context.model_dump(mode="json")
        template = draft["snapshot_refs"][0]
        draft["snapshot_refs"] = [{**template, "artifact_id": f"maximum-{i}"} for i in range(3)]
        draft["context_digest"] = canonical_harness_context_digest(draft)
        request = replace(request, context=HarnessContextEnvelopeV3.model_validate(draft))
        block = b"x" * (64 * 1024 * 1024)
        payloads = [block, block, b""]
        def resolve(**_):
            return tuple(HarnessRuntimeResolvedArtifact(f"maximum-{i}", "a" * 64, payload) for i, payload in enumerate(payloads))
        runtime = HarnessOperationRuntime(repository=self.fixture.repository, artifact_resolver=SimpleNamespace(resolve=resolve))
        self.assertEqual(sum(len(p) for p in runtime._resolve_artifacts(request).values()), 128 * 1024 * 1024)
        payloads[2] = b"x"
        with self.assertRaises(budget.HarnessBudgetExceeded) as total:
            runtime._resolve_artifacts(request)
        self.assertEqual(total.exception.evidence.dimension, "resolved_bytes")
        self.assertEqual(total.exception.evidence.actual, 128 * 1024 * 1024 + 1)
        payloads[:] = [block + b"x", b"", b""]
        with self.assertRaises(budget.HarnessBudgetExceeded) as single:
            runtime._resolve_artifacts(request)
        self.assertEqual(single.exception.evidence.dimension, "snapshot_bytes")
        self.assertEqual(single.exception.evidence.actual, 64 * 1024 * 1024 + 1)

    def test_expired_deadline_does_not_start_callback(self):
        runtime = HarnessOperationRuntime(repository=self.fixture.repository)
        with self.assertRaisesRegex(RuntimeError, "wall_time_budget"):
            runtime._call_with_heartbeat(None, 30, lambda: self.fail("expired callback ran"),
                deadline=runtime.clock() - timedelta(seconds=1))

    def test_runtime_evidence_limit_precedes_worker(self):
        calls = {}
        runtime = HarnessOperationRuntime(repository=self.fixture.repository)
        with patch.object(budget, "RUNTIME_MAX_EVIDENCE_BYTES", 1):
            result = runtime.execute(request=self.fixture.request, adapter=self.fixture.adapter(calls), claim_owner="test")
        self.assertEqual(calls, {})
        self.assertEqual(result.terminal_trace.error_code, "harness_budget_runtime_evidence_bytes_exceeded")

    def test_attempt_limit_does_not_start_another_callback(self):
        runtime = HarnessOperationRuntime(repository=self.fixture.repository)
        current = SimpleNamespace(attempt_records=[None] * 65)
        with patch.object(runtime, "_require_execution", return_value=current):
            with self.assertRaisesRegex(budget.HarnessBudgetExceeded, "attempt_count"):
                runtime._call_with_heartbeat(SimpleNamespace(trace_id="fixture"), 30,
                    lambda: self.fail("over-budget callback ran"))
