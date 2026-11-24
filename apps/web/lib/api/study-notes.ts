import type {
  StudyNoteArchiveV1,
  StudyNoteInput,
  StudyNoteMemoryImport,
  StudyNoteUpdate,
} from "@vibe-learner/shared";
import { diagnosticDecode } from "../diagnostics.ts";
import { ApiHttpError } from "../http-error.ts";
import {
  decodeStudyNote,
  decodeStudyNoteArchive,
  decodeStudyNoteConflictRevision,
  decodeStudyNoteImportReceipt,
  decodeStudyNoteList,
  STUDY_NOTE_REVISION_CONFLICT,
  StudyNotesDecodeError,
} from "../study-notes-decode.ts";
import { AI_BASE_URL, readJson, request } from "./_shared.ts";

interface ListOptions {
  q?: string;
  offset?: number;
  limit?: number;
  signal?: AbortSignal;
}
interface ExportOptions {
  after?: string;
  limit?: number;
  signal?: AbortSignal;
}

export class StudyNoteRevisionConflictError extends ApiHttpError {
  readonly current_revision: number;

  constructor(error: ApiHttpError, currentRevision: number) {
    super({
      status: error.status,
      code: STUDY_NOTE_REVISION_CONFLICT,
      message: STUDY_NOTE_REVISION_CONFLICT,
      payload: error.payload,
    });
    this.name = "StudyNoteRevisionConflictError";
    this.current_revision = currentRevision;
  }
}

export class InvalidStudyNotesArchiveError extends Error {}

function notesUrl(sessionId: string): string {
  return AI_BASE_URL() + "/study-sessions/" + encodeURIComponent(sessionId) + "/notes";
}

function noteUrl(sessionId: string, noteId: string): string {
  return notesUrl(sessionId) + "/" + encodeURIComponent(noteId);
}

function withQuery(
  url: string,
  fields: Record<string, string | number | undefined>,
): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(fields))
    if (value !== undefined) params.set(key, String(value));
  return params.size ? url + "?" + params.toString() : url;
}

function jsonWrite(method: "POST" | "PATCH", body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

async function readWithConflict(response: Response): Promise<unknown> {
  try {
    return await readJson<unknown>(response);
  } catch (error) {
    if (
      !(error instanceof ApiHttpError) ||
      error.status !== 409 ||
      error.code !== STUDY_NOTE_REVISION_CONFLICT
    )
      throw error;
    let currentRevision: number;
    try {
      currentRevision = diagnosticDecode(response, () =>
        decodeStudyNoteConflictRevision(error.payload),
      );
    } catch {
      throw error;
    }
    throw new StudyNoteRevisionConflictError(error, currentRevision);
  }
}

export async function listStudyNotes(
  sessionId: string,
  { q, offset, limit, signal }: ListOptions = {},
) {
  const response = await request(withQuery(notesUrl(sessionId), { q, offset, limit }), {
    cache: "no-store",
    signal,
  });
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () =>
    decodeStudyNoteList(raw, offset, limit ?? 30),
  );
}

export async function getStudyNote(
  sessionId: string,
  noteId: string,
  signal?: AbortSignal,
) {
  const response = await request(noteUrl(sessionId, noteId), {
    cache: "no-store",
    signal,
  });
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () => decodeStudyNote(raw, sessionId, noteId));
}

export async function createStudyNote(
  sessionId: string,
  { title, content }: StudyNoteInput,
) {
  const response = await request(
    notesUrl(sessionId),
    jsonWrite("POST", { title, content }),
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () =>
    decodeStudyNote(raw, sessionId, undefined, 1),
  );
}

export async function replaceStudyNote(
  sessionId: string,
  noteId: string,
  { title, content, expected_revision }: StudyNoteUpdate,
) {
  const response = await request(
    noteUrl(sessionId, noteId),
    jsonWrite("PATCH", { title, content, expected_revision }),
  );
  const raw = await readWithConflict(response);
  return diagnosticDecode(response, () =>
    decodeStudyNote(raw, sessionId, noteId, expected_revision + 1),
  );
}

export async function removeStudyNote(
  sessionId: string,
  noteId: string,
  expectedRevision: number,
): Promise<void> {
  const response = await request(
    withQuery(noteUrl(sessionId, noteId), { expected_revision: expectedRevision }),
    { method: "DELETE" },
  );
  if (!response.ok) await readWithConflict(response);
  if (response.status !== 204) {
    await response.body?.cancel();
    diagnosticDecode(response, () => {
      throw new StudyNotesDecodeError("study_note_delete", "expected_http_204");
    });
  }
}

export async function exportStudyNotesPage(
  sessionId: string,
  { after, limit, signal }: ExportOptions = {},
) {
  const response = await request(
    withQuery(notesUrl(sessionId) + "/export", { after, limit }),
    { cache: "no-store", signal },
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () => {
    const archive = decodeStudyNoteArchive(raw);
    if (
      !Object.hasOwn(archive, "next_after") ||
      archive.notes.length > (limit ?? 200) ||
      (archive.next_after != null &&
        (archive.notes.length === 0 ||
          (after !== undefined && archive.next_after <= after)))
    ) {
      throw new StudyNotesDecodeError("study_note_archive", "invalid_export_page");
    }
    return archive;
  });
}

export async function importStudyNotesArchive(sessionId: string, parsed: unknown) {
  let archive: StudyNoteArchiveV1;
  try {
    archive = decodeStudyNoteArchive(parsed);
  } catch (error) {
    throw new InvalidStudyNotesArchiveError("study_note_archive_invalid", {
      cause: error,
    });
  }
  const response = await request(
    notesUrl(sessionId) + "/import",
    jsonWrite("POST", archive),
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () =>
    decodeStudyNoteImportReceipt(raw, archive.notes.length),
  );
}

export async function importStudyNotesMemory(sessionId: string, keys: string[]) {
  const selection: StudyNoteMemoryImport = { keys: [...keys] };
  const response = await request(
    notesUrl(sessionId) + "/import-memory",
    jsonWrite("POST", selection),
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(response, () =>
    decodeStudyNoteImportReceipt(raw, selection.keys.length),
  );
}
