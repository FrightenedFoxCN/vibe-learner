from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.bootstrap import container
from app.core.logging import get_logger
from app.models.tavern import (
    CreateTavernRoomRequest,
    RetryTavernRunRequest,
    TavernErrorDetail,
    TavernRecoveryAction,
    TavernRoomDetail,
    TavernRoomListResponse,
    TavernRunListResponse,
    TavernRunRecoveryResponse,
    TavernTurnRequest,
    TavernTurnResponse,
    UpdateTavernRoomRequest,
)


router = APIRouter(prefix="/tavern", tags=["tavern"])
logger = get_logger("vibe_learner.tavern_routes")


def _structured_tavern_error(
    exc: HTTPException,
    *,
    room_id: str = "",
    idempotency_key: str = "",
    fallback_run_id: str = "",
) -> HTTPException:
    if isinstance(exc.detail, dict) and isinstance(exc.detail.get("code"), str):
        return exc
    raw_detail = str(exc.detail)
    parts = raw_detail.split(":")
    code = parts[0].strip() or "tavern_request_failed"
    run_id = fallback_run_id
    child_run_id = ""
    current_revision = None
    persisted_run = None
    service = container.tavern_service
    if room_id and idempotency_key:
        persisted_run = service.repository.get_run_by_idempotency_key(
            room_id=room_id,
            idempotency_key=idempotency_key,
        )
        if persisted_run is not None:
            run_id = persisted_run.id
    if code in {
        "tavern_run_failed",
        "tavern_run_in_progress",
        "tavern_run_canceled",
        "tavern_run_superseded",
    } and len(parts) > 1:
        run_id = parts[1]
    if code == "tavern_retry_already_created" and len(parts) > 1:
        child_run_id = parts[1]
    if room_id:
        room = service.repository.get_room(room_id, limit=1)
        if room is not None:
            current_revision = room.room.revision

    if exc.status_code == 502 and persisted_run is not None and persisted_run.status.value != "pending":
        action = TavernRecoveryAction.REPLAY_SAME_REQUEST
        code = "tavern_run_failed"
    elif code == "tavern_run_failed":
        action = TavernRecoveryAction.REPLAY_SAME_REQUEST
    elif code == "tavern_run_in_progress":
        action = TavernRecoveryAction.WAIT_AND_RESUME
    elif code == "tavern_retry_already_created":
        action = TavernRecoveryAction.RELOAD_ROOM
    elif code in {
        "tavern_revision_conflict",
        "tavern_continue_anchor_stale",
        "tavern_retry_context_changed",
        "tavern_retry_participant_changed",
        "tavern_run_context_changed",
        "tavern_run_participant_changed",
        "tavern_room_not_active",
    }:
        action = TavernRecoveryAction.RELOAD_ROOM
    else:
        action = TavernRecoveryAction.NONE
    detail = TavernErrorDetail(
        code=code,
        run_id=run_id,
        child_run_id=child_run_id,
        current_revision=current_revision,
        recovery_action=action,
    )
    return HTTPException(
        status_code=exc.status_code,
        detail=detail.model_dump(mode="json"),
        headers=exc.headers,
    )


@router.post("/rooms", response_model=TavernRoomDetail)
def create_tavern_room(payload: CreateTavernRoomRequest) -> TavernRoomDetail:
    try:
        return container.tavern_service.create_room(payload)
    except HTTPException as exc:
        raise _structured_tavern_error(exc) from exc


@router.get("/rooms", response_model=TavernRoomListResponse)
def list_tavern_rooms() -> TavernRoomListResponse:
    return TavernRoomListResponse(items=container.tavern_service.list_rooms())


@router.get("/rooms/{room_id}", response_model=TavernRoomDetail)
def get_tavern_room(
    room_id: str,
    after_sequence: int = Query(default=0, ge=0),
    before_sequence: int | None = Query(default=None, ge=1),
    tail: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=200),
) -> TavernRoomDetail:
    if tail and (before_sequence is not None or after_sequence != 0):
        raise HTTPException(status_code=400, detail="tavern_message_cursor_conflict")
    if before_sequence is not None and after_sequence != 0:
        raise HTTPException(status_code=400, detail="tavern_message_cursor_conflict")
    return container.tavern_service.require_room(
        room_id,
        after_sequence=after_sequence,
        before_sequence=before_sequence,
        tail=tail,
        limit=limit,
    )


@router.get("/rooms/{room_id}/runs", response_model=TavernRunListResponse)
def list_tavern_runs(
    room_id: str,
    limit: int = Query(default=50, ge=1, le=100),
) -> TavernRunListResponse:
    return TavernRunListResponse(items=container.tavern_service.list_runs(room_id, limit=limit))


@router.get(
    "/rooms/{room_id}/run-recovery",
    response_model=TavernRunRecoveryResponse,
)
def get_tavern_run_recovery(
    room_id: str,
    limit: int = Query(default=50, ge=1, le=100),
) -> TavernRunRecoveryResponse:
    return TavernRunRecoveryResponse(
        items=container.tavern_service.list_run_recovery(room_id, limit=limit)
    )


@router.patch("/rooms/{room_id}", response_model=TavernRoomDetail)
def update_tavern_room(
    room_id: str,
    payload: UpdateTavernRoomRequest,
) -> TavernRoomDetail:
    if not (payload.model_fields_set - {"expected_revision"}):
        raise HTTPException(status_code=400, detail="tavern_update_payload_empty")
    try:
        return container.tavern_service.update_room(room_id=room_id, payload=payload)
    except HTTPException as exc:
        raise _structured_tavern_error(exc, room_id=room_id) from exc


@router.delete("/rooms/{room_id}")
def delete_tavern_room(
    room_id: str,
    expected_revision: int = Query(ge=0),
) -> dict[str, str]:
    try:
        container.tavern_service.delete_room(
            room_id,
            expected_revision=expected_revision,
        )
    except HTTPException as exc:
        raise _structured_tavern_error(exc, room_id=room_id) from exc
    return {"deleted_room_id": room_id}


@router.post("/rooms/{room_id}/turns", response_model=TavernTurnResponse)
def run_tavern_turn(room_id: str, payload: TavernTurnRequest) -> TavernTurnResponse:
    try:
        return container.tavern_service.run_turn(room_id=room_id, payload=payload)
    except HTTPException as exc:
        raise _structured_tavern_error(
            exc,
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        ) from exc
    except RuntimeError as exc:
        logger.exception("tavern.turn_failed room_id=%s error=%s", room_id, str(exc))
        mapped = HTTPException(status_code=502, detail="tavern_model_upstream_error")
        raise _structured_tavern_error(
            mapped,
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
        ) from exc


@router.post(
    "/rooms/{room_id}/runs/{run_id}/retry",
    response_model=TavernTurnResponse,
)
def retry_tavern_run(
    room_id: str,
    run_id: str,
    payload: RetryTavernRunRequest,
) -> TavernTurnResponse:
    try:
        return container.tavern_service.retry_run(
            room_id=room_id,
            source_run_id=run_id,
            payload=payload,
        )
    except HTTPException as exc:
        raise _structured_tavern_error(
            exc,
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
            fallback_run_id=run_id,
        ) from exc
    except RuntimeError as exc:
        logger.exception("tavern.retry_failed room_id=%s run_id=%s", room_id, run_id)
        mapped = HTTPException(status_code=502, detail="tavern_model_upstream_error")
        raise _structured_tavern_error(
            mapped,
            room_id=room_id,
            idempotency_key=payload.idempotency_key,
            fallback_run_id=run_id,
        ) from exc


@router.post(
    "/rooms/{room_id}/runs/{run_id}/cancel",
    response_model=TavernTurnResponse,
)
def cancel_tavern_run(room_id: str, run_id: str) -> TavernTurnResponse:
    try:
        return container.tavern_service.cancel_run(room_id=room_id, run_id=run_id)
    except HTTPException as exc:
        raise _structured_tavern_error(
            exc,
            room_id=room_id,
            fallback_run_id=run_id,
        ) from exc


@router.post(
    "/rooms/{room_id}/runs/{run_id}/resume",
    response_model=TavernTurnResponse,
)
def resume_tavern_run(room_id: str, run_id: str) -> TavernTurnResponse:
    try:
        return container.tavern_service.resume_run(room_id=room_id, run_id=run_id)
    except HTTPException as exc:
        raise _structured_tavern_error(
            exc,
            room_id=room_id,
            fallback_run_id=run_id,
        ) from exc
    except RuntimeError as exc:
        logger.exception("tavern.resume_failed room_id=%s run_id=%s", room_id, run_id)
        mapped = HTTPException(status_code=502, detail="tavern_model_upstream_error")
        raise _structured_tavern_error(
            mapped,
            room_id=room_id,
            fallback_run_id=run_id,
        ) from exc
