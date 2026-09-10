import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePersonaDraft } from "../hooks/use-persona-draft.ts";
import { usePersonaAssist } from "../hooks/use-persona-assist.ts";
import { EMPTY_PERSONA_DRAFT } from "../lib/persona-draft.ts";

afterEach(cleanup);
after(() => dom.window.close());
const slot = (label, content, locked = false) => ({ kind: "custom", label, content, weight: 50, locked, sortOrder: locked ? 0 : 10 });
function fixture() {
  const requests = [];
  const request = (kind, input) => new Promise((resolve, reject) => requests.push({ kind, input, resolve, reject }));
  const view = renderHook(() => {
    const draft = usePersonaDraft({ personas: [], onSelectionChange: () => assist.resetPersonaAssist(), onPromptDismiss: () => assist.dismissSystemPromptSuggestion() });
    const assist = usePersonaAssist({ draft: draft.draft, updatePersonaDraft: draft.updatePersonaDraft, currentPersonaAsyncScope: draft.currentPersonaAsyncScope, onSettingStarted() {} }, {
      assistPersonaSlot: input => request("slot", input), assistPersonaSetting: input => request("setting", input),
    });
    return { draft, assist };
  });
  act(() => view.result.current.draft.replacePersonaDraft({ ...structuredClone(EMPTY_PERSONA_DRAFT), name: "Tutor", systemPrompt: "original", slots: [slot("locked", "keep", true), slot("open", "old")] }, true));
  return { ...view, requests };
}

test("single slot rewrite changes only the target and captures rewrite strength", async () => {
  const h = fixture(); let run;
  act(() => { run = h.result.current.assist.handleAssistSlot(1); });
  assert.equal(h.requests[0].input.rewriteStrength, 0.3);
  await act(async () => { h.requests[0].resolve({ slot: slot("open", "new"), modelRecoveries: [] }); await run; });
  assert.deepEqual(h.result.current.draft.draft.slots.map(item => item.content), ["keep", "new"]);
  assert.equal(h.result.current.assist.slotAssistIndex, null);
});

test("setting assist preserves locked slots and requires explicit acceptance of prompt suggestion", async () => {
  const h = fixture(); let run;
  act(() => { run = h.result.current.assist.handleAssistSetting(); });
  await act(async () => { h.requests[0].resolve({ slots: [slot("locked", "replace", true), slot("open", "new")], systemPromptSuggestion: " suggested ", modelRecoveries: [] }); await run; });
  assert.equal(h.result.current.draft.draft.slots.find(item => item.label === "locked").content, "keep");
  assert.equal(h.result.current.draft.draft.systemPrompt, "original");
  assert.equal(h.result.current.assist.systemPromptSuggestion, "suggested");
  act(() => h.result.current.assist.applySystemPromptSuggestion());
  assert.equal(h.result.current.draft.draft.systemPrompt, "suggested");
  assert.equal(h.result.current.assist.systemPromptSuggestion, "");
});

test("old slot failure cannot clear an active whole-persona request", async () => {
  const h = fixture(); let old, current;
  act(() => { old = h.result.current.assist.handleAssistSlot(1); });
  act(() => { current = h.result.current.assist.handleAssistSetting(); });
  await act(async () => { h.requests[0].reject(new Error("old")); await old; });
  assert.equal(h.result.current.assist.assistPending, true);
  assert.equal(h.result.current.assist.assistError, "");
  await act(async () => { h.requests[1].resolve({ slots: [], systemPromptSuggestion: "new", modelRecoveries: [] }); await current; });
  assert.equal(h.result.current.assist.assistPending, false);
});

test("draft edits, persona selection and unmount discard late assist replies", async () => {
  for (const change of ["draft", "selection", "unmount"]) {
    const h = fixture(); let run;
    act(() => { run = h.result.current.assist.handleAssistSetting(); });
    act(() => {
      if (change === "draft") h.result.current.draft.updatePersonaDraft(draft => ({ ...draft, summary: "edit" }));
      if (change === "selection") h.result.current.draft.selectPersonaDraft("other");
    });
    if (change === "unmount") h.unmount();
    await act(async () => { h.requests[0].resolve({ slots: [], systemPromptSuggestion: "stale", modelRecoveries: [] }); await run; });
    assert.equal(h.result.current.assist.systemPromptSuggestion, "");
    h.unmount();
  }
});

test("current assist failure is visible with no automatic provider replay", async () => {
  const h = fixture(); let run;
  act(() => { run = h.result.current.assist.handleAssistSetting(); });
  await act(async () => { h.requests[0].reject(new Error("offline")); await run; });
  assert.match(h.result.current.assist.assistError, /offline/);
  assert.equal(h.result.current.assist.assistPending, false);
  assert.equal(h.requests.length, 1);
});
