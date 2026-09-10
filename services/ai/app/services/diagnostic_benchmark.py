"""Provider-free diagnostic overhead and retained-storage measurements.

The paired HTTP probe isolates actual ASGI diagnostic middleware, not full
product latency. Synthetic records exercise production writer/query/export code.
"""
import argparse
import hashlib
import os
from contextlib import ExitStack, closing
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import sqlite3
import subprocess
from tempfile import TemporaryDirectory
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.diagnostic_middleware import DiagnosticMiddleware
from app.core.diagnostics import DiagnosticStore
from app.models.diagnostic import DiagnosticEventV1
from app.models.diagnostic_export import DiagnosticExportFiltersV1
from app.models.diagnostic_index import DiagnosticHarnessIndexV1
from app.services.diagnostic_export import build_diagnostic_export, DiagnosticExportTooLarge
from app.services.diagnostic_index import DiagnosticHarnessIndex

WARMUPS = 5


def summary(values):
    ordered = sorted(values)
    return dict(sample_count=len(values), p50_ms=ordered[math.ceil(.5 * len(values)) - 1],
                p95_ms=ordered[math.ceil(.95 * len(values)) - 1], max_ms=max(values))


def measure(callback):
    start = time.perf_counter_ns()
    result = callback()
    return (time.perf_counter_ns() - start) / 1_000_000, result


def files(path):
    result = {}
    for key, suffix in (("database", ""), ("wal", "-wal"), ("shm", "-shm"), ("journal", "-journal"), ("quota_lock", ".quota-lock")):
        candidate = Path(str(path) + suffix)
        result[key + "_bytes"] = candidate.stat().st_size if candidate.exists() else 0
    result["total_bytes"] = sum(result.values())
    return result


def paired_http(root, samples):
    running = DiagnosticStore(root / "http.db")
    stalled = DiagnosticStore(root / "stalled.db", capacity=1)
    running.start()
    raw = {name: [] for name in ("baseline", "writer_running", "queue_full")}
    pair_deltas = {name: [] for name in ("writer_running", "queue_full")}
    try:
        with ExitStack() as stack:
            clients = {}
            for name, store in (("baseline", None), ("writer_running", running), ("queue_full", stalled)):
                app = FastAPI()
                if store is not None:
                    app.state.diagnostics = store
                    app.add_middleware(DiagnosticMiddleware)
                @app.get("/health")
                async def health():
                    return {"ok": True}
                clients[name] = stack.enter_context(TestClient(app))
            for i in range(samples + WARMUPS):
                names = list(clients) if i % 2 == 0 else list(reversed(clients))
                durations = {}
                for name in names:
                    elapsed, response = measure(lambda: clients[name].get("/health"))
                    if response.status_code != 200 or response.json() != {"ok": True}:
                        raise RuntimeError("diagnostic_benchmark_probe_changed")
                    durations[name] = elapsed
                if i >= WARMUPS:
                    for name in clients:
                        raw[name].append(durations[name])
                    for name in pair_deltas:
                        pair_deltas[name].append(durations[name] - durations["baseline"])
            running.queue.join()
        return dict(scope="in_process_TestClient_fixed_async_health_route", raw_ms=raw,
            summaries={name: summary(values) for name, values in raw.items()},
            paired_delta_ms=pair_deltas, paired_delta_summaries={name: summary(values) for name, values in pair_deltas.items()},
            writer_health=running.health(), stalled_health=stalled.health(),
            full_product_latency_claim=False, network_latency_included=False)
    finally:
        running.close()
        stalled.close()


def event(i, trace_count, timestamp):
    operation = i // 2 % trace_count
    terminal = i % 2 == 1
    return DiagnosticEventV1.model_validate_json(json.dumps(dict(event_id=f"event-{i}", source="server",
        name="provider_attempt_finished" if terminal else "provider_attempt_started", timestamp=timestamp,
        request_id=f"request-{operation}", span_id=f"span-{i // 2}", duration_ms=10 if terminal else None,
        harness=dict(operation_id=f"harness-operation-{operation:032x}", trace_id=f"trace-{operation:05}", workflow="persona", stage="persona_generation"),
        provider_metric=dict(request_kind="setting", model="synthetic-model", timeout_seconds=30, attempt_index=1, attempts_used=1,
                             usage_source="unavailable", usage_gap="not_returned"))))


def storage_workload(root, samples, event_count, trace_count):
    store = DiagnosticStore(root / "events.sqlite3")
    index = DiagnosticHarnessIndex(None, root / "harness-index.sqlite3")
    store.start()
    timestamp = datetime.now(timezone.utc).isoformat()
    enqueue_samples, batch_samples = [], []
    try:
        batch_start = time.perf_counter_ns()
        for i in range(event_count):
            # DTO construction is excluded from enqueue timing and included in
            # paced batch duration. Production validation is timed by HTTP probe.
            payload = event(i, trace_count, timestamp)
            duration, accepted = measure(lambda: store.enqueue(payload))
            if not accepted:
                raise RuntimeError("diagnostic_benchmark_unexpected_drop")
            enqueue_samples.append(duration)
            if (i + 1) % 100 == 0 or i + 1 == event_count:
                store.queue.join()
                batch_samples.append((time.perf_counter_ns() - batch_start) / 1_000_000)
                batch_start = time.perf_counter_ns()
        with index._connect() as db:
            for i in range(trace_count):
                projection = DiagnosticHarnessIndexV1.model_validate_json(json.dumps(dict(trace_id=f"trace-{i:05}",
                    operation_id=f"harness-operation-{i:032x}", workflow="persona", stage="persona_generation", source_updated_at=timestamp,
                    state="terminal", status="passed", commit_status="committed", duration_ms=10,
                    components=[dict(name="synthetic-component", version="synthetic-v1")],
                    attempts=[dict(attempt_id=f"attempt-{i}", attempt_index=1, phase="generate", status="passed", duration_ms=10)])))
                db.execute("INSERT INTO projections(trace_id,operation_id,workflow,stage,payload,last_seen_sweep) VALUES (?,?,?,?,?,0)",
                    (projection.trace_id, projection.operation_id, "persona", "persona_generation", projection.model_dump_json()))
            index.retention.prune(db)
            db.commit()
            index_after_population = files(index.path)
        operations = {
            "event_page": lambda: store.query(0, 100, {}, strict=True, with_coverage=True),
            "operation_filter": lambda: store.query(0, 100, {"operation_id": "harness-operation-" + "0" * 32}, strict=True),
            "index_page": lambda: index.query(limit=100),
            "scoped_export": lambda: build_diagnostic_export(store, index, DiagnosticExportFiltersV1(operation_id="harness-operation-" + "0" * 32), "0.3.1"),
        }
        raw = {name: [] for name in operations}
        for i in range(samples + WARMUPS):
            for name, operation in operations.items():
                elapsed, result = measure(operation)
                if name == "index_page" and result["coverage"]["freshness"] != "eventual":
                    raise RuntimeError("diagnostic_benchmark_index_unavailable")
                if i >= WARMUPS:
                    raw[name].append(elapsed)
        try:
            elapsed, package = measure(lambda: build_diagnostic_export(store, index, DiagnosticExportFiltersV1(), "0.3.1"))
            full_export = dict(outcome="completed", duration_ms=elapsed, bytes=len(package))
        except DiagnosticExportTooLarge:
            full_export = dict(outcome="bounded_refusal", duration_ms=None, bytes=None)
        with closing(sqlite3.connect(store.path)) as db:
            retained = store.retention.coverage(db, 0)
            links = store.link_retention.coverage(db)
            before = files(store.path)
            elapsed, _ = measure(lambda: store.disk_maintenance.maintain(db, force=True))
            after = files(store.path)
        with index._connect() as db:
            index_coverage = index.retention.coverage(db)
            index.disk_maintenance.maintain(db, force=True)
        return dict(synthetic_fixture="diagnostic-local-load-v1", quota_limits_bytes=dict(events=store.quota.max_bytes, index=index.quota.max_bytes), inserted_events=event_count, inserted_projections=trace_count,
            enqueue_raw_ms=enqueue_samples, enqueue_summary=summary(enqueue_samples),
            paced_batch_raw_ms=batch_samples, paced_batch_summary=summary(batch_samples),
            batch_size=100, raw_ms=raw, summaries={name: summary(values) for name, values in raw.items()},
            full_export=full_export, event_retention=retained, link_retention=links, index_retention=index_coverage,
            files_before_event_maintenance=before, files_after_event_maintenance=after, index_files=files(index.path), index_files_after_population=index_after_population,
            maintenance_ms=elapsed, health=store.health(), total_disk_limit_certified=False)
    finally:
        store.close()


def pinned_reader_workload(root, count=500):
    """Bounded experiment only; the 64 MiB stop is not a production quota."""
    store = DiagnosticStore(root / "pinned.sqlite3")
    store.start()
    store.emit("lifecycle_started")
    store.queue.join()
    try:
        with closing(sqlite3.connect(store.path)) as reader, closing(sqlite3.connect(store.path)) as maintainer:
            reader.execute("BEGIN")
            original_count = reader.execute("SELECT count(*) FROM events").fetchone()[0]
            before = files(store.path)
            written = 0
            started = time.perf_counter_ns()
            while written < count:
                for _ in range(min(50, count - written)):
                    store.emit("lifecycle_started")
                    written += 1
                store.queue.join()
                if files(store.path)["total_bytes"] >= 64 * 1024 * 1024:
                    break
            write_ms = (time.perf_counter_ns() - started) / 1_000_000
            store.disk_maintenance.maintain(maintainer, force=True)
            pinned = files(store.path)
            if reader.execute("SELECT count(*) FROM events").fetchone()[0] != original_count:
                raise RuntimeError("diagnostic_benchmark_snapshot_changed")
            reader.rollback()
            store.disk_maintenance.maintain(maintainer, force=True)
            released = files(store.path)
            return dict(written_events=written, write_ms=write_ms, before=before, reader_pinned=pinned,
                reader_released=released, maintenance_busy=store.disk_maintenance.busy,
                maintenance_failures=store.disk_maintenance.failures, health=store.health(),
                experiment_stop_bytes=64 * 1024 * 1024, production_quota_claim=False)
    finally:
        store.close()


def run(samples=30, event_count=12000, trace_count=1000):
    if not 1 <= samples <= 1000 or not 100 <= event_count <= 100000 or not 1 <= trace_count <= 5000:
        raise ValueError("diagnostic_benchmark_bounds")
    repo = Path(__file__).resolve().parents[4]
    source_paths = sorted((repo / "services/ai/app").glob("**/diagnostic*.py"))
    source_hashes = {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()
    with TemporaryDirectory(prefix="diagnostic-benchmark-") as directory:
        root = Path(directory)
        return dict(schema_version="diagnostic-local-benchmark-v1", created_at=datetime.now(timezone.utc).isoformat(),
            git_revision=revision, diagnostic_source_sha256=source_hashes, environment=dict(os=platform.system(), os_release=platform.release(), machine=platform.machine(), logical_cpu_count=os.cpu_count(),
                python=platform.python_version(), sqlite=sqlite3.sqlite_version, fastapi=version("fastapi"), pydantic=version("pydantic")),
            samples=samples, warmups=WARMUPS, percentile_method="nearest_rank", acceptance="measurement_only_no_budget_certification",
            provider_calls=0, http=paired_http(root, samples), storage=storage_workload(root, samples, event_count, trace_count), pinned_reader=pinned_reader_workload(root))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--events", type=int, default=12000)
    parser.add_argument("--traces", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.samples, args.events, args.traces)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(dict(output=str(args.output), http=result["http"]["summaries"], storage=result["storage"]["summaries"], full_export=result["storage"]["full_export"])))


if __name__ == "__main__":
    main()
