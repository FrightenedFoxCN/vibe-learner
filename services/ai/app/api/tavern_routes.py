from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.bootstrap import container
from app.core.logging import get_logger
from app.models.tavern import (
    CreateTavernRoomRequest,
    TavernRoomDetail,
    TavernRoomListResponse,
    TavernRunListResponse,
    TavernTurnRequest,
    TavernTurnResponse,
    UpdateTavernRoomRequest,
)


router = APIRouter(prefix="/tavern", tags=["tavern"])
logger = get_logger("vibe_learner.tavern_routes")


@router.post("/rooms", response_model=TavernRoomDetail)
def create_tavern_room(payload: CreateTavernRoomRequest) -> TavernRoomDetail:
    return container.tavern_service.create_room(payload)


@router.get("/rooms", response_model=TavernRoomListResponse)
def list_tavern_rooms() -> TavernRoomListResponse:
    return TavernRoomListResponse(items=container.tavern_service.list_rooms())


@router.get("/rooms/{room_id}", response_model=TavernRoomDetail)
def get_tavern_room(
    room_id: str,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=200),
) -> TavernRoomDetail:
    return container.tavern_service.require_room(
        room_id,
        after_sequence=after_sequence,
        limit=limit,
    )


@router.get("/rooms/{room_id}/runs", response_model=TavernRunListResponse)
def list_tavern_runs(
    room_id: str,
    limit: int = Query(default=50, ge=1, le=100),
) -> TavernRunListResponse:
    return TavernRunListResponse(items=container.tavern_service.list_runs(room_id, limit=limit))


@router.patch("/rooms/{room_id}", response_model=TavernRoomDetail)
def update_tavern_room(
    room_id: str,
    payload: UpdateTavernRoomRequest,
) -> TavernRoomDetail:
    if not (payload.model_fields_set - {"expected_revision"}):
        raise HTTPException(status_code=400, detail="tavern_update_payload_empty")
    return container.tavern_service.update_room(room_id=room_id, payload=payload)


@router.delete("/rooms/{room_id}")
def delete_tavern_room(
    room_id: str,
    expected_revision: int = Query(ge=0),
) -> dict[str, str]:
    container.tavern_service.delete_room(
        room_id,
        expected_revision=expected_revision,
    )
    return {"deleted_room_id": room_id}


@router.post("/rooms/{room_id}/turns", response_model=TavernTurnResponse)
def run_tavern_turn(room_id: str, payload: TavernTurnRequest) -> TavernTurnResponse:
    try:
        return container.tavern_service.run_turn(room_id=room_id, payload=payload)
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.exception("tavern.turn_failed room_id=%s error=%s", room_id, str(exc))
        raise HTTPException(status_code=502, detail="tavern_model_upstream_error") from exc
