"""Session-scoped note rows; never mutate the Study Session revision or payload."""

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.models.study_notes import (
    StudyNote,
    StudyNoteArchiveV1,
    StudyNoteInput,
    StudyNoteList,
    StudyNoteListItem,
    StudyNoteUpdate,
)
from app.persistence.database import Database
from app.persistence.models import StudyNoteRow, StudySessionRow
from app.persistence.study_session_repository import StudySessionNotFound


class StudyNoteNotFound(Exception):
    pass


class StudyNoteRevisionConflict(Exception):
    def __init__(self, current_revision: int) -> None:
        self.current_revision = current_revision


class StudyNoteRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def create(self, session_id: str, note: StudyNoteInput) -> StudyNote:
        return self.insert_many(session_id, [note])[0]

    def insert_many(
        self, session_id: str, notes: Sequence[StudyNoteInput]
    ) -> list[StudyNote]:
        now = datetime.now(timezone.utc).isoformat(timespec="microseconds")
        with self.database.session() as db:
            _require_session(db, session_id)
            rows = [
                StudyNoteRow(
                    id=uuid4().hex,
                    session_id=session_id,
                    revision=1,
                    created_at=now,
                    updated_at=now,
                    **_text_fields(note),
                )
                for note in notes
            ]
            db.add_all(rows)
            db.flush()
            return [_note(row) for row in rows]

    def require(self, session_id: str, note_id: str) -> StudyNote:
        with self.database.session() as db:
            row = db.scalar(select(StudyNoteRow).where(*_target(session_id, note_id)))
            if row is None:
                _require_session(db, session_id)
                raise StudyNoteNotFound(note_id)
            return _note(row)

    def replace(
        self, session_id: str, note_id: str, note: StudyNoteUpdate
    ) -> StudyNote:
        with self.database.session() as db:
            row = db.scalar(
                update(StudyNoteRow)
                .where(
                    *_target(session_id, note_id),
                    StudyNoteRow.revision == note.expected_revision,
                )
                .values(
                    **_text_fields(note),
                    revision=StudyNoteRow.revision + 1,
                    updated_at=datetime.now(timezone.utc).isoformat(
                        timespec="microseconds"
                    ),
                )
                .returning(StudyNoteRow)
            )
            if row is None:
                _raise_cas_failure(db, session_id, note_id)
            return _note(row)

    def remove(self, session_id: str, note_id: str, expected_revision: int) -> None:
        with self.database.session() as db:
            removed = db.scalar(
                delete(StudyNoteRow)
                .where(
                    *_target(session_id, note_id),
                    StudyNoteRow.revision == expected_revision,
                )
                .returning(StudyNoteRow.id)
            )
            if removed is None:
                _raise_cas_failure(db, session_id, note_id)

    def search(
        self, session_id: str, *, query: str, offset: int, limit: int
    ) -> StudyNoteList:
        needle = query.strip().casefold()
        statement = select(StudyNoteRow).where(StudyNoteRow.session_id == session_id)
        if needle:
            statement = statement.where(
                or_(
                    StudyNoteRow.search_title.contains(needle, autoescape=True),
                    StudyNoteRow.search_content.contains(needle, autoescape=True),
                )
            )
        with self.database.session() as db:
            _require_session(db, session_id)
            rows = db.scalars(
                statement.order_by(
                    StudyNoteRow.updated_at.desc(), StudyNoteRow.id.desc()
                )
                .offset(offset)
                .limit(limit + 1)
            ).all()
            return StudyNoteList(
                items=[
                    StudyNoteListItem(
                        id=row.id,
                        title=row.title,
                        excerpt=_excerpt(row.content, row.search_content.find(needle)),
                        revision=row.revision,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    )
                    for row in rows[:limit]
                ],
                next_offset=offset + limit if len(rows) > limit else None,
            )

    def export(
        self, session_id: str, *, after: str | None, limit: int
    ) -> StudyNoteArchiveV1:
        statement = select(StudyNoteRow).where(StudyNoteRow.session_id == session_id)
        if after is not None:
            statement = statement.where(StudyNoteRow.id > after)
        with self.database.session() as db:
            _require_session(db, session_id)
            rows = db.scalars(
                statement.order_by(StudyNoteRow.id).limit(limit + 1)
            ).all()
            return StudyNoteArchiveV1(
                schema_version="study-note-archive-v1",
                notes=[
                    StudyNoteInput(title=row.title, content=row.content)
                    for row in rows[:limit]
                ],
                next_after=rows[limit - 1].id if len(rows) > limit else None,
            )


def _target(session_id: str, note_id: str):
    return StudyNoteRow.session_id == session_id, StudyNoteRow.id == note_id


def _require_session(db: Session, session_id: str) -> None:
    if (
        db.scalar(select(StudySessionRow.id).where(StudySessionRow.id == session_id))
        is None
    ):
        raise StudySessionNotFound(session_id)


def _raise_cas_failure(db: Session, session_id: str, note_id: str) -> None:
    current = db.scalar(
        select(StudyNoteRow.revision).where(*_target(session_id, note_id))
    )
    if current is None:
        _require_session(db, session_id)
        raise StudyNoteNotFound(note_id)
    raise StudyNoteRevisionConflict(current)


def _text_fields(note: StudyNoteInput) -> dict[str, str]:
    return {
        "title": note.title,
        "content": note.content,
        "search_title": note.title.casefold(),
        "search_content": note.content.casefold(),
    }


def _note(row: StudyNoteRow) -> StudyNote:
    return StudyNote(
        id=row.id,
        session_id=row.session_id,
        title=row.title,
        content=row.content,
        revision=row.revision,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _excerpt(content: str, folded_offset: int) -> str:
    # Case folding can expand characters (e.g. ß -> ss); map the match back
    # to the original before clipping so the snippet never alters user text.
    start = 0
    if folded_offset > 0:
        for index, char in enumerate(content):
            folded_offset -= len(char.casefold())
            if folded_offset < 0:
                start = max(0, index - 32)
                break
    end = start + 160
    return (
        ("…" if start else "")
        + content[start:end]
        + ("…" if end < len(content) else "")
    )
