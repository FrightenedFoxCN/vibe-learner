"""Read-only note lookup scoped to the admitted Study Chat session."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.models.study_chat_tool_contracts import (
    SearchStudyNotesArgumentsV1,
    SearchStudyNotesResultV1,
    StudyNoteSearchHitV1,
)
from app.persistence.study_session_repository import StudySessionNotFound

if TYPE_CHECKING:
    from app.persistence.study_note_repository import StudyNoteRepository


class StudyNoteSearchTools:
    def __init__(self, repository: StudyNoteRepository, session_id: str) -> None:
        self._repository = repository
        self._session_id = session_id

    def search_study_notes(self, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            search = SearchStudyNotesArgumentsV1.model_validate(arguments)
        except ValidationError:
            return {"ok": False, "error": "tool_arguments_contract_invalid"}
        try:
            results = self._repository.search(
                self._session_id, query=search.query, offset=0, limit=search.limit
            )
            return SearchStudyNotesResultV1(
                hits=[
                    StudyNoteSearchHitV1(
                        note_id=item.id,
                        note_revision=item.revision,
                        title=item.title,
                        excerpt=item.excerpt,
                    )
                    for item in results.items
                ],
                has_more=results.next_offset is not None,
            ).model_dump(mode="python")
        except (SQLAlchemyError, StudySessionNotFound, ValidationError):
            # Neither DB exceptions (which may contain query bindings) nor validation
            # exceptions (which may include raw note text) belong in tool feedback.
            return {"ok": False, "error": "study_note_search_unavailable"}
