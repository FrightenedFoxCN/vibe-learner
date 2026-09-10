"""Bounded, validated snapshot export; never reads business/protected storage."""
from contextlib import closing
from datetime import datetime, timezone
import sqlite3
import json
import time

from app.core.diagnostics import diagnostic_event_predicate
from app.models.diagnostic import DiagnosticEventV1, DiagnosticOperationLinkV1
from app.models.diagnostic_export import DiagnosticExportFiltersV1, DiagnosticExportV1
from app.models.diagnostic_index import DiagnosticHarnessIndexV1
from app.services.diagnostic_audit import build_diagnostic_audit

MAX_EXPORT_BYTES = 32 * 1024 * 1024
MAX_INPUT_BYTES = 16 * 1024 * 1024


class DiagnosticExportUnavailable(RuntimeError):
    pass


class DiagnosticExportTooLarge(RuntimeError):
    pass


def _connect(path, deadline):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=0.1)
    db.row_factory = sqlite3.Row
    db.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
    db.execute("BEGIN")
    return db


class _Budget:
    def __init__(self, deadline):
        self.bytes = 0
        self.deadline = deadline

    def check(self, payload=""):
        if time.monotonic() >= self.deadline:
            raise DiagnosticExportUnavailable("diagnostic_export_unavailable")
        self.bytes += len(payload.encode("utf-8"))
        if self.bytes > MAX_INPUT_BYTES:
            raise DiagnosticExportTooLarge("diagnostic_export_too_large")


def build_diagnostic_export(store, index, filters: DiagnosticExportFiltersV1, app_version: str) -> bytes:
    """No live pagination: each database is read through one pinned transaction.

    Event filters select events. Traces provide contextual operation records, so
    time/source/severity filters never imply trace-duration interval filtering.
    Oversized exports fail atomically instead of quietly dropping tail records.
    """
    try:
        deadline = time.monotonic() + 5
        budget = _Budget(deadline)
        values = filters.model_dump(mode="json", exclude_none=True)
        scope = "related_operations" if any(key not in ("workflow", "stage") for key in values) else "workflow_stage" if values else "all_retained"
        predicate, params = diagnostic_event_predicate(0, values)
        events, links = [], []
        operations, requests = set(), set()
        # Pin event snapshot with the first retention read. A concurrent writer
        # may append/prune after this read without changing any export member.
        with closing(_connect(store.path, deadline)) as db:
            retention = store.retention.coverage(db, 0)
            for row in db.execute("SELECT e.sequence,e.event_id,e.payload FROM events e WHERE " + predicate + " ORDER BY e.sequence LIMIT 10001", params):
                if len(events) == 10000:
                    raise DiagnosticExportTooLarge("diagnostic_export_too_large")
                budget.check(row["payload"])
                event = DiagnosticEventV1.model_validate_json(row["payload"])
                if event.event_id != row["event_id"]:
                    raise ValueError("diagnostic_event_identity_mismatch")
                events.append(dict(sequence=row["sequence"], event=event))
                if event.request_id:
                    requests.add(event.request_id)
                if event.harness:
                    operations.add(event.harness.operation_id)
            if filters.operation_id:
                operations.add(filters.operation_id)
            # JSON membership avoids SQLite's host parameter ceiling. Only
            # one hop is followed: selected events/explicit operation -> links.
            link_where, link_args = "", []
            if scope == "related_operations":
                link_where = " WHERE request_id IN (SELECT value FROM json_each(?)) OR operation_id IN (SELECT value FROM json_each(?))"
                link_args = [json.dumps(sorted(requests)), json.dumps(sorted(operations))]
            elif scope == "workflow_stage":
                link_where = " WHERE " + " AND ".join(f"json_extract(payload, '$.{key}')=?" for key in ("workflow", "stage") if key in values)
                link_args = [values[key] for key in ("workflow", "stage") if key in values]
            for row in db.execute("SELECT operation_id,request_id,payload FROM operation_links" + link_where + " ORDER BY operation_id,request_id LIMIT 5001", link_args):
                if len(links) == 5000:
                    raise DiagnosticExportTooLarge("diagnostic_export_too_large")
                budget.check(row["payload"])
                link = DiagnosticOperationLinkV1.model_validate_json(row["payload"])
                if (link.operation_id, link.request_id) != (row["operation_id"], row["request_id"]):
                    raise ValueError("diagnostic_link_identity_mismatch")
                links.append(link)
            operations.update(link.operation_id for link in links)
            writer_pages = []
            after = 0
            while True:
                budget.check()
                page = store.writer_coverage.read_snapshot(db, after)
                writer_pages.append(page)
                if len(writer_pages) > 3:
                    raise DiagnosticExportTooLarge("diagnostic_export_too_large")
                if not page["has_more"]:
                    break
                after = page["next_cursor"]
        traces = []
        coverage = dict(freshness="unavailable", scope=scope, missing_operation_count=len(operations))
        # Missing index is an explicit coverage gap; a present but unreadable or
        # corrupt database fails the whole export, never leaks raw SQL/data.
        if index is not None and index.path.exists():
            with closing(_connect(index.path, deadline)) as db:
                checkpoint = db.execute("SELECT cursor,sweeps FROM checkpoint WHERE name='runtime'").fetchone()
                if checkpoint is None:
                    raise ValueError("diagnostic_index_checkpoint_missing")
                clauses, args = [], []
                if scope == "related_operations":
                    clauses.append("operation_id IN (SELECT value FROM json_each(?))")
                    args.append(json.dumps(sorted(operations)))
                for key in ("workflow", "stage"):
                    if key in values:
                        clauses.append(key + "=?")
                        args.append(values[key])
                sql = "SELECT trace_id,operation_id,workflow,stage,payload FROM projections"
                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)
                for row in db.execute(sql + " ORDER BY trace_id LIMIT 5001", args):
                    if len(traces) == 5000:
                        raise DiagnosticExportTooLarge("diagnostic_export_too_large")
                    budget.check(row["payload"])
                    trace = DiagnosticHarnessIndexV1.model_validate_json(row["payload"])
                    if (trace.trace_id, trace.operation_id, trace.workflow, trace.stage) != (row["trace_id"], row["operation_id"], row["workflow"], row["stage"]):
                        raise ValueError("diagnostic_index_identity_mismatch")
                    traces.append(trace)
                coverage.update(freshness="eventual", cursor=checkpoint["cursor"], completed_sweeps=checkpoint["sweeps"],
                                missing_operation_count=len(operations - {trace.operation_id for trace in traces}))
        budget.check()
        try:
            audit = build_diagnostic_audit([row["event"] for row in events], traces)
        except ValueError as error:
            if str(error) in {"diagnostic_audit_input_limit", "diagnostic_audit_sample_limit"}:
                raise DiagnosticExportTooLarge("diagnostic_export_too_large") from None
            raise
        result = DiagnosticExportV1(app_version=app_version, created_at=datetime.now(timezone.utc), filters=filters,
            events=events, operation_links=links, retention=retention, writer_pages=writer_pages,
            index=traces, index_coverage=coverage, audit=audit).model_dump_json().encode("utf-8")
        budget.check()
        if len(result) > MAX_EXPORT_BYTES:
            raise DiagnosticExportTooLarge("diagnostic_export_too_large")
        return result
    except DiagnosticExportTooLarge:
        raise
    except Exception:
        store.read_failures += 1
        raise DiagnosticExportUnavailable("diagnostic_export_unavailable") from None
