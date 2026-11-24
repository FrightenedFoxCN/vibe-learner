"""Direct user CRUD, search, and portable archives for a single Study Session."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import ValidationError
from starlette.types import Receive, Scope, Send

from app.api.dependencies import get_container
from app.core.bootstrap import Container
from app.models.study_notes import (
    STUDY_NOTE_ARCHIVE_LIMIT,
    STUDY_NOTE_ID_PATTERN,
    STUDY_NOTE_REVISION_MAX,
    StudyNote,
    StudyNoteArchiveV1,
    StudyNoteImportReceipt,
    StudyNoteInput,
    StudyNoteList,
    StudyNoteMemoryImport,
    StudyNoteUpdate,
)
from app.persistence.study_note_repository import (
    StudyNoteNotFound,
    StudyNoteRevisionConflict,
)
from app.persistence.study_session_repository import StudySessionNotFound


class StudyNotesRoute(APIRoute):
    async def handle(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Bound JSON before FastAPI buffers/parses it, including chunked requests.
        method = scope["method"]
        if method not in {"POST", "PATCH"} or method not in (self.methods or ()):
            await super().handle(scope, receive, send)
            return
        maximum = (5 * 1024 if self.path.endswith("/notes/import") else 256) * 1024
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > maximum:
                error = JSONResponse(
                    {"detail": "study_note_body_too_large"}, status_code=413
                )
                await error(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        pending = True

        async def replay():
            nonlocal pending
            if pending:
                pending = False
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await super().handle(scope, replay, send)

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                response = await handler(request)
            except RequestValidationError as exc:
                # Do not echo user note text (possibly ill-formed Unicode) in errors.
                raise HTTPException(
                    422,
                    [
                        {name: error[name] for name in ("type", "loc", "msg")}
                        for error in exc.errors()
                    ],
                    headers={"Cache-Control": "no-store"},
                ) from exc
            except StudySessionNotFound as exc:
                raise HTTPException(404, "session_not_found") from exc
            except StudyNoteNotFound as exc:
                raise HTTPException(404, "study_note_not_found") from exc
            except StudyNoteRevisionConflict as exc:
                raise HTTPException(
                    409,
                    {
                        "code": "study_note_revision_conflict",
                        "current_revision": exc.current_revision,
                    },
                ) from exc
            response.headers["Cache-Control"] = "no-store"
            return response

        return handle


router = APIRouter(
    prefix="/study-sessions/{session_id}/notes", route_class=StudyNotesRoute
)

_Container = Annotated[Container, Depends(get_container)]
_SessionId = Annotated[str, Path(min_length=1, max_length=64, pattern=r"^[^\x00]+$")]
_NoteId = Annotated[str, Path(pattern=STUDY_NOTE_ID_PATTERN)]


@router.get("", summary="List or search saved notes in a Study Session")
def list_notes(
    session_id: _SessionId,
    container: _Container,
    q: Annotated[str, Query(max_length=120, pattern=r"^[^\x00]*$")] = "",
    offset: Annotated[int, Query(ge=0, le=2_147_483_647)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> StudyNoteList:
    return container.study_note_repository.search(
        session_id, query=q, offset=offset, limit=limit
    )


@router.post("", status_code=201, summary="Create a Study Note")
def create_note(
    session_id: _SessionId, note: StudyNoteInput, container: _Container
) -> StudyNote:
    return container.study_note_repository.create(session_id, note)


@router.get("/export", summary="Download a versioned JSON archive of Study Notes")
def export_notes(
    session_id: _SessionId,
    response: Response,
    container: _Container,
    after: Annotated[str | None, Query(pattern=STUDY_NOTE_ID_PATTERN)] = None,
    limit: Annotated[
        int, Query(ge=1, le=STUDY_NOTE_ARCHIVE_LIMIT)
    ] = STUDY_NOTE_ARCHIVE_LIMIT,
) -> StudyNoteArchiveV1:
    archive = container.study_note_repository.export(
        session_id, after=after, limit=limit
    )
    response.headers["Content-Disposition"] = (
        'attachment; filename="study-notes-v1.json"'
    )
    return archive


@router.post(
    "/import", status_code=201, summary="Append Study Notes from a JSON archive"
)
def import_notes(
    session_id: _SessionId, archive: StudyNoteArchiveV1, container: _Container
) -> StudyNoteImportReceipt:
    rows = container.study_note_repository.insert_many(session_id, archive.notes)
    return StudyNoteImportReceipt(note_ids=[note.id for note in rows])


@router.post(
    "/import-memory",
    status_code=201,
    summary="Copy selected legacy session memory into Study Notes",
)
def import_memory(
    session_id: _SessionId, selection: StudyNoteMemoryImport, container: _Container
) -> StudyNoteImportReceipt:
    session = container.study_session_service.require_session(session_id)
    if len(set(selection.keys)) != len(selection.keys):
        raise HTTPException(422, "study_note_duplicate_memory_keys")
    by_key = {}
    ambiguous = set()
    for entry in session.session_memory:
        if entry.key in by_key:
            ambiguous.add(entry.key)
        by_key[entry.key] = entry
    if any(key not in by_key or key in ambiguous for key in selection.keys):
        raise HTTPException(422, "study_note_memory_key_unavailable")
    try:
        notes = [
            StudyNoteInput(title=key, content=by_key[key].content)
            for key in selection.keys
        ]
    except ValidationError as exc:
        raise HTTPException(422, "study_note_memory_content_invalid") from exc
    rows = container.study_note_repository.insert_many(session_id, notes)
    return StudyNoteImportReceipt(note_ids=[note.id for note in rows])


@router.get("/{note_id}", summary="Read a saved Study Note")
def get_note(
    session_id: _SessionId, note_id: _NoteId, container: _Container
) -> StudyNote:
    return container.study_note_repository.require(session_id, note_id)


@router.patch(
    "/{note_id}", summary="Replace editable Study Note fields at a known revision"
)
def update_note(
    session_id: _SessionId,
    note_id: _NoteId,
    note: StudyNoteUpdate,
    container: _Container,
) -> StudyNote:
    return container.study_note_repository.replace(session_id, note_id, note)


@router.delete(
    "/{note_id}",
    status_code=204,
    summary="Delete a saved Study Note at a known revision",
)
def delete_note(
    session_id: _SessionId,
    note_id: _NoteId,
    expected_revision: Annotated[int, Query(ge=1, le=STUDY_NOTE_REVISION_MAX)],
    container: _Container,
) -> Response:
    container.study_note_repository.remove(session_id, note_id, expected_revision)
    return Response(status_code=204)
