"""Bounded, content-free diagnostics. These endpoints do not recurse into collection."""
import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.diagnostic import DiagnosticEventV1, Identity

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
    if any(event.source != "browser" or event.harness is not None or event.resource is not None or event.name in {"harness_reference", "resource_reference"} or len(event.model_dump_json().encode()) > 16384 for event in batch.events):
        raise HTTPException(422, "invalid_diagnostic_source_or_size")
    store = request.app.state.diagnostics
    accepted = sum(store.enqueue(event) for event in batch.events)
    return {"accepted": accepted, "dropped": len(batch.events) - accepted}


@router.get("/events")
def query_events(request: Request, after: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
                 request_id: Identity | None = None, action_id: Identity | None = None,
                 page_view_id: Identity | None = None, flow_id: Identity | None = None,
                 source: Literal["browser", "server", "desktop"] | None = None):
    store = request.app.state.diagnostics
    rows = store.query(after, limit, {"request_id": request_id, "action_id": action_id,
                       "page_view_id": page_view_id, "flow_id": flow_id, "source": source})
    return {"items": rows, "next_cursor": rows[-1]["sequence"] if rows else after,
            "health": store.health()}
