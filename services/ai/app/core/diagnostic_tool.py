"""One observer around existing decode/budget/runtime/result boundaries."""
from functools import wraps
import re
import time
from uuid import uuid4

from app.core.diagnostics import active_store, active_harness, active_span
from app.models.diagnostic_tool import DiagnosticToolMetricV1
from app.models.tool_manifest import resolve_tool_manifest_entry


def observe_tool_call(workflow, offered_stage, *, method=False):
    def decorate(function):
        @wraps(function)
        def observed(*args, **kwargs):
            raw = kwargs.get("tool_call", args[1 if method else 0] if len(args) > (1 if method else 0) else None)
            metric = None
            try:
                name = raw.get("function", {}).get("name") if isinstance(raw, dict) and isinstance(raw.get("function"), dict) else None
                provider_id = raw.get("id") if isinstance(raw, dict) else None
                if not isinstance(provider_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", provider_id):
                    provider_id = None
                try:
                    entry = resolve_tool_manifest_entry(workflow=workflow, offered_in_stage=offered_stage, transport_name=name) if isinstance(name, str) else None
                except (ValueError, KeyError):
                    entry = None
                metric = DiagnosticToolMetricV1(
                    workflow=workflow, offered_in_stage=offered_stage,
                    execution_stage=entry.execution_stage if entry else None,
                    manifest_key=entry.key if entry else None,
                    canonical_name=entry.canonical_name if entry else None,
                    input_contract_version=entry.input_contract.version if entry else None,
                    result_contract_version=entry.result_contract.version if entry else None,
                    provider_tool_call_id=provider_id,
                    max_calls_per_operation=entry.budget.max_calls_per_operation if entry else None,
                    max_calls_per_round=entry.budget.max_calls_per_round if entry else None,
                    timeout_ms=entry.budget.timeout_ms if entry else None,
                    manifest_gap=None if entry else "unregistered_tool",
                )
            except Exception:
                pass
            span = uuid4().hex
            parent = active_span.get()
            token = active_span.set(span)
            started = time.perf_counter()
            def emit(name, terminal=False):
                try:
                    sink = active_store.get()
                    if sink is not None and metric is not None:
                        sink.emit(name, harness=active_harness.get(), tool_metric=metric,
                                  span_id=span, parent_span_id=parent,
                                  duration_ms=(time.perf_counter() - started) * 1000 if terminal else None)
                except Exception:
                    pass
            emit("tool_started")
            try:
                output = function(*args, **kwargs)
                result = output.get("result") if isinstance(output, dict) else getattr(output, "result", None)
                ok = result.get("ok") if isinstance(result, dict) else None
                emit("tool_finished" if ok is True else "tool_failed" if ok is False else "tool_unknown", True)
                return output
            except BaseException:
                emit("tool_failed", True)
                raise
            finally:
                active_span.reset(token)
        return observed
    return decorate
