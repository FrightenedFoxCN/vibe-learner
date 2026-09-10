"""Bounded, content-free diagnostics. These endpoints do not recurse into collection."""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.diagnostics import DiagnosticQueryUnavailable
from app.models.harness import HarnessWorkflow, HarnessStage
from app.models.diagnostic import DiagnosticEventV1, Identity, DiagnosticPagePath

router = APIRouter(prefix="/diagnostics", tags=["diagnostics"])


class DiagnosticBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    events: list[DiagnosticEventV1] = Field(max_length=100)


@router.post("/events")
async def ingest(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 100 * 16384:
            raise HTTPException(413, "diagnostic_batch_too_large")
    try:
        batch = DiagnosticBatch.model_validate_json(raw)
    except ValidationError:
        # Pydantic's default error detail includes input values; never echo them.
        raise HTTPException(422, "invalid_diagnostic_batch") from None
    if any(event.source != "browser" or event.desktop_metric is not None or event.category == "desktop" or event.tool_metric is not None or event.name.startswith("tool_") or event.provider_metric is not None or event.name.startswith("provider_") or event.harness is not None or event.resource is not None or event.name in {"harness_reference", "resource_reference"} or len(event.model_dump_json().encode()) > 16384 for event in batch.events):
        raise HTTPException(422, "invalid_diagnostic_source_or_size")
    store = request.app.state.diagnostics
    accepted = sum(store.enqueue(event) for event in batch.events)
    return {"accepted": accepted, "dropped": len(batch.events) - accepted}


@router.get("/events")
def query_events(request: Request, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                 request_id: Identity | None = None, action_id: Identity | None = None,
                 page_view_id: Identity | None = None, flow_id: Identity | None = None,
                 source: Literal["browser", "server", "desktop"] | None = None, page_path: DiagnosticPagePath | None = None,
                 severity: Literal["info", "warning", "error"] | None = None,
                 operation_id: Identity | None = None, workflow: HarnessWorkflow | None = None, stage: HarnessStage | None = None,
                 resource_id: str | None = Query(None, max_length=160, pattern=r"^[A-Za-z0-9:._-]{1,160}$"),
                 resource_type: Literal["persona"] | None = None,
                 since: datetime | None = None, until: datetime | None = None):
    if any(value is not None and value.utcoffset() is None for value in (since, until)):
        raise HTTPException(422, "diagnostic_time_timezone_required")
    if since is not None and until is not None and since >= until:
        raise HTTPException(422, "diagnostic_time_range_invalid")
    store = request.app.state.diagnostics
    try:
        rows, retention = store.query(after, limit + 1, {"request_id": request_id, "action_id": action_id,
            "page_view_id": page_view_id, "flow_id": flow_id, "source": source, "page_path": page_path,
            "severity": severity, "operation_id": operation_id, "workflow": workflow, "stage": stage,
            "resource_id": resource_id, "resource_type": resource_type,
            "since": since.isoformat() if since else None, "until": until.isoformat() if until else None}, strict=True, with_coverage=True)
    except DiagnosticQueryUnavailable:
        raise HTTPException(503, "diagnostic_query_unavailable") from None
    has_more = len(rows) > limit
    rows = rows[:limit]
    spool = getattr(request.app.state, "desktop_diagnostic_spool", None)
    return {"desktop_spool": {"rejected": spool.rejected, "failures": spool.failures} if spool else None,
            "items": rows, "next_cursor": rows[-1]["sequence"] if rows else after, "has_more": has_more,
            "health": store.health(), "retention": retention}


@router.get("/harness-index")
def query_harness_index(request: Request, after: str = Query("", max_length=160),
                        limit: int = Query(100, ge=1, le=100), operation_id: Identity | None = None,
                        workflow: HarnessWorkflow | None = None, stage: HarnessStage | None = None):
    index = getattr(request.app.state, "diagnostic_index", None)
    if index is None:
        raise HTTPException(503, "diagnostic_index_unavailable")
    return index.query(after=after, limit=limit, operation_id=operation_id, workflow=workflow, stage=stage)


@router.get("/operation-links")
def query_operation_links(request: Request, operation_id: Identity, after: str = Query("", max_length=96), limit: int = Query(100, ge=1, le=100)):
    return request.app.state.diagnostics.operation_links(operation_id, after, limit)


@router.get("/writers")
def query_writers(request: Request, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100)):
    try:
        return request.app.state.diagnostics.writer_coverage.query(after, limit)
    except Exception:
        request.app.state.diagnostics.read_failures += 1
        raise HTTPException(503, "diagnostic_writer_coverage_unavailable") from None


@router.post("/export")
async def export_diagnostics(request: Request):
    from starlette.concurrency import run_in_threadpool
    from starlette.responses import Response
    from app.models.diagnostic_export import DiagnosticExportFiltersV1
    from app.services.diagnostic_export import build_diagnostic_export, DiagnosticExportTooLarge, DiagnosticExportUnavailable
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 8192:
            raise HTTPException(413, "diagnostic_export_filter_too_large")
    try:
        filters = DiagnosticExportFiltersV1.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "invalid_diagnostic_export_filter") from None
    try:
        data = await run_in_threadpool(build_diagnostic_export, request.app.state.diagnostics,
            getattr(request.app.state, "diagnostic_index", None), filters, request.app.version)
    except DiagnosticExportTooLarge:
        raise HTTPException(413, "diagnostic_export_too_large") from None
    except DiagnosticExportUnavailable:
        raise HTTPException(503, "diagnostic_export_unavailable") from None
    return Response(data, media_type="application/json", headers={
        "Content-Disposition": 'attachment; filename="vibe-learner-diagnostics.json"', "Cache-Control": "no-store"})
