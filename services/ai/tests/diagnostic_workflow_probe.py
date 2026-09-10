"""Opt-in paired Persona/Scene generation -> save -> reload backend overhead probe."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import gc
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
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


def sample(enabled, workflow="persona", profile_stages=False):
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
            prepared = None
            if workflow == "document_plan":
                from tests.diagnostic_document_plan_probe import prepare, chain
                prepared = prepare(client)
            stages = {}
            collections = []
            active_collections = {}
            def observe_gc(phase, info):
                generation = info["generation"]
                now = time.perf_counter_ns()
                if phase == "start":
                    active_collections[generation] = now
                elif generation in active_collections:
                    collections.append({"generation": generation,
                        "start_ns": active_collections.pop(generation), "end_ns": now})
            if profile_stages:
                gc.callbacks.append(observe_gc)
                stack.callback(gc.callbacks.remove, observe_gc)
            def request(method, url, **kwargs):
                before = time.perf_counter_ns()
                response = client.request(method, url, **kwargs)
                after = time.perf_counter_ns()
                if profile_stages:
                    stages[kwargs["headers"]["X-Debug-Action-Id"]] = (before, after)
                return response
            started = time.perf_counter_ns()
            if workflow == "persona":
                generated_response = request("POST", "/persona-cards/generate",
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
                saved_response = request("POST", "/personas", json=payload, headers={**headers, "X-Debug-Action-Id": "save"})
                assert saved_response.status_code == 200
                saved = saved_response.json()
                reloaded_response = request("GET", "/personas", headers={**headers, "X-Debug-Action-Id": "reload"})
                elapsed = (time.perf_counter_ns() - started) / 1_000_000
                assert reloaded_response.status_code == 200
                reloaded = next(item for item in reloaded_response.json()["items"] if item["id"] == saved["id"])
                assert reloaded == saved
                assert [slot["content"] for slot in reloaded["slots"]] == [card["content"] for card in generated["items"]]
            elif workflow == "scene":
                generated_response = request("POST", "/scene-setup/generate",
                    json={"mode": "keywords", "input_text": "PRIVATE_WORKFLOW_PROMPT"},
                    headers={**headers, "X-Debug-Action-Id": "generate"})
                assert generated_response.status_code == 200
                generated = generated_response.json()
                payload = {key: generated[key] for key in (
                    "scene_name", "scene_summary", "scene_layers", "selected_layer_id")}
                payload.update(contract_version="scene-committed-save-v1",
                               expected_revision=0, collapsed_layer_ids=[])
                saved_response = request("POST", "/scene-library", json=payload,
                    headers={**headers, "X-Debug-Action-Id": "save"})
                assert saved_response.status_code == 200
                saved = saved_response.json()
                reloaded_response = request("GET", f"/scene-library/{saved['scene_id']}",
                    headers={**headers, "X-Debug-Action-Id": "reload"})
                elapsed = (time.perf_counter_ns() - started) / 1_000_000
                assert reloaded_response.status_code == 200
                reloaded = reloaded_response.json()
                assert reloaded == saved
                for key in ("scene_name", "scene_summary", "scene_layers", "selected_layer_id"):
                    assert reloaded[key] == generated[key], f"scene_read_back_mismatch_{key}"
                assert reloaded["collapsed_layer_ids"] == []
            else:
                domain_result, resource_refs, expected_actions = chain(request, headers, prepared)
                elapsed = (time.perf_counter_ns() - started) / 1_000_000
            if workflow in ("persona", "scene"):
                count_key = "generated_cards" if workflow == "persona" else "generated_root_layers"
                domain_result = {"saved_revision": saved["revision"],
                    count_key: len(generated["items" if workflow == "persona" else "scene_layers"])}
                assert domain_result[count_key] > 0
                resource_refs = {("persona" if workflow == "persona" else "scene",
                                  saved["id" if workflow == "persona" else "scene_id"])}
                expected_actions = {"generate", "save", "reload"}
            if profile_stages:
                stage_measurements = {name: {
                    "elapsed_ms": (end - begin) / 1_000_000,
                    "gc_overlap_ms": sum(max(0, min(end, c["end_ns"]) - max(begin, c["start_ns"]))
                                         for c in collections) / 1_000_000,
                } for name, (begin, end) in stages.items()}
                collection_measurements = [{"generation": c["generation"],
                    "duration_ms": (c["end_ns"] - c["start_ns"]) / 1_000_000}
                    for c in collections if c["start_ns"] >= started]
            canonical = HarnessRuntimeRepository(app.state.container.database)
            traces = [canonical.get(identity) for identity in canonical.list_trace_ids(limit=100)]
            terminals = [trace.terminal_trace for trace in traces if trace.terminal_trace]
            assert terminals
            measured = dict(elapsed_ms=elapsed, domain_result=domain_result, **domain_result,
                            canonical_terminals=len(terminals),
                            canonical_commit_statuses=sorted(trace.commit_evidence.status.value for trace in terminals),
                            generated_content_read_back=True)
            if profile_stages:
                measured.update(stages=stage_measurements, gc_collections=collection_measurements)
            if enabled:
                store = app.state.diagnostics
                drain_start = time.perf_counter_ns()
                deadline = time.monotonic() + 5
                while store.queue.unfinished_tasks:
                    assert time.monotonic() < deadline, "diagnostic_drain_timeout"
                    time.sleep(.001)
                measured["post_response_drain_ms"] = (time.perf_counter_ns() - drain_start) / 1_000_000
                events = [row["event"] for row in store.query(0, 100, {"flow_id": flow})]
                assert resource_refs <= {(e["resource"]["resource_type"], e["resource"]["resource_id"]) for e in events if e["resource"]}
                assert {e["action_id"] for e in events} == expected_actions
                refs = {e["harness"]["trace_id"] for e in events if e["harness"] and e["harness"]["trace_id"]}
                if workflow == "document_plan":
                    operations = {e["harness"]["operation_id"] for e in events
                                  if e["harness"] and e["harness"]["operation_id"]}
                    assert operations
                    assert {e["harness"]["workflow"] for e in events if e["harness"]} == {"document_parse", "ocr", "study_unit_cleanup", "planning"}
                    linked = [t for operation in operations for t in canonical.list_operation_traces(operation)]
                    assert {t.trace_id for t in linked} == {t.trace_id for t in terminals}
                    for stage in ("document_parse", "plan_generation"):
                        parents = [t for t in terminals if t.stage.value == stage]
                        assert len(parents) == 1 and parents[0].commit_evidence.status.value == "committed"
                    assert refs <= {t.trace_id for t in terminals}
                    measured["canonical_operations_verified"] = len(operations)
                else:
                    assert refs and refs <= {t.trace_id for t in terminals}
                assert all(value not in json.dumps(events) for value in ("PRIVATE_WORKFLOW_PROMPT", "PRIVATE_DOCUMENT_CONTENT", "PRIVATE_WORKFLOW_FILENAME"))
                measured.update(events=len(events), health=store.health())
                assert measured["health"]["dropped"] == 0
            else:
                assert not (root / "data/diagnostics/events.sqlite3").exists()
            return measured


def isolated_sample(enabled, workflow, profile_stages):
    # Keep normal GC enabled; prevent a preceding temporary application's object
    # graph and allocation counters from determining this sample's collection.
    with TemporaryDirectory() as directory:
        output = Path(directory) / "sample.json"
        command = [sys.executable, "-m", "tests.diagnostic_workflow_probe",
                   "--workflow", workflow, "--single-mode", "enabled" if enabled else "disabled",
                   "--output", str(output)]
        if profile_stages:
            command.append("--profile-stages")
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL, timeout=60)
        return json.loads(output.read_text())


def run(samples, workflow="persona", profile_stages=False, isolate_samples=False):
    # Fixed before sampling: paired absolute overhead leaves most of the 200 ms
    # interactive response target to domain work; mock timing is not provider SLA.
    budget_ms = 50
    raw = []
    for index in range(samples + 3):
        order = [True, False] if index % 2 else [False, True]
        sampler = isolated_sample if isolate_samples else sample
        pair = {enabled: sampler(enabled, workflow, profile_stages) for enabled in order}
        for key in ("domain_result", "canonical_terminals", "canonical_commit_statuses"):
            assert pair[True][key] == pair[False][key], f"unequal_domain_result_{key}"
        if index >= 3:
            raw.append({"first": "enabled" if order[0] else "disabled", "enabled": pair[True], "disabled": pair[False],
                        "delta_ms": pair[True]["elapsed_ms"] - pair[False]["elapsed_ms"]})
    summaries = {name: summary([pair[name]["elapsed_ms"] for pair in raw]) for name in ("enabled", "disabled")}
    summaries["paired_delta"] = summary([pair["delta_ms"] for pair in raw])
    summaries["post_response_drain"] = summary([pair["enabled"]["post_response_drain_ms"] for pair in raw])
    return dict(schema_version=f"diagnostic-{workflow}-workflow-benchmark-v1", timestamp=datetime.now(timezone.utc).isoformat(),
        stage_profiling=profile_stages, isolated_sample_processes=isolate_samples, gc_policy="Python default; no forced collection or disabling", platform=platform.platform(), python=platform.python_version(), warmup_pairs=3, sample_pairs=samples,
        scope=f"Actual in-process ASGI {workflow} generation with mock provider and persisted reload; document_plan includes PDF upload and actual parsing and Planning streams. Fresh app/storage per sample; timing excludes startup, post-response drain, browser/native UI, network and live provider. Structured console logging remains the same in both modes.",
        disabled_control="Test-only null event sink, middleware bypass, index/spool workers not started; canonical Harness lifecycle unchanged.",
        budget_ms=budget_ms, gate="P95 paired enabled-minus-disabled request-chain overhead <=50 ms; signed deltas retained.",
        passed=summaries["paired_delta"]["p95_ms"] <= budget_ms, summary=summaries, raw=raw,
        probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        helper_sha256=(hashlib.sha256(Path(__file__).with_name("diagnostic_document_plan_probe.py").read_bytes()).hexdigest()
                       if workflow == "document_plan" else None))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--isolate-samples", action="store_true")
    parser.add_argument("--single-mode", choices=("enabled", "disabled"), help=argparse.SUPPRESS)
    parser.add_argument("--profile-stages", action="store_true")
    parser.add_argument("--workflow", choices=("persona", "scene", "document_plan"), default="persona")
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 1: parser.error("samples must be positive")
    if args.single_mode:
        report = sample(args.single_mode == "enabled", args.workflow, args.profile_stages)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        raise SystemExit(0)
    report = run(args.samples, args.workflow, args.profile_stages, args.isolate_samples)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    if not report["passed"]: raise SystemExit("workflow_overhead_budget_exceeded")
