/** Wire DTOs for the user-owned, session-scoped Study Notes API. */
/** Server-selected from successful reads in the admitted chat operation. */
export interface StudyNoteReference {
  noteId: string;
  noteRevision: number;
  title: string;
}

export interface StudyNoteInput {
  title: string;
  content: string;
}

export interface StudyNoteUpdate extends StudyNoteInput {
  expected_revision: number;
}

interface StudyNoteMetadata {
  id: string;
  title: string;
  revision: number;
  created_at: string;
  updated_at: string;
}

export interface StudyNote extends StudyNoteMetadata {
  session_id: string;
  content: string;
}

export interface StudyNoteListItem extends StudyNoteMetadata {
  excerpt: string;
}

export interface StudyNoteList {
  items: StudyNoteListItem[];
  next_offset: number | null;
}

export interface StudyNoteArchiveV1 {
  schema_version: "study-note-archive-v1";
  notes: StudyNoteInput[];
  next_after?: string | null;
}

export interface StudyNoteMemoryImport {
  keys: string[];
}

export interface StudyNoteImportReceipt {
  note_ids: string[];
}
