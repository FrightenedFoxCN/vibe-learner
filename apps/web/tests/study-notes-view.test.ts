import assert from "node:assert/strict";
import { test } from "node:test";
import {
  draftFromNote,
  getStudyNoteSaveReceipts,
  isStudyNoteDraftDirty,
  rebaseStudyNoteDraft,
  StudyNotesView,
  type StudyNoteDraft,
  type StudyNoteSaveOutcome,
} from "../lib/study-notes-view.ts";
import {
  decodeStudyChatExchange,
  decodeStudyNoteReferences,
} from "../lib/study-session-decode.ts";

const noteId = "c".repeat(32);
const note = {
  id: noteId,
  session_id: "original",
  title: "Title",
  content: "Saved",
  revision: 2,
  created_at: "2026-11-24T07:00:00+00:00",
  updated_at: "2026-11-24T07:00:00+00:00",
};

test("late results cannot cross a session switch, re-entry, or newer targets", () => {
  const first = new StudyNotesView("original");
  const write = first.begin("write", "new");
  const slow = first.begin("list", "keyword A");
  const fast = first.begin("list", "keyword B");
  assert.equal(slow.signal.aborted, true);
  assert.equal(first.current(slow), false);
  assert.equal(first.current(write), true);
  assert.equal(first.current(fast), true);
  const other = new StudyNotesView("other");
  const otherWrite = other.begin("write", "new");
  assert.equal(other.current(write), false);
  first.close();
  assert.equal(first.current(write), false);
  assert.equal(first.current(fast), false);
  const returned = new StudyNotesView("original");
  const newWrite = returned.begin("write", "new");
  assert.equal(returned.current(write), false);
  assert.equal(returned.current(newWrite), true);
  assert.equal(other.current(otherWrite), true);
});

function createSaveStore() {
  const drafts = new Map<string, StudyNoteDraft>();
  const read = (session: string) => drafts.get(session) ?? null;
  const store = (session: string, draft: StudyNoteDraft | null) => {
    if (draft) drafts.set(session, draft);
    else drafts.delete(session);
  };
  const original = {
    ...draftFromNote(note),
    fields: { ...draftFromNote(note).fields, content: "Edit" },
  };
  const pending = { ...original, unconfirmed: true };
  const saved = { ...note, revision: 3, content: "Canonical saved content" };
  const receipts = getStudyNoteSaveReceipts(read);
  receipts.begin(note.session_id, pending);
  store(note.session_id, pending);
  return { read, store, original, pending, saved, receipts };
}

function mountEditor(
  receipts: ReturnType<typeof getStudyNoteSaveReceipts>,
  sessionId: string,
  initial: StudyNoteDraft | null,
) {
  const editor = {
    draft: initial,
    reloads: 0,
    outcome: null as StudyNoteSaveOutcome | null,
  };
  const close = receipts.subscribe(
    sessionId,
    () => editor.draft,
    (receipt, matchesEditor) => {
      if (receipt.refreshList) editor.reloads++;
      if (matchesEditor) {
        editor.draft = receipt.nextDraft;
        editor.outcome = receipt.outcome;
      }
    },
  );
  return { editor, close };
}

for (const settleBeforeSubscription of [false, true]) {
  test(`A → B → A applies the saved baseline and reloads the list (settled before subscription: ${settleBeforeSubscription})`, () => {
    const a = note.session_id;
    const { receipts, read, store, original, pending, saved } = createSaveStore();
    const first = mountEditor(receipts, a, pending);
    first.close();
    const b = mountEditor(receipts, "B", null);
    const restored = read(a);
    assert.equal(restored, pending);
    assert.equal(receipts.pending(restored), true);
    const settle = () =>
      receipts.settle(pending, original, { kind: "saved", note: saved }, store);
    if (settleBeforeSubscription) settle();
    const returned = mountEditor(getStudyNoteSaveReceipts(read), a, restored);
    if (!settleBeforeSubscription) settle();

    assert.equal(read(a), null);
    assert.equal(receipts.pending(pending), false);
    assert.deepEqual(returned.editor.draft, draftFromNote(saved));
    assert.equal(returned.editor.reloads, 1);
    assert.equal(b.editor.reloads, 0);
    assert.equal(first.editor.draft, pending);
    assert.equal(first.editor.reloads, 0);
    b.close();
    returned.close();
  });
}

test("a late save refreshes its list without replacing a newer draft or reaching a different page store", () => {
  const { receipts, read, store, original, pending, saved } = createSaveStore();
  const replacement = {
    ...pending,
    fields: { ...pending.fields, content: "Newer edit" },
  };
  store(note.session_id, replacement);
  const returned = mountEditor(receipts, note.session_id, replacement);
  const otherPage = createSaveStore();
  const unrelated = mountEditor(otherPage.receipts, note.session_id, otherPage.pending);
  receipts.settle(pending, original, { kind: "saved", note: saved }, store);

  assert.equal(read(note.session_id), replacement);
  assert.equal(returned.editor.draft, replacement);
  assert.equal(returned.editor.outcome, null);
  assert.equal(returned.editor.reloads, 1);
  assert.equal(unrelated.editor.reloads, 0);
  assert.equal(otherPage.read(note.session_id), otherPage.pending);
  returned.close();
  unrelated.close();
});

test("a rejected remounted save restores the editable draft and conflict; an uncertain save requires review", () => {
  for (const outcome of [
    { kind: "rejected", error: "Conflict", conflictRevision: 3 },
    { kind: "unknown", error: "Review required" },
  ] as const) {
    const { receipts, read, store, original, pending } = createSaveStore();
    const returned = mountEditor(receipts, note.session_id, pending);
    receipts.settle(pending, original, outcome, store);
    const expected = outcome.kind === "unknown" ? pending : original;

    assert.equal(returned.editor.draft, expected);
    assert.equal(read(note.session_id), expected);
    assert.equal(receipts.pending(pending), false);
    assert.deepEqual(returned.editor.outcome, outcome);
    assert.equal(returned.editor.reloads, outcome.kind === "unknown" ? 1 : 0);
    returned.close();
  }
});

test("conflict comparison preserves local text and binds the accepted revision", () => {
  const baseline = draftFromNote(note);
  assert.equal(isStudyNoteDraftDirty(baseline), false);
  const draft = {
    ...baseline,
    fields: { ...baseline.fields, content: "  Local draft  " },
  };
  const rebased = rebaseStudyNoteDraft(draft, {
    ...note,
    revision: 3,
    content: "Other change",
  });
  assert.equal(rebased.original?.revision, 3);
  assert.equal(rebased.fields.content, "  Local draft  ");
  assert.equal(isStudyNoteDraftDirty(rebased), true);
  for (const latest of [
    { ...note, session_id: "wrong" },
    { ...note, id: "d".repeat(32) },
    { ...note, revision: 1 },
  ]) {
    assert.throws(
      () => rebaseStudyNoteDraft(draft, latest),
      /study_note_draft_revision_mismatch/,
    );
  }
});

test("only bounded structured committed note references can be navigation targets", () => {
  const wire = { note_id: noteId, note_revision: 1, title: "  <not HTML>  " };
  assert.deepEqual(decodeStudyNoteReferences([wire]), [
    { noteId, noteRevision: 1, title: wire.title },
  ]);
  assert.throws(() => decodeStudyNoteReferences([{ ...wire, url: "/study" }]));
  assert.throws(() =>
    decodeStudyNoteReferences([{ ...wire, note_id: "https://elsewhere/" }]),
  );
  assert.throws(() => decodeStudyNoteReferences([{ ...wire, note_revision: "1" }]));
  assert.throws(() => decodeStudyNoteReferences([wire, wire]));
  assert.throws(() => decodeStudyNoteReferences(Array(11).fill(wire)));
});

test("searched notes must agree between committed exchange and authoritative turn", () => {
  const fields = {
    citations: [],
    character_events: [],
    rich_blocks: [],
    interactive_question: null,
    persona_slot_trace: [],
    memory_trace: [],
    tool_calls: [],
    scene_profile: null,
    model_recoveries: [],
  };
  const turn = {
    ...fields,
    id: "turn-one",
    sequence: 1,
    assistant_reply: "Review your notes.",
    learner_message: "Find my notes",
    learner_message_kind: "learner",
    learner_attachments: [],
    created_at: note.created_at,
  };
  const session = {
    id: "session-a",
    document_id: "",
    persona_id: "persona-a",
    plan_id: null,
    study_unit_id: "unit-a",
    revision: 1,
    last_turn_sequence: 1,
    scene_instance_id: "",
    scene_profile: null,
    study_unit_title: "",
    theme_hint: "",
    session_system_prompt: "",
    status: "active",
    prepared_study_unit_ids: [],
    pending_follow_ups: [],
    session_memory: [],
    affinity_state: {
      score: 0,
      level: "neutral",
      summary: "",
      updated_at: "",
      events: [],
    },
    plan_confirmations: [],
    projected_pdf: null,
    created_at: note.created_at,
    updated_at: note.updated_at,
    turns: [turn],
  };
  const legacy = { ...fields, reply: turn.assistant_reply, session };
  const options = {
    expectedSessionId: session.id,
    evidence: {
      sessionId: session.id,
      admittedSessionRevision: 0,
      committedSessionRevision: 1,
      committedTurnId: turn.id,
      committedTurnSequence: 1,
    },
  };
  assert.equal(decodeStudyChatExchange(legacy, options).studyNoteReferences, undefined);
  const references = [{ note_id: noteId, note_revision: 1, title: "Plan" }];
  const current = {
    ...legacy,
    study_note_references: references,
    session: { ...session, turns: [{ ...turn, study_note_references: references }] },
  };
  const decoded = decodeStudyChatExchange(current, options);
  assert.deepEqual(
    decoded.session.turns[0].studyNoteReferences,
    decoded.studyNoteReferences,
  );
  assert.equal(decoded.studyNoteReferences?.[0].noteId, noteId);
  assert.throws(
    () => decodeStudyChatExchange({ ...current, session }, options),
    /chat_exchange_committed_turn_projection_mismatch/,
  );
});
