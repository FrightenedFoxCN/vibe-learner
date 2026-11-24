import type {
  StudyNote,
  StudyNoteArchiveV1,
  StudyNoteImportReceipt,
  StudyNoteInput,
  StudyNoteList,
  StudyNoteListItem,
} from "@vibe-learner/shared";
import { StrictResponseDecoder } from "./strict-response-decode.ts";

const ARCHIVE_VERSION = "study-note-archive-v1";
const ARCHIVE_LIMIT = 200;
export const STUDY_NOTE_REVISION_CONFLICT = "study_note_revision_conflict";

export class StudyNotesDecodeError extends Error {
  readonly path: string;
  constructor(path: string, reason: string) {
    super(reason + " at " + path);
    this.name = "StudyNotesDecodeError";
    this.path = path;
  }
}

function fail(path: string, reason: string): never {
  throw new StudyNotesDecodeError(path, reason);
}

const d = new StrictResponseDecoder(fail);

function record(raw: unknown, path: string, fields: readonly string[]) {
  const row = d.record(raw, path);
  if (Object.keys(row).some((key) => !fields.includes(key)))
    fail(path, "unexpected_field");
  return row;
}

function boundedArray<T>(
  raw: unknown,
  path: string,
  maximum: number,
  decode: (item: unknown, path: string) => T,
): T[] {
  if (!Array.isArray(raw)) fail(path, "expected_array");
  if (raw.length > maximum) fail(path, "expected_at_most_" + maximum + "_items");
  return Array.from(raw, (item, index) => decode(item, path + "[" + index + "]"));
}

function noteId(raw: unknown, path: string): string {
  const id = d.string(raw, path);
  if (id.length !== 32 || !/^[a-f0-9]{32}$/.test(id))
    fail(path, "expected_study_note_id");
  return id;
}

function revision(raw: unknown, path: string): number {
  return d.integer(raw, path, 1, 2_147_483_647);
}

function noteText(raw: unknown, path: string, maximum: number): string {
  const text = d.string(raw, path);
  // Match Python str.strip() for the blank check without trimming user text.
  if (/^[\p{White_Space}\u001c-\u001f]*$/u.test(text)) fail(path, "note_text_blank");
  if (/[\u0000\ud800-\udfff]/u.test(text)) fail(path, "invalid_database_text");
  if (
    text.length > maximum * 2 ||
    (text.length > maximum && [...text].length > maximum)
  )
    fail(path, "text_too_long");
  return text;
}

function decodeTextFields(row: Record<string, unknown>, path: string): StudyNoteInput {
  return {
    title: noteText(d.field(row, "title", path), path + ".title", 160),
    content: noteText(d.field(row, "content", path), path + ".content", 4_000),
  };
}

const METADATA_FIELDS = [
  "id",
  "title",
  "revision",
  "created_at",
  "updated_at",
] as const;

function decodeMetadata(row: Record<string, unknown>, path: string) {
  return {
    id: noteId(d.field(row, "id", path), path + ".id"),
    title: noteText(d.field(row, "title", path), path + ".title", 160),
    revision: revision(d.field(row, "revision", path), path + ".revision"),
    created_at: d.string(d.field(row, "created_at", path), path + ".created_at"),
    updated_at: d.string(d.field(row, "updated_at", path), path + ".updated_at"),
  };
}

export function decodeStudyNote(
  raw: unknown,
  sessionId: string,
  expectedNoteId?: string,
  expectedRevision?: number,
): StudyNote {
  const path = "study_note";
  const row = record(raw, path, [...METADATA_FIELDS, "session_id", "content"]);
  const note = {
    ...decodeMetadata(row, path),
    session_id: d.string(d.field(row, "session_id", path), path + ".session_id"),
    content: noteText(d.field(row, "content", path), path + ".content", 4_000),
  };
  d.equal(note.session_id, sessionId, path + ".session_id");
  if (expectedNoteId !== undefined) d.equal(note.id, expectedNoteId, path + ".id");
  if (expectedRevision !== undefined)
    d.equal(note.revision, expectedRevision, path + ".revision");
  return note;
}

export function decodeStudyNoteList(
  raw: unknown,
  offset = 0,
  limit = 100,
): StudyNoteList {
  const path = "study_note_list";
  const row = record(raw, path, ["items", "next_offset"]);
  const items = boundedArray(
    d.field(row, "items", path),
    path + ".items",
    limit,
    (item, itemPath): StudyNoteListItem => {
      const entry = record(item, itemPath, [...METADATA_FIELDS, "excerpt"]);
      return {
        ...decodeMetadata(entry, itemPath),
        excerpt: d.string(
          d.field(entry, "excerpt", itemPath),
          itemPath + ".excerpt",
          true,
        ),
      };
    },
  );
  d.unique(
    items.map((item) => item.id),
    path + ".items",
  );
  const nextOffsetPath = path + ".next_offset";
  const nextOffset = d.nullable(
    d.field(row, "next_offset", path),
    nextOffsetPath,
    (raw, path) => d.integer(raw, path, 1),
  );
  if (
    nextOffset !== null &&
    (items.length === 0 || nextOffset !== offset + items.length)
  )
    fail(nextOffsetPath, "invalid_next_offset");
  return { items, next_offset: nextOffset };
}

export function decodeStudyNoteArchive(raw: unknown): StudyNoteArchiveV1 {
  const path = "study_note_archive";
  const row = record(raw, path, ["schema_version", "notes", "next_after"]);
  d.equal(
    d.field(row, "schema_version", path),
    ARCHIVE_VERSION,
    path + ".schema_version",
  );
  const notes = boundedArray(
    d.field(row, "notes", path),
    path + ".notes",
    ARCHIVE_LIMIT,
    (item, itemPath) =>
      decodeTextFields(record(item, itemPath, ["title", "content"]), itemPath),
  );
  const archive: StudyNoteArchiveV1 = { schema_version: ARCHIVE_VERSION, notes };
  if (Object.hasOwn(row, "next_after"))
    archive.next_after = d.nullable(row.next_after, path + ".next_after", noteId);
  return archive;
}

export function decodeStudyNoteImportReceipt(
  raw: unknown,
  expectedCount: number,
): StudyNoteImportReceipt {
  const path = "study_note_import_receipt";
  const row = record(raw, path, ["note_ids"]);
  const ids = boundedArray(
    d.field(row, "note_ids", path),
    path + ".note_ids",
    ARCHIVE_LIMIT,
    noteId,
  );
  d.unique(ids, path + ".note_ids");
  d.equal(ids.length, expectedCount, path + ".note_ids");
  return { note_ids: ids };
}

export function decodeStudyNoteConflictRevision(raw: unknown): number {
  const path = "study_note_revision_conflict";
  const row = record(raw, path, ["detail"]);
  const detailPath = path + ".detail";
  const detail = record(d.field(row, "detail", path), detailPath, [
    "code",
    "current_revision",
  ]);
  d.equal(
    d.field(detail, "code", detailPath),
    STUDY_NOTE_REVISION_CONFLICT,
    detailPath + ".code",
  );
  return revision(
    d.field(detail, "current_revision", detailPath),
    detailPath + ".current_revision",
  );
}
