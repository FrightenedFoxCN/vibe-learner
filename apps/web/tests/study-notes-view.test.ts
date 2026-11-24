import assert from "node:assert/strict";
import { test } from "node:test";
import {
  draftFromNote,
  isStudyNoteDraftDirty,
  rebaseStudyNoteDraft,
  StudyNotesView,
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
