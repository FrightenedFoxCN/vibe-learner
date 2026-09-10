"""Deterministic aggregation of validated diagnostic samples, without I/O."""
from collections import Counter, defaultdict
import math
from app.models.diagnostic import DiagnosticEventV1
from app.models.diagnostic_index import DiagnosticHarnessIndexV1
from app.models.diagnostic_audit import DiagnosticAuditV1, DiagnosticAuditObservationV1, DiagnosticAuditGroupV1, DiagnosticAuditGroupKeyV1

KINDS = {"provider": "provider_call", "provider_attempt": "provider_attempt", "tool": "tool_call"}
STARTS = {"provider_started", "provider_attempt_started", "tool_started"}
ENDS = {"provider_finished", "provider_failed", "provider_attempt_finished", "provider_attempt_failed", "tool_finished", "tool_failed", "tool_unknown"}

def build_diagnostic_audit(events: list[DiagnosticEventV1], traces: list[DiagnosticHarnessIndexV1]) -> DiagnosticAuditV1:
    if len(events) > 10000 or len(traces) > 5000:
        raise ValueError("diagnostic_audit_input_limit")
    unique = {}
    for event in events:
        if event.event_id in unique and unique[event.event_id] != event:
            raise ValueError("diagnostic_audit_event_identity_conflict")
        unique[event.event_id] = event
    indexed = {}
    for trace in traces:
        if trace.trace_id in indexed and indexed[trace.trace_id] != trace:
            raise ValueError("diagnostic_audit_trace_identity_conflict")
        indexed[trace.trace_id] = trace
    spans = defaultdict(list)
    for event in unique.values():
        if event.name not in STARTS | ENDS:
            continue  # HTTP and harness_reference timings would duplicate primary observations.
        kind = "provider_attempt" if event.name.startswith("provider_attempt_") else "provider" if event.name.startswith("provider_") else "tool"
        spans[(kind, event.span_id or event.event_id)].append(event)
    observations = []
    for (kind, identity), records in sorted(spans.items()):
        records.sort(key=lambda item: item.event_id)
        starts = [item for item in records if item.name in STARTS]
        ends = [item for item in records if item.name in ENDS]
        event = ends[0] if ends else records[0]
        gaps = []
        if not starts: gaps.append("missing_start")
        if not ends: gaps.append("missing_terminal")
        if event.span_id is None: gaps.append("missing_span")
        references = {(item.request_id, item.parent_span_id, item.harness.operation_id if item.harness else None, item.harness.trace_id if item.harness else None) for item in records}
        configurations = set()
        for item in records:
            if item.provider_metric:
                metric = item.provider_metric
                configurations.add((metric.adapter, metric.adapter_contract, metric.model, metric.request_kind, metric.timeout_seconds, metric.max_attempts))
            elif item.tool_metric:
                configurations.add(item.tool_metric.model_dump_json())
        conflict = len(starts) > 1 or len(ends) > 1 or len(references) > 1 or len(configurations) > 1
        if conflict: gaps.append("conflicting_span_records")
        harness = event.harness
        components = []
        if harness is None: gaps.append("harness_reference_missing")
        context = indexed.get(harness.trace_id) if harness else None
        if context is not None and context.operation_id == harness.operation_id and context.gap in (None, "terminal_trace_not_available"):
            components = context.components
        else: gaps.append("component_context_unavailable")
        group = dict(kind=KINDS[kind], workflow=harness.workflow if harness else None, stage=harness.stage if harness else None,
                     components=sorted(components, key=lambda item: (item.name, item.version)))
        provider = event.provider_metric
        tool = event.tool_metric
        if provider:
            group.update(provider=provider.adapter, request_kind=provider.request_kind, model=provider.model, provider_contract=provider.adapter_contract,
                         timeout_ms=provider.timeout_seconds * 1000, retry_limit=provider.max_attempts)
            gaps.extend(["endpoint_configuration_not_recorded", "provider_cost_evidence_unavailable"])
            if provider.model_gap: gaps.append("model_label_unreviewed")
            if provider.usage_gap:
                gaps.append("usage_not_additive" if kind != "provider_attempt" else "usage_not_returned" if provider.usage_gap == "not_returned" else "usage_partial_or_invalid")
        elif tool:
            group.update(workflow=tool.workflow, stage=tool.execution_stage or tool.offered_in_stage, tool_name=tool.canonical_name,
                         timeout_ms=tool.timeout_ms, input_contract=tool.input_contract_version, result_contract=tool.result_contract_version,
                         tool_max_calls_operation=tool.max_calls_per_operation, tool_max_calls_round=tool.max_calls_per_round)
        if (kind.startswith("provider") and provider is None) or (kind == "tool" and tool is None):
            gaps.append("metric_missing")
        duration = event.duration_ms if ends and not conflict else None
        if duration is None: gaps.append("duration_unavailable")
        tokens = {key: getattr(provider, key) if provider and provider.usage_source == "provider_reported" and kind == "provider_attempt" and ends and not conflict else None for key in ("input_tokens", "output_tokens", "total_tokens")}
        if conflict:
            group = dict(kind=KINDS[kind])
            harness = None
        observations.append(DiagnosticAuditObservationV1(sample_id=f"{kind}:{identity}", group=DiagnosticAuditGroupKeyV1(**group),
            event_ids=[item.event_id for item in records], operation_id=harness.operation_id if harness else None,
            trace_id=harness.trace_id if harness else None, span_id=event.span_id, parent_span_id=event.parent_span_id,
            outcome=event.outcome if ends and not conflict and event.outcome in {"completed", "failed", "cancelled", "unknown"} else "unknown",
            duration_ms=duration, recovered=bool(provider and kind == "provider" and not conflict and ends and provider.recovered),
            gaps=sorted(set(gaps)), **tokens))
    for trace in sorted(indexed.values(), key=lambda item: item.trace_id):
        available = trace.gap is None and trace.state == "terminal"
        outcome = {"passed": "completed", "repaired": "completed", "failed": "failed", "skipped": "skipped"}.get(trace.status, "unknown") if available else "unknown"
        group = DiagnosticAuditGroupKeyV1(kind="harness_stage", workflow=trace.workflow, stage=trace.stage,
            components=sorted(trace.components, key=lambda item: (item.name, item.version)))
        observations.append(DiagnosticAuditObservationV1(sample_id=f"trace:{trace.trace_id}", group=group,
            operation_id=trace.operation_id, trace_id=trace.trace_id, outcome=outcome, duration_ms=float(trace.duration_ms) if available and trace.duration_ms is not None else None,
            recovered=available and trace.status == "repaired", gaps=(["duration_unavailable"] if trace.duration_ms is None else []) if available else ["missing_terminal" if trace.gap == "terminal_trace_not_available" else "source_unavailable"]))
        attempts_available = trace.gap in (None, "terminal_trace_not_available")
        for attempt in trace.attempts:
            if len(observations) >= 20000: raise ValueError("diagnostic_audit_sample_limit")
            observations.append(DiagnosticAuditObservationV1(sample_id=f"attempt:{attempt.attempt_id}", group=group.model_copy(update={"kind": "harness_attempt", "phase": attempt.phase.value}),
                operation_id=trace.operation_id, trace_id=trace.trace_id,
                outcome={"passed": "completed", "failed": "failed", "skipped": "skipped"}.get(attempt.status.value, "unknown") if attempts_available else "unknown",
                duration_ms=float(attempt.duration_ms) if attempts_available else None, gaps=[] if attempts_available else ["source_unavailable"]))
    if len({item.sample_id for item in observations}) != len(observations):
        raise ValueError("diagnostic_audit_sample_identity_conflict")
    grouped = defaultdict(list)
    for item in observations:
        grouped[item.group.model_dump_json()].append(item)
    summaries = []
    for _, samples in sorted(grouped.items()):
        durations = sorted(item.duration_ms for item in samples if item.duration_ms is not None)
        outcomes = Counter(item.outcome for item in samples)
        gaps = Counter(gap for item in samples for gap in item.gaps)
        tokens = {}
        for field in ("input", "output", "total"):
            values = [getattr(item, f"{field}_tokens") for item in samples if getattr(item, f"{field}_tokens") is not None]
            tokens[f"{field}_tokens"] = sum(values) if values else None
            tokens[f"{field}_token_sample_count"] = len(values)
        summaries.append(DiagnosticAuditGroupV1(key=samples[0].group, sample_count=len(samples),
            **{f"{key}_count": outcomes[key] for key in ("completed", "failed", "cancelled", "unknown", "skipped")},
            recovered_count=sum(item.recovered for item in samples), duration_sample_count=len(durations),
            p50_ms=durations[math.ceil(len(durations)*0.5)-1] if durations else None,
            p95_ms=durations[math.ceil(len(durations)*0.95)-1] if durations else None,
            gaps=[dict(gap=gap, count=count) for gap, count in sorted(gaps.items())], **tokens))
    return DiagnosticAuditV1(observations=observations, groups=summaries, input_event_count=len(unique),
        input_trace_count=len(indexed), duplicate_event_count=len(events)-len(unique))
