"""Study Notes wire contracts. Notes are user data, not chat memory effects."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

STUDY_NOTE_ARCHIVE_LIMIT = 200
STUDY_NOTE_TITLE_LIMIT = 160
STUDY_NOTE_CONTENT_LIMIT = 4_000
STUDY_NOTE_REVISION_MAX = 2_147_483_647
STUDY_NOTE_ID_PATTERN = r"^[a-f0-9]{32}$"


def require_database_text(value: str) -> str:
    if "\x00" in value or any("\ud800" <= char <= "\udfff" for char in value):
        raise ValueError("text_contains_invalid_characters")
    return value


def require_note_text(value: str) -> str:
    require_database_text(value)
    if not value.strip():
        raise ValueError("note_text_blank")
    return value


StudyNoteTitle = Annotated[
    str,
    Field(min_length=1, max_length=STUDY_NOTE_TITLE_LIMIT),
    AfterValidator(require_note_text),
]
StudyNoteContent = Annotated[
    str,
    Field(min_length=1, max_length=STUDY_NOTE_CONTENT_LIMIT),
    AfterValidator(require_note_text),
]
StudyNoteId = Annotated[str, Field(pattern=STUDY_NOTE_ID_PATTERN)]
StudyNoteRevision = Annotated[int, Field(ge=1, le=STUDY_NOTE_REVISION_MAX)]


class _StudyNotesModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class StudyNoteInput(_StudyNotesModel):
    title: StudyNoteTitle
    content: StudyNoteContent


class StudyNoteUpdate(StudyNoteInput):
    expected_revision: StudyNoteRevision


class StudyNote(_StudyNotesModel):
    id: StudyNoteId
    session_id: str
    title: StudyNoteTitle
    content: StudyNoteContent
    revision: StudyNoteRevision
    created_at: str
    updated_at: str


class StudyNoteListItem(_StudyNotesModel):
    id: StudyNoteId
    title: StudyNoteTitle
    excerpt: str
    revision: StudyNoteRevision
    created_at: str
    updated_at: str


class StudyNoteList(_StudyNotesModel):
    items: list[StudyNoteListItem]
    next_offset: int | None


class StudyNoteArchiveV1(_StudyNotesModel):
    schema_version: Literal["study-note-archive-v1"]
    notes: Annotated[list[StudyNoteInput], Field(max_length=STUDY_NOTE_ARCHIVE_LIMIT)]
    next_after: StudyNoteId | None = None


StudyMemoryKey = Annotated[
    str, Field(min_length=1, max_length=120), AfterValidator(require_note_text)
]


class StudyNoteMemoryImport(_StudyNotesModel):
    keys: Annotated[
        list[StudyMemoryKey], Field(min_length=1, max_length=STUDY_NOTE_ARCHIVE_LIMIT)
    ]


class StudyNoteImportReceipt(_StudyNotesModel):
    note_ids: list[StudyNoteId]
