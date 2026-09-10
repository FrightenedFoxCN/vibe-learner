"""Best-effort transport observations with distinct parent/attempt spans."""
from __future__ import annotations
import re
import time
from uuid import uuid4

from app.core.diagnostics import active_store, active_harness
from app.models.diagnostic_provider import DiagnosticProviderMetricV1


class ProviderObservation:
    def __init__(self, request_kind: str, model: str, timeout_seconds: int):
        self.kind = request_kind if request_kind in {"plan", "chat", "setting", "embedding"} else "other"
        self.model = model if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}", model) else None
        self.timeout = timeout_seconds
        self.span = uuid4().hex
        self.started = time.perf_counter()
        self.attempt_span = None
        self.attempt_started = self.started
        self.attempt = 0
        self._emit("provider_started")

    def begin_attempt(self, index):
        self.attempt = index
        self.attempt_span = uuid4().hex
        self.attempt_started = time.perf_counter()
        self._emit("provider_attempt_started", child=True)

    def end_attempt(self, payload=None, failed=False):
        self._emit("provider_attempt_failed" if failed else "provider_attempt_finished", child=True, payload=payload, terminal=True)

    def finish(self, failed=False):
        self._emit("provider_failed" if failed else "provider_finished", terminal=True)

    def _emit(self, name, *, child=False, payload=None, terminal=False):
        try:
            store = active_store.get()
            if store is None:
                return
            usage = payload.get("usage") if isinstance(payload, dict) else None
            def count(*keys):
                if not isinstance(usage, dict):
                    return None
                for key in keys:
                    value = usage.get(key)
                    if type(value) is int and 0 <= value <= 1_000_000_000_000:
                        return value
                return None
            tokens = (count("input_tokens", "prompt_tokens"), count("output_tokens", "completion_tokens"), count("total_tokens")) if child else (None, None, None)
            reported = any(value is not None for value in tokens)
            metric = DiagnosticProviderMetricV1(
                request_kind=self.kind, model=self.model,
                model_gap="model_label_unreviewed" if self.model is None else None,
                timeout_seconds=self.timeout, attempt_index=self.attempt if child else None,
                attempts_used=self.attempt, recovered=name == "provider_finished" and self.attempt > 1,
                input_tokens=tokens[0], output_tokens=tokens[1], total_tokens=tokens[2],
                usage_source="provider_reported" if reported else "unavailable",
                usage_gap=("aggregate_not_additive" if not child else "not_returned" if not isinstance(usage, dict) else "partial_or_invalid" if any(value is None for value in tokens) else None),
            )
            store.emit(name, harness=active_harness.get(), provider_metric=metric,
                       span_id=self.attempt_span if child else self.span,
                       parent_span_id=self.span if child else None,
                       duration_ms=(time.perf_counter() - (self.attempt_started if child else self.started)) * 1000 if terminal else None)
        except Exception:
            # Diagnostics never change transport retry, errors or successful output.
            pass
