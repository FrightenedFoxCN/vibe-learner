import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { test } from "node:test";
import { isApiHttpError } from "../lib/http-error.ts";
import {
  decodeStudyNote,
  decodeStudyNoteArchive,
  decodeStudyNoteImportReceipt,
  decodeStudyNoteList,
  StudyNotesDecodeError,
} from "../lib/study-notes-decode.ts";

const hooks = registerHooks({
  resolve(specifier, context, nextResolve) {
    if (
      context.parentURL?.endsWith("/lib/api/_shared.ts") &&
      specifier.startsWith("../")
    ) {
      return nextResolve(specifier + ".ts", context);
    }
    return nextResolve(specifier, context);
  },
});
const {
  studyNotesData,
  StudyNoteRevisionConflictError,
  InvalidStudyNotesArchiveError,
} = await import("../lib/data/study-notes.ts");
hooks.deregister();

const id = "a".repeat(32);
const secondId = "b".repeat(32);
const sessionId = "session ?";
const fields = { title: "  Title  ", content: "\n  正文 😀\r\n" };
const metadata = {
  id,
  title: fields.title,
  revision: 1,
  created_at: "2026-11-24T07:00:00.012345+00:00",
  updated_at: "2026-11-24T07:01:00.012345+00:00",
};
const note = { ...metadata, session_id: sessionId, content: fields.content };
const summary = { ...metadata, excerpt: "…正文…" };
const archive = { schema_version: "study-note-archive-v1", notes: [fields] };
const receipt = { note_ids: [id] };
const rootPath = "/study-sessions/session%20%3F/notes";

function hasDecodePath(path: string) {
  return (error: unknown) =>
    error instanceof StudyNotesDecodeError && error.path === path;
}

test("note responses bind session, note, revision and required content without trimming", () => {
  assert.deepEqual(decodeStudyNote(note, sessionId, id, 1), note);
  assert.throws(
    () => decodeStudyNote({ ...note, content: undefined }, sessionId, id),
    hasDecodePath("study_note.content"),
  );
  assert.throws(
    () => decodeStudyNote(note, "other session", id),
    hasDecodePath("study_note.session_id"),
  );
  assert.throws(
    () => decodeStudyNote(note, sessionId, secondId),
    hasDecodePath("study_note.id"),
  );
  assert.throws(
    () => decodeStudyNote(note, sessionId, id, 2),
    hasDecodePath("study_note.revision"),
  );
  for (const revision of [0, 2 ** 31, 1.5, "1", null]) {
    assert.throws(
      () => decodeStudyNote({ ...note, revision }, sessionId),
      hasDecodePath("study_note.revision"),
    );
  }
});

test("list pages must have summaries and consistent pagination", () => {
  assert.deepEqual(decodeStudyNoteList({ items: [summary], next_offset: 4 }, 3), {
    items: [summary],
    next_offset: 4,
  });
  assert.throws(
    () => decodeStudyNoteList({ items: [] }),
    hasDecodePath("study_note_list.next_offset"),
  );
  assert.throws(
    () => decodeStudyNoteList({ items: [summary], next_offset: 1 }, 1),
    hasDecodePath("study_note_list.next_offset"),
  );
  assert.throws(
    () => decodeStudyNoteList({ items: [summary, summary], next_offset: null }),
    hasDecodePath("study_note_list.items"),
  );
  assert.throws(
    () => decodeStudyNoteList({ items: [note], next_offset: null }),
    hasDecodePath("study_note_list.items[0]"),
  );
});

test("archive decoding preserves original Unicode and rejects nonportable metadata or contents", () => {
  assert.deepEqual(decodeStudyNoteArchive(archive), archive);
  assert.deepEqual(decodeStudyNoteArchive({ ...archive, next_after: id }), {
    ...archive,
    next_after: id,
  });
  const edge = { title: "😀".repeat(160), content: "𠀀".repeat(4000) };
  assert.deepEqual(decodeStudyNoteArchive({ ...archive, notes: [edge] }).notes, [edge]);
  assert.throws(
    () => decodeStudyNoteArchive({ ...archive, schema_version: "v2" }),
    hasDecodePath("study_note_archive.schema_version"),
  );
  assert.throws(
    () => decodeStudyNoteArchive({ ...archive, notes: Array(201).fill(fields) }),
    hasDecodePath("study_note_archive.notes"),
  );
  assert.throws(
    () => decodeStudyNoteArchive({ ...archive, notes: [note] }),
    hasDecodePath("study_note_archive.notes[0]"),
  );
  for (const title of [" \n\u001c ", "😀".repeat(161), "a\0", "\ud800", null]) {
    assert.throws(
      () => decodeStudyNoteArchive({ ...archive, notes: [{ ...fields, title }] }),
      hasDecodePath("study_note_archive.notes[0].title"),
    );
  }
  assert.deepEqual(decodeStudyNoteImportReceipt(receipt, 1), receipt);
  assert.throws(
    () => decodeStudyNoteImportReceipt(receipt, 2),
    hasDecodePath("study_note_import_receipt.note_ids"),
  );
  assert.throws(
    () => decodeStudyNoteImportReceipt({ note_ids: [id, id] }, 2),
    hasDecodePath("study_note_import_receipt.note_ids"),
  );
});

test("data API sends scoped methods, query, request fields and read signals", async (t) => {
  const pages = { items: [summary], next_offset: 1 };
  const edited = { ...note, revision: 2 };
  const exportPage = { ...archive, next_after: secondId };
  const replies: [number, unknown][] = [
    [200, pages],
    [200, note],
    [201, note],
    [200, edited],
    [204, null],
    [200, exportPage],
    [201, receipt],
    [201, receipt],
  ];
  const calls: { url: URL; init?: RequestInit }[] = [];
  t.mock.method(
    globalThis,
    "fetch",
    async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push({ url: new URL(String(input)), init });
      const [status, payload] = replies.shift() ?? [500, null];
      return status === 204
        ? new Response(null, { status })
        : Response.json(payload, { status });
    },
  );
  const { signal } = new AbortController();
  const q = " a &%+中 ";
  const patch = { ...fields, expected_revision: 1 };
  const keys = [" key "];
  assert.deepEqual(
    await studyNotesData.list(sessionId, { q, offset: 0, limit: 1, signal }),
    pages,
  );
  assert.deepEqual(await studyNotesData.get(sessionId, id, signal), note);
  assert.deepEqual(await studyNotesData.create(sessionId, fields), note);
  assert.deepEqual(await studyNotesData.replace(sessionId, id, patch), edited);
  assert.equal(await studyNotesData.remove(sessionId, id, 2), undefined);
  assert.deepEqual(
    await studyNotesData.exportPage(sessionId, { after: id, limit: 1, signal }),
    exportPage,
  );
  assert.deepEqual(await studyNotesData.importArchive(sessionId, exportPage), receipt);
  assert.deepEqual(await studyNotesData.importMemory(sessionId, keys), receipt);
  assert.deepEqual(
    calls.map(({ url, init }) => [
      init?.method ?? "GET",
      url.pathname,
      Object.fromEntries(url.searchParams),
      init?.body === undefined ? undefined : JSON.parse(String(init.body)),
      init?.signal,
    ]),
    [
      ["GET", rootPath, { q, offset: "0", limit: "1" }, undefined, signal],
      ["GET", rootPath + "/" + id, {}, undefined, signal],
      ["POST", rootPath, {}, fields, undefined],
      ["PATCH", rootPath + "/" + id, {}, patch, undefined],
      ["DELETE", rootPath + "/" + id, { expected_revision: "2" }, undefined, undefined],
      ["GET", rootPath + "/export", { after: id, limit: "1" }, undefined, signal],
      ["POST", rootPath + "/import", {}, exportPage, undefined],
      ["POST", rootPath + "/import-memory", {}, { keys }, undefined],
    ],
  );
});

test("invalid archive never uploads; server conflict exposes only a verified revision", async (t) => {
  const detail = { code: "study_note_revision_conflict", current_revision: 4 };
  const payloads: [number, unknown][] = [
    [409, { detail }],
    [409, { detail: { ...detail, current_revision: "4" } }],
    [404, { detail: "study_note_not_found" }],
  ];
  const fetchMock = t.mock.method(globalThis, "fetch", async () => {
    const [status, payload] = payloads.shift() ?? [500, null];
    return Response.json(payload, { status });
  });
  await assert.rejects(
    studyNotesData.importArchive(sessionId, {
      ...archive,
      notes: [{ title: "x", content: 5 }],
    }),
    (err: unknown) =>
      err instanceof InvalidStudyNotesArchiveError &&
      hasDecodePath("study_note_archive.notes[0].content")(err.cause),
  );
  assert.equal(fetchMock.mock.callCount(), 0);
  await assert.rejects(
    studyNotesData.replace(sessionId, id, { ...fields, expected_revision: 1 }),
    (err: unknown) =>
      err instanceof StudyNoteRevisionConflictError &&
      err.status === 409 &&
      err.current_revision === 4,
  );
  await assert.rejects(
    studyNotesData.remove(sessionId, id, 1),
    (err: unknown) =>
      !(err instanceof StudyNoteRevisionConflictError) &&
      isApiHttpError(err) &&
      err.status === 409 &&
      err.code === detail.code,
  );
  await assert.rejects(
    studyNotesData.get(sessionId, id),
    (err: unknown) =>
      isApiHttpError(err) &&
      err.status === 404 &&
      err.message === "study_note_not_found",
  );
});
