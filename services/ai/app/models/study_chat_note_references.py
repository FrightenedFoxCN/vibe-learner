"""Bounded, server-owned Study Chat references; never model-authored URLs."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.models.study_notes import StudyNoteId, StudyNoteRevision, StudyNoteTitle


STUDY_NOTE_SEARCH_RESULT_LIMIT = 5
STUDY_NOTE_SEARCH_CALL_LIMIT = 2
STUDY_NOTE_REFERENCE_LIMIT = (
    STUDY_NOTE_SEARCH_RESULT_LIMIT * STUDY_NOTE_SEARCH_CALL_LIMIT
)


class StudyNoteReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    note_id: StudyNoteId
    note_revision: StudyNoteRevision
    title: StudyNoteTitle


def _require_unique_notes(
    references: list[StudyNoteReferenceV1],
) -> list[StudyNoteReferenceV1]:
    if len({item.note_id for item in references}) != len(references):
        raise ValueError("study_note_reference_ids_not_unique")
    return references


StudyNoteReferences = Annotated[
    list[StudyNoteReferenceV1],
    Field(max_length=STUDY_NOTE_REFERENCE_LIMIT, strict=True),
    AfterValidator(_require_unique_notes),
]
