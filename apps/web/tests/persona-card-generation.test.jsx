import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { useState } from "react";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePersonaCardGeneration } from "../hooks/use-persona-card-generation.ts";
import { EMPTY_PERSONA_DRAFT } from "../lib/persona-draft.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const card = { id: "card", kind: "custom", label: "Method", content: "Ask why", sourceNote: "reference" };
const reply = () => ({ items: [card], summary: "Generated", relationship: "Tutor", learnerAddress: "Student", usedModel: "mock", usedWebSearch: false, modelRecoveries: [] });
function fixture() {
  const scope = { subjectId: "persona", draftRevision: 0 }, requests = [];
  const view = renderHook(() => {
    const [draft, setDraft] = useState(() => ({ ...structuredClone(EMPTY_PERSONA_DRAFT), name: "Existing", systemPrompt: "Keep this prompt" }));
    const generation = usePersonaCardGeneration({ draft, updatePersonaDraft: setDraft, currentPersonaAsyncScope: fieldTarget => ({ ...scope, fieldTarget }) }, input => {
      const pending = deferred(); requests.push({ input, ...pending }); return pending.promise;
    });
    return { draft, ...generation };
  });
  act(() => view.result.current.setCardKeywordInput("tutor"));
  return { ...view, scope, requests };
}

test("generation produces a candidate; explicit backfill preserves prompt and avoids duplicate slots", async () => {
  const h = fixture(); let run;
  act(() => { run = h.result.current.handleGenerateCards("keywords"); });
  await act(async () => { h.requests[0].resolve(reply()); await run; });
  assert.equal(h.result.current.draft.summary, EMPTY_PERSONA_DRAFT.summary);
  act(() => h.result.current.applyGeneratedCardsToDraft());
  assert.equal(h.result.current.draft.summary, "Generated");
  assert.equal(h.result.current.draft.systemPrompt, "Keep this prompt");
  assert.deepEqual(h.result.current.draft.referenceHints, ["reference"]);
  const count = h.result.current.draft.slots.length;
  act(() => h.result.current.applyGeneratedCardsToDraft());
  assert.equal(h.result.current.draft.slots.length, count);
});

test("superseded file read cannot issue another generation request or clear the newer pending state", async () => {
  const h = fixture(), file = deferred(); let old, current;
  act(() => h.result.current.setCardLongTextFile({ text: () => file.promise }));
  act(() => { old = h.result.current.handleGenerateCards("long_text"); });
  act(() => { current = h.result.current.handleGenerateCards("keywords"); });
  await act(async () => { file.resolve("old input"); await old; });
  assert.equal(h.requests.length, 1);
  assert.equal(h.result.current.cardActionPending, "generate_keywords");
  await act(async () => { h.requests[0].resolve(reply()); await current; });
});

test("draft edits, persona selection and unmount all reject late candidates", async () => {
  for (const change of ["draft", "selection", "unmount"]) {
    const h = fixture(); let run;
    act(() => { run = h.result.current.handleGenerateCards("keywords"); });
    act(() => {
      if (change === "draft") h.scope.draftRevision++;
      if (change === "selection") { h.scope.subjectId = "other"; h.result.current.resetCardGeneration(); }
    });
    if (change === "unmount") h.unmount();
    await act(async () => { h.requests[0].resolve(reply()); await run; });
    assert.deepEqual(h.result.current.generatedCards, []);
    h.unmount();
  }
});

test("late failure does not replace the newer candidate or its feedback", async () => {
  const h = fixture(); let old, current;
  act(() => { old = h.result.current.handleGenerateCards("keywords"); });
  act(() => { current = h.result.current.handleGenerateCards("keywords"); });
  await act(async () => { h.requests[1].resolve(reply()); await current; });
  const message = h.result.current.cardMessage;
  await act(async () => { h.requests[0].reject(new Error("old")); await old; });
  assert.equal(h.result.current.cardError, "");
  assert.equal(h.result.current.cardMessage, message);
});

test("exact card count rejects invalid input before transport and preserves a valid limit", async () => {
  const h = fixture();
  act(() => h.result.current.setCardGenerateCount("25"));
  await act(async () => { await h.result.current.handleGenerateCards("keywords"); });
  assert.equal(h.requests.length, 0);
  assert.match(h.result.current.cardError, /1 到 24/);
  assert.equal(h.result.current.cardActionPending, null);
  act(() => h.result.current.setCardGenerateCount("24"));
  let run;
  act(() => { run = h.result.current.handleGenerateCards("keywords"); });
  assert.equal(h.requests[0].input.count, 24);
  await act(async () => { h.requests[0].resolve(reply()); await run; });
});

test("clearing before backfill requires the user confirmation and preserves persona identity fields", async () => {
  const h = fixture(); let run;
  act(() => { run = h.result.current.handleGenerateCards("keywords"); });
  await act(async () => { h.requests[0].resolve(reply()); await run; });
  act(() => h.result.current.setClearBeforeBackfill(true));
  const confirm = window.confirm;
  try {
    window.confirm = () => false;
    act(() => h.result.current.applyGeneratedCardsToDraft());
    assert.equal(h.result.current.draft.summary, EMPTY_PERSONA_DRAFT.summary);
    window.confirm = () => true;
    act(() => h.result.current.applyGeneratedCardsToDraft());
    assert.equal(h.result.current.draft.name, "Existing");
    assert.equal(h.result.current.draft.systemPrompt, "Keep this prompt");
    assert.equal(h.result.current.draft.slots.length, 1);
  } finally {
    window.confirm = confirm;
  }
});
