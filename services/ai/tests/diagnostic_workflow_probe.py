"""Opt-in paired Persona generation -> save -> reload backend overhead probe."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
from tempfile import TemporaryDirectory
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.api.diagnostic_middleware import DiagnosticMiddleware
from app.core.settings import Settings
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.diagnostic_benchmark import summary
from tests.test_persona_lifecycle import create_request


class DisabledDiagnostics:
    """Benchmark-only null sink; production has no disable switch."""
    def __init__(self, *args): pass
    def start(self): pass
    def emit(self, *args, **kwargs): pass
    def close(self): pass


async def without_middleware(self, scope, receive, send):
    return await self.app(scope, receive, send)


def sample(enabled):
    with TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)
        if not enabled:
            stack.enter_context(patch("app.app_factory.DiagnosticStore", DisabledDiagnostics))
            stack.enter_context(patch("app.app_factory.DiagnosticHarnessIndex.start", lambda self: None))
            stack.enter_context(patch("app.app_factory.DesktopDiagnosticSpool.start", lambda self: None))
            stack.enter_context(patch.object(DiagnosticMiddleware, "__call__", without_middleware))
        settings = Settings(storage_root=str(root / "data"), database_url=f"sqlite:///{root / 'domain.db'}",
                            plan_provider="mock", ocr_engine="disabled")
        app = create_app(settings=settings)
        with TestClient(app) as client:
            flow = "synthetic-workflow"
            headers = {"X-Debug-Flow-Id": flow}
            started = time.perf_counter_ns()
            generated_response = client.post("/persona-cards/generate",
                json={"mode": "keywords", "input_text": "PRIVATE_WORKFLOW_PROMPT"},
                headers={**headers, "X-Debug-Action-Id": "generate"})
            assert generated_response.status_code == 200
            generated = generated_response.json()
            assert generated["items"]
            payload = create_request("Synthetic benchmark persona").model_dump(mode="json")
            payload.update(summary=generated["summary"], relationship=generated["relationship"],
                           learner_address=generated["learner_address"])
            payload["slots"] = [{"kind": card["kind"], "label": card["label"], "content": card["content"],
                                 "weight": 50, "locked": False, "sort_order": i} for i, card in enumerate(generated["items"])]
            saved_response = client.post("/personas", json=payload, headers={**headers, "X-Debug-Action-Id": "save"})
            assert saved_response.status_code == 200
            saved = saved_response.json()
            reloaded_response = client.get("/personas", headers={**headers, "X-Debug-Action-Id": "reload"})
            elapsed = (time.perf_counter_ns() - started) / 1_000_000
            assert reloaded_response.status_code == 200
            reloaded = next(item for item in reloaded_response.json()["items"] if item["id"] == saved["id"])
            assert reloaded == saved
            assert [slot["content"] for slot in reloaded["slots"]] == [card["content"] for card in generated["items"]]
            canonical = HarnessRuntimeRepository(app.state.container.database)
            traces = [canonical.get(identity) for identity in canonical.list_trace_ids(limit=100)]
            terminals = [trace.terminal_trace for trace in traces if trace.terminal_trace]
            assert terminals
            measured = dict(elapsed_ms=elapsed, saved_revision=saved["revision"],
                            generated_cards=len(generated["items"]), canonical_terminals=len(terminals),
                            canonical_commit_statuses=sorted(trace.commit_evidence.status.value for trace in terminals),
                            generated_content_read_back=True)
            if enabled:
                store = app.state.diagnostics
                drain_start = time.perf_counter_ns()
                deadline = time.monotonic() + 5
                while store.queue.unfinished_tasks:
                    assert time.monotonic() < deadline, "diagnostic_drain_timeout"
                    time.sleep(.001)
                measured["post_response_drain_ms"] = (time.perf_counter_ns() - drain_start) / 1_000_000
                events = [row["event"] for row in store.query(0, 100, {"flow_id": flow})]
                assert any(e["resource"] and e["resource"]["resource_id"] == saved["id"] for e in events)
                assert {e["action_id"] for e in events} == {"generate", "save", "reload"}
                refs = {e["harness"]["trace_id"] for e in events if e["harness"] and e["harness"]["trace_id"]}
                assert refs and refs <= {t.trace_id for t in terminals}
                assert "PRIVATE_WORKFLOW_PROMPT" not in json.dumps(events)
                measured.update(events=len(events), health=store.health())
                assert measured["health"]["dropped"] == 0
            else:
                assert not (root / "data/diagnostics/events.sqlite3").exists()
            return measured


def run(samples):
    # Fixed before sampling: paired absolute overhead leaves most of the 200 ms
    # interactive response target to domain work; mock timing is not provider SLA.
    budget_ms = 50
    raw = []
    for index in range(samples + 3):
        order = [True, False] if index % 2 else [False, True]
        pair = {enabled: sample(enabled) for enabled in order}
        for key in ("saved_revision", "generated_cards", "canonical_terminals", "canonical_commit_statuses"):
            assert pair[True][key] == pair[False][key], f"unequal_domain_result_{key}"
        if index >= 3:
            raw.append({"first": "enabled" if order[0] else "disabled", "enabled": pair[True], "disabled": pair[False],
                        "delta_ms": pair[True]["elapsed_ms"] - pair[False]["elapsed_ms"]})
    summaries = {name: summary([pair[name]["elapsed_ms"] for pair in raw]) for name in ("enabled", "disabled")}
    summaries["paired_delta"] = summary([pair["delta_ms"] for pair in raw])
    summaries["post_response_drain"] = summary([pair["enabled"]["post_response_drain_ms"] for pair in raw])
    return dict(schema_version="diagnostic-persona-workflow-benchmark-v1", timestamp=datetime.now(timezone.utc).isoformat(),
        platform=platform.platform(), python=platform.python_version(), warmup_pairs=3, sample_pairs=samples,
        scope="Actual in-process ASGI Persona generation with mock provider, application of generated card contents to saved Persona, and persisted reload. Fresh app/storage per sample; timing excludes startup, post-response drain, browser/native UI, network and live provider. Structured console logging remains the same in both modes.",
        disabled_control="Test-only null event sink, middleware bypass, index/spool workers not started; canonical Harness lifecycle unchanged.",
        budget_ms=budget_ms, gate="P95 paired enabled-minus-disabled request-chain overhead <=50 ms; signed deltas retained.",
        passed=summaries["paired_delta"]["p95_ms"] <= budget_ms, summary=summaries, raw=raw,
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1: parser.error("samples must be positive")
    report = run(args.samples)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]: raise SystemExit("workflow_overhead_budget_exceeded")
